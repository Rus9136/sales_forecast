"""Loader for real menu prices set by iiko orders (приказы).

Source: GET /resto/api/v2/price — returns ProductPriceDto with price intervals
[date_from, date_to] per (department, product, size), tagged by document_id.

This is the AUTHORITATIVE price source. Unlike the derived avg_price
(revenue/qty in sku_weekly_summary), these are actual menu prices —
no contamination from modifiers, weight-based items, or order mix.

Resolves iiko_product_id → product.id via (iiko_source_domain, iiko_product_id).
departments.id is already the iiko department UUID (set in Phase 1).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx
from psycopg2.extras import execute_values
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)

DEFAULT_FROM = "2024-06-01"
DEFAULT_TO = "2500-01-01"


def _domain_host(url: str) -> str:
    return urlparse(url).hostname or url


class IikoPriceLoader:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    async def fetch_from_single_domain(
        self, base_url: str, date_from: str, date_to: str,
    ) -> list:
        host = _domain_host(base_url)
        auth = IikoAuthService(base_url)
        token = await auth.get_auth_token()
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.get(
                f"{base_url}/resto/api/v2/price",
                params={
                    "key": token,
                    "dateFrom": date_from,
                    "dateTo": date_to,
                    "type": "BASE",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            products = data.get("response", [])
            logger.info(
                "%s: fetched %d products with prices (revision %s)",
                host, len(products), data.get("revision"),
            )
            return products

    def _build_product_map(self, domain: str, iiko_product_ids: set) -> Dict[str, int]:
        """Map iiko_product_id (UUID str) → product.id (BIGINT) for one domain."""
        if not iiko_product_ids:
            return {}
        rows = self.db.execute(
            text("""
                SELECT iiko_product_id::text, id
                FROM product
                WHERE iiko_source_domain = :domain
                  AND iiko_product_id = ANY(:ids ::uuid[])
            """),
            {"domain": domain, "ids": list(iiko_product_ids)},
        ).fetchall()
        return {str(r[0]): r[1] for r in rows}

    def _known_departments(self) -> set:
        rows = self.db.execute(text("SELECT id::text FROM departments")).fetchall()
        return {str(r[0]) for r in rows}

    def _parse(self, products: list, host: str) -> list[dict]:
        """Flatten ProductPriceDto[] → one row per price interval."""
        rows = []
        for p in products:
            dept_id = p.get("departmentId")
            iiko_pid = p.get("productId")
            size_id = p.get("productSizeId")
            if not dept_id or not iiko_pid:
                continue
            for pr in p.get("prices", []):
                price = pr.get("price")
                date_from = pr.get("dateFrom")
                date_to = pr.get("dateTo")
                if price is None or not date_from or not date_to:
                    continue
                rows.append({
                    "department_id": dept_id,
                    "iiko_product_id": iiko_pid,
                    "product_size_id": size_id,
                    "price": price,
                    "date_from": date_from,
                    "date_to": date_to,
                    "price_type": "BASE",
                    "document_id": pr.get("documentId"),
                    "included": pr.get("included"),
                    "is_dish_of_day": pr.get("dishOfDay"),
                    "iiko_source_domain": host,
                })
        return rows

    def _upsert(self, rows: list[dict], product_map: Dict[str, int], known_depts: set) -> int:
        """Batch upsert price intervals, resolving product_id and filtering unknown depts."""
        if not rows:
            return 0

        values = []
        for r in rows:
            if r["department_id"] not in known_depts:
                continue
            product_id = product_map.get(r["iiko_product_id"])
            values.append((
                r["department_id"],
                r["iiko_product_id"],
                product_id,
                r["product_size_id"],
                r["price"],
                r["date_from"],
                r["date_to"],
                r["price_type"],
                r["document_id"],
                r["included"],
                r["is_dish_of_day"],
                r["iiko_source_domain"],
            ))

        if not values:
            return 0

        raw = self.db.connection().connection
        cur = raw.cursor()
        try:
            # synced_at = clock_timestamp(): реальное время выполнения, НЕ NOW()
            # (NOW() прибит к началу транзакции сессии и может быть РАНЬШЕ
            # sync_started_at — stale-маркировка зацепила бы свежие строки)
            execute_values(
                cur,
                """
                INSERT INTO sku_catalog_price
                    (department_id, iiko_product_id, product_id, product_size_id,
                     price, date_from, date_to, price_type, document_id,
                     included, is_dish_of_day, iiko_source_domain, synced_at)
                VALUES %s
                ON CONFLICT (department_id, iiko_product_id,
                    COALESCE(product_size_id, '00000000-0000-0000-0000-000000000000'::uuid),
                    date_from, price_type)
                DO UPDATE SET
                    price = EXCLUDED.price,
                    date_to = EXCLUDED.date_to,
                    product_id = EXCLUDED.product_id,
                    document_id = EXCLUDED.document_id,
                    included = EXCLUDED.included,
                    is_dish_of_day = EXCLUDED.is_dish_of_day,
                    is_stale = false,
                    synced_at = clock_timestamp()
                """,
                values,
                template="(" + ", ".join(["%s"] * 12) + ", clock_timestamp())",
                page_size=1000,
            )
            raw.commit()
        finally:
            cur.close()
        return len(values)

    def _mark_stale(self, host: str, sync_started_at, upserted: int) -> int:
        """Интервалы домена, не пришедшие в полном снапшоте — отозванные
        приказы. Помечаем is_stale (не удаляем: аудит); при повторном
        появлении upsert снимает флаг.

        Предохранитель: если снапшот подозрительно мал относительно уже
        известных интервалов домена (обрезанный ответ iiko), маркировку
        пропускаем — лучше недомаркировать, чем выключить домен целиком."""
        existing = self.db.execute(
            text("""
                SELECT COUNT(*) FROM sku_catalog_price
                WHERE iiko_source_domain = :host AND NOT is_stale
            """),
            {"host": host},
        ).scalar() or 0
        if existing > 0 and upserted < 0.5 * existing:
            logger.warning(
                "%s: snapshot has %d intervals vs %d known — skipping stale marking",
                host, upserted, existing,
            )
            return 0

        result = self.db.execute(
            text("""
                UPDATE sku_catalog_price
                SET is_stale = true
                WHERE iiko_source_domain = :host
                  AND synced_at < :started
                  AND is_stale = false
            """),
            {"host": host, "started": sync_started_at},
        )
        self.db.commit()
        return result.rowcount

    async def sync(self, date_from: str = DEFAULT_FROM, date_to: str = DEFAULT_TO) -> dict:
        total_rows = 0
        total_resolved = 0
        per_domain = []
        errors = []
        known_depts = self._known_departments()
        # stale-маркировка корректна только при полном снапшоте всей истории
        full_snapshot = (date_from == DEFAULT_FROM and date_to == DEFAULT_TO)

        for base_url in self.domains:
            host = _domain_host(base_url)
            try:
                # отметка по часам БД — сравнение с synced_at без расхождений часов
                sync_started_at = self.db.execute(text("SELECT clock_timestamp()")).scalar()
                products = await self.fetch_from_single_domain(base_url, date_from, date_to)
                parsed = self._parse(products, host)

                iiko_ids = {r["iiko_product_id"] for r in parsed}
                product_map = self._build_product_map(host, iiko_ids)
                resolved = sum(1 for r in parsed if r["iiko_product_id"] in product_map)

                upserted = self._upsert(parsed, product_map, known_depts)

                stale_marked = 0
                if full_snapshot and parsed:
                    stale_marked = self._mark_stale(host, sync_started_at, upserted)
                    if stale_marked:
                        logger.info("%s: %d price intervals marked stale (rescinded orders)",
                                    host, stale_marked)

                total_rows += upserted
                total_resolved += resolved
                per_domain.append({
                    "domain": host,
                    "products": len(products),
                    "price_intervals": len(parsed),
                    "upserted": upserted,
                    "stale_marked": stale_marked,
                    "product_resolved": resolved,
                    "resolve_pct": round(100.0 * resolved / len(parsed), 1) if parsed else 0,
                })
            except Exception as e:
                msg = f"Price sync failed for {host}: {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)

        return {
            "status": "success" if not errors else ("partial" if per_domain else "error"),
            "total_intervals": total_rows,
            "total_resolved": total_resolved,
            "per_domain": per_domain,
            "errors": errors,
        }

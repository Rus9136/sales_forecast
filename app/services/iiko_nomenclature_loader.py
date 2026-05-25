"""Loader for iiko nomenclature catalog: categories + groups + products.

Sync order is strict:
  1. categories  (no FKs, simple)
  2. groups      (multi-pass: parent group may live in the same batch)
  3. products    (FK on group_id + category_id; resolve via lookup map)

For each domain in `settings.IIKO_DOMAINS` we tag every record with the bare
hostname (`iiko_source_domain`). Natural key = (domain, iiko_<entity>_id) —
same UUID may legitimately exist under different domains.

The loader uses **batch upsert** via `INSERT … ON CONFLICT … DO UPDATE` over
`execute_values` to handle the ~18k Sandy product set without the row-by-row
SQLAlchemy overhead that `iiko_sales_loader` still uses.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from psycopg2.extras import Json, execute_values
from sqlalchemy.orm import Session

from ..config import settings
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)


def _domain_host(url: str) -> str:
    """Bare hostname for stable storage (mirrors iiko_department_loader._domain_host)."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url


def _to_decimal_str(value: Any) -> Optional[str]:
    """iiko returns numbers as floats. Render as string so psycopg2 stores them
    in NUMERIC columns without float-precision drift. None passes through."""
    if value is None:
        return None
    try:
        # Drop trailing zeros while keeping integers/decimals readable.
        return format(float(value), ".6f").rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return None


class IikoNomenclatureLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def _fetch_json(self, base_url: str, path: str, token: str) -> Any:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(
                f"{base_url}{path}",
                params={"key": token, "includeDeleted": "true"},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_from_single_domain(
        self, base_url: str
    ) -> Tuple[List[dict], List[dict], List[dict]]:
        """Return (categories, groups, products) tagged with iiko_source_domain."""
        host = _domain_host(base_url)
        auth = IikoAuthService(base_url)
        token = await auth._refresh_token()

        categories = await self._fetch_json(
            base_url, "/resto/api/v2/entities/products/category/list", token
        )
        groups = await self._fetch_json(
            base_url, "/resto/api/v2/entities/products/group/list", token
        )
        products = await self._fetch_json(
            base_url, "/resto/api/v2/entities/products/list", token
        )

        for c in categories:
            c["iiko_source_domain"] = host
        for g in groups:
            g["iiko_source_domain"] = host
        for p in products:
            p["iiko_source_domain"] = host

        logger.info(
            f"{host}: fetched {len(categories)} categories, "
            f"{len(groups)} groups, {len(products)} products"
        )
        return categories, groups, products

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def _upsert_categories(self, categories: List[dict]) -> Dict[Tuple[str, str], int]:
        """Returns {(domain, iiko_category_id): db_id} for downstream FK resolution.

        Note: psycopg2's execute_values RETURNING only exposes the *last batch*
        via cur.fetchall(). With fetch=True it materialises all rows across
        pages — critical so the FK map covers the full input, not just the last
        page_size=100 rows.
        """
        if not categories:
            return {}
        now = datetime.utcnow()
        rows = [
            (
                c["iiko_source_domain"],
                c["id"],
                c.get("name") or "",
                bool(c.get("deleted")),
                now,
            )
            for c in categories
        ]
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            returned = execute_values(
                cur,
                """
                INSERT INTO nomenclature_category
                    (iiko_source_domain, iiko_category_id, name, is_deleted, synced_at)
                VALUES %s
                ON CONFLICT (iiko_source_domain, iiko_category_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    is_deleted = EXCLUDED.is_deleted,
                    synced_at = EXCLUDED.synced_at
                RETURNING id, iiko_source_domain, iiko_category_id
                """,
                rows,
                template="(%s, %s::uuid, %s, %s, %s)",
                fetch=True,
            )
        return {(domain, str(uuid)): db_id for (db_id, domain, uuid) in returned}

    def _upsert_groups(
        self, groups: List[dict]
    ) -> Dict[Tuple[str, str], int]:
        """Upsert groups in a single batch (parent_id is left NULL initially),
        then run a self-resolving UPDATE for parent_id. This avoids the multi-pass
        loop used in `iiko_department_loader` — simpler and faster for ~450 rows.
        """
        if not groups:
            return {}
        now = datetime.utcnow()
        rows = [
            (
                g["iiko_source_domain"],
                g["id"],
                g.get("name") or "",
                g.get("num"),
                g.get("code"),
                g.get("position"),
                bool(g.get("deleted")),
                Json(g),
                now,
            )
            for g in groups
        ]
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            returned = execute_values(
                cur,
                """
                INSERT INTO nomenclature_group
                    (iiko_source_domain, iiko_group_id, name, num, code, position,
                     is_deleted, iiko_payload, synced_at)
                VALUES %s
                ON CONFLICT (iiko_source_domain, iiko_group_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    num = EXCLUDED.num,
                    code = EXCLUDED.code,
                    position = EXCLUDED.position,
                    is_deleted = EXCLUDED.is_deleted,
                    iiko_payload = EXCLUDED.iiko_payload,
                    synced_at = EXCLUDED.synced_at
                RETURNING id, iiko_source_domain, iiko_group_id
                """,
                rows,
                template="(%s, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s)",
                fetch=True,
            )
            id_map: Dict[Tuple[str, str], int] = {
                (domain, str(uuid)): db_id for (db_id, domain, uuid) in returned
            }

            # Resolve parent FK. iiko gives parent as UUID + same domain as child.
            parent_updates: List[Tuple[int, int]] = []
            for g in groups:
                if g.get("parent"):
                    child_db = id_map.get(
                        (g["iiko_source_domain"], g["id"])
                    )
                    parent_db = id_map.get(
                        (g["iiko_source_domain"], g["parent"])
                    )
                    if child_db and parent_db:
                        parent_updates.append((parent_db, child_db))
            if parent_updates:
                execute_values(
                    cur,
                    """
                    UPDATE nomenclature_group AS g
                    SET parent_id = upd.parent_id
                    FROM (VALUES %s) AS upd(parent_id, id)
                    WHERE g.id = upd.id
                    """,
                    parent_updates,
                )
                logger.info(
                    f"Resolved parent_id for {len(parent_updates)} groups"
                )
        return id_map

    def _upsert_products(
        self,
        products: List[dict],
        group_map: Dict[Tuple[str, str], int],
        category_map: Dict[Tuple[str, str], int],
    ) -> int:
        if not products:
            return 0
        now = datetime.utcnow()
        rows = []
        for p in products:
            domain = p["iiko_source_domain"]
            group_db_id = (
                group_map.get((domain, p["parent"])) if p.get("parent") else None
            )
            category_db_id = (
                category_map.get((domain, p["category"])) if p.get("category") else None
            )
            rows.append(
                (
                    domain,
                    p["id"],
                    p.get("num"),
                    p.get("code"),
                    p.get("name") or "",
                    p.get("description"),
                    p.get("type") or "DISH",
                    group_db_id,
                    category_db_id,
                    p.get("mainUnit"),
                    _to_decimal_str(p.get("defaultSalePrice")),
                    _to_decimal_str(p.get("estimatedPurchasePrice")),
                    _to_decimal_str(p.get("unitWeight")),
                    _to_decimal_str(p.get("coldLossPercent")),
                    _to_decimal_str(p.get("hotLossPercent")),
                    p.get("taxCategory"),
                    p.get("accountingCategory"),
                    bool(p.get("deleted")),
                    bool(p.get("defaultIncludedInMenu", True)),
                    Json(p),
                    now,
                )
            )
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO product (
                    iiko_source_domain, iiko_product_id, num, code, name, description,
                    type, group_id, category_id, measure_unit_id,
                    default_sale_price, estimated_purchase_price, weight_kg,
                    cold_loss_percent, hot_loss_percent,
                    tax_category_id, accounting_category_id,
                    is_deleted, is_included_in_menu, iiko_payload, synced_at
                ) VALUES %s
                ON CONFLICT (iiko_source_domain, iiko_product_id) DO UPDATE SET
                    num = EXCLUDED.num,
                    code = EXCLUDED.code,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    type = EXCLUDED.type,
                    group_id = EXCLUDED.group_id,
                    category_id = EXCLUDED.category_id,
                    measure_unit_id = EXCLUDED.measure_unit_id,
                    default_sale_price = EXCLUDED.default_sale_price,
                    estimated_purchase_price = EXCLUDED.estimated_purchase_price,
                    weight_kg = EXCLUDED.weight_kg,
                    cold_loss_percent = EXCLUDED.cold_loss_percent,
                    hot_loss_percent = EXCLUDED.hot_loss_percent,
                    tax_category_id = EXCLUDED.tax_category_id,
                    accounting_category_id = EXCLUDED.accounting_category_id,
                    is_deleted = EXCLUDED.is_deleted,
                    is_included_in_menu = EXCLUDED.is_included_in_menu,
                    iiko_payload = EXCLUDED.iiko_payload,
                    synced_at = EXCLUDED.synced_at
                """,
                rows,
                template=(
                    "(%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s, %s, %s,"
                    " %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s)"
                ),
            )
        return len(rows)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def sync(self) -> dict:
        total_categories = 0
        total_groups = 0
        total_products = 0
        per_domain: List[dict] = []
        errors: List[str] = []

        for domain in self.domains:
            try:
                categories, groups, products = await self.fetch_from_single_domain(domain)
            except Exception as e:
                msg = f"Fetch failed for {domain}: {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)
                continue

            try:
                category_map = self._upsert_categories(categories)
                group_map = self._upsert_groups(groups)
                product_count = self._upsert_products(products, group_map, category_map)
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                msg = f"Upsert failed for {domain}: {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)
                continue

            host = _domain_host(domain)
            per_domain.append({
                "domain": host,
                "categories": len(categories),
                "groups": len(groups),
                "products": product_count,
            })
            total_categories += len(categories)
            total_groups += len(groups)
            total_products += product_count

        status = "success" if not errors else ("partial" if per_domain else "error")
        result = {
            "status": status,
            "total_categories": total_categories,
            "total_groups": total_groups,
            "total_products": total_products,
            "per_domain": per_domain,
            "errors": errors,
        }
        logger.info(
            f"Nomenclature sync complete: {total_categories} categories, "
            f"{total_groups} groups, {total_products} products across "
            f"{len(per_domain)} domains"
        )
        return result

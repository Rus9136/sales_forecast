"""Снимки складских остатков iiko.

``GET /resto/api/v2/reports/balance/stores?timestamp=`` отдаёт срез остатков на
момент времени — истории у отчёта нет. Поэтому снимок снимается раз в день на
конец учётного дня и складывается в ``sku_stock_balance``: обратной перемотки
не существует, не сняли — потеряли.

Разведано на боевом контуре 2026-08-06:
  * ответ по всей сети ≈ 8 600 строк / 1 МБ, отдаётся за 0,5–1,2 с;
  * нулевые позиции в ответ НЕ попадают — отсутствие строки за загруженный день
    означает нулевой остаток;
  * ≈15% строк отрицательные: это документы, проведённые задним числом, а не
    физическое отсутствие товара. Поэтому «нет товара» определяется не по знаку
    остатка, а связкой «остаток ≤ 0 И продаж в этот день не было»;
  * фильтры ``store`` и ``product`` работают на сервере — в отличие от
    ``writeoff``/``incomingInvoice``, где ``storeId`` молча игнорируется.

Снимок берётся на 23:59 учётного дня: продажи iiko списывает при закрытии дня,
приход появляется утром следующего. На проверке 29.07 значения в 23:30 и в
06:00 следующего дня совпали.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from psycopg2.extras import execute_values
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 180.0
BALANCE_PATH = "/resto/api/v2/reports/balance/stores"


def _domain_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url


def _days(from_date: date, to_date: date) -> Iterable[date]:
    cur = from_date
    while cur <= to_date:
        yield cur
        cur += timedelta(days=1)


class IikoStockLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    # -- справочники домена ----------------------------------------------

    def _store_map(self, domain: str) -> Dict[str, Optional[str]]:
        rows = self.db.execute(
            text("""SELECT id::text, department_id::text FROM store
                    WHERE iiko_source_domain = :d"""),
            {"d": domain},
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def _product_map(self, domain: str) -> Dict[str, int]:
        rows = self.db.execute(
            text("""SELECT iiko_product_id::text, id FROM product
                    WHERE iiko_source_domain = :d AND iiko_product_id IS NOT NULL"""),
            {"d": domain},
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    # -- загрузка ---------------------------------------------------------

    async def sync_range(self, from_date: date, to_date: date) -> Dict[str, int]:
        """Снять остатки за каждый день диапазона по всем доменам."""
        totals = {"days": 0, "rows": 0, "skipped_unknown": 0}

        for base_url in self.domains:
            host = _domain_host(base_url)
            stores = self._store_map(host)
            products = self._product_map(host)
            if not stores or not products:
                logger.warning("%s: нет складов или номенклатуры, остатки пропущены", host)
                continue

            try:
                token = await IikoAuthService(base_url)._refresh_token()
            except Exception as e:
                logger.error("%s: авторизация для остатков не удалась: %s", host, e)
                continue

            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                for day in _days(from_date, to_date):
                    try:
                        rows, unknown = await self._fetch_day(
                            client, base_url, token, day, stores, products)
                    except Exception as e:
                        logger.error("%s %s: остатки не сняты: %s", host, day, e)
                        continue
                    stored = self._store_rows(day, rows, set(stores))
                    # Коммит на каждый день: бэкфилл за полгода — это сотни
                    # тысяч строк, и одна транзакция на всё означает, что сбой
                    # на последнем дне обнуляет часы работы.
                    self.db.commit()
                    totals["days"] += 1
                    totals["rows"] += stored
                    totals["skipped_unknown"] += unknown
                    if totals["days"] % 10 == 0:
                        logger.info("Остатки: снято дней %s, строк %s",
                                    totals["days"], totals["rows"])

        logger.info("Остатки: дней %(days)s, строк %(rows)s, нераспознанных %(skipped_unknown)s",
                    totals)
        return totals

    async def _fetch_day(self, client: httpx.AsyncClient, base_url: str, token: str,
                         day: date, stores: Dict[str, Optional[str]],
                         products: Dict[str, int]) -> Tuple[List[tuple], int]:
        resp = await client.get(
            f"{base_url}{BALANCE_PATH}",
            params={"key": token, "timestamp": f"{day}T23:59:00"},
        )
        resp.raise_for_status()

        out: List[tuple] = []
        unknown = 0
        for row in resp.json():
            store_id = row.get("store")
            product_key = row.get("product")
            product_id = products.get(product_key)
            if store_id not in stores or product_id is None:
                unknown += 1
                continue
            out.append((day, store_id, product_id, stores[store_id],
                        row.get("amount"), row.get("sum")))
        return out, unknown

    def _store_rows(self, day: date, rows: List[tuple], domain_stores: set) -> int:
        """Перезалить день целиком по всем складам домена.

        Чистить только те склады, что пришли в ответе, нельзя: если позиция
        обнулилась после правки документов, в ответе её больше нет — и старая
        строка осталась бы жить как фантомный остаток. Поэтому день сносится
        по всему домену и пишется заново.
        """
        if not domain_stores:
            return 0
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sku_stock_balance WHERE balance_date = %s AND store_id IN %s",
                (day, tuple(domain_stores)),
            )
            if not rows:
                return 0
            execute_values(
                cur,
                """INSERT INTO sku_stock_balance
                       (balance_date, store_id, product_id, department_id, amount, cost_sum)
                   VALUES %s
                   ON CONFLICT (balance_date, store_id, product_id) DO UPDATE
                   SET amount = EXCLUDED.amount,
                       cost_sum = EXCLUDED.cost_sum,
                       department_id = EXCLUDED.department_id,
                       synced_at = now()""",
                rows,
                page_size=2000,
            )
        return len(rows)


async def run_daily_stock_sync(lookback_days: int = 3) -> Dict[str, int]:
    """Ежедневная задача: вчерашний день плюс небольшое окно назад.

    Документы в iiko правят задним числом, поэтому свежие дни пересниматься
    должны — иначе остаток «на вчера» навсегда останется тем, каким его видели
    в момент снимка.
    """
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        today = date.today()
        return await IikoStockLoaderService(db).sync_range(
            today - timedelta(days=lookback_days), today - timedelta(days=1))
    finally:
        db.close()

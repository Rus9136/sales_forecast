"""APScheduler-обёртка для ежедневной загрузки складских документов.

Окно перезагружается скользящее (`INVENTORY_SYNC_LOOKBACK_DAYS`), а не только
вчерашний день: акты списания и накладные в iiko правят и удаляют задним
числом, и повторный проход по неделе заодно закрывает пропуски после сбоя.
Отдельная gap-джоба поэтому не нужна.

Область загрузки задаётся `INVENTORY_SYNC_DEPARTMENTS`. Пустое значение
означает всю сеть — это десятки мегабайт XML на каждый недельный срез, так
что для пилота там перечислены конкретные точки.
"""

import asyncio
import concurrent.futures
import logging
from datetime import date, timedelta
from typing import List, Optional

from ..config import settings
from ..db import get_db
from .iiko_inventory_loader import IikoInventoryLoaderService

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Выполнить корутину из синхронного колбэка APScheduler."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                lambda: asyncio.new_event_loop().run_until_complete(coro)
            ).result(timeout=1800)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _target_departments() -> Optional[List[str]]:
    raw = (settings.INVENTORY_SYNC_DEPARTMENTS or "").strip()
    if not raw:
        return None
    return [d.strip() for d in raw.split(",") if d.strip()]


def run_inventory_sync():
    """Ежедневно: справочники + списания и накладные за скользящее окно."""
    logger.info("Scheduler triggered: inventory documents sync")
    try:
        db = next(get_db())
        try:
            svc = IikoInventoryLoaderService(db)
            depts = _target_departments()
            to_date = date.today()
            from_date = to_date - timedelta(days=max(1, settings.INVENTORY_SYNC_LOOKBACK_DAYS) - 1)

            refs = _run_async(svc.sync_references())
            writeoffs = _run_async(svc.sync_writeoffs(from_date, to_date, depts))
            invoices = _run_async(svc.sync_incoming_invoices(from_date, to_date, depts))

            logger.info(
                "Inventory sync done %s..%s: списаний %s док./%s поз., накладных %s док./%s поз.",
                from_date, to_date,
                writeoffs["documents"], writeoffs["items"],
                invoices["documents"], invoices["items"],
            )
            return {"references": refs, "writeoffs": writeoffs, "invoices": invoices}
        finally:
            db.close()
    except Exception as e:
        logger.error("Inventory sync failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}

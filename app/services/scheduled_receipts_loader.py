"""APScheduler wrappers for receipts sync + gap check."""

import asyncio
import concurrent.futures
import logging
from datetime import date, timedelta

from ..db import get_db
from .iiko_receipts_loader import IikoReceiptsLoaderService

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync APScheduler callback."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                lambda: asyncio.new_event_loop().run_until_complete(coro)
            ).result(timeout=600)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def run_receipts_sync():
    """Daily sync: fetch yesterday's receipts from all iiko domains."""
    logger.info("Scheduler triggered: receipts sync")
    try:
        db = next(get_db())
        try:
            svc = IikoReceiptsLoaderService(db)
            yesterday = date.today() - timedelta(days=1)
            result = _run_async(svc.sync(yesterday, yesterday))
            logger.info(f"Receipts sync done: {result.get('total_receipts')} receipts, {result.get('total_items')} items")
            from .sku_daily_aggregation_service import SkuDailyAggregationService
            SkuDailyAggregationService(db).aggregate_date_range(yesterday, yesterday)
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Receipts sync failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def run_receipts_gap_check():
    """Check last 7 days for missing receipt data and resync gaps."""
    logger.info("Scheduler triggered: receipts gap check")
    try:
        db = next(get_db())
        try:
            from sqlalchemy import text
            days_back = 7
            resynced = []
            for i in range(days_back):
                check_date = date.today() - timedelta(days=i + 1)
                count = db.execute(
                    text("SELECT COUNT(*) FROM receipt WHERE open_date = :d"),
                    {"d": check_date},
                ).scalar() or 0
                if count == 0:
                    logger.warning(f"No receipts for {check_date}, resyncing")
                    svc = IikoReceiptsLoaderService(db)
                    result = _run_async(svc.sync(check_date, check_date))
                    resynced.append({"date": str(check_date), "receipts": result.get("total_receipts", 0)})
                    from .sku_daily_aggregation_service import SkuDailyAggregationService
                    SkuDailyAggregationService(db).aggregate_date_range(check_date, check_date)
            logger.info(f"Receipts gap check done: resynced {len(resynced)} dates")
            return {"status": "success", "resynced": resynced}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Receipts gap check failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

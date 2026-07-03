"""APScheduler wrappers for pricing analytics (A2 views) and menu clustering (B1).

Elasticity (B2) estimation and the price optimizer (B3) have their own wrappers
in scheduled_pricing_engine.py.
"""

import logging
from datetime import date, timedelta

from ..db import get_db
from .pricing_analytics_service import PricingAnalyticsService
from .menu_clustering_service import MenuClusteringService

logger = logging.getLogger(__name__)


def run_pricing_analytics_aggregation():
    """Daily aggregation: price history (last 8 days) + weekly summaries (current + prev week).

    Окно price history = 8 дней ≥ окна receipts gap check (7 дней): дозалитые
    задним числом чеки раньше не попадали в историю цен (окно было 3 дня).
    """
    logger.info("Scheduler triggered: pricing analytics aggregation")
    try:
        db = next(get_db())
        try:
            svc = PricingAnalyticsService(db)
            today = date.today()

            price_from = today - timedelta(days=8)
            r1 = svc.aggregate_price_history(price_from, today)

            from_monday = today - timedelta(days=today.weekday() + 7)
            r2 = svc.aggregate_sku_weekly(from_monday, today)
            r3 = svc.aggregate_department_weekly(from_monday, today)

            logger.info(
                "Pricing analytics done: price_history=%s, sku_weekly=%s, dept_weekly=%s",
                r1, r2, r3,
            )
            result = {"status": "ok", "price_history": r1, "sku_weekly": r2, "department_weekly": r3}
            from .pricing_jobs import log_job_run
            log_job_run("pricing_analytics", result,
                        records=r2.get("rows_upserted", 0) + r3.get("rows_upserted", 0))
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error("Pricing analytics aggregation failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_analytics", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}


def run_menu_clustering():
    """Weekly menu role clustering (Sunday 03:15)."""
    logger.info("Scheduler triggered: menu role clustering")
    try:
        db = next(get_db())
        try:
            svc = MenuClusteringService(db)
            result = svc.run_clustering()
            logger.info("Menu clustering done: %s", result)
            from .pricing_jobs import log_job_run
            log_job_run("menu_clustering", result, records=result.get("skus_classified", 0))
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error("Menu clustering failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("menu_clustering", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}

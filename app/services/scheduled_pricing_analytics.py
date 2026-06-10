"""APScheduler wrappers for pricing analytics (A2 views), menu clustering (B1)
and price elasticity estimation (B2).

These run inside BackgroundScheduler's own thread pool — separate from the
uvicorn event loop — so the CPU-heavy elasticity regression does NOT block the
single web worker (unlike calling POST /elasticity/estimate at runtime).
"""

import logging
from datetime import date, timedelta

from ..db import get_db
from .pricing_analytics_service import PricingAnalyticsService
from .menu_clustering_service import MenuClusteringService
from .elasticity_estimation_service import ElasticityEstimationService

logger = logging.getLogger(__name__)

# Full sales history (~24 months) so the grade counter sees every price event.
ELASTICITY_LOOKBACK_DAYS = 730


def run_pricing_analytics_aggregation():
    """Daily aggregation: price history (last 3 days) + weekly summaries (current + prev week)."""
    logger.info("Scheduler triggered: pricing analytics aggregation")
    try:
        db = next(get_db())
        try:
            svc = PricingAnalyticsService(db)
            today = date.today()

            price_from = today - timedelta(days=3)
            r1 = svc.aggregate_price_history(price_from, today)

            from_monday = today - timedelta(days=today.weekday() + 7)
            r2 = svc.aggregate_sku_weekly(from_monday, today)
            r3 = svc.aggregate_department_weekly(from_monday, today)

            logger.info(
                "Pricing analytics done: price_history=%s, sku_weekly=%s, dept_weekly=%s",
                r1, r2, r3,
            )
            return {"price_history": r1, "sku_weekly": r2, "department_weekly": r3}
        finally:
            db.close()
    except Exception as e:
        logger.error("Pricing analytics aggregation failed: %s", e, exc_info=True)
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
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error("Menu clustering failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}


def run_elasticity_estimation():
    """Weekly price elasticity estimation (B2), Sunday 05:00.

    Runs after menu clustering (03:15) and pricing analytics (04:30) so it reads
    fresh sku_menu_role + sku_weekly_summary. Heavy OLS regressions execute in
    the scheduler's background thread, never on the web event loop.
    """
    logger.info("Scheduler triggered: elasticity estimation")
    try:
        db = next(get_db())
        try:
            svc = ElasticityEstimationService(db)
            result = svc.estimate_all(lookback_days=ELASTICITY_LOOKBACK_DAYS)
            logger.info("Elasticity estimation done: %s", result)
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error("Elasticity estimation failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}

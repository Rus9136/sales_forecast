"""Scheduler wrappers for pricing engine (B2 elasticity + B3 optimizer)."""

from __future__ import annotations

import logging

from sqlalchemy import text

from ..db import SessionLocal

logger = logging.getLogger(__name__)


def run_catalog_price_sync():
    """Daily menu price sync from iiko orders. Schedule: daily 03:20.

    Pulls real catalog prices (GET /resto/api/v2/price) — the authoritative
    price source for elasticity AND the optimizer's current_price. Daily (not
    weekly) so that approved→applied detection sees a fresh catalog. On
    Sundays still runs BEFORE elasticity update (03:30).

    After a successful sync, immediately detects applied recommendations —
    approved recs whose price has appeared in the catalog (feedback loop §7.4).
    """
    import asyncio
    logger.info("Starting daily catalog price sync")
    db = SessionLocal()
    try:
        from .iiko_price_loader import IikoPriceLoader
        loader = IikoPriceLoader(db)
        result = asyncio.run(loader.sync())
        logger.info("Catalog price sync complete: %s intervals", result.get("total_intervals"))

        try:
            from .pricing_feedback_service import PricingFeedbackService
            detection = PricingFeedbackService(db).detect_applied()
            result["applied_detection"] = detection
        except Exception as e:
            logger.error("Applied-recommendation detection failed: %s", e, exc_info=True)
            result["applied_detection"] = {"status": "error", "message": str(e)}

        from .pricing_jobs import log_job_run
        log_job_run("pricing_catalog_price", result, records=result.get("total_intervals", 0))
        return result
    except Exception as e:
        logger.error("Catalog price sync failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_catalog_price", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def run_outcome_evaluation():
    """Daily evaluation of applied recommendations (14d window). Schedule: 05:30."""
    logger.info("Starting recommendation outcome evaluation")
    db = SessionLocal()
    try:
        from .pricing_feedback_service import PricingFeedbackService
        result = PricingFeedbackService(db).evaluate_outcomes()
        logger.info(
            "Outcome evaluation complete: %s evaluated of %s pending",
            result.get("evaluated"), result.get("pending"),
        )
        from .pricing_jobs import log_job_run
        log_job_run("pricing_outcomes", result, records=result.get("evaluated", 0))
        return result
    except Exception as e:
        logger.error("Outcome evaluation failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_outcomes", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def run_elasticity_update():
    """Weekly elasticity re-estimation. Schedule: Sunday 03:30.

    Runs in BackgroundScheduler's thread pool (not the web event loop), so the
    heavy OLS regressions never block the single uvicorn worker. lookback=730d
    covers the full ~24-month sales history so the grade counter sees every
    price event.
    """
    logger.info("Starting weekly elasticity estimation")
    db = SessionLocal()
    try:
        from .elasticity_estimation_service import ElasticityEstimationService
        svc = ElasticityEstimationService(db)
        result = svc.estimate_all(lookback_days=730)
        logger.info("Elasticity estimation complete: %s", result.get("status"))
        from .pricing_jobs import log_job_run
        log_job_run("pricing_elasticity", result, records=result.get("upserted", 0))
        return result
    except Exception as e:
        logger.error("Elasticity estimation failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_elasticity", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def run_pricing_weekly_report():
    """Weekly pricing LLM report (network). Schedule: Monday 08:00."""
    import asyncio
    from datetime import date
    logger.info("Starting weekly pricing report")
    db = SessionLocal()
    try:
        from .pricing_report_service import PricingReportService, last_full_week
        start, end = last_full_week(date.today())
        report = asyncio.run(PricingReportService(db).generate("weekly", start, end))
        result = {"status": report.status, "report_id": report.id, "period": f"{start}..{end}"}
        logger.info("Weekly pricing report done: id=%s status=%s", report.id, report.status)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_report_weekly", result, records=1)
        return result
    except Exception as e:
        logger.error("Weekly pricing report failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_report_weekly", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def run_pricing_monthly_report():
    """Monthly pricing LLM report (network). Schedule: 1st of month 08:00."""
    import asyncio
    from datetime import date
    logger.info("Starting monthly pricing report")
    db = SessionLocal()
    try:
        from .pricing_report_service import PricingReportService, last_full_month
        start, end = last_full_month(date.today())
        report = asyncio.run(PricingReportService(db).generate("monthly", start, end))
        result = {"status": report.status, "report_id": report.id, "period": f"{start}..{end}"}
        logger.info("Monthly pricing report done: id=%s status=%s", report.id, report.status)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_report_monthly", result, records=1)
        return result
    except Exception as e:
        logger.error("Monthly pricing report failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_report_monthly", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def run_recommendation_explanations():
    """C4': LLM-обоснования топ-N новых рекомендаций. Schedule: daily 05:45.

    Идёт после генерации рекомендаций (05:00): дневной батч оптимизатора
    замещает открытые рекомендации, поэтому обоснования генерируются заново.
    Объясняем только топ-N на подразделение по ΔGP — остальные по запросу из UI.
    """
    import asyncio

    from ..config import settings

    logger.info("Starting recommendation LLM explanations")
    db = SessionLocal()
    try:
        from .pricing_explanation_service import PricingExplanationService
        svc = PricingExplanationService(db)
        result = asyncio.run(
            svc.explain_batch(top_n_per_department=settings.PRICING_EXPLAIN_TOP_N)
        )
        logger.info(
            "Recommendation explanations complete: %s of %s explained",
            result.get("explained"), result.get("total"),
        )
        from .pricing_jobs import log_job_run
        log_job_run("pricing_explanations", result, records=result.get("explained", 0))
        return result
    except Exception as e:
        logger.error("Recommendation explanations failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_explanations", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def run_price_optimization():
    """Daily price recommendation generation. Schedule: daily 05:00."""
    logger.info("Starting daily price optimization")
    db = SessionLocal()
    try:
        active_depts = db.execute(
            text("""
                SELECT DISTINCT department_id::text
                FROM sku_daily_sales
                WHERE sale_date >= CURRENT_DATE - 30
            """)
        ).fetchall()

        from .price_optimizer_service import PriceOptimizerService
        svc = PriceOptimizerService(db)

        total_recs = 0
        dept_results = {}
        for (dept_id,) in active_depts:
            try:
                result = svc.generate_recommendations(dept_id)
                dept_results[dept_id] = result.get("recommendations_created", 0)
                total_recs += result.get("recommendations_created", 0)
            except Exception as e:
                logger.error("Optimization failed for dept %s: %s", dept_id, e)
                dept_results[dept_id] = f"error: {e}"

        logger.info(
            "Price optimization complete: %d recommendations across %d departments",
            total_recs, len(active_depts),
        )
        result = {
            "status": "ok",
            "total_recommendations": total_recs,
            "departments_processed": len(active_depts),
            "per_department": dept_results,
        }
        from .pricing_jobs import log_job_run
        log_job_run("pricing_optimization", result, records=total_recs)
        return result
    except Exception as e:
        logger.error("Price optimization failed: %s", e, exc_info=True)
        from .pricing_jobs import log_job_run
        log_job_run("pricing_optimization", {"status": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

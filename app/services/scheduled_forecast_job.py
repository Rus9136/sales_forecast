"""Ежедневный batch-прогноз по всей сети (ML_AUDIT_REPORT.md P0-6, Фаза 1.3/1.4).

До этой джобы таблица `forecasts` наполнялась только когда кто-то вручную
дёргал /api/forecast/batch — мониторинг качества видел 4 точки из 41, а
`sku_forecasts` была пуста (0 строк) и SKU-качество не измерялось вообще.

Расписание: ежедневно 06:00 (после ночных синков продаж 02:00-02:30).
Пишет:
- forecasts: t+1 и t+7 для всех активных подразделений (горизонт хранится
  в forecasts.horizon_days — миграция 030), UPSERT → идемпотентно;
- sku_forecasts: t+1, топ-50 SKU по прогнозному обороту на подразделение.

«Активное подразделение» = были продажи за последние 14 дней.
"""

import logging
from datetime import date, timedelta
from typing import List

from sqlalchemy import text

from ..agents.sales_forecaster_agent import get_forecaster_agent
from ..agents.sku_forecaster_agent import get_sku_forecaster_agent
from ..db import get_db

logger = logging.getLogger(__name__)

ACTIVE_WINDOW_DAYS = 14
DEPT_HORIZONS = (1, 7)
SKU_TOP_N = 50


def _get_active_department_ids(db, today: date) -> List[str]:
    rows = db.execute(text("""
        SELECT DISTINCT department_id::text
        FROM sales_summary
        WHERE date >= :cutoff
        ORDER BY 1
    """), {"cutoff": today - timedelta(days=ACTIVE_WINDOW_DAYS)}).fetchall()
    return [r[0] for r in rows]


def run_daily_forecast_sweep() -> dict:
    """APScheduler entry point (06:00) — прогноз по всем активным точкам."""
    logger.info("Scheduler triggered: daily forecast sweep")
    db = next(get_db())
    try:
        today = date.today()
        dept_ids = _get_active_department_ids(db, today)

        summary = {
            "date": today.isoformat(),
            "active_departments": len(dept_ids),
            "dept_forecasts_written": 0,
            "dept_skipped": 0,
            "sku_departments": 0,
            "sku_rows_written": 0,
            "sku_errors": 0,
        }

        # --- Department-level: t+1 и t+7 ---
        agent = get_forecaster_agent()
        if agent.model is None:
            logger.error("Forecast sweep: department model not loaded — skipping dept part")
        else:
            for dept_id in dept_ids:
                for horizon in DEPT_HORIZONS:
                    target = today + timedelta(days=horizon)
                    # forecast() ловит свои исключения и возвращает None;
                    # save_to_db=True → UPSERT в forecasts с horizon_days
                    pred = agent.forecast(dept_id, target, db, save_to_db=True)
                    if pred is None:
                        summary["dept_skipped"] += 1
                    else:
                        summary["dept_forecasts_written"] += 1

        # --- SKU-level: t+1, топ-N по прогнозному обороту (Фаза 1.4) ---
        sku_agent = get_sku_forecaster_agent()
        if sku_agent.model is None:
            logger.warning("Forecast sweep: SKU model not loaded — skipping SKU part")
        else:
            sku_target = today + timedelta(days=1)
            for dept_id in dept_ids:
                try:
                    items = sku_agent.forecast_department_skus(
                        dept_id, sku_target, db,
                        top_n=SKU_TOP_N, save_to_db=True, order_by="revenue",
                    )
                    if items:
                        summary["sku_departments"] += 1
                        summary["sku_rows_written"] += len(items)
                except Exception as e:
                    summary["sku_errors"] += 1
                    logger.error(f"SKU sweep failed for department {dept_id}: {e}")
                    db.rollback()

        logger.info(
            "Forecast sweep done: %(active_departments)s depts, "
            "%(dept_forecasts_written)s dept forecasts (+%(dept_skipped)s skipped), "
            "%(sku_rows_written)s SKU rows in %(sku_departments)s depts "
            "(%(sku_errors)s errors)" % summary
        )
        return summary
    finally:
        db.close()

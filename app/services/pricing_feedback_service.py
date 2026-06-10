"""Pricing feedback loop (roadmap §7.4) + pilot baseline (A3).

Three responsibilities:

1. detect_applied() — пометить approved-рекомендации как applied, когда в
   sku_catalog_price появился интервал с рекомендованной ценой (приказ iiko
   реально вышел). Запускается после каждого синка каталожных цен.

2. evaluate_outcomes() — для каждой applied-рекомендации, отлежавшей полное
   окно (14 дней), посчитать факт vs ожидание: qty/выручка/GP до и после,
   поправка на контрольную группу (та же категория без изменения цены),
   реализованная эластичность. Результат — в price_recommendation_outcome.

3. freeze_baseline() — зафиксировать KPI подразделений за N полных недель
   как базу для метрики пилота «ΔGP vs baseline».
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

EVAL_WINDOW_DAYS = 14
PRICE_MATCH_TOLERANCE = 0.01


def compute_realized_elasticity(
    qty_change_pct: float,
    control_qty_change_pct: Optional[float],
    old_price: float,
    new_price: float,
) -> tuple[Optional[float], Optional[float]]:
    """Control-adjusted qty change and realized elasticity.

    adj = (1 + own) / (1 + control) - 1;  ε = ln(1 + adj) / ln(P_new / P_old).
    Returns (adj_qty_change_pct, realized_elasticity); None where undefined.
    """
    if control_qty_change_pct is not None and control_qty_change_pct > -1.0:
        adj = (1.0 + qty_change_pct) / (1.0 + control_qty_change_pct) - 1.0
    else:
        adj = qty_change_pct

    if old_price <= 0 or new_price <= 0 or new_price == old_price or adj <= -1.0:
        return round(adj, 4), None

    eps = math.log(1.0 + adj) / math.log(new_price / old_price)
    return round(adj, 4), round(eps, 4)


class PricingFeedbackService:
    def __init__(self, db: Session):
        self.db = db

    # -- 1. applied detection -------------------------------------------------

    def detect_applied(self) -> dict:
        """Mark approved recommendations as applied when the catalog shows
        a new price interval matching the recommended price."""
        result = self.db.execute(
            text("""
                WITH matches AS (
                    SELECT DISTINCT ON (pr.id)
                        pr.id, scp.date_from, scp.price
                    FROM price_recommendation pr
                    JOIN sku_catalog_price scp
                        ON scp.product_id = pr.product_id
                        AND scp.department_id = pr.department_id
                        AND scp.price > 0
                        AND ABS(scp.price - pr.recommended_price) <= :tol
                        AND scp.date_from >= pr.reviewed_at::date
                    WHERE pr.status = 'approved'
                    ORDER BY pr.id, scp.date_from
                )
                UPDATE price_recommendation pr
                SET status = 'applied',
                    applied_at = m.date_from,
                    applied_price = m.price
                FROM matches m
                WHERE pr.id = m.id
                RETURNING pr.id
            """),
            {"tol": PRICE_MATCH_TOLERANCE},
        )
        applied_ids = [r[0] for r in result.fetchall()]
        self.db.commit()
        if applied_ids:
            logger.info("Detected %d applied recommendations: %s", len(applied_ids), applied_ids)
        return {"status": "ok", "applied": len(applied_ids), "ids": applied_ids}

    # -- 2. outcome evaluation -------------------------------------------------

    def evaluate_outcomes(self, eval_window_days: int = EVAL_WINDOW_DAYS) -> dict:
        """Evaluate applied recommendations whose eval window has fully elapsed."""
        pending = self.db.execute(
            text("""
                SELECT pr.id, pr.product_id, pr.department_id::text,
                       pr.applied_at, pr.current_price, pr.applied_price,
                       pr.cogs, pr.delta_gp
                FROM price_recommendation pr
                LEFT JOIN price_recommendation_outcome o ON o.recommendation_id = pr.id
                WHERE pr.status = 'applied'
                  AND pr.applied_at IS NOT NULL
                  AND pr.applied_at + :window <= CURRENT_DATE
                  AND o.id IS NULL
            """),
            {"window": eval_window_days},
        ).fetchall()

        evaluated = 0
        skipped: list[str] = []
        for rec in pending:
            try:
                outcome = self._evaluate_single(rec, eval_window_days)
                if outcome:
                    evaluated += 1
                else:
                    skipped.append(f"rec {rec[0]}: no sales data in windows")
            except Exception as e:
                skipped.append(f"rec {rec[0]}: {e}")
                logger.warning("Outcome evaluation failed for rec %s: %s", rec[0], e)

        self.db.commit()
        logger.info("Outcome evaluation: %d evaluated, %d skipped of %d pending",
                    evaluated, len(skipped), len(pending))
        return {"status": "ok", "pending": len(pending), "evaluated": evaluated, "skipped": skipped}

    def _evaluate_single(self, rec, eval_window_days: int) -> Optional[dict]:
        rec_id, product_id, dept_id, applied_at, old_price, new_price, cogs, weekly_delta_gp = rec
        old_price = float(old_price)
        new_price = float(new_price) if new_price is not None else old_price
        cogs = float(cogs) if cogs is not None else 0.0

        eval_from = applied_at
        eval_to = applied_at + timedelta(days=eval_window_days - 1)
        baseline_to = applied_at - timedelta(days=1)
        baseline_from = applied_at - timedelta(days=eval_window_days)

        windows = self.db.execute(
            text("""
                SELECT
                    SUM(total_qty) FILTER (WHERE sale_date BETWEEN :bfrom AND :bto) AS qty_before,
                    SUM(total_sum) FILTER (WHERE sale_date BETWEEN :bfrom AND :bto) AS rev_before,
                    SUM(total_qty) FILTER (WHERE sale_date BETWEEN :efrom AND :eto) AS qty_after,
                    SUM(total_sum) FILTER (WHERE sale_date BETWEEN :efrom AND :eto) AS rev_after
                FROM sku_daily_sales
                WHERE product_id = :pid AND department_id = CAST(:did AS uuid)
                  AND sale_date BETWEEN :bfrom AND :eto
            """),
            {"pid": product_id, "did": dept_id,
             "bfrom": baseline_from, "bto": baseline_to,
             "efrom": eval_from, "eto": eval_to},
        ).fetchone()

        qty_before = float(windows[0] or 0)
        rev_before = float(windows[1] or 0)
        qty_after = float(windows[2] or 0)
        rev_after = float(windows[3] or 0)
        if qty_before <= 0:
            return None  # нечего сравнивать — позиция не продавалась до изменения

        # Контрольная группа: та же категория и подразделение, без изменения
        # каталожной цены за весь период наблюдения.
        control = self.db.execute(
            text("""
                WITH changed AS (
                    SELECT DISTINCT product_id FROM sku_catalog_price
                    WHERE department_id = CAST(:did AS uuid)
                      AND date_from BETWEEN :bfrom AND :eto
                ),
                peers AS (
                    SELECT p2.id FROM product p2
                    JOIN product p1 ON p1.id = :pid
                    WHERE p2.category_id = p1.category_id
                      AND p2.id <> p1.id
                      AND p2.id NOT IN (SELECT product_id FROM changed)
                )
                SELECT
                    SUM(total_qty) FILTER (WHERE sale_date BETWEEN :bfrom AND :bto) AS qty_before,
                    SUM(total_qty) FILTER (WHERE sale_date BETWEEN :efrom AND :eto) AS qty_after,
                    COUNT(DISTINCT product_id) AS n_skus
                FROM sku_daily_sales
                WHERE department_id = CAST(:did AS uuid)
                  AND product_id IN (SELECT id FROM peers)
                  AND sale_date BETWEEN :bfrom AND :eto
            """),
            {"pid": product_id, "did": dept_id,
             "bfrom": baseline_from, "bto": baseline_to,
             "efrom": eval_from, "eto": eval_to},
        ).fetchone()

        ctl_before = float(control[0] or 0)
        ctl_after = float(control[1] or 0)
        n_control = int(control[2] or 0)
        control_change = (ctl_after / ctl_before - 1.0) if ctl_before > 0 else None

        qty_change = qty_after / qty_before - 1.0
        adj_change, realized_eps = compute_realized_elasticity(
            qty_change, control_change, old_price, new_price,
        )

        gp_before = rev_before - cogs * qty_before
        gp_after = rev_after - cogs * qty_after
        expected_delta_gp = (
            float(weekly_delta_gp) * (eval_window_days / 7.0)
            if weekly_delta_gp is not None else None
        )

        self.db.execute(
            text("""
                INSERT INTO price_recommendation_outcome
                    (recommendation_id, product_id, department_id, applied_at,
                     eval_window_days, baseline_from, baseline_to, eval_from, eval_to,
                     old_price, new_price, qty_before, qty_after,
                     revenue_before, revenue_after, gp_before, gp_after,
                     expected_delta_gp, actual_delta_gp,
                     qty_change_pct, control_qty_change_pct, adj_qty_change_pct,
                     realized_elasticity, n_control_skus)
                VALUES
                    (:rec_id, :pid, CAST(:did AS uuid), :applied_at,
                     :window, :bfrom, :bto, :efrom, :eto,
                     :old_price, :new_price, :qty_before, :qty_after,
                     :rev_before, :rev_after, :gp_before, :gp_after,
                     :expected_dgp, :actual_dgp,
                     :qty_change, :ctl_change, :adj_change,
                     :realized_eps, :n_control)
                ON CONFLICT (recommendation_id) DO NOTHING
            """),
            {
                "rec_id": rec_id, "pid": product_id, "did": dept_id,
                "applied_at": applied_at, "window": eval_window_days,
                "bfrom": baseline_from, "bto": baseline_to,
                "efrom": eval_from, "eto": eval_to,
                "old_price": old_price, "new_price": new_price,
                "qty_before": round(qty_before, 3), "qty_after": round(qty_after, 3),
                "rev_before": round(rev_before, 2), "rev_after": round(rev_after, 2),
                "gp_before": round(gp_before, 2), "gp_after": round(gp_after, 2),
                "expected_dgp": round(expected_delta_gp, 2) if expected_delta_gp is not None else None,
                "actual_dgp": round(gp_after - gp_before, 2),
                "qty_change": round(qty_change, 4),
                "ctl_change": round(control_change, 4) if control_change is not None else None,
                "adj_change": adj_change,
                "realized_eps": realized_eps,
                "n_control": n_control,
            },
        )
        return {"recommendation_id": rec_id}

    # -- 3. baseline freeze ----------------------------------------------------

    def freeze_baseline(self, label: str, weeks: int = 8) -> dict:
        """Freeze per-department + network KPI over the last N complete ISO weeks."""
        today = date.today()
        last_monday = today - timedelta(days=today.weekday())
        baseline_to = last_monday - timedelta(days=1)        # воскресенье прошлой недели
        baseline_from = last_monday - timedelta(weeks=weeks)  # понедельник N недель назад

        result = self.db.execute(
            text("""
                WITH dept_kpi AS (
                    SELECT
                        dw.department_id,
                        SUM(dw.total_revenue) AS total_revenue,
                        SUM(dw.total_cost) AS total_cost,
                        SUM(dw.gross_profit) AS gross_profit,
                        SUM(dw.total_receipts) AS total_receipts,
                        AVG(dw.gross_profit) AS weekly_gp_avg,
                        COALESCE(STDDEV_SAMP(dw.gross_profit), 0) AS weekly_gp_stddev,
                        AVG(dw.cost_coverage) AS cost_coverage
                    FROM department_weekly_summary dw
                    WHERE dw.week_start >= :bfrom AND dw.week_start < :next_monday
                    GROUP BY dw.department_id
                ),
                active AS (
                    SELECT department_id, COUNT(DISTINCT product_id) AS active_skus
                    FROM sku_daily_sales
                    WHERE sale_date BETWEEN :bfrom AND :bto
                    GROUP BY department_id
                )
                INSERT INTO pricing_baseline_kpi
                    (label, scope, department_id, baseline_from, baseline_to, weeks,
                     total_revenue, total_cost, gross_profit, gp_margin,
                     total_receipts, avg_receipt_sum, weekly_gp_avg, weekly_gp_stddev,
                     active_skus, cost_coverage)
                SELECT
                    :label, 'department', dk.department_id, :bfrom, :bto, :weeks,
                    dk.total_revenue, dk.total_cost, dk.gross_profit,
                    CASE WHEN dk.total_revenue > 0
                         THEN ROUND(dk.gross_profit / dk.total_revenue, 4) END,
                    dk.total_receipts,
                    CASE WHEN dk.total_receipts > 0
                         THEN ROUND(dk.total_revenue / dk.total_receipts, 2) END,
                    dk.weekly_gp_avg, dk.weekly_gp_stddev,
                    COALESCE(a.active_skus, 0), ROUND(dk.cost_coverage, 4)
                FROM dept_kpi dk
                LEFT JOIN active a ON a.department_id = dk.department_id
                ON CONFLICT (label, scope, department_id) DO UPDATE SET
                    baseline_from = EXCLUDED.baseline_from,
                    baseline_to = EXCLUDED.baseline_to,
                    weeks = EXCLUDED.weeks,
                    total_revenue = EXCLUDED.total_revenue,
                    total_cost = EXCLUDED.total_cost,
                    gross_profit = EXCLUDED.gross_profit,
                    gp_margin = EXCLUDED.gp_margin,
                    total_receipts = EXCLUDED.total_receipts,
                    avg_receipt_sum = EXCLUDED.avg_receipt_sum,
                    weekly_gp_avg = EXCLUDED.weekly_gp_avg,
                    weekly_gp_stddev = EXCLUDED.weekly_gp_stddev,
                    active_skus = EXCLUDED.active_skus,
                    cost_coverage = EXCLUDED.cost_coverage
                RETURNING department_id
            """),
            {"label": label, "weeks": weeks, "bfrom": baseline_from,
             "bto": baseline_to, "next_monday": last_monday},
        )
        dept_count = len(result.fetchall())

        self.db.execute(
            text("""
                INSERT INTO pricing_baseline_kpi
                    (label, scope, department_id, baseline_from, baseline_to, weeks,
                     total_revenue, total_cost, gross_profit, gp_margin,
                     total_receipts, avg_receipt_sum, weekly_gp_avg, weekly_gp_stddev,
                     active_skus, cost_coverage)
                SELECT
                    :label, 'network', NULL, :bfrom, :bto, :weeks,
                    SUM(total_revenue), SUM(total_cost), SUM(gross_profit),
                    CASE WHEN SUM(total_revenue) > 0
                         THEN ROUND(SUM(gross_profit) / SUM(total_revenue), 4) END,
                    SUM(total_receipts),
                    CASE WHEN SUM(total_receipts) > 0
                         THEN ROUND(SUM(total_revenue) / SUM(total_receipts), 2) END,
                    AVG(weekly_gp_avg), NULL,
                    SUM(active_skus), ROUND(AVG(cost_coverage), 4)
                FROM pricing_baseline_kpi
                WHERE label = :label AND scope = 'department'
                ON CONFLICT (label, scope, department_id) DO UPDATE SET
                    baseline_from = EXCLUDED.baseline_from,
                    baseline_to = EXCLUDED.baseline_to,
                    weeks = EXCLUDED.weeks,
                    total_revenue = EXCLUDED.total_revenue,
                    total_cost = EXCLUDED.total_cost,
                    gross_profit = EXCLUDED.gross_profit,
                    gp_margin = EXCLUDED.gp_margin,
                    total_receipts = EXCLUDED.total_receipts,
                    avg_receipt_sum = EXCLUDED.avg_receipt_sum,
                    weekly_gp_avg = EXCLUDED.weekly_gp_avg,
                    weekly_gp_stddev = EXCLUDED.weekly_gp_stddev,
                    active_skus = EXCLUDED.active_skus,
                    cost_coverage = EXCLUDED.cost_coverage
            """),
            {"label": label, "weeks": weeks, "bfrom": baseline_from, "bto": baseline_to},
        )
        self.db.commit()

        logger.info("Baseline '%s' frozen: %d departments, %s..%s",
                    label, dept_count, baseline_from, baseline_to)
        return {
            "status": "ok",
            "label": label,
            "departments": dept_count,
            "baseline_from": str(baseline_from),
            "baseline_to": str(baseline_to),
            "weeks": weeks,
        }

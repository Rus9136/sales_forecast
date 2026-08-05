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
# детекция applied ограничена окном после approve: цены дискретны (сетка
# 50/100 KZT, коридор ±5%) — ручное изменение цены через месяцы случайно
# совпадало с рекомендованной и порождало мусорный outcome
APPLIED_DETECTION_WINDOW_DAYS = 30


def compute_significance_z(
    adj_qty_change_pct: Optional[float],
    qty_before: float,
    qty_after: float,
    ctl_before: float,
    ctl_after: float,
) -> Optional[float]:
    """z-оценка разности разностей по логарифму отношения ставок продаж.

    SE(ln(rate ratio)) ≈ sqrt(1/n) для пуассоновского счётчика; четыре
    независимых счётчика складываются в квадратах. Нужна потому, что штучный
    торт продаётся 0.2–2 шт/день: «+8 штук за две недели» на глаз выглядит как
    эффект, а на деле неотличимо от нуля.
    """
    if adj_qty_change_pct is None or adj_qty_change_pct <= -1.0:
        return None
    counts = [qty_before, qty_after, ctl_before, ctl_after]
    if any(c <= 0 for c in counts):
        return None
    se = math.sqrt(sum(1.0 / c for c in counts))
    if se <= 0:
        return None
    return round(math.log(1.0 + adj_qty_change_pct) / se, 4)


def compute_realized_elasticity(
    qty_change_pct: float,
    control_qty_change_pct: Optional[float],
    old_price: float,
    new_price: float,
) -> tuple[Optional[float], Optional[float]]:
    """Control-adjusted qty change and realized elasticity.

    adj = (1 + own) / (1 + control) - 1;  ε = ln(1 + adj) / ln(P_new / P_old).
    Returns (adj_qty_change_pct, realized_elasticity); None where undefined.

    Оба изменения ожидаются в среднесуточных ставках продаж, а не в сырых
    суммах окон — иначе разное число рабочих дней (закрытие точки, праздник)
    подмешивается в результат.
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

    def detect_applied(self, actor: str = "scheduler") -> dict:
        """Mark approved recommendations as applied when the catalog shows
        a new price interval matching the recommended price.

        Детекция ограничена окном APPLIED_DETECTION_WINDOW_DAYS после approve;
        approved старше окна переводятся в expired — их базис устарел, а позднее
        совпадение цены почти наверняка не связано с рекомендацией.
        """
        from .pricing_audit import log_audit

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
                        AND NOT scp.is_stale
                        AND ABS(scp.price - pr.recommended_price) <= :tol
                        AND scp.date_from >= pr.reviewed_at::date
                        AND scp.date_from <= pr.reviewed_at::date + :window
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
            {"tol": PRICE_MATCH_TOLERANCE, "window": APPLIED_DETECTION_WINDOW_DAYS},
        )
        applied_ids = [r[0] for r in result.fetchall()]
        for rid in applied_ids:
            log_audit(self.db, "recommendation", rid, "applied", actor=actor)

        expired = self.db.execute(
            text("""
                UPDATE price_recommendation
                SET status = 'expired'
                WHERE status = 'approved'
                  AND reviewed_at < NOW() - make_interval(days => :window)
                RETURNING id
            """),
            {"window": APPLIED_DETECTION_WINDOW_DAYS},
        )
        expired_ids = [r[0] for r in expired.fetchall()]
        for rid in expired_ids:
            log_audit(self.db, "recommendation", rid, "expired", actor=actor,
                      details={"reason": f"approved, not applied within {APPLIED_DETECTION_WINDOW_DAYS}d"})

        # протухшие 'new': точка перестала торговать → ночной оптимизатор её
        # не супersede'ит, и майские рекомендации вечно висели бы открытыми,
        # завышая summary. TTL тот же, что и для approved.
        stale_new = self.db.execute(
            text("""
                UPDATE price_recommendation
                SET status = 'expired'
                WHERE status = 'new'
                  AND created_at < NOW() - make_interval(days => :window)
            """),
            {"window": APPLIED_DETECTION_WINDOW_DAYS},
        )
        expired_new = stale_new.rowcount

        self.db.commit()
        if applied_ids or expired_ids or expired_new:
            logger.info(
                "Detected %d applied recommendations: %s; expired %d stale approved, %d stale new",
                len(applied_ids), applied_ids, len(expired_ids), expired_new,
            )
        return {
            "status": "ok",
            "applied": len(applied_ids),
            "ids": applied_ids,
            "expired_stale_approved": len(expired_ids),
            "expired_stale_new": expired_new,
        }

    # -- 2. outcome evaluation -------------------------------------------------

    def evaluate_outcomes(self, eval_window_days: int = EVAL_WINDOW_DAYS,
                          recompute: bool = False) -> dict:
        """Evaluate applied recommendations whose eval window has fully elapsed.

        recompute=True пересчитывает уже оценённые строки — нужно после смены
        методики (миграция 036) и после дозагрузки продаж за пропущенный день,
        иначе старая цифра живёт в дашборде вечно.
        """
        if recompute:
            self.db.execute(
                text("""
                    DELETE FROM price_recommendation_outcome
                    WHERE recommendation_id IN (
                        SELECT pr.id FROM price_recommendation pr
                        WHERE pr.status = 'applied'
                          AND pr.applied_at IS NOT NULL
                          AND pr.applied_at + :window <= CURRENT_DATE
                    )
                """),
                {"window": eval_window_days},
            )

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
                # SAVEPOINT: ошибка SQL на одном rec переводила транзакцию в
                # failed state — все последующие итерации и финальный commit
                # падали, и уже посчитанные outcome-строки ночи терялись
                with self.db.begin_nested():
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

        # Рабочие дни ТОЧКИ, а не календарные: 12.07.2026 «Мадлен 18 мкр» не
        # работала, база вышла 13 дней против 14 в оценке и завысила эффект на
        # ~7.7%. Считаем по тому же источнику, что и qty, чтобы окна сходились.
        days = self.db.execute(
            text("""
                SELECT COUNT(DISTINCT sale_date) FILTER (WHERE sale_date BETWEEN :bfrom AND :bto),
                       COUNT(DISTINCT sale_date) FILTER (WHERE sale_date BETWEEN :efrom AND :eto)
                FROM sku_daily_sales
                WHERE department_id = CAST(:did AS uuid)
                  AND sale_date BETWEEN :bfrom AND :eto
            """),
            {"did": dept_id, "bfrom": baseline_from, "bto": baseline_to,
             "efrom": eval_from, "eto": eval_to},
        ).fetchone()

        days_before = int(days[0] or 0)
        days_after = int(days[1] or 0)
        if days_before <= 0 or days_after <= 0:
            return None  # точка не работала в одном из окон — сравнивать нечего

        # Контрольная группа: та же категория и подразделение, без изменения
        # каталожной цены за весь период наблюдения.
        control = self.db.execute(
            text("""
                WITH changed AS (
                    SELECT DISTINCT product_id FROM sku_catalog_price
                    WHERE department_id = CAST(:did AS uuid)
                      AND date_from BETWEEN :bfrom AND :eto
                      AND NOT is_stale
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

        # Всё в среднесуточных ставках продаж: дневные множители сокращаются в
        # adj (отношение отношений), но каждое изменение по отдельности
        # становится честным.
        rate_before = qty_before / days_before
        rate_after = qty_after / days_after
        qty_change = rate_after / rate_before - 1.0

        if ctl_before > 0:
            ctl_rate_ratio = (ctl_after / days_after) / (ctl_before / days_before)
            control_change = ctl_rate_ratio - 1.0
        else:
            ctl_rate_ratio = None
            control_change = None

        adj_change, realized_eps = compute_realized_elasticity(
            qty_change, control_change, old_price, new_price,
        )
        significance_z = compute_significance_z(
            adj_change, qty_before, qty_after, ctl_before, ctl_after,
        )

        gp_before = rev_before - cogs * qty_before
        gp_after = rev_after - cogs * qty_after

        # Контрфакт: сколько бы продали за оценочное окно по старой цене, если
        # бы позиция просто повторила динамику своей категории.
        counterfactual_qty = rate_before * (ctl_rate_ratio or 1.0) * days_after
        gp_counterfactual = counterfactual_qty * (old_price - cogs)
        incremental_delta_gp = gp_after - gp_counterfactual

        # «Что произошло в кассе», приведённое к равному числу рабочих дней.
        # Фон категории здесь НЕ вычтен — это делает incremental_delta_gp.
        actual_delta_gp = gp_after - gp_before * (days_after / days_before)

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
                     realized_elasticity, n_control_skus,
                     days_before, days_after, counterfactual_qty,
                     incremental_delta_gp, significance_z)
                VALUES
                    (:rec_id, :pid, CAST(:did AS uuid), :applied_at,
                     :window, :bfrom, :bto, :efrom, :eto,
                     :old_price, :new_price, :qty_before, :qty_after,
                     :rev_before, :rev_after, :gp_before, :gp_after,
                     :expected_dgp, :actual_dgp,
                     :qty_change, :ctl_change, :adj_change,
                     :realized_eps, :n_control,
                     :days_before, :days_after, :cf_qty,
                     :incremental_dgp, :sig_z)
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
                "actual_dgp": round(actual_delta_gp, 2),
                "qty_change": round(qty_change, 4),
                "ctl_change": round(control_change, 4) if control_change is not None else None,
                "adj_change": adj_change,
                "realized_eps": realized_eps,
                "n_control": n_control,
                "days_before": days_before,
                "days_after": days_after,
                "cf_qty": round(counterfactual_qty, 3),
                "incremental_dgp": round(incremental_delta_gp, 2),
                "sig_z": significance_z,
            },
        )
        return {"recommendation_id": rec_id}

    # -- 3. baseline freeze ----------------------------------------------------

    def freeze_baseline(self, label: str, weeks: int = 8, force: bool = False,
                        actor: Optional[str] = None) -> dict:
        """Freeze per-department + network KPI over the last N complete ISO weeks.

        Повторный вызов с существующим label БЕЗ force — ошибка: «замороженная»
        пред-пилотная база молча пересчитывалась по свежим (пост-пилотным)
        данным, обнуляя точку отсчёта метрики «ΔGP vs baseline».
        """
        existing = self.db.execute(
            text("SELECT COUNT(*) FROM pricing_baseline_kpi WHERE label = :label"),
            {"label": label},
        ).scalar()
        if existing and not force:
            return {
                "status": "error",
                "code": "label_exists",
                "message": (
                    f"Baseline '{label}' уже заморожен ({existing} строк). "
                    "Перезапись — только с force=true"
                ),
            }

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
        from .pricing_audit import log_audit
        log_audit(self.db, "baseline", label, "freeze", actor=actor,
                  details={"weeks": weeks, "departments": dept_count, "force": force,
                           "baseline_from": str(baseline_from), "baseline_to": str(baseline_to)})
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

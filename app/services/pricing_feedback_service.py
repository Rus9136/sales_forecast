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

# Окна замера настраиваются на экране «Правила цен» (правило effect_measurement).
# Здесь — только дефолт на случай, если правила нет; см.
# PricingRulesService.get_measurement_window().
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
        self._estimator = None
        self._rules = None

    @property
    def rules(self):
        if self._rules is None:
            from .pricing_rules_service import PricingRulesService
            self._rules = PricingRulesService(self.db)
        return self._rules

    @property
    def estimator(self):
        """Ленивая инициализация: numpy тянется только когда реально считаем."""
        if self._estimator is None:
            from .pricing_effect import PriceEffectEstimator
            self._estimator = PriceEffectEstimator(self.db)
        return self._estimator

    # -- 1. applied detection -------------------------------------------------

    def detect_applied(self, actor: str = "scheduler") -> dict:
        """Mark approved recommendations as applied when the catalog shows
        a new price interval matching the recommended price.

        Детекция ограничена окном APPLIED_DETECTION_WINDOW_DAYS после approve;
        approved старше окна переводятся в expired — их базис устарел, а позднее
        совпадение цены почти наверняка не связано с рекомендацией.
        """
        from .pricing_audit import log_audit

        # Сопоставление по документу (миграция 039): если цена уехала нашим
        # приказом, каталог принесёт интервал с ЕГО document_id. Это точнее
        # совпадения цены: applied_at = дата вступления приказа в силу, а не
        # «когда мы заметили похожую цену». Совпадение по цене остаётся ниже
        # фолбэком — цены правят и в обход системы.
        by_document = self.db.execute(
            text("""
                WITH matches AS (
                    SELECT DISTINCT ON (pr.id)
                        pr.id, scp.date_from, scp.price
                    FROM price_recommendation pr
                    JOIN price_change_order o ON o.id = pr.order_id
                    JOIN sku_catalog_price scp
                        ON scp.product_id = pr.product_id
                        AND scp.department_id = pr.department_id
                        AND scp.document_id = o.iiko_document_id
                        AND scp.price > 0
                        AND NOT scp.is_stale
                    WHERE pr.status = 'approved'
                      AND o.status = 'sent'
                      AND o.iiko_document_id IS NOT NULL
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
        )
        applied_by_document = [r[0] for r in by_document.fetchall()]
        for rid in applied_by_document:
            log_audit(self.db, "recommendation", rid, "applied", actor=actor,
                      details={"matched_by": "order_document"})

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
                UPDATE price_recommendation pr
                SET status = 'expired'
                WHERE pr.status = 'approved'
                  AND pr.reviewed_at < NOW() - make_interval(days => :window)
                  -- приказ уже уехал в iiko и ещё не вступил в силу: цена
                  -- впереди, экспирировать такую рекомендацию нельзя
                  AND NOT EXISTS (
                      SELECT 1 FROM price_change_order o
                      WHERE o.id = pr.order_id AND o.status = 'sent'
                        AND o.effective_date >= CURRENT_DATE
                  )
                RETURNING pr.id
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
        applied_ids = applied_by_document + applied_ids
        if applied_ids or expired_ids or expired_new:
            logger.info(
                "Detected %d applied recommendations (%d по документу приказа): %s; "
                "expired %d stale approved, %d stale new",
                len(applied_ids), len(applied_by_document), applied_ids,
                len(expired_ids), expired_new,
            )
        return {
            "status": "ok",
            "applied": len(applied_ids),
            "applied_by_document": len(applied_by_document),
            "ids": applied_ids,
            "expired_stale_approved": len(expired_ids),
            "expired_stale_new": expired_new,
        }

    # -- 2. outcome evaluation -------------------------------------------------

    def evaluate_outcomes(self, eval_window_days: Optional[int] = None,
                          baseline_days: Optional[int] = None,
                          recompute: bool = False) -> dict:
        """Evaluate applied recommendations whose eval window has fully elapsed.

        recompute=True пересчитывает уже оценённые строки — нужно после смены
        методики (миграция 036) и после дозагрузки продаж за пропущенный день,
        иначе старая цифра живёт в дашборде вечно.

        Длины окон берутся из правила effect_measurement (экран «Правила цен»).
        База и окно замера независимы: база должна стоять на тихом участке без
        чужих переоценок, иначе контрольные точки выкашиваются фильтром «цену
        не меняли» — при симметричных 30 днях контроль обнулялся полностью.
        """
        window = self.rules.get_measurement_window()
        eval_window_days = eval_window_days or window["eval_days"]
        baseline_days = baseline_days or window["baseline_days"]

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
            self.db.execute(
                text("""
                    DELETE FROM price_outcome_batch
                    WHERE (department_id, applied_at) IN (
                        SELECT pr.department_id, pr.applied_at FROM price_recommendation pr
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
        batches: dict[tuple[str, date], list[dict]] = {}
        for rec in pending:
            try:
                # SAVEPOINT: ошибка SQL на одном rec переводила транзакцию в
                # failed state — все последующие итерации и финальный commit
                # падали, и уже посчитанные outcome-строки ночи терялись
                with self.db.begin_nested():
                    outcome = self._evaluate_single(rec, eval_window_days, baseline_days)
                if outcome:
                    evaluated += 1
                    key = (outcome["department_id"], outcome["applied_at"])
                    batches.setdefault(key, []).append(outcome)
                else:
                    skipped.append(f"rec {rec[0]}: no sales data in windows")
            except Exception as e:
                skipped.append(f"rec {rec[0]}: {e}")
                logger.warning("Outcome evaluation failed for rec %s: %s", rec[0], e)

        for key, items in batches.items():
            try:
                with self.db.begin_nested():
                    self._store_batch(key, items, eval_window_days)
            except Exception as e:
                logger.warning("Batch outcome failed for %s: %s", key, e)

        self.db.commit()
        logger.info("Outcome evaluation: %d evaluated, %d skipped of %d pending, %d batches",
                    evaluated, len(skipped), len(pending), len(batches))
        return {"status": "ok", "pending": len(pending), "evaluated": evaluated,
                "batches": len(batches), "skipped": skipped}

    def _store_batch(self, key, items: list[dict], eval_window_days: int) -> None:
        """Эффект приказа целиком: одна перетасовка дней на все его позиции.

        Отдельный штучный торт при 1–2 шт/день неизмерим почти всегда — это
        свойство товара, а не метода. Пачка решений измерима, и именно она
        отвечает на вопрос «стоил ли этот приказ чего-нибудь».
        """
        dept_id, applied_at = key
        panels = [i["panel"] for i in items if i["panel"] is not None]
        batch = self.estimator.estimate_batch(panels)

        self.db.execute(
            text("""
                INSERT INTO price_outcome_batch
                    (department_id, applied_at, concept, eval_window_days,
                     n_positions, n_measurable, gp_before, gp_after,
                     actual_delta_gp, expected_delta_gp,
                     effect_gp, effect_ci_low, effect_ci_high, p_negative)
                VALUES
                    (CAST(:dept AS uuid), :applied_at, :concept, :window,
                     :n_pos, :n_meas, :gp_b, :gp_a,
                     :actual, :expected,
                     :effect, :ci_low, :ci_high, :p_neg)
                ON CONFLICT (department_id, applied_at, eval_window_days) DO UPDATE SET
                    concept = EXCLUDED.concept,
                    n_positions = EXCLUDED.n_positions,
                    n_measurable = EXCLUDED.n_measurable,
                    gp_before = EXCLUDED.gp_before,
                    gp_after = EXCLUDED.gp_after,
                    actual_delta_gp = EXCLUDED.actual_delta_gp,
                    expected_delta_gp = EXCLUDED.expected_delta_gp,
                    effect_gp = EXCLUDED.effect_gp,
                    effect_ci_low = EXCLUDED.effect_ci_low,
                    effect_ci_high = EXCLUDED.effect_ci_high,
                    p_negative = EXCLUDED.p_negative,
                    created_at = now()
            """),
            {
                "dept": dept_id, "applied_at": applied_at,
                "concept": items[0].get("concept"), "window": eval_window_days,
                "n_pos": len(items), "n_meas": len(panels),
                "gp_b": round(sum(i["gp_before_norm"] for i in items), 2),
                "gp_a": round(sum(i["gp_after"] for i in items), 2),
                "actual": round(sum(i["actual_delta_gp"] for i in items), 2),
                "expected": round(sum(i["expected_delta_gp"] or 0.0 for i in items), 2),
                "effect": round(batch.effect_gp, 2) if batch.effect_gp is not None else None,
                "ci_low": round(batch.ci_low, 2) if batch.ci_low is not None else None,
                "ci_high": round(batch.ci_high, 2) if batch.ci_high is not None else None,
                "p_neg": batch.p_negative,
            },
        )

    def _evaluate_single(self, rec, eval_window_days: int,
                         baseline_days: int) -> Optional[dict]:
        rec_id, product_id, dept_id, applied_at, old_price, new_price, cogs, weekly_delta_gp = rec
        old_price = float(old_price)
        new_price = float(new_price) if new_price is not None else old_price
        cogs = float(cogs) if cogs is not None else 0.0

        eval_from = applied_at
        eval_to = applied_at + timedelta(days=eval_window_days - 1)
        baseline_to = applied_at - timedelta(days=1)
        baseline_from = applied_at - timedelta(days=baseline_days)

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

        # Контроль — «тот же товар в других точках той же концепции, где цену
        # не меняли». Прежний контроль по соседним блюдам той же точки убран:
        # сосед задет нашим же решением (переток спроса), ассортимент выпечки
        # крутится, объёмы мизерные. Подробный разбор — в pricing_effect.py.
        eff, panel = self.estimator.estimate(
            product_id=product_id, dept_id=dept_id,
            old_price=old_price, new_price=new_price, cogs=cogs,
            baseline_from=baseline_from, baseline_to=baseline_to,
            eval_from=eval_from, eval_to=eval_to,
        )

        # Всё в среднесуточных ставках продаж: дневные множители сокращаются в
        # adj (отношение отношений), но каждое изменение по отдельности
        # становится честным.
        rate_before = qty_before / days_before
        rate_after = qty_after / days_after
        qty_change = rate_after / rate_before - 1.0

        # Фон = тренд товара по сети × поправка на тренд самой точки. Второй
        # множитель нужен, чтобы слабый месяц у точки не записался в минус
        # решению о цене.
        if eff.measurable and eff.control_trend and eff.store_trend_adj:
            control_change = eff.control_trend * eff.store_trend_adj - 1.0
            adj_change, realized_eps = compute_realized_elasticity(
                qty_change, control_change, old_price, new_price,
            )
            significance_z = compute_significance_z(
                adj_change, qty_before, qty_after,
                eff.control_qty_before, eff.control_qty_after,
            )
        else:
            # Без контроля «очищенных» чисел не существует. Раньше здесь молча
            # подставлялось сырое изменение — и оно уезжало в отчёты как эффект.
            control_change = adj_change = realized_eps = significance_z = None

        gp_before = rev_before - cogs * qty_before
        gp_after = rev_after - cogs * qty_after

        counterfactual_qty = eff.counterfactual_qty
        incremental_delta_gp = eff.effect_gp

        # «Что произошло в кассе», приведённое к равному числу рабочих дней.
        # Фон сети здесь НЕ вычтен — это делает incremental_delta_gp.
        actual_delta_gp = gp_after - gp_before * (days_after / days_before)

        concept = self.db.execute(
            text("SELECT iiko_source_domain FROM departments WHERE id = CAST(:d AS uuid)"),
            {"d": dept_id},
        ).scalar()

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
                     incremental_delta_gp, significance_z,
                     control_method, measurable, not_measurable_reason,
                     n_control_stores, control_qty_before, control_qty_after,
                     control_trend, store_trend_adj,
                     effect_ci_low, effect_ci_high, p_negative, concept)
                VALUES
                    (:rec_id, :pid, CAST(:did AS uuid), :applied_at,
                     :window, :bfrom, :bto, :efrom, :eto,
                     :old_price, :new_price, :qty_before, :qty_after,
                     :rev_before, :rev_after, :gp_before, :gp_after,
                     :expected_dgp, :actual_dgp,
                     :qty_change, :ctl_change, :adj_change,
                     :realized_eps, :n_control,
                     :days_before, :days_after, :cf_qty,
                     :incremental_dgp, :sig_z,
                     :ctl_method, :measurable, :reason,
                     :n_ctl_stores, :ctl_qb, :ctl_qa,
                     :ctl_trend, :store_adj,
                     :ci_low, :ci_high, :p_neg, :concept)
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
                "n_control": eff.n_control_stores,
                "days_before": days_before,
                "days_after": days_after,
                "cf_qty": round(counterfactual_qty, 3) if counterfactual_qty is not None else None,
                "incremental_dgp": round(incremental_delta_gp, 2) if incremental_delta_gp is not None else None,
                "sig_z": significance_z,
                "ctl_method": eff.control_method,
                "measurable": eff.measurable,
                "reason": eff.reason,
                "n_ctl_stores": eff.n_control_stores,
                "ctl_qb": round(eff.control_qty_before, 3),
                "ctl_qa": round(eff.control_qty_after, 3),
                "ctl_trend": round(eff.control_trend, 4) if eff.control_trend is not None else None,
                "store_adj": round(eff.store_trend_adj, 4) if eff.store_trend_adj is not None else None,
                "ci_low": round(eff.ci_low, 2) if eff.ci_low is not None else None,
                "ci_high": round(eff.ci_high, 2) if eff.ci_high is not None else None,
                "p_neg": eff.p_negative,
                "concept": concept,
            },
        )
        return {
            "recommendation_id": rec_id, "panel": panel, "concept": concept,
            "department_id": dept_id, "applied_at": applied_at,
            "gp_before_norm": gp_before * (days_after / days_before),
            "gp_after": gp_after, "actual_delta_gp": actual_delta_gp,
            "expected_delta_gp": expected_delta_gp,
        }

    # -- 3. baseline freeze ----------------------------------------------------

    def freeze_baseline(self, label: str, weeks: int = 8, force: bool = False,
                        actor: Optional[str] = None,
                        as_of: Optional[date] = None) -> dict:
        """Freeze per-department + network KPI over the last N complete ISO weeks.

        Повторный вызов с существующим label БЕЗ force — ошибка: «замороженная»
        пред-пилотная база молча пересчитывалась по свежим (пост-пилотным)
        данным, обнуляя точку отсчёта метрики «ΔGP vs baseline».

        `as_of` сдвигает точку отсчёта окна: без него берутся последние N недель
        от сегодня. Нужен, чтобы пересчитать УЖЕ замороженный снимок за тот же
        период — витрины могли поехать задним числом (так и вышло: база от
        10.06 попала на ошибку в себестоимости, исправленную 09.07, и держала
        отрицательную валовую прибыль). Без этого параметра «пересчитать»
        означало бы «заморозить другой период», то есть потерять точку отсчёта.
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

        today = as_of or date.today()
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

"""B3: Price optimizer — grid-search GP maximizer with constraint enforcement."""

from __future__ import annotations

import logging
import math
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .pricing_rules_service import PricingRulesService

logger = logging.getLogger(__name__)

MIN_GP_THRESHOLD = 500.0
DEFAULT_ELASTICITY = -0.5
CONSERVATIVE_FALLBACK_ELASTICITY = -1.0
# кумулятивный потолок: цена не выше +15% к цене 90 дней назад — иначе
# монотонная модель qty=q0·ratio^ε с ре-базированием на новую цену даёт
# «храповик» +max_step каждые min_frequency дней без ограничения
CUMULATIVE_CAP_PCT = 0.15
CUMULATIVE_CAP_WINDOW_DAYS = 90
# approved-рекомендация без применения протухает: базис (цена/COGS/эластичность)
# устаревает, а детекция applied без TTL ловила совпадения через полгода
APPROVED_TTL_DAYS = 30


def select_planning_elasticity(
    mean: float, ci_lower: Optional[float], grade: str,
    estimation_level: Optional[str] = None,
) -> float:
    """Elasticity used for planning expected qty/GP.

    Grade A/B — точечная оценка надёжна. Grade C/D — оценка в основном
    заимствована (group/global), точечная ε почти не информативна, поэтому
    планируем по консервативному краю CI (наиболее эластичный сценарий):
    завышенные ΔGP от «слепого» prior не проходят порог.

    estimation_level='global' — про SKU не известно ничего: global prior
    почти нулевой (≈ −0.1) делал data-poor позиции «неэластичными» и толкал
    их к верху коридора. Планируем не мягче жёсткого fallback −1.0 — как для
    SKU вовсе без записи эластичности.
    """
    if grade in ("A", "B"):
        return mean
    if estimation_level == "global":
        candidate = ci_lower if ci_lower is not None else mean
        return min(candidate, CONSERVATIVE_FALLBACK_ELASTICITY)
    if ci_lower is not None:
        return ci_lower
    return min(mean, CONSERVATIVE_FALLBACK_ELASTICITY)


# «почти нет отклика спроса» — пессимизм для снижения цены без данных
CONSERVATIVE_DOWN_ELASTICITY = -0.1


def select_planning_elasticity_down(
    mean: float, ci_upper: Optional[float], grade: str,
    estimation_level: Optional[str] = None,
) -> float:
    """Планирующая ε для КАНДИДАТОВ НИЖЕ текущей цены.

    Консервативность двусторонняя: для повышений пессимизм — эластичный край
    (ci_lower), но для снижений тот же край наоборот РАЗДУВАЕТ ожидаемый рост
    qty и делает снижение цены ложно привлекательным. Для снижений пессимизм —
    НЕэластичный край (ci_upper, ближе к нулю): скидка почти не приводит
    покупателей → GP от снижения падает → спекулятивные снижения на слабых
    грейдах не проходят порог ΔGP.
    """
    if grade in ("A", "B"):
        return mean
    if ci_upper is not None:
        return min(ci_upper, 0.0)
    return max(mean, CONSERVATIVE_DOWN_ELASTICITY)


class PriceOptimizerService:
    def __init__(self, db: Session):
        self.db = db
        self.rules_service = PricingRulesService(db)

    def generate_recommendations(
        self,
        department_id: str,
        min_gp_threshold: float = MIN_GP_THRESHOLD,
    ) -> dict:
        """Generate price recommendations for all active SKUs in a department."""
        batch_id = str(uuid.uuid4())
        today = date.today()
        errors: list[str] = []

        # сериализуем генерацию по точке: ручной POST конкурентно с ночным
        # джобом (или двойной клик) давал два батча и дубли 'new' на SKU
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('pricing_gen:' || :d))"),
            {"d": department_id},
        )

        skus = self._load_sku_data(department_id)
        if not skus:
            return {
                "status": "no_data",
                "department_id": department_id,
                "recommendations_created": 0,
                "skus_processed": 0,
                "batch_id": batch_id,
                "errors": ["No active SKUs found"],
            }

        self._supersede_open_recommendations(department_id)
        experiment_products = self._open_experiment_products(department_id)
        pending_products = self._pending_review_products(department_id)

        created = 0
        skipped_no_cogs = 0
        skipped_pending = 0
        for sku in skus:
            try:
                if sku["product_id"] in experiment_products:
                    continue  # идёт эксперимент — не загрязняем измерение
                if sku["product_id"] in pending_products:
                    skipped_pending += 1  # есть approved/недооценённая applied
                    continue
                if sku["cogs"] is None:
                    skipped_no_cogs += 1
                    continue
                # SAVEPOINT: сбой SQL на одном SKU не абортит транзакцию всего
                # батча (иначе остальные итерации падали InFailedSqlTransaction)
                with self.db.begin_nested():
                    rec = self._optimize_single(sku, batch_id, min_gp_threshold, today)
                    if rec:
                        self._insert_recommendation(rec)
                        created += 1
            except Exception as e:
                errors.append(f"SKU {sku['product_id']}: {e}")
                logger.warning("Optimization error for SKU %s: %s", sku["product_id"], e)

        # переносим LLM-объяснение с только что замещённой рекомендации, если
        # содержание не изменилось — иначе каждая ночь заново жгла ~150-200
        # вызовов Claude на неизменные рекомендации
        self.db.execute(
            text("""
                UPDATE price_recommendation new_r
                SET llm_explanation = old_r.llm_explanation
                FROM price_recommendation old_r
                WHERE new_r.batch_id = CAST(:batch_id AS uuid)
                  AND new_r.llm_explanation IS NULL
                  AND old_r.id = (
                      SELECT o.id FROM price_recommendation o
                      WHERE o.product_id = new_r.product_id
                        AND o.department_id = new_r.department_id
                        AND o.status = 'expired'
                        AND o.llm_explanation IS NOT NULL
                        AND o.recommended_price = new_r.recommended_price
                        AND o.current_price = new_r.current_price
                      ORDER BY o.id DESC LIMIT 1
                  )
            """),
            {"batch_id": batch_id},
        )

        self.db.commit()
        logger.info(
            "Optimization for dept %s: %d recommendations from %d SKUs "
            "(%d skipped: no COGS, %d skipped: pending review)",
            department_id, created, len(skus), skipped_no_cogs, skipped_pending,
        )

        return {
            "status": "ok" if not errors else "partial",
            "department_id": department_id,
            "recommendations_created": created,
            "skus_processed": len(skus),
            "skipped_no_cogs": skipped_no_cogs,
            "skipped_pending_review": skipped_pending,
            "batch_id": batch_id,
            "errors": errors,
        }

    def _load_sku_data(self, department_id: str) -> list[dict]:
        """Load current price, COGS, elasticity, role, base qty for active SKUs.

        current_price comes from sku_catalog_price (real menu prices set by
        orders) with fallback on the derived revenue/qty price — the derived
        price is contaminated by modifiers/weight items. last_change_date also
        comes from the catalog (start of the current price interval), not from
        the noisy sku_price_history.
        """
        rows = self.db.execute(
            text("""
                WITH recent_sales AS (
                    -- avg_daily_qty over 30 CALENDAR days, not days-with-sales:
                    -- dividing by days-with-sales inflated sparse SKUs ~15x
                    SELECT product_id,
                        ROUND(SUM(total_sum) / NULLIF(SUM(total_qty), 0), 2) AS derived_price,
                        ROUND(SUM(total_qty) / 30.0, 2) AS avg_daily_qty
                    FROM sku_daily_sales
                    WHERE department_id = CAST(:dept_id AS uuid)
                      AND sale_date >= CURRENT_DATE - 30
                      AND total_qty > 0
                    GROUP BY product_id
                ),
                catalog_now AS (
                    -- цена БАЗОВОЙ серии (BASE, без размера), не AVG по
                    -- размерам/прайс-категориям: среднее — несуществующая цена,
                    -- detect_applied по ней никогда не матчился
                    SELECT DISTINCT ON (product_id)
                        product_id,
                        price AS catalog_price,
                        date_from AS last_change_date
                    FROM sku_catalog_price
                    WHERE department_id = CAST(:dept_id AS uuid)
                      AND product_id IS NOT NULL
                      AND price > 0
                      AND NOT is_stale
                      AND date_from <= CURRENT_DATE
                      AND date_to > CURRENT_DATE
                    ORDER BY product_id, (price_type <> 'BASE'),
                             (product_size_id IS NOT NULL), product_size_id, id
                ),
                price_90 AS (
                    -- цена базовой серии 90 дней назад — база кумулятивного
                    -- потолка (+15% за окно)
                    SELECT DISTINCT ON (product_id)
                        product_id, price AS price_90d
                    FROM sku_catalog_price
                    WHERE department_id = CAST(:dept_id AS uuid)
                      AND product_id IS NOT NULL
                      AND price > 0
                      AND NOT is_stale
                      AND date_from <= CURRENT_DATE - :cum_window
                      AND date_to > CURRENT_DATE - :cum_window
                    ORDER BY product_id, (price_type <> 'BASE'),
                             (product_size_id IS NOT NULL), product_size_id, id
                ),
                recent_cost AS (
                    SELECT sws.product_id,
                        ROUND(SUM(sws.total_cost) / NULLIF(SUM(sws.total_qty), 0), 2) AS unit_cogs
                    FROM sku_weekly_summary sws
                    WHERE sws.department_id = CAST(:dept_id AS uuid)
                      AND sws.week_start >= CURRENT_DATE - 28
                      AND sws.total_cost > 0
                    GROUP BY sws.product_id
                )
                SELECT
                    rs.product_id,
                    p.name AS product_name,
                    COALESCE(cn.catalog_price, rs.derived_price) AS current_price,
                    rs.avg_daily_qty,
                    rc.unit_cogs,
                    COALESCE(se.elasticity_mean, :default_eps) AS elasticity,
                    se.elasticity_ci_lower,
                    COALESCE(se.reliability_grade, 'D') AS elasticity_grade,
                    COALESCE(smr.effective_role, 'unknown') AS menu_role,
                    cn.last_change_date,
                    d.segment_type,
                    se.estimation_level,
                    p90.price_90d,
                    se.elasticity_ci_upper
                FROM recent_sales rs
                JOIN product p ON p.id = rs.product_id
                JOIN departments d ON d.id = CAST(:dept_id AS uuid)
                LEFT JOIN catalog_now cn ON cn.product_id = rs.product_id
                LEFT JOIN price_90 p90 ON p90.product_id = rs.product_id
                LEFT JOIN recent_cost rc ON rc.product_id = rs.product_id
                LEFT JOIN sku_elasticity se
                    ON se.product_id = rs.product_id
                    AND se.department_id = CAST(:dept_id AS uuid)
                LEFT JOIN sku_menu_role smr
                    ON smr.product_id = rs.product_id
                    AND smr.department_id = CAST(:dept_id AS uuid)
                WHERE COALESCE(cn.catalog_price, rs.derived_price) > 0
                ORDER BY COALESCE(cn.catalog_price, rs.derived_price) * rs.avg_daily_qty DESC
            """),
            {
                "dept_id": department_id,
                "default_eps": DEFAULT_ELASTICITY,
                "cum_window": CUMULATIVE_CAP_WINDOW_DAYS,
            },
        ).fetchall()

        skus = []
        for r in rows:
            mean = float(r[5])
            ci_lower = float(r[6]) if r[6] is not None else None
            grade = r[7]
            estimation_level = r[11]
            ci_upper = float(r[13]) if r[13] is not None else None
            skus.append({
                "product_id": r[0],
                "product_name": r[1],
                "current_price": float(r[2]),
                "avg_daily_qty": float(r[3]),
                "cogs": float(r[4]) if r[4] is not None else None,
                "elasticity": select_planning_elasticity(mean, ci_lower, grade, estimation_level),
                "elasticity_down": select_planning_elasticity_down(mean, ci_upper, grade, estimation_level),
                "elasticity_mean": mean,
                "elasticity_grade": grade,
                "menu_role": r[8],
                "last_change_date": r[9],
                "segment_type": r[10],
                "estimation_level": estimation_level,
                "price_90d": float(r[12]) if r[12] is not None else None,
                "department_id": department_id,
            })
        return skus

    def _optimize_single(
        self,
        sku: dict,
        batch_id: str,
        min_gp_threshold: float,
        today: date,
    ) -> Optional[dict]:
        """Find optimal price for a single SKU via grid search."""
        current_price = sku["current_price"]
        cogs = sku["cogs"]
        elasticity = sku["elasticity"]  # пессимизм для повышений (эластичный край)
        elasticity_down = sku.get("elasticity_down", elasticity)  # пессимизм для снижений
        menu_role = sku["menu_role"]
        q_base = sku["avg_daily_qty"] * 7  # weekly qty

        if current_price <= 0 or q_base <= 0:
            return None

        # Без себестоимости GP вырождается в выручку (маржа 100%), а правило
        # min_margin молча пропускается — такие SKU не оптимизируем.
        if cogs is None:
            return None

        rules = self.rules_service.get_effective_rules(
            sku["product_id"], sku["department_id"], sku.get("segment_type"),
        )

        candidates = self._enumerate_candidates(current_price, rules, menu_role)
        if not candidates:
            return None

        current_gp = self._compute_gp(current_price, current_price, cogs, q_base, elasticity)

        # кумулятивный потолок: не выше +15% к цене 90 дней назад
        cum_cap_price = None
        if sku.get("price_90d"):
            cum_cap_price = sku["price_90d"] * (1 + CUMULATIVE_CAP_PCT)

        best_price = current_price
        best_gp = current_gp
        best_qty = q_base
        best_eps = elasticity
        binding_constraints: set[str] = set()

        for p in candidates:
            if p == current_price:
                continue

            if cum_cap_price is not None and p > cum_cap_price:
                binding_constraints.add("cumulative_cap")
                continue

            is_valid, violations = self.rules_service.check_recommendation(
                current_price, p, cogs, menu_role, sku.get("last_change_date"), rules,
            )
            if not is_valid:
                # правила, отсёкшие кандидатов, ограничили пространство поиска
                binding_constraints.update(v.split(":", 1)[0] for v in violations)
                continue

            # двусторонний пессимизм: вверх — эластичный край, вниз — неэластичный
            eps = elasticity if p > current_price else elasticity_down
            gp, qty = self._compute_gp_and_qty(p, current_price, cogs, q_base, eps)
            if gp > best_gp:
                best_price = p
                best_gp = gp
                best_qty = qty
                best_eps = eps

        if best_price == current_price:
            return None

        delta_gp = best_gp - current_gp
        if delta_gp < min_gp_threshold:
            return None

        delta_pct = (best_price - current_price) / current_price * 100

        # коридор ±max_step ограничивает грид всегда; фиксируем, если упёрлись в край
        if best_price == candidates[-1] or best_price == candidates[0]:
            binding_constraints.add("max_step")
        applied = sorted(binding_constraints)

        return {
            "product_id": sku["product_id"],
            "department_id": sku["department_id"],
            "batch_id": batch_id,
            "current_price": current_price,
            "recommended_price": best_price,
            "delta_pct": round(delta_pct, 2),
            "cogs": cogs,
            "current_qty_forecast": round(q_base, 1),
            "new_qty_forecast": round(best_qty, 1),
            "current_gp": round(current_gp, 2),
            "expected_gp": round(best_gp, 2),
            "delta_gp": round(delta_gp, 2),
            "elasticity_used": best_eps,
            "elasticity_grade": sku["elasticity_grade"],
            "menu_role": menu_role,
            "constraints_applied": applied if applied else None,
            "status": "new",
        }

    def _enumerate_candidates(
        self, current_price: float, rules: dict, menu_role: str,
    ) -> list[float]:
        max_step = rules.get("max_step", {}).get("value", 0.05)
        rounding_cfg = rules.get("rounding", {})
        if menu_role in ("premium_anchor", "image_rare"):
            step = rounding_cfg.get("flagship_step", 100)
        else:
            step = rounding_cfg.get("step", 50)

        p_min = current_price * (1 - max_step)
        p_max = current_price * (1 + max_step)

        p_min_r = math.ceil(p_min / step) * step
        p_max_r = math.floor(p_max / step) * step

        candidates = []
        p = p_min_r
        while p <= p_max_r:
            candidates.append(float(p))
            p += step

        if current_price not in candidates:
            candidates.append(current_price)
        candidates.sort()
        return candidates

    def _compute_gp(
        self, price: float, current_price: float,
        cogs: Optional[float], q_base: float, elasticity: float,
    ) -> float:
        _, qty = self._compute_gp_and_qty(price, current_price, cogs, q_base, elasticity)
        unit_cogs = cogs if cogs else 0
        return (price - unit_cogs) * qty

    def _compute_gp_and_qty(
        self, price: float, current_price: float,
        cogs: Optional[float], q_base: float, elasticity: float,
    ) -> tuple[float, float]:
        if current_price <= 0:
            return 0.0, q_base

        ratio = price / current_price
        if ratio <= 0:
            return 0.0, 0.0

        qty = q_base * (ratio ** elasticity)
        qty = max(qty, 0)
        unit_cogs = cogs if cogs else 0
        gp = (price - unit_cogs) * qty
        return gp, qty

    def _insert_recommendation(self, rec: dict) -> None:
        self.db.execute(
            text("""
                INSERT INTO price_recommendation
                    (product_id, department_id, batch_id,
                     current_price, recommended_price, delta_pct,
                     cogs, current_qty_forecast, new_qty_forecast,
                     current_gp, expected_gp, delta_gp,
                     elasticity_used, elasticity_grade, menu_role,
                     constraints_applied, status, rec_type)
                VALUES
                    (:product_id, CAST(:department_id AS uuid), CAST(:batch_id AS uuid),
                     :current_price, :recommended_price, :delta_pct,
                     :cogs, :current_qty_forecast, :new_qty_forecast,
                     :current_gp, :expected_gp, :delta_gp,
                     :elasticity_used, :elasticity_grade, :menu_role,
                     :constraints_applied, :status, :rec_type)
                ON CONFLICT (batch_id, product_id, department_id) DO NOTHING
            """),
            {
                "rec_type": "optimizer",
                **rec,
                "constraints_applied": rec.get("constraints_applied"),
            },
        )

    # ---- №7: управляемые ценовые эксперименты --------------------------------

    def generate_experiments(
        self,
        department_id: str,
        n: int = 10,
        delta_pct: float = 4.0,
        actor: Optional[str] = None,
    ) -> dict:
        """Предложить контролируемые изменения цены для ИЗМЕРЕНИЯ эластичности.

        Кандидаты — grade C/D SKU с большим оборотом (быстрый сигнал), известной
        себестоимостью и без недавних изменений цены. Цена +delta_pct%, округление
        и все бизнес-правила соблюдаются. Рекомендации идут обычным циклом
        approve → applied → outcome; реализованная эластичность из outcome
        улучшает грейд при следующих переоценках.
        """
        from .pricing_audit import log_audit

        batch_id = str(uuid.uuid4())
        skus = self._load_sku_data(department_id)
        experiment_products = self._open_experiment_products(department_id)

        candidates = [
            s for s in skus
            if s["elasticity_grade"] in ("C", "D")
            and s["cogs"] is not None
            and s["product_id"] not in experiment_products
            and (s["last_change_date"] is None
                 or (date.today() - s["last_change_date"]).days >= 28)
        ]
        # больший оборот → быстрее набирается статистика
        candidates.sort(key=lambda s: s["current_price"] * s["avg_daily_qty"], reverse=True)

        created = []
        for sku in candidates:
            if len(created) >= n:
                break

            current_price = sku["current_price"]
            rules = self.rules_service.get_effective_rules(
                sku["product_id"], sku["department_id"], sku.get("segment_type"),
            )
            rounding_cfg = rules.get("rounding") or {}
            step = (rounding_cfg.get("flagship_step", 100)
                    if sku["menu_role"] in ("premium_anchor", "image_rare")
                    else rounding_cfg.get("step", 50))

            target = current_price * (1 + delta_pct / 100.0)
            target = round(target / step) * step
            if target <= current_price:
                target = current_price + step

            is_valid, _ = self.rules_service.check_recommendation(
                current_price, target, sku["cogs"], sku["menu_role"],
                sku.get("last_change_date"), rules,
            )
            if not is_valid:
                continue

            q_base = sku["avg_daily_qty"] * 7
            elasticity = sku["elasticity"]
            current_gp = self._compute_gp(current_price, current_price, sku["cogs"], q_base, elasticity)
            expected_gp, expected_qty = self._compute_gp_and_qty(
                target, current_price, sku["cogs"], q_base, elasticity,
            )

            rec = {
                "product_id": sku["product_id"],
                "department_id": department_id,
                "batch_id": batch_id,
                "current_price": current_price,
                "recommended_price": float(target),
                "delta_pct": round((target - current_price) / current_price * 100, 2),
                "cogs": sku["cogs"],
                "current_qty_forecast": round(q_base, 1),
                "new_qty_forecast": round(expected_qty, 1),
                "current_gp": round(current_gp, 2),
                "expected_gp": round(expected_gp, 2),
                "delta_gp": round(expected_gp - current_gp, 2),
                "elasticity_used": elasticity,
                "elasticity_grade": sku["elasticity_grade"],
                "menu_role": sku["menu_role"],
                "constraints_applied": ["experiment"],
                "status": "new",
                "rec_type": "experiment",
            }
            # эксперимент замещает открытую оптимизаторскую рекомендацию SKU
            self.db.execute(
                text("""
                    UPDATE price_recommendation
                    SET status = 'expired'
                    WHERE status = 'new' AND rec_type = 'optimizer'
                      AND department_id = CAST(:dept_id AS uuid)
                      AND product_id = :pid
                """),
                {"dept_id": department_id, "pid": sku["product_id"]},
            )
            self._insert_recommendation(rec)
            created.append({"product_id": sku["product_id"], "product_name": sku["product_name"],
                            "current_price": current_price, "target_price": float(target)})

        log_audit(self.db, "experiment", batch_id, "generate",
                  actor=actor, department_id=department_id,
                  details={"n_requested": n, "n_created": len(created), "delta_pct": delta_pct})
        self.db.commit()

        logger.info("Experiments for dept %s: %d created of %d candidates",
                    department_id, len(created), len(candidates))
        return {
            "status": "ok",
            "department_id": department_id,
            "batch_id": batch_id,
            "candidates": len(candidates),
            "experiments_created": len(created),
            "items": created,
        }

    def _supersede_open_recommendations(self, department_id: str) -> int:
        """Expire open OPTIMIZER recommendations for the department before a new batch.

        Каждая генерация полностью заменяет открытый список: иначе ежедневные
        батчи копят дубли 'new' на один SKU и summary завышает ΔGP кратно.
        Эксперименты (rec_type='experiment') живут по своему циклу и не трогаются.
        Runs in the same transaction as the inserts (commit at the end).
        """
        result = self.db.execute(
            text("""
                UPDATE price_recommendation
                SET status = 'expired'
                WHERE status = 'new'
                  AND rec_type = 'optimizer'
                  AND department_id = CAST(:dept_id AS uuid)
            """),
            {"dept_id": department_id},
        )
        return result.rowcount

    def _open_experiment_products(self, department_id: str) -> set[int]:
        """SKUs с открытым/идущим экспериментом — оптимизатор их не трогает,
        чтобы не загрязнять измерение."""
        rows = self.db.execute(
            text("""
                SELECT DISTINCT product_id FROM price_recommendation
                WHERE department_id = CAST(:dept_id AS uuid)
                  AND rec_type = 'experiment'
                  AND status IN ('new', 'approved', 'applied')
            """),
            {"dept_id": department_id},
        ).fetchall()
        return {r[0] for r in rows}

    def _pending_review_products(self, department_id: str) -> set[int]:
        """SKUs с pending approved или applied-без-outcome рекомендацией.

        Новая генерация для них создавала вторую живую рекомендацию: менеджер
        мог утвердить оба повышения подряд, а detect_applied помечал applied
        обе — двойной outcome и задвоение summary.
        """
        rows = self.db.execute(
            text("""
                SELECT DISTINCT pr.product_id FROM price_recommendation pr
                WHERE pr.department_id = CAST(:dept_id AS uuid)
                  AND (
                      pr.status = 'approved'
                      OR (pr.status = 'applied' AND NOT EXISTS (
                          SELECT 1 FROM price_recommendation_outcome o
                          WHERE o.recommendation_id = pr.id
                      ))
                  )
            """),
            {"dept_id": department_id},
        ).fetchall()
        return {r[0] for r in rows}

    def _cycle_cap_remaining(self, department_id: str) -> Optional[dict]:
        """Сколько изменений ещё можно утвердить в текущем окне для точки.
        → {'cap', 'window_days', 'used', 'remaining'} или None (правило не задано)."""
        cap_rule = self.rules_service.get_change_cycle_cap(department_id)
        if not cap_rule:
            return None
        used = self.db.execute(
            text("""
                SELECT COUNT(*) FROM price_recommendation
                WHERE department_id = CAST(:dept_id AS uuid)
                  AND status IN ('approved', 'applied')
                  AND reviewed_at >= NOW() - make_interval(days => :window)
            """),
            {"dept_id": department_id, "window": cap_rule["window_days"]},
        ).scalar()
        return {
            "cap": cap_rule["value"],
            "window_days": cap_rule["window_days"],
            "used": used,
            "remaining": max(cap_rule["value"] - used, 0),
        }

    def review_recommendation(
        self, rec_id: int, status: str, reviewer_id: Optional[str] = None,
        comment: Optional[str] = None, actor: Optional[str] = None,
    ) -> dict:
        from .pricing_audit import log_audit

        if status not in ("approved", "rejected"):
            return {"status": "error", "message": "Status must be 'approved' or 'rejected'"}

        # FOR UPDATE: без блокировки конкурентный ревью/супersede между SELECT
        # и UPDATE давал «тихий успех» на 0 строк с фантомной audit-записью
        row = self.db.execute(
            text("""
                SELECT id, department_id::text, product_id, status, created_at,
                       current_price
                FROM price_recommendation WHERE id = :id FOR UPDATE
            """),
            {"id": rec_id},
        ).fetchone()
        if not row:
            self.db.rollback()
            return {"status": "error", "message": f"Recommendation {rec_id} not found"}
        if row.status != "new":
            self.db.rollback()
            return {
                "status": "error",
                "message": f"Recommendation {rec_id} is not in 'new' status (current: {row.status})",
            }
        department_id = row[1]

        if status == "approved":
            revalidation_error = self._revalidate_for_approve(row, department_id)
            if revalidation_error:
                self.db.commit()  # фиксируем возможную авто-экспирацию
                return revalidation_error

            # cap-проверка + UPDATE атомарны только под блокировкой по точке:
            # два конкурентных approve по разным rec'ам совместно пробивали лимит
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('pricing_review:' || :d))"),
                {"d": department_id},
            )
            cap = self._cycle_cap_remaining(department_id)
            if cap and cap["remaining"] < 1:
                self.db.rollback()
                return {
                    "status": "error",
                    "code": "cycle_cap_exceeded",
                    "message": (
                        f"max_changes_per_cycle: уже {cap['used']} утверждённых изменений "
                        f"за {cap['window_days']}д при лимите {cap['cap']}"
                    ),
                }

        result = self.db.execute(
            text("""
                UPDATE price_recommendation
                SET status = :status,
                    reviewed_by = CAST(:reviewer_id AS uuid),
                    reviewed_at = NOW(),
                    review_comment = :comment
                WHERE id = :id AND status = 'new'
            """),
            {"id": rec_id, "status": status, "reviewer_id": reviewer_id, "comment": comment},
        )
        if result.rowcount != 1:
            self.db.rollback()
            return {"status": "error", "message": f"Recommendation {rec_id} was modified concurrently"}
        log_audit(
            self.db, "recommendation", rec_id, status,
            actor=actor or reviewer_id, department_id=department_id,
            details={"comment": comment} if comment else None,
        )
        self.db.commit()
        return {"status": "ok", "recommendation_id": rec_id, "new_status": status}

    def _revalidate_for_approve(self, row, department_id: str) -> Optional[dict]:
        """Правила проверялись только при генерации — на approve базис мог
        устареть. Возвращает error-dict или None (валидно).

        Проверки: TTL рекомендации, актуальность current_price по каталогу,
        stop_list и min_frequency по текущему состоянию правил.
        """
        from datetime import datetime as _dt

        created_at = row.created_at
        age_days = (date.today() - created_at.date()).days if isinstance(created_at, _dt) \
            else (date.today() - created_at).days
        if age_days > APPROVED_TTL_DAYS:
            self.db.execute(
                text("UPDATE price_recommendation SET status = 'expired' WHERE id = :id AND status = 'new'"),
                {"id": row.id},
            )
            from .pricing_audit import log_audit
            log_audit(self.db, "recommendation", row.id, "expired",
                      actor="system", department_id=department_id,
                      details={"reason": f"older than {APPROVED_TTL_DAYS}d at approve"})
            return {
                "status": "error",
                "code": "expired",
                "message": f"Рекомендация старше {APPROVED_TTL_DAYS} дней — истекла, перегенерируйте батч",
            }

        catalog = self.db.execute(
            text("""
                SELECT price, date_from FROM sku_catalog_price
                WHERE department_id = CAST(:dept_id AS uuid)
                  AND product_id = :pid AND price > 0 AND NOT is_stale
                  AND date_from <= CURRENT_DATE AND date_to > CURRENT_DATE
                ORDER BY (price_type <> 'BASE'), (product_size_id IS NOT NULL),
                         product_size_id, id
                LIMIT 1
            """),
            {"dept_id": department_id, "pid": row.product_id},
        ).fetchone()
        if catalog and abs(float(catalog[0]) - float(row.current_price)) > 0.01:
            return {
                "status": "error",
                "code": "stale_price",
                "message": (
                    f"Цена в каталоге ({float(catalog[0]):.0f}) изменилась после генерации "
                    f"(базис {float(row.current_price):.0f}) — перегенерируйте рекомендации"
                ),
            }

        rules = self.rules_service.get_effective_rules(row.product_id, department_id, None)
        if "stop_list" in rules:
            return {
                "status": "error",
                "code": "stop_list",
                "message": "Позиция в стоп-листе (правило добавлено после генерации)",
            }
        r = rules.get("min_frequency")
        last_change = catalog[1] if catalog else None
        if r is not None and last_change is not None:
            min_days = r.get("days", 14)
            days_since = (date.today() - last_change).days
            if days_since < min_days:
                return {
                    "status": "error",
                    "code": "min_frequency",
                    "message": f"Цена менялась {days_since}д назад при лимите частоты {min_days}д",
                }
        return None

    def batch_review(
        self, rec_ids: list[int], status: str, reviewer_id: Optional[str] = None,
        comment: Optional[str] = None, actor: Optional[str] = None,
    ) -> dict:
        from .pricing_audit import log_audit

        if status not in ("approved", "rejected"):
            return {"status": "error", "message": "Status must be 'approved' or 'rejected'"}
        if not rec_ids:
            return {"status": "ok", "updated": 0}

        extra_cond = ""
        if status == "approved":
            # свежесть базиса: протухшие 'new' не утверждаются батчем
            extra_cond = " AND created_at >= NOW() - make_interval(days => :ttl)"
            # лимит изменений за цикл проверяется по каждой затронутой точке
            # под advisory-блокировками (sorted — от deadlock'ов), иначе два
            # параллельных batch-approve совместно пробивали cap
            dept_counts = self.db.execute(
                text(f"""
                    SELECT department_id::text, COUNT(*)
                    FROM price_recommendation
                    WHERE id = ANY(:ids) AND status = 'new'{extra_cond}
                    GROUP BY department_id
                """),
                {"ids": rec_ids, "ttl": APPROVED_TTL_DAYS},
            ).fetchall()
            for dept_id in sorted(d for d, _ in dept_counts):
                self.db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext('pricing_review:' || :d))"),
                    {"d": dept_id},
                )
            for dept_id, n_requested in dept_counts:
                cap = self._cycle_cap_remaining(dept_id)
                if cap and n_requested > cap["remaining"]:
                    self.db.rollback()
                    return {
                        "status": "error",
                        "code": "cycle_cap_exceeded",
                        "department_id": dept_id,
                        "message": (
                            f"max_changes_per_cycle: запрошено {n_requested}, доступно "
                            f"{cap['remaining']} из {cap['cap']} за {cap['window_days']}д"
                        ),
                    }

        result = self.db.execute(
            text(f"""
                UPDATE price_recommendation
                SET status = :status,
                    reviewed_by = CAST(:reviewer_id AS uuid),
                    reviewed_at = NOW(),
                    review_comment = :comment
                WHERE id = ANY(:ids) AND status = 'new'{extra_cond}
                RETURNING id, department_id::text
            """),
            {"status": status, "reviewer_id": reviewer_id, "ids": rec_ids,
             "comment": comment, "ttl": APPROVED_TTL_DAYS},
        )
        updated_rows = result.fetchall()
        for rid, dept_id in updated_rows:
            log_audit(
                self.db, "recommendation", rid, status,
                actor=actor or reviewer_id, department_id=dept_id,
                details={"batch": True, "comment": comment} if comment else {"batch": True},
            )
        self.db.commit()
        return {"status": "ok", "updated": len(updated_rows), "requested": len(rec_ids)}

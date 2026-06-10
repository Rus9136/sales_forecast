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


def select_planning_elasticity(
    mean: float, ci_lower: Optional[float], grade: str,
) -> float:
    """Elasticity used for planning expected qty/GP.

    Grade A/B — точечная оценка надёжна. Grade C/D — оценка в основном
    заимствована (group/global), точечная ε почти не информативна, поэтому
    планируем по консервативному краю CI (наиболее эластичный сценарий):
    завышенные ΔGP от «слепого» prior не проходят порог. Без записи
    эластичности — жёсткий консервативный fallback.
    """
    if grade in ("A", "B"):
        return mean
    if ci_lower is not None:
        return ci_lower
    return min(mean, CONSERVATIVE_FALLBACK_ELASTICITY)


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

        created = 0
        skipped_no_cogs = 0
        for sku in skus:
            try:
                if sku["product_id"] in experiment_products:
                    continue  # идёт эксперимент — не загрязняем измерение
                if sku["cogs"] is None:
                    skipped_no_cogs += 1
                    continue
                rec = self._optimize_single(sku, batch_id, min_gp_threshold, today)
                if rec:
                    self._insert_recommendation(rec)
                    created += 1
            except Exception as e:
                errors.append(f"SKU {sku['product_id']}: {e}")
                logger.warning("Optimization error for SKU %s: %s", sku["product_id"], e)

        self.db.commit()
        logger.info(
            "Optimization for dept %s: %d recommendations from %d SKUs (%d skipped: no COGS)",
            department_id, created, len(skus), skipped_no_cogs,
        )

        return {
            "status": "ok" if not errors else "partial",
            "department_id": department_id,
            "recommendations_created": created,
            "skus_processed": len(skus),
            "skipped_no_cogs": skipped_no_cogs,
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
                    SELECT product_id,
                        ROUND(AVG(price), 2) AS catalog_price,
                        MAX(date_from) AS last_change_date
                    FROM sku_catalog_price
                    WHERE department_id = CAST(:dept_id AS uuid)
                      AND product_id IS NOT NULL
                      AND price > 0
                      AND NOT is_stale
                      AND date_from <= CURRENT_DATE
                      AND date_to > CURRENT_DATE
                    GROUP BY product_id
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
                    d.segment_type
                FROM recent_sales rs
                JOIN product p ON p.id = rs.product_id
                JOIN departments d ON d.id = CAST(:dept_id AS uuid)
                LEFT JOIN catalog_now cn ON cn.product_id = rs.product_id
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
            {"dept_id": department_id, "default_eps": DEFAULT_ELASTICITY},
        ).fetchall()

        skus = []
        for r in rows:
            mean = float(r[5])
            ci_lower = float(r[6]) if r[6] is not None else None
            grade = r[7]
            skus.append({
                "product_id": r[0],
                "product_name": r[1],
                "current_price": float(r[2]),
                "avg_daily_qty": float(r[3]),
                "cogs": float(r[4]) if r[4] is not None else None,
                "elasticity": select_planning_elasticity(mean, ci_lower, grade),
                "elasticity_mean": mean,
                "elasticity_grade": grade,
                "menu_role": r[8],
                "last_change_date": r[9],
                "segment_type": r[10],
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
        elasticity = sku["elasticity"]
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

        best_price = current_price
        best_gp = current_gp
        best_qty = q_base
        binding_constraints: set[str] = set()

        for p in candidates:
            if p == current_price:
                continue

            is_valid, violations = self.rules_service.check_recommendation(
                current_price, p, cogs, menu_role, sku.get("last_change_date"), rules,
            )
            if not is_valid:
                # правила, отсёкшие кандидатов, ограничили пространство поиска
                binding_constraints.update(v.split(":", 1)[0] for v in violations)
                continue

            gp, qty = self._compute_gp_and_qty(p, current_price, cogs, q_base, elasticity)
            if gp > best_gp:
                best_price = p
                best_gp = gp
                best_qty = qty

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
            "elasticity_used": sku["elasticity"],
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
                  department_id=department_id,
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
        comment: Optional[str] = None,
    ) -> dict:
        from .pricing_audit import log_audit

        if status not in ("approved", "rejected"):
            return {"status": "error", "message": "Status must be 'approved' or 'rejected'"}

        row = self.db.execute(
            text("SELECT department_id::text FROM price_recommendation WHERE id = :id AND status = 'new'"),
            {"id": rec_id},
        ).fetchone()
        if not row:
            return {
                "status": "error",
                "message": f"Recommendation {rec_id} not found or not in 'new' status",
            }
        department_id = row[0]

        if status == "approved":
            cap = self._cycle_cap_remaining(department_id)
            if cap and cap["remaining"] < 1:
                return {
                    "status": "error",
                    "code": "cycle_cap_exceeded",
                    "message": (
                        f"max_changes_per_cycle: уже {cap['used']} утверждённых изменений "
                        f"за {cap['window_days']}д при лимите {cap['cap']}"
                    ),
                }

        self.db.execute(
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
        log_audit(
            self.db, "recommendation", rec_id, status,
            actor=reviewer_id, department_id=department_id,
            details={"comment": comment} if comment else None,
        )
        self.db.commit()
        return {"status": "ok", "recommendation_id": rec_id, "new_status": status}

    def batch_review(
        self, rec_ids: list[int], status: str, reviewer_id: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> dict:
        from .pricing_audit import log_audit

        if status not in ("approved", "rejected"):
            return {"status": "error", "message": "Status must be 'approved' or 'rejected'"}
        if not rec_ids:
            return {"status": "ok", "updated": 0}

        if status == "approved":
            # лимит изменений за цикл проверяется по каждой затронутой точке
            dept_counts = self.db.execute(
                text("""
                    SELECT department_id::text, COUNT(*)
                    FROM price_recommendation
                    WHERE id = ANY(:ids) AND status = 'new'
                    GROUP BY department_id
                """),
                {"ids": rec_ids},
            ).fetchall()
            for dept_id, n_requested in dept_counts:
                cap = self._cycle_cap_remaining(dept_id)
                if cap and n_requested > cap["remaining"]:
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
            text("""
                UPDATE price_recommendation
                SET status = :status,
                    reviewed_by = CAST(:reviewer_id AS uuid),
                    reviewed_at = NOW(),
                    review_comment = :comment
                WHERE id = ANY(:ids) AND status = 'new'
                RETURNING id, department_id::text
            """),
            {"status": status, "reviewer_id": reviewer_id, "ids": rec_ids, "comment": comment},
        )
        updated_rows = result.fetchall()
        for rid, dept_id in updated_rows:
            log_audit(
                self.db, "recommendation", rid, status,
                actor=reviewer_id, department_id=dept_id,
                details={"batch": True, "comment": comment} if comment else {"batch": True},
            )
        self.db.commit()
        return {"status": "ok", "updated": len(updated_rows), "requested": len(rec_ids)}

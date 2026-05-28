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

        self._expire_old_recommendations(department_id)

        created = 0
        for sku in skus:
            try:
                rec = self._optimize_single(sku, batch_id, min_gp_threshold, today)
                if rec:
                    self._insert_recommendation(rec)
                    created += 1
            except Exception as e:
                errors.append(f"SKU {sku['product_id']}: {e}")
                logger.warning("Optimization error for SKU %s: %s", sku["product_id"], e)

        self.db.commit()
        logger.info(
            "Optimization for dept %s: %d recommendations from %d SKUs",
            department_id, created, len(skus),
        )

        return {
            "status": "ok" if not errors else "partial",
            "department_id": department_id,
            "recommendations_created": created,
            "skus_processed": len(skus),
            "batch_id": batch_id,
            "errors": errors,
        }

    def _load_sku_data(self, department_id: str) -> list[dict]:
        """Load current price, COGS, elasticity, role, base qty for active SKUs."""
        rows = self.db.execute(
            text("""
                WITH recent_sales AS (
                    SELECT product_id,
                        ROUND(SUM(total_sum) / NULLIF(SUM(total_qty), 0), 2) AS current_price,
                        ROUND(SUM(total_qty) / COUNT(DISTINCT sale_date), 1) AS avg_daily_qty
                    FROM sku_daily_sales
                    WHERE department_id = CAST(:dept_id AS uuid)
                      AND sale_date >= CURRENT_DATE - 30
                      AND total_qty > 0
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
                ),
                last_change AS (
                    SELECT product_id,
                        MAX(first_seen_date) AS last_change_date
                    FROM sku_price_history
                    WHERE department_id = CAST(:dept_id AS uuid)
                      AND prev_price IS NOT NULL
                    GROUP BY product_id
                )
                SELECT
                    rs.product_id,
                    p.name AS product_name,
                    rs.current_price,
                    rs.avg_daily_qty,
                    rc.unit_cogs,
                    COALESCE(se.elasticity_mean, -0.5) AS elasticity,
                    COALESCE(se.reliability_grade, 'D') AS elasticity_grade,
                    COALESCE(smr.effective_role, 'unknown') AS menu_role,
                    lc.last_change_date,
                    d.segment_type
                FROM recent_sales rs
                JOIN product p ON p.id = rs.product_id
                JOIN departments d ON d.id = CAST(:dept_id AS uuid)
                LEFT JOIN recent_cost rc ON rc.product_id = rs.product_id
                LEFT JOIN sku_elasticity se
                    ON se.product_id = rs.product_id
                    AND se.department_id = CAST(:dept_id AS uuid)
                LEFT JOIN sku_menu_role smr
                    ON smr.product_id = rs.product_id
                    AND smr.department_id = CAST(:dept_id AS uuid)
                LEFT JOIN last_change lc ON lc.product_id = rs.product_id
                WHERE rs.current_price > 0
                ORDER BY rs.current_price * rs.avg_daily_qty DESC
            """),
            {"dept_id": department_id},
        ).fetchall()

        return [
            {
                "product_id": r[0],
                "product_name": r[1],
                "current_price": float(r[2]),
                "avg_daily_qty": float(r[3]),
                "cogs": float(r[4]) if r[4] else None,
                "elasticity": float(r[5]),
                "elasticity_grade": r[6],
                "menu_role": r[7],
                "last_change_date": r[8],
                "segment_type": r[9],
                "department_id": department_id,
            }
            for r in rows
        ]

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
        best_constraints: list[str] = []

        for p in candidates:
            if p == current_price:
                continue

            is_valid, violations = self.rules_service.check_recommendation(
                current_price, p, cogs, menu_role, sku.get("last_change_date"), rules,
            )
            if not is_valid:
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

        _, applied = self.rules_service.check_recommendation(
            current_price, best_price, cogs, menu_role, sku.get("last_change_date"), rules,
        )

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
        import json
        self.db.execute(
            text("""
                INSERT INTO price_recommendation
                    (product_id, department_id, batch_id,
                     current_price, recommended_price, delta_pct,
                     cogs, current_qty_forecast, new_qty_forecast,
                     current_gp, expected_gp, delta_gp,
                     elasticity_used, elasticity_grade, menu_role,
                     constraints_applied, status)
                VALUES
                    (:product_id, CAST(:department_id AS uuid), CAST(:batch_id AS uuid),
                     :current_price, :recommended_price, :delta_pct,
                     :cogs, :current_qty_forecast, :new_qty_forecast,
                     :current_gp, :expected_gp, :delta_gp,
                     :elasticity_used, :elasticity_grade, :menu_role,
                     :constraints_applied, :status)
                ON CONFLICT (batch_id, product_id, department_id) DO NOTHING
            """),
            {
                **rec,
                "constraints_applied": rec.get("constraints_applied"),
            },
        )

    def _expire_old_recommendations(self, department_id: str) -> int:
        result = self.db.execute(
            text("""
                UPDATE price_recommendation
                SET status = 'expired'
                WHERE status = 'new'
                  AND department_id = CAST(:dept_id AS uuid)
                  AND created_at < NOW() - INTERVAL '14 days'
            """),
            {"dept_id": department_id},
        )
        return result.rowcount

    def review_recommendation(
        self, rec_id: int, status: str, reviewer_id: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> dict:
        if status not in ("approved", "rejected"):
            return {"status": "error", "message": "Status must be 'approved' or 'rejected'"}

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
        self.db.commit()
        return {"status": "ok", "recommendation_id": rec_id, "new_status": status}

    def batch_review(
        self, rec_ids: list[int], status: str, reviewer_id: Optional[str] = None,
    ) -> dict:
        if not rec_ids:
            return {"status": "ok", "updated": 0}

        self.db.execute(
            text("""
                UPDATE price_recommendation
                SET status = :status,
                    reviewed_by = CAST(:reviewer_id AS uuid),
                    reviewed_at = NOW()
                WHERE id = ANY(:ids) AND status = 'new'
            """),
            {"status": status, "reviewer_id": reviewer_id, "ids": rec_ids},
        )
        self.db.commit()
        return {"status": "ok", "updated": len(rec_ids)}

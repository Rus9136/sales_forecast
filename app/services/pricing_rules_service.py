"""B4: Configurable pricing rules with scope cascade."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VALID_RULE_TYPES = {
    "min_margin", "max_step", "min_frequency", "no_decrease_anchor",
    "min_competitive_idx", "rounding", "no_psychological", "stop_list",
}

PREMIUM_ROLES = {"premium_anchor", "image_rare"}


class PricingRulesService:
    def __init__(self, db: Session):
        self.db = db

    def get_effective_rules(
        self,
        product_id: int,
        department_id: str,
        segment_type: Optional[str] = None,
    ) -> dict[str, dict[str, Any]]:
        """Resolve all rules for a SKU. Cascade: product → department → segment → global."""
        today = date.today()
        rows = self.db.execute(
            text("""
                SELECT rule_type, scope_type, scope_id, params
                FROM pricing_rule
                WHERE is_active = true
                  AND effective_from <= :today
                  AND (effective_to IS NULL OR effective_to >= :today)
                  AND (
                      (scope_type = 'global' AND scope_id IS NULL)
                      OR (scope_type = 'segment' AND scope_id = :segment)
                      OR (scope_type = 'department' AND scope_id = :dept_id)
                      OR (scope_type = 'product' AND scope_id = :product_id_str)
                  )
                ORDER BY
                    CASE scope_type
                        WHEN 'product' THEN 1
                        WHEN 'department' THEN 2
                        WHEN 'segment' THEN 3
                        WHEN 'global' THEN 4
                    END,
                    id
            """),
            {
                "today": today,
                "segment": segment_type or "",
                "dept_id": str(department_id),
                "product_id_str": str(product_id),
            },
        ).fetchall()

        effective: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row[0] not in effective:
                effective[row[0]] = row[3]
        return effective

    def check_recommendation(
        self,
        current_price: float,
        candidate_price: float,
        cogs: Optional[float],
        menu_role: Optional[str],
        last_change_date: Optional[date],
        rules: dict[str, dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        """Check a candidate price against all rules. Returns (is_valid, violations)."""
        violations: list[str] = []

        # Rule 1: min_margin
        r = rules.get("min_margin")
        if r and cogs is not None and candidate_price > 0:
            min_margin = r.get("value", 0.60)
            margin = (candidate_price - cogs) / candidate_price
            if margin < min_margin:
                violations.append(f"min_margin: {margin:.2%} < {min_margin:.0%}")

        # Rule 2: max_step
        r = rules.get("max_step")
        if r and current_price > 0:
            max_step = r.get("value", 0.05)
            step = abs(candidate_price - current_price) / current_price
            if step > max_step:
                violations.append(f"max_step: {step:.2%} > {max_step:.0%}")

        # Rule 3: min_frequency
        r = rules.get("min_frequency")
        if r and last_change_date:
            days_since = (date.today() - last_change_date).days
            min_days = r.get("days", 14)
            if days_since < min_days:
                violations.append(f"min_frequency: {days_since}d < {min_days}d")

        # Rule 4: no_decrease_anchor
        r = rules.get("no_decrease_anchor")
        if r and r.get("enabled", True) and menu_role == "premium_anchor":
            if candidate_price < current_price:
                violations.append("no_decrease_anchor: price decrease on premium_anchor")

        # Rule 5: min_competitive_idx — skip in Phase 1 (no competitor data)

        # Rule 6: rounding
        r = rules.get("rounding")
        if r:
            step = r.get("flagship_step", 100) if menu_role in PREMIUM_ROLES else r.get("step", 50)
            if candidate_price % step != 0:
                violations.append(f"rounding: {candidate_price} not divisible by {step}")

        # Rule 7: no_psychological
        r = rules.get("no_psychological")
        if r and r.get("enabled", True) and menu_role in PREMIUM_ROLES:
            endings = r.get("endings", [9, 99])
            last_digits = int(candidate_price) % 100
            if last_digits in endings:
                violations.append(f"no_psychological: ending {last_digits} on {menu_role}")

        # Rule 8: stop_list
        r = rules.get("stop_list")
        if r:
            if candidate_price != current_price:
                violations.append("stop_list: price change blocked")

        return (len(violations) == 0, violations)

    def list_rules(
        self,
        rule_type: Optional[str] = None,
        scope_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> list[dict]:
        conditions = ["1=1"]
        params: dict[str, Any] = {}
        if rule_type:
            conditions.append("rule_type = :rule_type")
            params["rule_type"] = rule_type
        if scope_type:
            conditions.append("scope_type = :scope_type")
            params["scope_type"] = scope_type
        if is_active is not None:
            conditions.append("is_active = :is_active")
            params["is_active"] = is_active

        rows = self.db.execute(
            text(f"""
                SELECT id, rule_type, scope_type, scope_id, params,
                       is_active, configured_by_role, effective_from, effective_to
                FROM pricing_rule
                WHERE {' AND '.join(conditions)}
                ORDER BY rule_type, scope_type
            """),
            params,
        ).fetchall()

        return [
            {
                "id": r[0], "rule_type": r[1], "scope_type": r[2],
                "scope_id": r[3], "params": r[4], "is_active": r[5],
                "configured_by_role": r[6], "effective_from": r[7],
                "effective_to": r[8],
            }
            for r in rows
        ]

    def create_rule(self, data: dict) -> dict:
        if data["rule_type"] not in VALID_RULE_TYPES:
            raise ValueError(
                f"Invalid rule_type '{data['rule_type']}'. "
                f"Must be one of: {', '.join(sorted(VALID_RULE_TYPES))}"
            )
        self.db.execute(
            text("""
                INSERT INTO pricing_rule
                    (rule_type, scope_type, scope_id, params, configured_by_role,
                     effective_from, effective_to)
                VALUES (:rule_type, :scope_type, :scope_id, CAST(:params AS jsonb),
                        :configured_by_role, COALESCE(:effective_from, CURRENT_DATE),
                        :effective_to)
            """),
            {
                "rule_type": data["rule_type"],
                "scope_type": data["scope_type"],
                "scope_id": data.get("scope_id"),
                "params": __import__("json").dumps(data["params"]),
                "configured_by_role": data.get("configured_by_role"),
                "effective_from": data.get("effective_from"),
                "effective_to": data.get("effective_to"),
            },
        )
        self.db.commit()
        return {"status": "ok"}

    def update_rule(self, rule_id: int, data: dict) -> dict:
        sets = ["updated_at = NOW()"]
        params: dict[str, Any] = {"id": rule_id}
        if "params" in data and data["params"] is not None:
            sets.append("params = CAST(:params AS jsonb)")
            params["params"] = __import__("json").dumps(data["params"])
        if "is_active" in data and data["is_active"] is not None:
            sets.append("is_active = :is_active")
            params["is_active"] = data["is_active"]
        if "effective_from" in data and data["effective_from"] is not None:
            sets.append("effective_from = :effective_from")
            params["effective_from"] = data["effective_from"]
        if "effective_to" in data and data["effective_to"] is not None:
            sets.append("effective_to = :effective_to")
            params["effective_to"] = data["effective_to"]

        self.db.execute(
            text(f"UPDATE pricing_rule SET {', '.join(sets)} WHERE id = :id"),
            params,
        )
        self.db.commit()
        return {"status": "ok"}

    def delete_rule(self, rule_id: int) -> dict:
        # Hard delete: soft-deleted строки блокировали повторное создание
        # правила через UNIQUE (rule_type, scope_type, scope_id).
        result = self.db.execute(
            text("DELETE FROM pricing_rule WHERE id = :id"),
            {"id": rule_id},
        )
        self.db.commit()
        if result.rowcount == 0:
            return {"status": "error", "message": f"Rule {rule_id} not found"}
        return {"status": "ok"}

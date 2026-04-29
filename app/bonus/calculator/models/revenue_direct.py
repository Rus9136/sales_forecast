from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...schemas.calc_configs import RevenueDirectConfig
from ...utils.decimal_utils import round_money, to_decimal
from ..base import BaseBonusModel
from ..context import CalculationContext
from ..registry import register_model
from ..result import BonusBreakdown, BonusResult


@register_model("revenue_direct")
class RevenueDirectModel(BaseBonusModel):
    """Revenue × fixed rate (no KPI, no grade). Used for: Кассир, Старший бариста."""

    def validate_config(self, config: dict[str, Any]) -> None:
        RevenueDirectConfig.model_validate(config)

    def calculate(self, config: dict[str, Any], context: CalculationContext) -> BonusResult:
        breakdown = BonusBreakdown()

        revenue_source = config["revenue_source"]
        revenue = to_decimal(context.revenue_values.get(revenue_source, 0))
        rate = to_decimal(config["rate"])
        breakdown.add("revenue_fetched", source=revenue_source, value=str(revenue))
        breakdown.add("rate", rate=str(rate))

        applied_proration = False
        if config.get("apply_shifts_proration", False):
            worked = context.shifts.worked
            norm = context.shifts.norm
            formula = config.get("shifts_proration_formula", "ratio")
            if formula == "norm_then_actual":
                # revenue / norm × worked × rate
                if norm > 0:
                    bonus = revenue / norm * worked * rate
                else:
                    bonus = Decimal(0)
            else:
                # revenue × rate × ratio
                bonus = revenue * rate * context.shifts.ratio
            applied_proration = True
            breakdown.add("shifts_proration", formula=formula,
                          worked=str(worked), norm=str(norm),
                          bonus_after=str(bonus))
        else:
            bonus = revenue * rate
            breakdown.add("formula", expression="revenue × rate", bonus=str(bonus))

        final = round_money(bonus)
        breakdown.add("final", final_bonus=str(final))

        return BonusResult(
            base_bonus=bonus,
            final_bonus=final,
            breakdown=breakdown,
            applied_coefficient=rate,
            coefficient_type="percent",
            revenue_used=revenue,
            revenue_source_used=revenue_source,
            shifts_worked=context.shifts.worked if applied_proration else None,
            shifts_norm=context.shifts.norm if applied_proration else None,
            shifts_proration_applied=applied_proration,
        )

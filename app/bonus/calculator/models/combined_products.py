from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...schemas.calc_configs import CombinedProductsConfig
from ...utils.decimal_utils import round_money, to_decimal
from ..base import BaseBonusModel
from ..context import CalculationContext
from ..registry import register_model
from ..result import BonusBreakdown, BonusResult


@register_model("combined_products")
class CombinedProductsModel(BaseBonusModel):
    """Sum of (component_revenue × component_rate). Used for: Бариста."""

    def validate_config(self, config: dict[str, Any]) -> None:
        CombinedProductsConfig.model_validate(config)

    def calculate(self, config: dict[str, Any], context: CalculationContext) -> BonusResult:
        breakdown = BonusBreakdown()
        components = config["components"]
        total = Decimal(0)
        component_details = []

        for comp in components:
            source = comp["source"]
            rate = to_decimal(comp["rate"])
            revenue = to_decimal(context.revenue_values.get(source, 0))
            part = revenue * rate
            total += part
            component_details.append({
                "code": comp["code"],
                "name": comp["name"],
                "source": source,
                "revenue": str(revenue),
                "rate": str(rate),
                "part": str(part),
            })
        breakdown.add("components", items=component_details, total_before_proration=str(total))

        applied_proration = False
        if config.get("apply_shifts_proration", False):
            ratio = context.shifts.ratio
            total = total * ratio
            applied_proration = True
            breakdown.add("shifts_proration",
                          worked=str(context.shifts.worked), norm=str(context.shifts.norm),
                          ratio=str(ratio), bonus_after=str(total))

        final = round_money(total)
        breakdown.add("final", final_bonus=str(final))

        return BonusResult(
            base_bonus=total,
            final_bonus=final,
            breakdown=breakdown,
            coefficient_type="percent",
            shifts_worked=context.shifts.worked if applied_proration else None,
            shifts_norm=context.shifts.norm if applied_proration else None,
            shifts_proration_applied=applied_proration,
        )

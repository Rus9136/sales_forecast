from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...schemas.calc_configs import RevenuePercentByKpiConfig
from ...utils.decimal_utils import round_money, to_decimal
from ..base import BaseBonusModel
from ..context import CalculationContext
from ..grading import find_grade, parse_grades
from ..kpi_engine import overall_kpi
from ..registry import register_model
from ..result import BonusBreakdown, BonusResult


@register_model("revenue_percent_by_kpi")
class RevenuePercentByKpiModel(BaseBonusModel):
    """KPI → grade(rate) → revenue × rate. Used for: Менеджер, Официант."""

    def validate_config(self, config: dict[str, Any]) -> None:
        RevenuePercentByKpiConfig.model_validate(config)

    def calculate(self, config: dict[str, Any], context: CalculationContext) -> BonusResult:
        breakdown = BonusBreakdown()
        kpi_codes = [k["code"] for k in config["kpis"]]
        kpi_percents = []
        kpi_snapshot = []

        for code in kpi_codes:
            fact = context.kpi_values.get(code)
            if fact is None:
                kpi_percents.append(Decimal(0))
                kpi_snapshot.append({"code": code, "missing": True, "percent": "0"})
                continue
            kpi_percents.append(fact.percent)
            kpi_snapshot.append({
                "code": code,
                "fact": str(fact.fact) if fact.fact is not None else None,
                "target": str(fact.target) if fact.target is not None else None,
                "percent": str(fact.percent),
                "direction": fact.direction,
            })

        overall = overall_kpi(kpi_percents)
        breakdown.add("kpi_overall", percent=str(overall), kpis=kpi_snapshot)

        revenue_source = config["revenue_source"]
        revenue = to_decimal(context.revenue_values.get(revenue_source, 0))
        breakdown.add("revenue_fetched", source=revenue_source, value=str(revenue))

        grades = parse_grades(config["grades"])
        grade = find_grade(grades, overall)

        if grade is None:
            breakdown.add("below_threshold", overall=str(overall),
                          min_grade=str(grades[0].from_percent) if grades else None)
            return BonusResult(
                base_bonus=Decimal(0),
                final_bonus=Decimal(0),
                breakdown=breakdown,
                overall_kpi_percent=overall,
                revenue_used=revenue,
                revenue_source_used=revenue_source,
                coefficient_type="percent",
                kpi_values_snapshot=kpi_snapshot,
                is_zero_reason="kpi_below_min_grade",
            )

        rate = to_decimal(grade.rate)
        bonus = revenue * rate
        breakdown.add("grade_resolved",
                      grade_from=str(grade.from_percent), grade_to=str(grade.to_percent),
                      rate=str(rate), bonus_before_proration=str(bonus))

        applied_proration = False
        if config.get("apply_shifts_proration", False):
            ratio = context.shifts.ratio
            bonus = bonus * ratio
            applied_proration = True
            breakdown.add("shifts_proration",
                          worked=str(context.shifts.worked), norm=str(context.shifts.norm),
                          ratio=str(ratio), bonus_after=str(bonus))

        final = round_money(bonus)
        breakdown.add("final", final_bonus=str(final))

        return BonusResult(
            base_bonus=bonus,
            final_bonus=final,
            breakdown=breakdown,
            overall_kpi_percent=overall,
            applied_grade_from=grade.from_percent,
            applied_grade_to=grade.to_percent,
            applied_coefficient=rate,
            coefficient_type="percent",
            revenue_used=revenue,
            revenue_source_used=revenue_source,
            shifts_worked=context.shifts.worked if applied_proration else None,
            shifts_norm=context.shifts.norm if applied_proration else None,
            shifts_proration_applied=applied_proration,
            kpi_values_snapshot=kpi_snapshot,
        )

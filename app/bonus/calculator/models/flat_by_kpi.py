from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...schemas.calc_configs import FlatByKpiConfig
from ...utils.decimal_utils import round_money, to_decimal
from ..base import BaseBonusModel
from ..context import CalculationContext
from ..grading import find_grade, parse_grades
from ..kpi_engine import overall_kpi
from ..registry import register_model
from ..result import BonusBreakdown, BonusResult


@register_model("flat_by_kpi")
class FlatByKpiModel(BaseBonusModel):
    """KPI → grade → fixed sum (in tenge).

    Used for: Управляющий.
    """

    def validate_config(self, config: dict[str, Any]) -> None:
        FlatByKpiConfig.model_validate(config)

    def calculate(self, config: dict[str, Any], context: CalculationContext) -> BonusResult:
        breakdown = BonusBreakdown()
        kpi_codes = [k["code"] for k in config["kpis"]]
        kpi_percents = []
        kpi_snapshot = []

        for code in kpi_codes:
            fact = context.kpi_values.get(code)
            if fact is None:
                # Missing KPI is treated as 0% (depresses average)
                kpi_percents.append(Decimal(0))
                kpi_snapshot.append({
                    "code": code, "fact": None, "target": None,
                    "percent": "0", "missing": True,
                })
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

        grades = parse_grades(config["grades"])
        grade = find_grade(grades, overall)

        if grade is None:
            below = to_decimal(config.get("below_threshold_bonus", 0))
            breakdown.add("below_threshold", overall=str(overall),
                          min_grade=str(grades[0].from_percent) if grades else None,
                          bonus=str(below))
            return BonusResult(
                base_bonus=below,
                final_bonus=round_money(below),
                breakdown=breakdown,
                overall_kpi_percent=overall,
                coefficient_type="fixed_amount",
                applied_coefficient=below,
                kpi_values_snapshot=kpi_snapshot,
                is_zero_reason="kpi_below_min_grade",
            )

        base = to_decimal(grade.value)
        breakdown.add("grade_resolved",
                      grade_from=str(grade.from_percent), grade_to=str(grade.to_percent),
                      value=str(base))

        bonus = base
        applied_proration = False
        if config.get("apply_shifts_proration", False):
            ratio = context.shifts.ratio
            bonus = bonus * ratio
            applied_proration = True
            breakdown.add("shifts_proration",
                          worked=str(context.shifts.worked), norm=str(context.shifts.norm),
                          ratio=str(ratio), bonus_after=str(bonus))

        final = round_money(bonus)
        breakdown.add("final", base_bonus=str(base), final_bonus=str(final))

        return BonusResult(
            base_bonus=base,
            final_bonus=final,
            breakdown=breakdown,
            overall_kpi_percent=overall,
            applied_grade_from=grade.from_percent,
            applied_grade_to=grade.to_percent,
            applied_coefficient=base,
            coefficient_type="fixed_amount",
            shifts_worked=context.shifts.worked if applied_proration else None,
            shifts_norm=context.shifts.norm if applied_proration else None,
            shifts_proration_applied=applied_proration,
            kpi_values_snapshot=kpi_snapshot,
        )

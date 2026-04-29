from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...schemas.calc_configs import TeamRevenueByKpiConfig
from ...utils.decimal_utils import round_money, to_decimal
from ..base import BaseBonusModel
from ..context import CalculationContext
from ..grading import find_grade, parse_grades
from ..kpi_engine import overall_kpi
from ..registry import register_model
from ..result import BonusBreakdown, BonusResult


@register_model("team_revenue_by_kpi")
class TeamRevenueByKpiModel(BaseBonusModel):
    """Collective KITCHEN model.

    Per-employee bonus = revenue × slot_weight × shifts_ratio  (gated by KPI threshold).

    The team-level KPI overall % only acts as a *gate*: if it's below the
    minimum grade, the bonus is zero for everyone in the team. Distribution
    among slots is done by `team_position.distribution_weight` (already in DB).
    """

    def validate_config(self, config: dict[str, Any]) -> None:
        TeamRevenueByKpiConfig.model_validate(config)

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

        grades = parse_grades(config["grades"])
        grade = find_grade(grades, overall)
        revenue_source = config["revenue_source"]
        revenue = to_decimal(context.revenue_values.get(revenue_source, 0))
        breakdown.add("revenue_fetched", source=revenue_source, value=str(revenue))

        # Probation guard
        if config.get("exclude_probation_period", True) and context.employment_type == "probation":
            breakdown.add("probation_excluded", probation_until=str(context.probation_until))
            return BonusResult(
                base_bonus=Decimal(0),
                final_bonus=Decimal(0),
                breakdown=breakdown,
                overall_kpi_percent=overall,
                revenue_used=revenue,
                revenue_source_used=revenue_source,
                kpi_values_snapshot=kpi_snapshot,
                is_zero_reason="probation_period",
            )

        # KPI threshold gate
        if grade is None and config.get("below_threshold_bonus_zero", True):
            breakdown.add("below_threshold", overall=str(overall),
                          min_grade=str(grades[0].from_percent) if grades else None)
            return BonusResult(
                base_bonus=Decimal(0),
                final_bonus=Decimal(0),
                breakdown=breakdown,
                overall_kpi_percent=overall,
                revenue_used=revenue,
                revenue_source_used=revenue_source,
                kpi_values_snapshot=kpi_snapshot,
                is_zero_reason="team_kpi_below_min_grade",
            )

        slot_weight = to_decimal(context.team_position_weight or 0)
        ratio = context.shifts.ratio if config.get("apply_shifts_proration", True) else Decimal(1)

        bonus = revenue * slot_weight * ratio
        breakdown.add(
            "distribution",
            slot=context.team_position_slot,
            slot_weight=str(slot_weight),
            shifts_worked=str(context.shifts.worked),
            shifts_norm=str(context.shifts.norm),
            shifts_ratio=str(ratio),
            bonus_before_round=str(bonus),
        )

        final = round_money(bonus)
        breakdown.add("final", final_bonus=str(final))

        return BonusResult(
            base_bonus=bonus,
            final_bonus=final,
            breakdown=breakdown,
            overall_kpi_percent=overall,
            applied_grade_from=grade.from_percent if grade else None,
            applied_grade_to=grade.to_percent if grade else None,
            applied_coefficient=slot_weight,
            coefficient_type="percent",
            revenue_used=revenue,
            revenue_source_used=revenue_source,
            shifts_worked=context.shifts.worked,
            shifts_norm=context.shifts.norm,
            shifts_proration_applied=config.get("apply_shifts_proration", True),
            kpi_values_snapshot=kpi_snapshot,
        )

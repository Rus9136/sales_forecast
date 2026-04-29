from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .common import KpiConfig, RateGrade


class TeamRevenueByKpiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "team_revenue_by_kpi"
    kpis: list[KpiConfig]
    revenue_source: str
    grades: list[RateGrade]
    below_threshold_bonus_zero: bool = True
    distribution_formula: Literal[
        "revenue * slot_weight * shifts_ratio",
        "revenue * grade_rate * slot_share * shifts_ratio",
    ] = "revenue * slot_weight * shifts_ratio"
    apply_shifts_proration: bool = True
    exclude_probation_period: bool = True
    exclude_violators: bool = False

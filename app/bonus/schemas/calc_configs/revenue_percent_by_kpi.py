from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .common import KpiConfig, RateGrade


class RevenuePercentByKpiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "revenue_percent_by_kpi"
    kpis: list[KpiConfig]
    revenue_source: str
    grades: list[RateGrade]
    apply_shifts_proration: bool = False
    only_worked_days: bool = False

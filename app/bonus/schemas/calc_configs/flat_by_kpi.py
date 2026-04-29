from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .common import KpiConfig, FlatGrade


class FlatByKpiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "flat_by_kpi"
    kpis: list[KpiConfig]
    grades: list[FlatGrade]
    below_threshold_bonus: Decimal = Decimal(0)
    apply_shifts_proration: bool = False

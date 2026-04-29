from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RevenueDirectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "revenue_direct"
    revenue_source: str
    rate: Decimal
    apply_shifts_proration: bool = False
    # Two ways to apply proration:
    #   "ratio"             — bonus = revenue × rate × (worked / norm)
    #   "norm_then_actual"  — bonus = revenue / norm × worked × rate
    # Both yield identical results mathematically but stored as documentation.
    shifts_proration_formula: Literal["ratio", "norm_then_actual"] = "ratio"

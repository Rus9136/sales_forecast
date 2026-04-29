from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class KpiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    source: str
    direction: Literal["higher_is_better", "lower_is_better", "binary"]
    target: Optional[Decimal] = None
    target_metric: Optional[str] = None
    cap_at_100: bool = True
    weight: Decimal = Decimal(1)


class FlatGrade(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: Decimal = Field(..., alias="from")
    to: Decimal
    value: Decimal


class RateGrade(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: Decimal = Field(..., alias="from")
    to: Decimal
    rate: Decimal

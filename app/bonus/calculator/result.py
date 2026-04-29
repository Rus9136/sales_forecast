from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional


@dataclass
class BonusBreakdown:
    """Step-by-step explanation of how the bonus was computed (for audit/UI)."""
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add(self, label: str, **values: Any) -> None:
        self.steps.append({"label": label, **values})

    def to_dict(self) -> dict[str, Any]:
        return {"steps": self.steps}


@dataclass
class BonusResult:
    base_bonus: Decimal
    final_bonus: Decimal
    breakdown: BonusBreakdown

    overall_kpi_percent: Optional[Decimal] = None
    applied_grade_from: Optional[Decimal] = None
    applied_grade_to: Optional[Decimal] = None
    applied_coefficient: Optional[Decimal] = None
    coefficient_type: Optional[str] = None  # 'fixed_amount' | 'percent' | None

    revenue_used: Optional[Decimal] = None
    revenue_source_used: Optional[str] = None
    shifts_worked: Optional[Decimal] = None
    shifts_norm: Optional[Decimal] = None
    shifts_proration_applied: bool = False

    kpi_values_snapshot: list[dict[str, Any]] = field(default_factory=list)
    is_zero_reason: Optional[str] = None

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from ..utils.period import PeriodKey


@dataclass
class KpiFact:
    """Single KPI snapshot."""
    code: str
    fact: Optional[Decimal]
    target: Optional[Decimal]
    percent: Decimal
    direction: str
    weight: Decimal = Decimal(1)


@dataclass
class ShiftStats:
    worked: Decimal
    norm: Decimal

    @property
    def ratio(self) -> Decimal:
        if self.norm <= 0:
            return Decimal(0)
        return self.worked / self.norm


@dataclass
class CalculationContext:
    """Pre-loaded data needed to compute a bonus.

    Calculator models read everything they need from this context — they do
    not call data sources or the DB directly.
    """
    period: PeriodKey
    department_id: str
    department_name: str
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    team_id: Optional[int] = None
    team_position_slot: Optional[str] = None
    team_position_weight: Optional[Decimal] = None
    employment_type: str = "permanent"
    probation_until: Optional[date] = None

    kpi_values: dict[str, KpiFact] = field(default_factory=dict)
    revenue_values: dict[str, Decimal] = field(default_factory=dict)
    shifts: ShiftStats = field(default_factory=lambda: ShiftStats(worked=Decimal(0), norm=Decimal(22)))
    monthly_plans: dict[str, Decimal] = field(default_factory=dict)

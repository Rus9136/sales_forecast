from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..utils.period import PeriodKey


@dataclass
class DataSourceParams:
    """Parameters passed to a data source. Not all sources use every field."""
    period: PeriodKey
    department_id: Optional[str] = None
    employee_id: Optional[str] = None
    extras: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.extras is None:
            self.extras = {}


class BonusDataSource(ABC):
    """Base class for any bonus data source (real or mock).

    Implementations receive a SQLAlchemy session if they need DB access; mock
    sources can ignore it.

    Metadata fields (name/description/value_type/unit/category/is_stub) are
    surfaced via GET /api/bonus/config/data-sources so the UI can render
    human-readable dropdowns instead of raw codes.
    """

    code: str = ""

    # Human-readable metadata (used by the UI scheme editor)
    name: str = ""
    description: str = ""
    # What the source returns. Drives UI grouping/validation:
    #   "revenue"     — Decimal in KZT, used as revenue_source
    #   "kpi_percent" — Decimal, % of target (auto-comparable in KPI direction)
    #   "kpi_value"   — Decimal, raw value (rating, count) — needs explicit target
    #   "shifts"      — ShiftStats object
    value_type: str = ""
    unit: str = ""           # "KZT" | "%" | "count" | "stars" | "shifts"
    category: str = ""       # iiko_location | iiko_personal | iiko_plan | iiko_products | manual | crm | hr | tco
    is_stub: bool = False    # True = returns mock data; UI shows a warning badge

    @classmethod
    def metadata(cls) -> dict:
        """Return a serialisable metadata dict for the API."""
        return {
            "code": cls.code,
            "name": cls.name or cls.code,
            "description": cls.description,
            "value_type": cls.value_type,
            "unit": cls.unit,
            "category": cls.category,
            "is_stub": cls.is_stub,
        }

    @abstractmethod
    def fetch(self, db: Session, params: DataSourceParams) -> Any:
        """Return the source value. Type depends on the source (Decimal, KpiFactRaw, ShiftStats…)."""

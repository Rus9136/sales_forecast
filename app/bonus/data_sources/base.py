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
    """

    code: str = ""

    @abstractmethod
    def fetch(self, db: Session, params: DataSourceParams) -> Any:
        """Return the source value. Type depends on the source (Decimal, KpiFactRaw, ShiftStats…)."""

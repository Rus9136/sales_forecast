from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PeriodKey:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not (1 <= self.month <= 12):
            raise ValueError(f"month must be 1..12, got {self.month}")

    @property
    def start(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def end(self) -> date:
        last_day = monthrange(self.year, self.month)[1]
        return date(self.year, self.month, last_day)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

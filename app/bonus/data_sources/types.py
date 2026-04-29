from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class KpiFactRaw:
    """Raw KPI fact + target before scoring."""
    fact: Optional[Decimal]
    target: Optional[Decimal]

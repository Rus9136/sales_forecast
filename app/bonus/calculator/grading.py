from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from ..utils.decimal_utils import to_decimal


@dataclass
class Grade:
    from_percent: Decimal
    to_percent: Decimal
    value: Optional[Decimal] = None  # tenge for flat_by_kpi
    rate: Optional[Decimal] = None   # 0..1 for revenue_percent_by_kpi / team_revenue


def parse_grades(raw: list[dict[str, Any]]) -> list[Grade]:
    grades: list[Grade] = []
    for g in raw:
        grades.append(Grade(
            from_percent=to_decimal(g["from"]),
            to_percent=to_decimal(g["to"]),
            value=to_decimal(g["value"]) if "value" in g else None,
            rate=to_decimal(g["rate"]) if "rate" in g else None,
        ))
    return sorted(grades, key=lambda g: g.from_percent)


def find_grade(grades: list[Grade], percent: Decimal) -> Optional[Grade]:
    """Return the grade where percent ∈ [from..to], else None.

    For percents falling into "holes" between grade ranges (e.g. 89.5 between
    85-89 and 90-97), we round up to the next integer using ceil. This is the
    MVP rule fixed in docs/04-domain-rules.md §6.
    """
    p = to_decimal(percent)
    p_int = Decimal(math.ceil(p))
    for grade in grades:
        if grade.from_percent <= p_int <= grade.to_percent:
            return grade
    return None

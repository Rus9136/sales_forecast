from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


TWO_DP = Decimal("0.01")
ZERO_DP = Decimal("1")


def to_decimal(value) -> Decimal:
    """Coerce a numeric/string value to Decimal."""
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_money(value: Decimal) -> Decimal:
    """Round to whole tenge (final bonuses)."""
    return to_decimal(value).quantize(ZERO_DP, rounding=ROUND_HALF_UP)


def round_intermediate(value: Decimal) -> Decimal:
    """Round intermediate amounts to 2 decimals."""
    return to_decimal(value).quantize(TWO_DP, rounding=ROUND_HALF_UP)

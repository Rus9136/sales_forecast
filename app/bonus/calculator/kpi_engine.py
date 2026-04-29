from __future__ import annotations

from decimal import Decimal

from ..utils.decimal_utils import to_decimal


def score_kpi(
    fact,
    target,
    direction: str,
    cap_at_100: bool = True,
) -> Decimal:
    """Return the KPI completion percentage in 0..N (capped at 100 by default).

    direction:
        'higher_is_better'  — fact/target × 100   (e.g. sales plan)
        'lower_is_better'   — target/fact × 100   (e.g. negative reviews share)
        'binary'            — fact/target × 100   (e.g. rating 1..5 → 20..100)
    """
    fact_d = to_decimal(fact)
    target_d = to_decimal(target)

    if target_d == 0:
        return Decimal(0)

    if direction == "higher_is_better":
        result = (fact_d / target_d) * 100
    elif direction == "lower_is_better":
        if fact_d == 0:
            result = Decimal(100)
        else:
            result = (target_d / fact_d) * 100
    elif direction == "binary":
        result = (fact_d / target_d) * 100
    else:
        raise ValueError(f"Unknown KPI direction: {direction!r}")

    if cap_at_100 and result > 100:
        result = Decimal(100)

    return result.quantize(Decimal("0.01"))


def overall_kpi(percents: list[Decimal]) -> Decimal:
    """Average KPI percentages (no weights in current version)."""
    if not percents:
        return Decimal(0)
    total = sum((to_decimal(p) for p in percents), Decimal(0))
    return (total / Decimal(len(percents))).quantize(Decimal("0.01"))

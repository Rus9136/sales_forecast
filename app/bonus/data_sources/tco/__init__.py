"""TCO (Time Control Office) shift sources — currently stubbed.

For MVP we approximate worked shifts as the count of distinct dates a
waiter has sales in sales_by_waiter (so we don't introduce a new dependency).
The norm is taken from monthly_plan(metric='shifts_norm') if present, else 22.
"""

from .shifts import TcoShifts  # noqa: F401


def register_tco_sources() -> None:
    from ..registry import DataSourceRegistry
    DataSourceRegistry.register(TcoShifts())

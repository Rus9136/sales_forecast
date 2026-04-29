"""Data sources for the bonus calculator.

The calculator never queries the DB or HTTP directly. It asks the
DataSourceRegistry for a named source (e.g. 'iiko_personal_revenue_with_discount')
and gets a Decimal back. This keeps the calculator pure logic.

To swap a mock for a real adapter — register a different class under the same code.
"""

from .base import BonusDataSource, DataSourceParams  # noqa: F401
from .registry import DataSourceRegistry  # noqa: F401
from .types import KpiFactRaw  # noqa: F401

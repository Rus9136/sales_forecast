from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from ...calculator.context import ShiftStats
from ...models.monthly_plan import BonusMonthlyPlan
from ...utils.decimal_utils import to_decimal
from ..base import BonusDataSource, DataSourceParams


DEFAULT_NORM = Decimal("22")


class TcoShifts(BonusDataSource):
    """Approximated shifts: worked = distinct sale-dates in sales_by_waiter.

    Norm is loaded from bonus_monthly_plan(metric='shifts_norm') for the
    location/period; falls back to DEFAULT_NORM (22).
    """

    code = "tco_shifts"

    def fetch(self, db: Session, params: DataSourceParams) -> ShiftStats:
        from ....models.employee import SalesByWaiter

        worked = Decimal(0)
        if params.employee_id and params.department_id:
            count = (
                db.query(func.count(distinct(SalesByWaiter.date)))
                .filter(
                    SalesByWaiter.department_id == params.department_id,
                    SalesByWaiter.employee_id == params.employee_id,
                    SalesByWaiter.date >= params.period.start,
                    SalesByWaiter.date <= params.period.end,
                )
                .scalar()
            )
            worked = to_decimal(count or 0)

        norm = DEFAULT_NORM
        if params.department_id:
            norm_row = (
                db.query(BonusMonthlyPlan.target_value)
                .filter(
                    BonusMonthlyPlan.department_id == params.department_id,
                    BonusMonthlyPlan.metric == "shifts_norm",
                    BonusMonthlyPlan.year == params.period.year,
                    BonusMonthlyPlan.month == params.period.month,
                )
                .scalar()
            )
            if norm_row is not None:
                norm = to_decimal(norm_row)

        return ShiftStats(worked=worked, norm=norm)

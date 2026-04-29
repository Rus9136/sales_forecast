"""Revenue sources backed by the existing sales_summary / sales_by_waiter tables.

Naming convention:
    *_with_discount      → DishDiscountSumInt (sum incl. discounts/markups)
    *_dish_sum           → DishSumInt          (gross, without discounts)

For backward compatibility with the bonus_service docs we expose
'iiko_revenue_with_discount' as the «sum with discount» source for a location,
even though sales_summary today only stores DishSumInt. The location-level
adapter SUMs sales_summary.total_sales (= DishSumInt) by default; if a
DishDiscountSumInt column is added to sales_summary later, switch the value
expression in IikoLocationRevenueWithDiscount.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...utils.decimal_utils import to_decimal
from ..base import BonusDataSource, DataSourceParams


def _period_dates(params: DataSourceParams):
    return params.period.start, params.period.end


# ---------------------------------------------------------------------------
# Location-level revenue
# ---------------------------------------------------------------------------
class IikoLocationRevenueDishSum(BonusDataSource):
    """SUM(sales_summary.total_sales) — DishSumInt for the location/period."""
    code = "iiko_revenue_dish_sum"

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        from ....models.sales import SalesSummary
        if not params.department_id:
            return Decimal(0)
        from_d, to_d = _period_dates(params)
        total = (
            db.query(func.coalesce(func.sum(SalesSummary.total_sales), 0))
            .filter(
                SalesSummary.department_id == params.department_id,
                SalesSummary.date >= from_d,
                SalesSummary.date <= to_d,
            )
            .scalar()
        )
        return to_decimal(total)


class IikoLocationRevenueWithDiscount(BonusDataSource):
    """Location revenue 'with discount'.

    Currently uses sales_summary.total_sales (which holds DishSumInt). When
    sales_summary is extended with DishDiscountSumInt, swap the column here.
    """
    code = "iiko_revenue_with_discount"

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        from ....models.sales import SalesSummary
        if not params.department_id:
            return Decimal(0)
        from_d, to_d = _period_dates(params)
        total = (
            db.query(func.coalesce(func.sum(SalesSummary.total_sales), 0))
            .filter(
                SalesSummary.department_id == params.department_id,
                SalesSummary.date >= from_d,
                SalesSummary.date <= to_d,
            )
            .scalar()
        )
        return to_decimal(total)


# ---------------------------------------------------------------------------
# Per-employee revenue (officianty)
# ---------------------------------------------------------------------------
class IikoPersonalRevenueWithDiscount(BonusDataSource):
    """SUM(sales_by_waiter.total_sales_with_discount) — DishDiscountSumInt per employee."""
    code = "iiko_personal_revenue_with_discount"

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        from ....models.employee import SalesByWaiter
        if not params.employee_id or not params.department_id:
            return Decimal(0)
        from_d, to_d = _period_dates(params)
        total = (
            db.query(func.coalesce(func.sum(SalesByWaiter.total_sales_with_discount), 0))
            .filter(
                SalesByWaiter.department_id == params.department_id,
                SalesByWaiter.employee_id == params.employee_id,
                SalesByWaiter.date >= from_d,
                SalesByWaiter.date <= to_d,
            )
            .scalar()
        )
        return to_decimal(total)


class IikoPersonalRevenueDishSum(BonusDataSource):
    """SUM(sales_by_waiter.total_sales) — DishSumInt per employee (without discounts)."""
    code = "iiko_personal_revenue_dish_sum"

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        from ....models.employee import SalesByWaiter
        if not params.employee_id or not params.department_id:
            return Decimal(0)
        from_d, to_d = _period_dates(params)
        total = (
            db.query(func.coalesce(func.sum(SalesByWaiter.total_sales), 0))
            .filter(
                SalesByWaiter.department_id == params.department_id,
                SalesByWaiter.employee_id == params.employee_id,
                SalesByWaiter.date >= from_d,
                SalesByWaiter.date <= to_d,
            )
            .scalar()
        )
        return to_decimal(total)


# ---------------------------------------------------------------------------
# Sales-plan KPI sources (return Decimal — % of plan)
# ---------------------------------------------------------------------------
class IikoSalesPlanLocation(BonusDataSource):
    """% выполнения плана продаж локации = SUM(sales_summary) / monthly_plan(sales) × 100."""
    code = "iiko_sales_plan_location"

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        from ....models.sales import SalesSummary
        from ...models.monthly_plan import BonusMonthlyPlan
        if not params.department_id:
            return Decimal(0)
        from_d, to_d = _period_dates(params)
        actual = to_decimal(
            db.query(func.coalesce(func.sum(SalesSummary.total_sales), 0))
            .filter(
                SalesSummary.department_id == params.department_id,
                SalesSummary.date >= from_d,
                SalesSummary.date <= to_d,
            )
            .scalar()
        )
        plan = (
            db.query(BonusMonthlyPlan.target_value)
            .filter(
                BonusMonthlyPlan.department_id == params.department_id,
                BonusMonthlyPlan.metric == "sales",
                BonusMonthlyPlan.year == params.period.year,
                BonusMonthlyPlan.month == params.period.month,
            )
            .scalar()
        )
        plan_d = to_decimal(plan) if plan is not None else Decimal(0)
        if plan_d <= 0:
            return Decimal(0)
        return (actual / plan_d * 100)


class IikoSalesPlanPersonal(BonusDataSource):
    """% выполнения личного плана продаж = SUM(sales_by_waiter) / personal_plan × 100.

    Personal plan is approximated as (location plan / number_of_waiters) — this is
    a placeholder until per-employee plans are introduced. For MVP returns the
    actual personal sales as a Decimal — the calculator's KPI definition decides
    what target to score against.
    """
    code = "iiko_sales_plan_personal"

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        from ....models.employee import SalesByWaiter
        if not params.employee_id or not params.department_id:
            return Decimal(0)
        from_d, to_d = _period_dates(params)
        actual = (
            db.query(func.coalesce(func.sum(SalesByWaiter.total_sales_with_discount), 0))
            .filter(
                SalesByWaiter.department_id == params.department_id,
                SalesByWaiter.employee_id == params.employee_id,
                SalesByWaiter.date >= from_d,
                SalesByWaiter.date <= to_d,
            )
            .scalar()
        )
        return to_decimal(actual)

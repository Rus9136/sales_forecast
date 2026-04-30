"""Pure unit tests for `IikoWaiterSalesLoaderService.aggregate`.

Tests for the DB-dependent `_build_name_to_employee_map` and `upsert`
methods live in tests/integration/test_iiko_waiter_loader.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.iiko_waiter_sales_loader import IikoWaiterSalesLoaderService

pytestmark = pytest.mark.unit


class TestAggregate:
    def test_empty_input_returns_empty(self) -> None:
        assert IikoWaiterSalesLoaderService.aggregate([]) == []

    def test_groups_by_dept_date_waiter_and_sums_amounts(self) -> None:
        rows = [
            # Same dept/date/waiter — must sum.
            {"Department.Id": "d1", "WaiterName": "Alice", "OpenDate": "2026-04-01",
             "DishSumInt": 1000, "DishDiscountSumInt": 950},
            {"Department.Id": "d1", "WaiterName": "Alice", "OpenDate": "2026-04-01",
             "DishSumInt": 500, "DishDiscountSumInt": 480},
            # Different waiter, same dept/date.
            {"Department.Id": "d1", "WaiterName": "Bob", "OpenDate": "2026-04-01",
             "DishSumInt": 700, "DishDiscountSumInt": 700},
            # Different date.
            {"Department.Id": "d1", "WaiterName": "Alice", "OpenDate": "2026-04-02",
             "DishSumInt": 200, "DishDiscountSumInt": 200},
        ]
        result = IikoWaiterSalesLoaderService.aggregate(rows)

        # Three groups: d1+Alice+04-01 (=1500/1430), d1+Bob+04-01 (=700/700),
        # d1+Alice+04-02 (=200/200).
        keyed = {
            (r["department_id"], r["date"], r["waiter_name"]): r
            for r in result
        }
        alice_apr1 = keyed[("d1", date(2026, 4, 1), "Alice")]
        assert alice_apr1["total_sales"] == 1500.0
        assert alice_apr1["total_sales_with_discount"] == 1430.0

        bob_apr1 = keyed[("d1", date(2026, 4, 1), "Bob")]
        assert bob_apr1["total_sales"] == 700.0

        alice_apr2 = keyed[("d1", date(2026, 4, 2), "Alice")]
        assert alice_apr2["total_sales"] == 200.0

    def test_returns_empty_when_OpenDate_column_missing(self) -> None:
        # If iiko changes its response shape, the loader must fail-soft (log
        # and return []) — never crash with KeyError.
        rows = [
            {"Department.Id": "d1", "WaiterName": "X",
             "DishSumInt": 100, "DishDiscountSumInt": 100},
        ]
        assert IikoWaiterSalesLoaderService.aggregate(rows) == []

    def test_treats_null_discount_as_zero_in_sum(self) -> None:
        # pandas .sum() with skipna=True (default) treats None/NaN as 0, so
        # the returned amount is 0.0 rather than None — but the path through
        # `pd.notna()` in the serializer would still produce None if pandas
        # ever yielded a true NaN (e.g. all-NaN group on float columns).
        rows = [
            {"Department.Id": "d1", "WaiterName": "X", "OpenDate": "2026-04-01",
             "DishSumInt": 100, "DishDiscountSumInt": None},
        ]
        result = IikoWaiterSalesLoaderService.aggregate(rows)
        assert result[0]["total_sales_with_discount"] == 0.0

    def test_amounts_are_floats(self) -> None:
        rows = [
            {"Department.Id": "d", "WaiterName": "X", "OpenDate": "2026-04-01",
             "DishSumInt": 100, "DishDiscountSumInt": 90},
        ]
        r = IikoWaiterSalesLoaderService.aggregate(rows)[0]
        assert isinstance(r["total_sales"], float)
        assert isinstance(r["total_sales_with_discount"], float)

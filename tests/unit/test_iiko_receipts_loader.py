"""Unit tests for IikoReceiptsLoaderService helpers."""

from __future__ import annotations

import pytest

from app.services.iiko_receipts_loader import IikoReceiptsLoaderService, _domain_host

pytestmark = pytest.mark.unit


class TestDomainHost:
    def test_full_url(self) -> None:
        assert _domain_host("https://sandy-co-co.iiko.it") == "sandy-co-co.iiko.it"

    def test_bare_hostname(self) -> None:
        assert _domain_host("example.com") == "example.com"

    def test_with_path(self) -> None:
        assert _domain_host("https://example.com/api/v2") == "example.com"


class TestToFloat:
    def test_int(self) -> None:
        assert IikoReceiptsLoaderService._to_float(1590) == 1590.0

    def test_float(self) -> None:
        assert IikoReceiptsLoaderService._to_float(0.48) == 0.48

    def test_none(self) -> None:
        assert IikoReceiptsLoaderService._to_float(None) == 0.0

    def test_string(self) -> None:
        assert IikoReceiptsLoaderService._to_float("bad") == 0.0


class TestParseOlapRows:
    """Test the OLAP row grouping logic without a DB connection."""

    def _make_loader(self):
        """Create a loader instance with db=None (only _parse_olap_rows is tested)."""
        svc = object.__new__(IikoReceiptsLoaderService)
        svc.db = None
        svc.domains = []
        return svc

    def test_single_order_two_items(self) -> None:
        rows = [
            {
                "Department.Id": "dept-1",
                "OpenDate.Typed": "2026-05-24",
                "OrderNum": 1,
                "CloseTime": "2026-05-24T12:00:00",
                "OrderType": "Обычный заказ",
                "TableNum": 5,
                "WaiterName": "Иванов",
                "DishId": "aaa-111",
                "DishName": "Чай",
                "DishCode": "001",
                "DishGroup": "Напитки",
                "DishCategory": "Горячие",
                "DishAmountInt": 2,
                "DishSumInt": 1000,
                "DishDiscountSumInt": 0,
                "DishReturnSum": 0,
                "GuestNum": 1,
            },
            {
                "Department.Id": "dept-1",
                "OpenDate.Typed": "2026-05-24",
                "OrderNum": 1,
                "CloseTime": "2026-05-24T12:00:00",
                "OrderType": "Обычный заказ",
                "TableNum": 5,
                "WaiterName": "Иванов",
                "DishId": "bbb-222",
                "DishName": "Кофе",
                "DishCode": "002",
                "DishGroup": "Напитки",
                "DishCategory": "Горячие",
                "DishAmountInt": 1,
                "DishSumInt": 500,
                "DishDiscountSumInt": 100,
                "DishReturnSum": 0,
                "GuestNum": 1,
            },
        ]
        svc = self._make_loader()
        receipts, items = svc._parse_olap_rows(rows, "test.iiko.it")

        assert len(receipts) == 1
        assert len(items) == 2

        r = receipts[0]
        assert r["department_id"] == "dept-1"
        assert r["order_num"] == 1
        assert r["total_sum"] == 1500.0
        assert r["paid_sum"] == 100.0  # DishDiscountSumInt — сумма к оплате, не величина скидки
        assert r["items_count"] == 2
        assert r["waiter_name"] == "Иванов"
        assert r["guest_num"] == 1

        tea = next(i for i in items if i["dish_name"] == "Чай")
        assert tea["qty"] == 2.0
        assert tea["price_per_unit"] == 500.0
        assert tea["dish_sum"] == 1000.0

    def test_two_orders_separated(self) -> None:
        rows = [
            {
                "Department.Id": "dept-1",
                "OpenDate.Typed": "2026-05-24",
                "OrderNum": 1,
                "CloseTime": "2026-05-24T12:00:00",
                "OrderType": None,
                "TableNum": None,
                "WaiterName": None,
                "DishId": "aaa",
                "DishName": "A",
                "DishCode": None,
                "DishGroup": None,
                "DishCategory": None,
                "DishAmountInt": 1,
                "DishSumInt": 100,
                "DishDiscountSumInt": 0,
                "DishReturnSum": 0,
                "GuestNum": 1,
            },
            {
                "Department.Id": "dept-2",
                "OpenDate.Typed": "2026-05-24",
                "OrderNum": 1,
                "CloseTime": "2026-05-24T13:00:00",
                "OrderType": None,
                "TableNum": None,
                "WaiterName": None,
                "DishId": "bbb",
                "DishName": "B",
                "DishCode": None,
                "DishGroup": None,
                "DishCategory": None,
                "DishAmountInt": 3,
                "DishSumInt": 900,
                "DishDiscountSumInt": 50,
                "DishReturnSum": 10,
                "GuestNum": 2,
            },
        ]
        svc = self._make_loader()
        receipts, items = svc._parse_olap_rows(rows, "test.iiko.it")

        assert len(receipts) == 2
        assert len(items) == 2

    def test_fractional_qty(self) -> None:
        rows = [
            {
                "Department.Id": "dept-1",
                "OpenDate.Typed": "2026-05-24",
                "OrderNum": 99,
                "CloseTime": "2026-05-24T14:00:00",
                "OrderType": None,
                "TableNum": None,
                "WaiterName": None,
                "DishId": "ccc",
                "DishName": "Весовой товар",
                "DishCode": None,
                "DishGroup": None,
                "DishCategory": None,
                "DishAmountInt": 0.48,
                "DishSumInt": 2400,
                "DishDiscountSumInt": 0,
                "DishReturnSum": 0,
                "GuestNum": 0,
            },
        ]
        svc = self._make_loader()
        receipts, items = svc._parse_olap_rows(rows, "test.iiko.it")

        assert items[0]["qty"] == 0.48
        assert items[0]["price_per_unit"] == 5000.0
        assert receipts[0]["guest_num"] is None

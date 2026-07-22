"""Unit tests for `IikoSalesLoaderService` — OLAP request body, response
parsing, daily/hourly aggregation. No DB writes — `sync_sales_summary` and
`sync_sales_by_hour` are exercised in integration tests separately.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import pytest
import respx

from app.services.iiko_sales_loader import IikoSalesLoaderService

pytestmark = pytest.mark.unit

DOMAIN = "https://sales-test.example.com"
OLAP_URL = f"{DOMAIN}/resto/api/v2/reports/olap"
AUTH_URL = f"{DOMAIN}/resto/api/auth"


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "IIKO_LOGIN", "x")
    monkeypatch.setattr(settings, "IIKO_PASSWORD", "y")
    monkeypatch.setattr(settings, "IIKO_DOMAINS", DOMAIN)


@pytest.fixture
def service():
    """The processing methods don't touch the DB; pass None."""
    return IikoSalesLoaderService(db=None)  # type: ignore[arg-type]


class TestProcessSalesData:
    def test_returns_empty_for_empty_input(self, service) -> None:
        assert service.process_sales_data([]) == ([], [])

    def test_aggregates_to_daily_summary_and_hourly(self, service) -> None:
        rows = [
            # Same dept, same day — two orders. Hour 10 and hour 12.
            {"Department.Id": "d1", "CloseTime": "2026-04-01T10:30:00", "OrderNum": "1", "DishSumInt": 1000},
            {"Department.Id": "d1", "CloseTime": "2026-04-01T10:45:00", "OrderNum": "2", "DishSumInt": 500},
            {"Department.Id": "d1", "CloseTime": "2026-04-01T12:00:00", "OrderNum": "3", "DishSumInt": 2000},
            # Different dept, same day.
            {"Department.Id": "d2", "CloseTime": "2026-04-01T15:00:00", "OrderNum": "4", "DishSumInt": 700},
        ]
        summary, hourly = service.process_sales_data(rows)

        # Daily summary: d1=3500, d2=700.
        by_dept = {(r["department_id"], r["date"]): r["total_sales"] for r in summary}
        assert by_dept[("d1", date(2026, 4, 1))] == 3500.0
        assert by_dept[("d2", date(2026, 4, 1))] == 700.0

        # Hourly: d1@10=1500, d1@12=2000, d2@15=700.
        by_hour = {
            (r["department_id"], r["date"], r["hour"]): r["sales_amount"]
            for r in hourly
        }
        assert by_hour[("d1", date(2026, 4, 1), 10)] == 1500.0
        assert by_hour[("d1", date(2026, 4, 1), 12)] == 2000.0
        assert by_hour[("d2", date(2026, 4, 1), 15)] == 700.0

    def test_handles_mixed_datetime_formats(self, service) -> None:
        # iiko returns timestamps in different formats across calls — the
        # loader uses `format='mixed'` so both must parse.
        rows = [
            {"Department.Id": "d", "CloseTime": "2026-04-01T10:00:00", "OrderNum": "1", "DishSumInt": 100},
            {"Department.Id": "d", "CloseTime": "2026-04-01 11:00:00", "OrderNum": "2", "DishSumInt": 200},
        ]
        summary, hourly = service.process_sales_data(rows)
        assert len(summary) == 1
        assert summary[0]["total_sales"] == 300.0
        assert {r["hour"] for r in hourly} == {10, 11}

    def test_hour_key_is_int(self, service) -> None:
        rows = [
            {"Department.Id": "d", "CloseTime": "2026-04-01T09:00:00", "OrderNum": "1", "DishSumInt": 100}
        ]
        _, hourly = service.process_sales_data(rows)
        assert isinstance(hourly[0]["hour"], int)


class TestFetchSalesFromSingleDomain:
    """OLAP HTTP shape — must POST to /v2/reports/olap with the exact
    request body the iiko docs require, especially `OpenDate.Typed` (NOT
    plain `OpenDate`, which iiko explicitly rejects)."""

    async def test_uses_OpenDate_Typed_filter_not_OpenDate(self, service) -> None:
        with respx.mock() as router:
            router.get(AUTH_URL).mock(return_value=httpx.Response(200, text="tok"))
            olap = router.post(OLAP_URL).mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            await service.fetch_sales_from_single_domain(
                DOMAIN, date(2026, 4, 1), date(2026, 4, 7)
            )
            assert olap.called
            sent = json.loads(olap.calls.last.request.content)
            # The bug-prevention guarantee: filter key is `OpenDate.Typed`.
            assert "OpenDate.Typed" in sent["filters"]
            assert "OpenDate" not in sent["filters"]
            assert sent["filters"]["OpenDate.Typed"]["from"] == "2026-04-01"
            assert sent["filters"]["OpenDate.Typed"]["to"] == "2026-04-07"

    async def test_request_body_groups_by_required_fields(self, service) -> None:
        with respx.mock() as router:
            router.get(AUTH_URL).mock(return_value=httpx.Response(200, text="tok"))
            olap = router.post(OLAP_URL).mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            await service.fetch_sales_from_single_domain(
                DOMAIN, date(2026, 4, 1), date(2026, 4, 1)
            )
            sent = json.loads(olap.calls.last.request.content)
            assert sent["reportType"] == "SALES"
            assert sent["groupByRowFields"] == [
                "Department.Id",
                "CloseTime",
                "OrderNum",
            ]
            assert sent["aggregateFields"] == ["DishSumInt", "DishDiscountSumInt"]
            # Deleted-orders filters present.
            assert sent["filters"]["OrderDeleted"]["values"] == ["NOT_DELETED"]
            assert sent["filters"]["DeletedWithWriteoff"]["values"] == ["NOT_DELETED"]

    async def test_returns_data_array_from_response(self, service) -> None:
        with respx.mock() as router:
            router.get(AUTH_URL).mock(return_value=httpx.Response(200, text="tok"))
            router.post(OLAP_URL).mock(
                return_value=httpx.Response(200, json={
                    "data": [
                        {"Department.Id": "d1", "CloseTime": "2026-04-01T10:00:00", "OrderNum": "1", "DishSumInt": 100},
                    ]
                })
            )
            result = await service.fetch_sales_from_single_domain(
                DOMAIN, date(2026, 4, 1), date(2026, 4, 1)
            )
            assert len(result) == 1
            assert result[0]["Department.Id"] == "d1"

    async def test_5xx_returns_empty_list_does_not_raise(self, service) -> None:
        # The loader catches HTTPError and returns [] so a single bad domain
        # doesn't kill the whole multi-domain sync.
        with respx.mock() as router:
            router.get(AUTH_URL).mock(return_value=httpx.Response(200, text="tok"))
            router.post(OLAP_URL).mock(return_value=httpx.Response(503))
            result = await service.fetch_sales_from_single_domain(
                DOMAIN, date(2026, 4, 1), date(2026, 4, 1)
            )
            assert result == []

    async def test_invalid_json_returns_empty(self, service) -> None:
        with respx.mock() as router:
            router.get(AUTH_URL).mock(return_value=httpx.Response(200, text="tok"))
            router.post(OLAP_URL).mock(
                return_value=httpx.Response(200, text="not json")
            )
            result = await service.fetch_sales_from_single_domain(
                DOMAIN, date(2026, 4, 1), date(2026, 4, 1)
            )
            assert result == []

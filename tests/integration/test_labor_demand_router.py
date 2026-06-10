"""Smoke tests for the labor-demand signal router (Sales Forecast → TCO).

Mirrors test_router_smoke.py: we assert the auth boundary, input validation
and the not-found path — all data-independent, so they run against the empty
test DB. Full domain behaviour (forecast/menu aggregation) needs trained
models + seeded sales and is out of scope for wiring smoke.

The service resolves the department first, so an unknown (but well-formed)
UUID returns 404 before any model/data access.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration

BASE = "/api/labor-demand"
FROM = "2026-06-12"


class TestMenuMix:
    def test_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get(
            f"{BASE}/{uuid4()}/menu-mix?from_date={FROM}"
        ).status_code in (401, 403)

    def test_invalid_uuid_returns_400(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/not-a-uuid/menu-mix?from_date={FROM}", headers=auth_headers
        )
        assert response.status_code == 400

    def test_missing_from_date_returns_422(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/{uuid4()}/menu-mix", headers=auth_headers
        )
        assert response.status_code == 422

    def test_range_over_31_days_returns_400(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/{uuid4()}/menu-mix?from_date=2026-06-01&to_date=2026-08-01",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_unknown_department_returns_404(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/{uuid4()}/menu-mix?from_date={FROM}", headers=auth_headers
        )
        assert response.status_code == 404


class TestForecast:
    def test_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get(
            f"{BASE}/{uuid4()}/forecast?from_date={FROM}"
        ).status_code in (401, 403)

    def test_invalid_uuid_returns_400(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/not-a-uuid/forecast?from_date={FROM}", headers=auth_headers
        )
        assert response.status_code == 400

    def test_to_before_from_returns_400(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/{uuid4()}/forecast?from_date=2026-06-12&to_date=2026-06-10",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_unknown_department_returns_404(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/{uuid4()}/forecast?from_date={FROM}", headers=auth_headers
        )
        assert response.status_code == 404


class TestElasticitySignal:
    def test_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get(
            f"{BASE}/{uuid4()}/elasticity-signal"
        ).status_code in (401, 403)

    def test_invalid_uuid_returns_400(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/not-a-uuid/elasticity-signal", headers=auth_headers
        )
        assert response.status_code == 400

    def test_invalid_grade_returns_400(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/{uuid4()}/elasticity-signal?grade=A,Z", headers=auth_headers
        )
        assert response.status_code == 400

    def test_unknown_department_returns_404(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            f"{BASE}/{uuid4()}/elasticity-signal", headers=auth_headers
        )
        assert response.status_code == 404

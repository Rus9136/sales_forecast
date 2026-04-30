"""Smoke tests for the public router surface.

For each router we confirm:
- auth boundary returns 401 when the Bearer header is missing
- the route is wired and runs to completion when authenticated

These tests do NOT exercise full domain logic — that belongs in the
domain-specific suites added in later stages. The goal is to catch broken
imports, missing routes, and accidentally-loosened auth guards.

In DEBUG mode (set in tests/conftest.py), `get_api_key_or_bypass` accepts
the env API_TOKEN as a bypass — so `auth_headers` (Bearer test-api-token)
is sufficient to clear the dependency without provisioning a real key.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.auth_ui import AppUser

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_session_headers(seeded_admin: AppUser, session_token_for) -> dict:
    return {"X-Session-Token": session_token_for(seeded_admin)}


@pytest.fixture()
def manager_session_headers(seeded_manager: AppUser, session_token_for) -> dict:
    return {"X-Session-Token": session_token_for(seeded_manager)}


# ---------------------------------------------------------------------------
# Departments / Employees / Sales — Bearer auth via DEBUG bypass
# ---------------------------------------------------------------------------


class TestDepartmentsRouter:
    def test_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get("/api/departments/").status_code in (401, 403)

    def test_list_with_auth_returns_array(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get("/api/departments/", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_unknown_id_returns_404(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get(
            f"/api/departments/{uuid4()}", headers=auth_headers
        )
        assert response.status_code == 404


class TestEmployeesRouter:
    def test_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get("/api/employees/").status_code in (401, 403)

    def test_list_with_auth_returns_array(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get("/api/employees/", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestSalesRouter:
    def test_summary_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get("/api/sales/summary").status_code in (401, 403)

    def test_summary_with_auth_returns_array(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get(
            "/api/sales/summary", headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_hourly_with_auth_returns_array(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get(
            "/api/sales/hourly", headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Monitoring — model health may be 200 or 503 depending on whether a model
# file exists in the test container; either response proves the route is wired.
# ---------------------------------------------------------------------------


class TestMonitoringRouter:
    def test_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get("/api/monitoring/health").status_code in (
            401,
            403,
        )

    def test_retrain_status_with_auth(
        self, client_with_db, auth_headers
    ) -> None:
        # /retrain/status doesn't depend on data, only on the scheduler — so
        # it's the most reliable smoke for monitoring router wiring. (The
        # `/health` endpoint can 500 in a test container because it joins on
        # forecast tables that are empty under savepoint rollback.)
        response = client_with_db.get(
            "/api/monitoring/retrain/status", headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), dict)


# ---------------------------------------------------------------------------
# API Key management
# ---------------------------------------------------------------------------


class TestApiKeysRouter:
    def test_list_keys_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get("/api/auth/keys").status_code in (401, 403)

    def test_list_keys_with_bypass_token(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get("/api/auth/keys", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Users (admin-only via session)
# ---------------------------------------------------------------------------


class TestUsersRouter:
    def test_no_session_returns_401(self, client_with_db) -> None:
        assert client_with_db.get("/api/users/").status_code == 401

    def test_admin_session_returns_user_list(
        self, client_with_db, admin_session_headers
    ) -> None:
        response = client_with_db.get(
            "/api/users/", headers=admin_session_headers
        )
        assert response.status_code == 200
        body = response.json()
        # serialize_user shape — at least the seeded admin appears.
        assert isinstance(body, list)
        phones = {u["phone"] for u in body}
        assert "77001234567" in phones

    def test_manager_session_returns_403(
        self, client_with_db, manager_session_headers
    ) -> None:
        response = client_with_db.get(
            "/api/users/", headers=manager_session_headers
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# AI Recommendations — read-only metadata endpoints
# ---------------------------------------------------------------------------


class TestAIRecommendationsRouter:
    def test_providers_no_auth_returns_401(self, client_with_db) -> None:
        assert client_with_db.get(
            "/api/ai-recommendations/providers"
        ).status_code in (401, 403)

    def test_providers_with_auth(self, client_with_db, auth_headers) -> None:
        response = client_with_db.get(
            "/api/ai-recommendations/providers", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        # Loose shape check — at least claude/openai keys or a `providers` field.
        assert isinstance(body, (dict, list))

    def test_history_with_auth_returns_array(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get(
            "/api/ai-recommendations/history", headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Forecast — wiring smoke
# ---------------------------------------------------------------------------


class TestForecastRouter:
    def test_postprocessing_settings_no_auth_returns_401(
        self, client_with_db
    ) -> None:
        assert client_with_db.get(
            "/api/forecast/postprocessing/settings"
        ).status_code in (401, 403)

    def test_postprocessing_settings_with_auth(
        self, client_with_db, auth_headers
    ) -> None:
        response = client_with_db.get(
            "/api/forecast/postprocessing/settings", headers=auth_headers
        )
        # 200 (settings exist) or 404 (no settings row); both prove wiring.
        assert response.status_code in (200, 404)

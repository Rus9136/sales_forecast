"""Root pytest fixtures for the Sales Forecast API.

This file runs *before* any `app.*` module is imported, so it is the only
safe place to point the Pydantic `settings` singleton at the test database.
Integration fixtures (`db_session`, `client_with_db`, `seeded_admin`, …)
live in `tests/integration/conftest.py` and depend on the env override here.
"""

from __future__ import annotations

import os

# CRITICAL: force the test DB before any `app.*` import. `app.config.settings`
# is built at module load time, so a late override has no effect. Tests run
# inside the `sales-forecast-app` container where POSTGRES_DB defaults to
# `sales_forecast`; this line redirects the engine to `sales_forecast_test`,
# which is provisioned with `pg_dump --schema-only` from prod (see Stage 3
# notes in CLAUDE.md). Unit tests don't hit the DB, but the engine still gets
# built when `app.main` is imported, so the override must apply universally.
os.environ["POSTGRES_DB"] = "sales_forecast_test"

# Direct assignment (NOT setdefault): the container ships with DEBUG=False
# and a production API_TOKEN. We must override before `app.config.settings`
# is built. With DEBUG=True the API token bypass kicks in, so `auth_headers`
# (Bearer test-api-token) clears `get_api_key_or_bypass` without provisioning
# a DB-backed key. The DB auth path is covered separately in
# tests/integration/test_api_key_db.py.
os.environ["DEBUG"] = "True"
os.environ["API_TOKEN"] = "test-api-token"

import pytest


@pytest.fixture(scope="session")
def app():
    """Return the FastAPI application without entering its lifespan.

    Importing `app.main` triggers `Base.metadata.create_all(bind=engine)` —
    that's fine: the test DB already has the schema, so it's a no-op. The
    `lifespan` (which would seed roles + bootstrap admin) does NOT run unless
    a test enters `TestClient(app)` as a context manager.
    """
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app):
    """Plain `TestClient` — no lifespan, no scheduler, no admin bootstrap.

    Endpoints that depend on the DB will hit the (test) engine unless the
    test overrides `app.db.get_db`. Use `client_with_db` from the integration
    conftest to get a transactional, rolled-back-per-test client.
    """
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Bearer header that matches the test API_TOKEN set in this conftest."""
    return {"Authorization": f"Bearer {os.environ['API_TOKEN']}"}

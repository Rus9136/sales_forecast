"""Root pytest fixtures for the Sales Forecast API.

Stage 1 of the test infrastructure provides only the most foundational fixtures:
- `app` — the FastAPI application instance (no lifespan triggered).
- `client` — a `TestClient` bound to `app` that does NOT enter the lifespan
  context, so the APScheduler background jobs and admin bootstrap do not run.
- `auth_headers` — Bearer header for endpoints guarded by API key auth.

DB / auth integration fixtures will be added in later stages (Stage 2 for
auth, Stage 3 for routers + transactional DB).
"""

from __future__ import annotations

import os

import pytest

# Make sure tests never accidentally pick up a real production token from the
# host environment. Individual tests can still override via fixtures.
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("API_TOKEN", "test-api-token")


@pytest.fixture(scope="session")
def app():
    """Return the FastAPI application without entering its lifespan.

    Importing `app.main` triggers `Base.metadata.create_all(bind=engine)`, so
    a Postgres instance must be reachable. For tests that mock the DB layer
    this is fine — only the engine handle is created, no queries run until a
    request hits a route.
    """
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app):
    """Plain `TestClient` — no lifespan, no scheduler, no admin bootstrap.

    Endpoints that depend on the DB will still hit the real engine unless the
    test overrides `app.db.get_db` via `app.dependency_overrides`. Stage 3
    will add a transactional DB fixture for proper integration tests.
    """
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Bearer header that matches the test API_TOKEN set in this conftest."""
    return {"Authorization": f"Bearer {os.environ['API_TOKEN']}"}

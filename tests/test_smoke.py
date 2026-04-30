"""Smoke tests — verify the test harness can import the app and hit a route.

These tests are intentionally trivial. Their job is to fail loudly if the
test environment is misconfigured (missing dependency, broken import,
unreachable DB at startup, etc.) before the more serious test suites run.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


def test_app_imports(app):
    """The FastAPI app object is importable and exposes the expected metadata."""
    assert app.title  # FastAPI sets a default title; just assert it exists
    routes = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in routes


def test_health_endpoint(client):
    """`GET /health` returns 200 and a JSON body with `status: healthy`."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "version" in body


def test_health_does_not_require_auth(client):
    """`/health` must be reachable without an Authorization header."""
    response = client.get("/health")
    assert response.status_code == 200

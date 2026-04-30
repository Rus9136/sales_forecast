"""Smoke tests for the integration fixtures themselves.

If these fail, all other integration tests will also fail — fix this first.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_db_session_is_bound_to_test_db(db_session: Session) -> None:
    name = db_session.execute(text("SELECT current_database()")).scalar()
    assert name == "sales_forecast_test"


def test_db_session_can_query_app_role(db_session: Session) -> None:
    # Schema parity: app_role must exist (mirrors prod schema).
    result = db_session.execute(
        text("SELECT to_regclass('public.app_role')")
    ).scalar()
    assert result == "app_role"


def test_writes_in_one_test_dont_leak_to_next_a(db_session: Session) -> None:
    # Insert a marker role, commit, and trust that the rollback fixture wipes it.
    from app.models.auth_ui import AppRole

    db_session.add(AppRole(code="leak_check", name="X", allowed_sections=[], is_system=False))
    db_session.commit()
    assert db_session.query(AppRole).filter_by(code="leak_check").one_or_none() is not None


def test_writes_in_one_test_dont_leak_to_next_b(db_session: Session) -> None:
    # If the rollback works, the marker from the previous test is gone.
    from app.models.auth_ui import AppRole

    assert db_session.query(AppRole).filter_by(code="leak_check").one_or_none() is None


def test_client_with_db_health(client_with_db) -> None:
    response = client_with_db.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_seeded_roles_creates_four_system_roles(db_session, seeded_roles) -> None:
    from app.models.auth_ui import AppRole

    rows = db_session.query(AppRole).filter_by(is_system=True).all()
    assert {r.code for r in rows} == {"admin", "manager", "accountant", "viewer"}


def test_seeded_admin_links_to_admin_role(seeded_admin) -> None:
    assert seeded_admin.role_code == "admin"
    assert seeded_admin.is_active is True
    assert seeded_admin.phone == "77001234567"

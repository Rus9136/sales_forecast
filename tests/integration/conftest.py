"""Integration test fixtures: real PostgreSQL with per-test rollback.

The fixtures here assume `tests/conftest.py` has already redirected
`POSTGRES_DB` to `sales_forecast_test`. The schema is provisioned once via
``pg_dump --schema-only`` from prod (see CLAUDE.md → Stage 3 notes).

Each test gets a fresh `db_session` bound to its own outer transaction.
Any `db.commit()` inside tested code only releases an inner savepoint, so
the outer rollback at teardown wipes everything. Tests cannot leak state
even when the code under test commits.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Session-scoped engine pointing at `sales_forecast_test`."""
    from app.db import DATABASE_URL

    # The DATABASE_URL was already built against the test DB because
    # tests/conftest.py overrode POSTGRES_DB. Re-create the engine here so
    # the integration tests don't share a pool with `app.db.engine`.
    assert DATABASE_URL.endswith("/sales_forecast_test"), (
        f"Test engine must point at sales_forecast_test, got {DATABASE_URL!r}. "
        "tests/conftest.py should have set POSTGRES_DB=sales_forecast_test."
    )
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _truncate_all_tables(test_engine: Engine) -> None:
    """Wipe every table in the test DB once per session.

    Defence in depth: the savepoint pattern below should already prevent
    inter-test leakage, but if a previous run crashed mid-test (or if a
    previous developer ran ad-hoc inserts in the test DB), this gives a
    deterministic starting state.
    """
    with test_engine.begin() as conn:
        conn.exec_driver_sql(
            """
            DO $$
            DECLARE r RECORD;
            BEGIN
                FOR r IN
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                LOOP
                    EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename)
                            || ' RESTART IDENTITY CASCADE';
                END LOOP;
            END $$;
            """
        )


@pytest.fixture()
def db_session(test_engine: Engine) -> Iterator[Session]:
    """Per-test transactional session.

    Pattern: outer transaction + nested savepoint. Tested code that calls
    ``db.commit()`` only releases the savepoint; the outer rollback at
    teardown wipes everything. Works for SQLAlchemy 2.x.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture()
def client_with_db(app, db_session: Session) -> Iterator[TestClient]:
    """`TestClient` whose `get_db` dependency yields the per-test session."""
    from app.db import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def seeded_roles(db_session: Session):
    """Insert the four system roles (admin/manager/accountant/viewer)."""
    from app.auth_ui import seed_default_roles

    seed_default_roles(db_session)
    return db_session


@pytest.fixture()
def seeded_admin(db_session: Session, seeded_roles):
    """Create one active admin user with phone 77001234567."""
    from uuid import uuid4

    from app.models.auth_ui import AppUser

    user = AppUser(
        id=uuid4(),
        phone="77001234567",
        full_name="Test Admin",
        role_code="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def seeded_manager(db_session: Session, seeded_roles):
    """Create one active manager user with phone 77007654321."""
    from uuid import uuid4

    from app.models.auth_ui import AppUser

    user = AppUser(
        id=uuid4(),
        phone="77007654321",
        full_name="Test Manager",
        role_code="manager",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def session_token_for(db_session: Session):
    """Factory: ``token = session_token_for(user)`` — returns a fresh session token."""
    from app.auth_ui import create_session

    def _make(user) -> str:
        s = create_session(db_session, user)
        db_session.commit()
        return s.token

    return _make

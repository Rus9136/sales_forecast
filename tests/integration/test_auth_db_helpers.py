"""DB-backed auth helpers: seed_default_roles, bootstrap_admin, create_session.

Real PostgreSQL (per-test rollback) — these helpers cannot be exercised with
a MagicMock DB because they rely on Postgres-specific behaviour (JSONB, FK
relationships, UUID).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.auth_ui import (
    ALWAYS_GRANTED_SECTIONS,
    DEFAULT_ROLES,
    bootstrap_admin,
    create_session,
    seed_default_roles,
)
from app.models.auth_ui import AppRole, AppSession, AppUser

pytestmark = pytest.mark.integration


class TestSeedDefaultRoles:
    def test_creates_all_four_system_roles(self, db_session: Session) -> None:
        seed_default_roles(db_session)
        rows = db_session.query(AppRole).all()
        assert {r.code for r in rows} == {spec["code"] for spec in DEFAULT_ROLES}

    def test_admin_role_has_all_sections(self, db_session: Session) -> None:
        seed_default_roles(db_session)
        admin = db_session.query(AppRole).filter_by(code="admin").one()
        # Admin gets every section in AVAILABLE_SECTIONS.
        from app.auth_ui import AVAILABLE_SECTIONS

        assert set(admin.allowed_sections) == set(AVAILABLE_SECTIONS)

    def test_is_idempotent(self, db_session: Session) -> None:
        seed_default_roles(db_session)
        seed_default_roles(db_session)
        seed_default_roles(db_session)
        # Still exactly 4 system roles, no duplicates.
        assert db_session.query(AppRole).count() == len(DEFAULT_ROLES)

    def test_grants_always_on_sections_to_pre_existing_role(
        self, db_session: Session
    ) -> None:
        # Simulate: a custom role created before the "dashboard" page existed,
        # missing the always-granted sections. Seeding should patch it.
        db_session.add(
            AppRole(
                code="custom_legacy",
                name="Legacy",
                allowed_sections=["sales.daily"],
                is_system=False,
            )
        )
        db_session.commit()

        seed_default_roles(db_session)
        legacy = db_session.query(AppRole).filter_by(code="custom_legacy").one()
        for section in ALWAYS_GRANTED_SECTIONS:
            assert section in legacy.allowed_sections
        # Original sections preserved.
        assert "sales.daily" in legacy.allowed_sections


class TestBootstrapAdmin:
    def test_returns_none_when_phone_not_set(
        self, db_session: Session, seeded_roles
    ) -> None:
        assert bootstrap_admin(db_session, None, "Whatever") is None
        assert bootstrap_admin(db_session, "", "Whatever") is None

    def test_creates_new_admin_when_none_exists(
        self, db_session: Session, seeded_roles
    ) -> None:
        user = bootstrap_admin(db_session, "+7 (700) 555-11-22", "Admin Inst")
        assert user is not None
        assert user.role_code == "admin"
        assert user.is_active is True
        assert user.phone == "77005551122"  # normalized
        assert user.full_name == "Admin Inst"

    def test_returns_none_when_admin_already_exists(
        self, db_session: Session, seeded_admin
    ) -> None:
        result = bootstrap_admin(db_session, "+7 (700) 555-99-99", "Other")
        assert result is None
        # Original admin untouched.
        assert (
            db_session.query(AppUser).filter_by(role_code="admin").count() == 1
        )

    def test_promotes_existing_user_with_same_phone(
        self, db_session: Session, seeded_roles
    ) -> None:
        # Seed a manager with a specific phone.
        manager = AppUser(
            id=uuid4(),
            phone="77005554433",
            full_name="Was Manager",
            role_code="manager",
            is_active=True,
        )
        db_session.add(manager)
        db_session.commit()

        result = bootstrap_admin(db_session, "8 700 555 44 33", "Now Admin")
        # Same user, promoted in place. (Note: bootstrap doesn't rename.)
        assert result is not None
        assert result.id == manager.id
        assert result.role_code == "admin"
        assert result.is_active is True

    def test_invalid_phone_returns_none_and_does_not_create(
        self, db_session: Session, seeded_roles
    ) -> None:
        result = bootstrap_admin(db_session, "abc", "X")
        assert result is None
        assert db_session.query(AppUser).count() == 0


class TestCreateSession:
    def test_returns_session_with_token_and_30d_expiry(
        self, db_session: Session, seeded_admin: AppUser
    ) -> None:
        before = datetime.utcnow()
        session = create_session(db_session, seeded_admin)
        db_session.commit()

        assert session.token  # non-empty
        assert len(session.token) >= 40  # token_urlsafe(32) → ~43 chars
        assert session.user_id == seeded_admin.id
        # ~30 day TTL, allow some clock drift.
        delta = session.expires_at - before
        assert timedelta(days=29, hours=23) < delta <= timedelta(days=30, hours=1)

    def test_lookup_by_token_returns_the_session(
        self, db_session: Session, seeded_admin: AppUser
    ) -> None:
        session = create_session(db_session, seeded_admin)
        db_session.commit()

        found = (
            db_session.query(AppSession).filter_by(token=session.token).one()
        )
        assert found.user_id == seeded_admin.id

    def test_each_call_yields_unique_token(
        self, db_session: Session, seeded_admin: AppUser
    ) -> None:
        a = create_session(db_session, seeded_admin)
        b = create_session(db_session, seeded_admin)
        db_session.commit()
        assert a.token != b.token

    def test_cascade_delete_when_user_removed(
        self, db_session: Session, seeded_admin: AppUser
    ) -> None:
        # AppUser.sessions has cascade="all, delete-orphan" + FK ondelete=CASCADE.
        token = create_session(db_session, seeded_admin).token
        db_session.commit()

        db_session.delete(seeded_admin)
        db_session.commit()
        assert (
            db_session.query(AppSession).filter_by(token=token).one_or_none()
            is None
        )

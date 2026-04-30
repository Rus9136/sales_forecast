"""Invariants on `DEFAULT_ROLES` / `AVAILABLE_SECTIONS` plus serializer helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.auth_ui import (
    ALWAYS_GRANTED_SECTIONS,
    AVAILABLE_SECTIONS,
    DEFAULT_ROLES,
    serialize_role,
    serialize_user,
)


pytestmark = pytest.mark.unit


class TestDefaultRolesInvariants:
    def test_codes_are_unique(self):
        codes = [r["code"] for r in DEFAULT_ROLES]
        assert len(codes) == len(set(codes))

    def test_admin_role_has_all_sections(self):
        admin = next(r for r in DEFAULT_ROLES if r["code"] == "admin")
        assert set(admin["allowed_sections"]) == set(AVAILABLE_SECTIONS)

    def test_every_role_section_is_in_available_sections(self):
        available = set(AVAILABLE_SECTIONS)
        for role in DEFAULT_ROLES:
            unknown = set(role["allowed_sections"]) - available
            assert not unknown, (
                f"Role '{role['code']}' lists unknown sections: {unknown}. "
                f"Add them to AVAILABLE_SECTIONS or remove from the role."
            )

    def test_all_default_roles_marked_system(self):
        for role in DEFAULT_ROLES:
            assert role["is_system"] is True, (
                f"Role '{role['code']}' must be is_system=True — "
                "non-system roles should be created via the UI, not the seed."
            )

    def test_always_granted_sections_are_known(self):
        unknown = set(ALWAYS_GRANTED_SECTIONS) - set(AVAILABLE_SECTIONS)
        assert not unknown, f"Unknown always-granted sections: {unknown}"

    def test_available_sections_are_unique(self):
        assert len(AVAILABLE_SECTIONS) == len(set(AVAILABLE_SECTIONS))


class TestSerializeUser:
    def test_includes_role_allowed_sections(self):
        role = SimpleNamespace(
            name="Manager",
            allowed_sections=["sales.daily", "forecast.branches"],
            updated_at=None,
        )
        user = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            phone="77001234567",
            full_name="Test User",
            role_code="manager",
            role=role,
            is_active=True,
            created_at=None,
            last_login_at=None,
        )
        out = serialize_user(user)
        assert out["allowed_sections"] == ["sales.daily", "forecast.branches"]
        assert out["role_name"] == "Manager"
        assert out["role_code"] == "manager"
        assert out["phone"] == "77001234567"

    def test_handles_user_without_role(self):
        user = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000002",
            phone="77001234567",
            full_name="Orphan",
            role_code=None,
            role=None,
            is_active=True,
            created_at=None,
            last_login_at=None,
        )
        out = serialize_user(user)
        assert out["allowed_sections"] == []
        assert out["role_name"] is None

    def test_explicit_role_argument_overrides_relationship(self):
        bound_role = SimpleNamespace(name="Bound", allowed_sections=["a"], updated_at=None)
        override_role = SimpleNamespace(name="Override", allowed_sections=["b"], updated_at=None)
        user = SimpleNamespace(
            id="x", phone="77001234567", full_name="U", role_code="r",
            role=bound_role, is_active=True, created_at=None, last_login_at=None,
        )
        out = serialize_user(user, role=override_role)
        assert out["role_name"] == "Override"
        assert out["allowed_sections"] == ["b"]


class TestSerializeRole:
    def test_returns_expected_keys(self):
        role = SimpleNamespace(
            code="manager",
            name="Manager",
            allowed_sections=["sales.daily"],
            is_system=True,
            updated_at=None,
        )
        out = serialize_role(role)
        assert set(out.keys()) == {"code", "name", "allowed_sections", "is_system", "updated_at"}
        assert out["code"] == "manager"
        assert out["allowed_sections"] == ["sales.daily"]

    def test_handles_none_allowed_sections(self):
        role = SimpleNamespace(
            code="empty", name="E", allowed_sections=None, is_system=False, updated_at=None,
        )
        out = serialize_role(role)
        assert out["allowed_sections"] == []

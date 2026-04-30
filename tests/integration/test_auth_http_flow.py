"""HTTP integration tests for /api/auth/{login,me,logout}.

End-to-end against a real DB and FastAPI's TestClient. Covers the happy
flow and every error branch the SPA can hit at runtime.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.auth_ui import AppSession, AppUser

pytestmark = pytest.mark.integration


class TestLogin:
    def test_happy_path_returns_token_and_user(
        self, client_with_db, seeded_admin: AppUser, db_session: Session
    ) -> None:
        response = client_with_db.post(
            "/api/auth/login", json={"phone": "77001234567"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_token"]
        assert body["user"]["phone"] == "77001234567"
        assert body["user"]["role_code"] == "admin"
        assert body["user"]["role_name"] == "Администратор"
        # last_login_at was bumped.
        db_session.refresh(seeded_admin)
        assert seeded_admin.last_login_at is not None

    def test_normalizes_phone_with_legacy_8_prefix(
        self, client_with_db, seeded_admin: AppUser
    ) -> None:
        # 8XXX → 7XXX rewrite happens server-side.
        response = client_with_db.post(
            "/api/auth/login", json={"phone": "8 (700) 123-45-67"}
        )
        assert response.status_code == 200
        assert response.json()["user"]["phone"] == "77001234567"

    def test_unknown_phone_returns_401(self, client_with_db, seeded_roles) -> None:
        response = client_with_db.post(
            "/api/auth/login", json={"phone": "77999999999"}
        )
        assert response.status_code == 401

    def test_inactive_user_returns_403(
        self, client_with_db, seeded_admin: AppUser, db_session: Session
    ) -> None:
        seeded_admin.is_active = False
        db_session.commit()

        response = client_with_db.post(
            "/api/auth/login", json={"phone": "77001234567"}
        )
        assert response.status_code == 403

    def test_phone_with_no_digits_returns_400(
        self, client_with_db, seeded_roles
    ) -> None:
        # 4+ chars passes Pydantic min_length, but normalize_phone raises.
        response = client_with_db.post(
            "/api/auth/login", json={"phone": "++++"}
        )
        assert response.status_code == 400

    def test_too_short_phone_fails_pydantic_validation(
        self, client_with_db, seeded_roles
    ) -> None:
        # 3 chars — caught by Pydantic min_length=4 → 422.
        response = client_with_db.post("/api/auth/login", json={"phone": "ab"})
        assert response.status_code == 422


class TestMe:
    def test_returns_user_with_allowed_sections(
        self, client_with_db, seeded_admin: AppUser, session_token_for
    ) -> None:
        token = session_token_for(seeded_admin)
        response = client_with_db.get(
            "/api/auth/me", headers={"X-Session-Token": token}
        )
        assert response.status_code == 200
        body = response.json()["user"]
        assert body["phone"] == "77001234567"
        assert body["role_code"] == "admin"
        assert "users" in body["allowed_sections"]
        assert "roles" in body["allowed_sections"]

    def test_no_token_returns_401(self, client_with_db) -> None:
        response = client_with_db.get("/api/auth/me")
        assert response.status_code == 401

    def test_unknown_token_returns_401(
        self, client_with_db, seeded_roles
    ) -> None:
        response = client_with_db.get(
            "/api/auth/me", headers={"X-Session-Token": "totally-bogus"}
        )
        assert response.status_code == 401

    def test_authorization_session_scheme_works(
        self, client_with_db, seeded_admin: AppUser, session_token_for
    ) -> None:
        token = session_token_for(seeded_admin)
        response = client_with_db.get(
            "/api/auth/me", headers={"Authorization": f"Session {token}"}
        )
        assert response.status_code == 200

    def test_bearer_scheme_does_not_authenticate_session(
        self, client_with_db, seeded_admin: AppUser, session_token_for
    ) -> None:
        # Bearer is for API key auth — must not be accepted as session token.
        token = session_token_for(seeded_admin)
        response = client_with_db.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_expired_session_returns_401_and_deletes_row(
        self,
        client_with_db,
        seeded_admin: AppUser,
        db_session: Session,
    ) -> None:
        # Insert an already-expired session manually.
        from app.auth_ui import create_session

        session = create_session(db_session, seeded_admin)
        session.expires_at = datetime.utcnow() - timedelta(hours=1)
        db_session.commit()
        token = session.token

        response = client_with_db.get(
            "/api/auth/me", headers={"X-Session-Token": token}
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()
        # Best-effort cleanup happened.
        assert (
            db_session.query(AppSession).filter_by(token=token).one_or_none()
            is None
        )

    def test_inactive_user_session_returns_401(
        self,
        client_with_db,
        seeded_admin: AppUser,
        session_token_for,
        db_session: Session,
    ) -> None:
        token = session_token_for(seeded_admin)
        seeded_admin.is_active = False
        db_session.commit()

        response = client_with_db.get(
            "/api/auth/me", headers={"X-Session-Token": token}
        )
        assert response.status_code == 401


class TestLogout:
    def test_logout_invalidates_token(
        self,
        client_with_db,
        seeded_admin: AppUser,
        session_token_for,
        db_session: Session,
    ) -> None:
        token = session_token_for(seeded_admin)
        # Sanity check: token works pre-logout.
        assert client_with_db.get(
            "/api/auth/me", headers={"X-Session-Token": token}
        ).status_code == 200

        logout = client_with_db.post(
            "/api/auth/logout", headers={"X-Session-Token": token}
        )
        assert logout.status_code == 200
        assert logout.json() == {"ok": True}

        # Subsequent /me must fail.
        again = client_with_db.get(
            "/api/auth/me", headers={"X-Session-Token": token}
        )
        assert again.status_code == 401
        assert (
            db_session.query(AppSession).filter_by(token=token).one_or_none()
            is None
        )

    def test_logout_without_session_returns_401(self, client_with_db) -> None:
        # Logout requires a valid session — guarded by get_current_user.
        response = client_with_db.post("/api/auth/logout")
        assert response.status_code == 401

    def test_logout_only_kills_current_session_not_all(
        self,
        client_with_db,
        seeded_admin: AppUser,
        session_token_for,
        db_session: Session,
    ) -> None:
        # Two devices, one logout — the other must survive.
        token_a = session_token_for(seeded_admin)
        token_b = session_token_for(seeded_admin)

        client_with_db.post(
            "/api/auth/logout", headers={"X-Session-Token": token_a}
        )

        # token_b still works.
        assert client_with_db.get(
            "/api/auth/me", headers={"X-Session-Token": token_b}
        ).status_code == 200

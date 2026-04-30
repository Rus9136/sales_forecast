"""Unit tests for UI session auth: token extraction, `get_current_user`, `require_admin`.

`get_current_user` and `require_admin` are exercised with a `MagicMock`-based
DB session so we can verify all the 401/403 branches without standing up a
real Postgres test database (that comes in Stage 3).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth_ui import _extract_token, get_current_user, require_admin


pytestmark = pytest.mark.unit


class TestExtractToken:
    def test_x_session_token_header_is_used(self):
        assert _extract_token("abc123", None) == "abc123"

    def test_authorization_session_scheme_is_used(self):
        assert _extract_token(None, "Session abc123") == "abc123"

    def test_session_scheme_is_case_insensitive(self):
        assert _extract_token(None, "session abc123") == "abc123"
        assert _extract_token(None, "SESSION abc123") == "abc123"

    def test_x_session_token_takes_priority_over_authorization(self):
        assert _extract_token("primary", "Session secondary") == "primary"

    def test_bearer_scheme_is_ignored_for_ui_session(self):
        # Bearer is for API key auth, not UI sessions.
        assert _extract_token(None, "Bearer abc123") is None

    def test_returns_none_when_both_missing(self):
        assert _extract_token(None, None) is None

    def test_strips_whitespace_from_x_session_token(self):
        assert _extract_token("  abc123  ", None) == "abc123"


def _mock_db(session_row=None, user_row=None) -> MagicMock:
    """Build a MagicMock DB whose `db.query(...).filter(...).first()` returns,
    in order: the session row first, the user row second.
    """
    db = MagicMock()
    first_results = [session_row, user_row]

    def _filter(*_args, **_kwargs):
        chain = MagicMock()
        chain.first.side_effect = first_results.pop(0) if first_results else lambda: None
        # `first` here returns a value, not a callable — fix that:
        return chain

    # Simpler: track call count.
    call = {"i": 0}

    def query_chain(*_args, **_kwargs):
        chain = MagicMock()

        def first():
            i = call["i"]
            call["i"] += 1
            return [session_row, user_row][i] if i < 2 else None

        chain.filter.return_value.first.side_effect = first
        return chain

    db.query.side_effect = query_chain
    return db


class TestGetCurrentUser:
    def test_missing_token_raises_401(self):
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            get_current_user(x_session_token=None, authorization=None, db=db)
        assert exc.value.status_code == 401
        # No DB query should have been made.
        assert db.query.call_count == 0

    def test_unknown_token_raises_401(self):
        db = _mock_db(session_row=None, user_row=None)
        with pytest.raises(HTTPException) as exc:
            get_current_user(x_session_token="bogus", authorization=None, db=db)
        assert exc.value.status_code == 401
        assert "Invalid session" in exc.value.detail

    def test_expired_session_is_rejected_and_deleted(self):
        expired_session = SimpleNamespace(
            token="expired",
            user_id="u1",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db = _mock_db(session_row=expired_session, user_row=None)
        with pytest.raises(HTTPException) as exc:
            get_current_user(x_session_token="expired", authorization=None, db=db)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()
        # Best-effort cleanup: expired session was deleted + committed.
        db.delete.assert_called_once_with(expired_session)
        db.commit.assert_called_once()

    def test_inactive_user_is_rejected(self):
        valid_session = SimpleNamespace(
            token="t",
            user_id="u1",
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        inactive_user = SimpleNamespace(id="u1", is_active=False, role_code="manager")
        db = _mock_db(session_row=valid_session, user_row=inactive_user)
        with pytest.raises(HTTPException) as exc:
            get_current_user(x_session_token="t", authorization=None, db=db)
        assert exc.value.status_code == 401
        assert "inactive" in exc.value.detail.lower() or "removed" in exc.value.detail.lower()

    def test_valid_session_returns_user(self):
        valid_session = SimpleNamespace(
            token="t",
            user_id="u1",
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        active_user = SimpleNamespace(id="u1", is_active=True, role_code="manager")
        db = _mock_db(session_row=valid_session, user_row=active_user)
        result = get_current_user(x_session_token="t", authorization=None, db=db)
        assert result is active_user


class TestRequireAdmin:
    def test_admin_user_passes(self):
        admin = SimpleNamespace(role_code="admin", is_active=True)
        assert require_admin(user=admin) is admin

    def test_non_admin_raises_403(self):
        manager = SimpleNamespace(role_code="manager", is_active=True)
        with pytest.raises(HTTPException) as exc:
            require_admin(user=manager)
        assert exc.value.status_code == 403
        assert "admin" in exc.value.detail.lower()

    def test_viewer_raises_403(self):
        viewer = SimpleNamespace(role_code="viewer", is_active=True)
        with pytest.raises(HTTPException) as exc:
            require_admin(user=viewer)
        assert exc.value.status_code == 403

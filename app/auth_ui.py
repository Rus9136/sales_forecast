"""UI session authentication — phone-only login.

Provides FastAPI dependencies for endpoints under /api/auth/* and /api/users/*.
Sessions are stored in `app_session`; clients send the token via the
`X-Session-Token` header (or `Authorization: Session <token>`).
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .db import get_db
from .models.auth_ui import AppRole, AppSession, AppUser

SESSION_TTL = timedelta(days=30)


def normalize_phone(phone: str) -> str:
    """Strip everything except digits. Empty string raises ValueError."""
    if not phone:
        raise ValueError("phone is empty")
    digits = re.sub(r"\D+", "", phone)
    if not digits:
        raise ValueError("phone has no digits")
    # Treat 8XXXXXXXXXX as 7XXXXXXXXXX (Kazakhstan/Russia legacy prefix)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("phone length must be 10..15 digits")
    return digits


def create_session(db: Session, user: AppUser) -> AppSession:
    """Create a new session row and return it. Caller must commit."""
    token = secrets.token_urlsafe(32)  # ~43 chars, fits VARCHAR(64)
    session = AppSession(
        token=token,
        user_id=user.id,
        expires_at=datetime.utcnow() + SESSION_TTL,
    )
    db.add(session)
    return session


def _extract_token(
    x_session_token: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    if x_session_token:
        return x_session_token.strip()
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "session":
            return parts[1].strip()
    return None


def get_current_user(
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> AppUser:
    """Resolve current UI user from session token. Raises 401 if missing/invalid."""
    token = _extract_token(x_session_token, authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token required",
        )

    session = db.query(AppSession).filter(AppSession.token == token).first()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
    if session.expires_at < datetime.utcnow():
        # Best-effort cleanup
        db.delete(session)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    user = db.query(AppUser).filter(AppUser.id == session.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User inactive or removed",
        )
    return user


def require_admin(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role_code != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


def serialize_user(user: AppUser, role: Optional[AppRole] = None) -> dict:
    role_obj = role or user.role
    return {
        "id": str(user.id),
        "phone": user.phone,
        "full_name": user.full_name,
        "role_code": user.role_code,
        "role_name": role_obj.name if role_obj else None,
        "is_active": user.is_active,
        "allowed_sections": list(role_obj.allowed_sections) if role_obj else [],
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def serialize_role(role: AppRole) -> dict:
    return {
        "code": role.code,
        "name": role.name,
        "allowed_sections": list(role.allowed_sections or []),
        "is_system": role.is_system,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
    }


# All available section keys — used by frontend "Roles" editor as a fixed checklist
AVAILABLE_SECTIONS = [
    "departments",
    "employees",
    "sales.daily",
    "sales.hourly",
    "sales.waiters",
    "forecast.branches",
    "forecast.comparison",
    "bonus.calculations",
    "bonus.schemes",
    "bonus.manual-kpi",
    "bonus.monthly-plans",
    "ai.recommendations",
    "sync",
    "users",
    "roles",
]


DEFAULT_ROLES = [
    {
        "code": "admin",
        "name": "Администратор",
        "allowed_sections": list(AVAILABLE_SECTIONS),
        "is_system": True,
    },
    {
        "code": "manager",
        "name": "Менеджер",
        "allowed_sections": [
            "departments", "employees",
            "sales.daily", "sales.hourly", "sales.waiters",
            "forecast.branches", "forecast.comparison",
            "ai.recommendations", "sync",
        ],
        "is_system": True,
    },
    {
        "code": "accountant",
        "name": "Бухгалтер",
        "allowed_sections": [
            "departments", "employees",
            "sales.daily", "sales.waiters",
            "bonus.calculations", "bonus.schemes", "bonus.manual-kpi", "bonus.monthly-plans",
        ],
        "is_system": True,
    },
    {
        "code": "viewer",
        "name": "Наблюдатель",
        "allowed_sections": [
            "sales.daily", "sales.hourly",
            "forecast.branches", "forecast.comparison",
        ],
        "is_system": True,
    },
]


def seed_default_roles(db: Session) -> None:
    """Insert system roles if missing. Existing rows are not touched."""
    existing = {r.code for r in db.query(AppRole.code).all()}
    created = False
    for spec in DEFAULT_ROLES:
        if spec["code"] in existing:
            continue
        db.add(AppRole(
            code=spec["code"],
            name=spec["name"],
            allowed_sections=spec["allowed_sections"],
            is_system=spec["is_system"],
        ))
        created = True
    if created:
        db.commit()


def bootstrap_admin(db: Session, phone: Optional[str], full_name: Optional[str] = None) -> Optional[AppUser]:
    """If admin user does not exist and BOOTSTRAP_ADMIN_PHONE is set, create one.

    Returns the user if a new one was created, otherwise None.
    """
    if not phone:
        return None
    try:
        normalized = normalize_phone(phone)
    except ValueError:
        return None

    existing = db.query(AppUser).filter(AppUser.role_code == "admin").first()
    if existing is not None:
        return None

    same_phone = db.query(AppUser).filter(AppUser.phone == normalized).first()
    if same_phone is not None:
        # Promote existing user with that phone to admin
        same_phone.role_code = "admin"
        same_phone.is_active = True
        db.commit()
        return same_phone

    user = AppUser(
        id=uuid4(),
        phone=normalized,
        full_name=full_name or "Bootstrap Admin",
        role_code="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user

"""UI authentication and user/role management.

Endpoints under /api/auth/* (login/logout/me/roles) and /api/users/*
authenticate via session token (X-Session-Token header). They are
independent from the API_TOKEN-based auth used by all other routers.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth_ui import (
    AVAILABLE_SECTIONS,
    create_session,
    get_current_user,
    normalize_phone,
    require_admin,
    serialize_role,
    serialize_user,
)
from ..db import get_db
from ..models.auth_ui import AppRole, AppSession, AppUser

ui_auth_router = APIRouter(prefix="/auth", tags=["ui-auth"])
ui_users_router = APIRouter(prefix="/users", tags=["ui-users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    phone: str = Field(..., min_length=4, max_length=32)


class LoginResponse(BaseModel):
    session_token: str
    expires_at: datetime
    user: dict


class MeResponse(BaseModel):
    user: dict


class RoleUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    allowed_sections: Optional[List[str]] = None


class UserCreateRequest(BaseModel):
    phone: str = Field(..., min_length=4, max_length=32)
    full_name: Optional[str] = Field(default=None, max_length=255)
    role_code: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    role_code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    is_active: Optional[bool] = None
    phone: Optional[str] = Field(default=None, min_length=4, max_length=32)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_sections(sections: List[str]) -> List[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in sections:
        if not isinstance(raw, str):
            raise HTTPException(status_code=400, detail="allowed_sections must be strings")
        s = raw.strip()
        if not s:
            continue
        if s not in AVAILABLE_SECTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown section '{s}'. Available: {AVAILABLE_SECTIONS}",
            )
        if s not in seen:
            seen.add(s)
            cleaned.append(s)
    return cleaned


def _ensure_role_exists(db: Session, code: str) -> AppRole:
    role = db.query(AppRole).filter(AppRole.code == code).first()
    if role is None:
        raise HTTPException(status_code=400, detail=f"Role '{code}' does not exist")
    return role


# ---------------------------------------------------------------------------
# Auth: login / logout / me
# ---------------------------------------------------------------------------

@ui_auth_router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        phone = normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = db.query(AppUser).filter(AppUser.phone == phone).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись отключена")

    session = create_session(db, user)
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    db.refresh(user)
    return LoginResponse(
        session_token=session.token,
        expires_at=session.expires_at,
        user=serialize_user(user),
    )


@ui_auth_router.post("/logout")
def logout(
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    authorization: Optional[str] = Header(default=None),
):
    token = x_session_token
    if not token and authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "session":
            token = parts[1].strip()
    if token:
        db.query(AppSession).filter(
            AppSession.token == token, AppSession.user_id == user.id
        ).delete(synchronize_session=False)
        db.commit()
    return {"ok": True}


@ui_auth_router.get("/me", response_model=MeResponse)
def me(user: AppUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=serialize_user(user))


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@ui_auth_router.get("/roles")
def list_roles(
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
):
    roles = db.query(AppRole).order_by(AppRole.code).all()
    return {
        "roles": [serialize_role(r) for r in roles],
        "available_sections": AVAILABLE_SECTIONS,
    }


@ui_auth_router.put("/roles/{code}")
def update_role(
    code: str,
    body: RoleUpdateRequest,
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin),
):
    role = _ensure_role_exists(db, code)
    if body.name is not None:
        if role.is_system and body.name != role.name:
            raise HTTPException(status_code=400, detail="Cannot rename a system role")
        role.name = body.name
    if body.allowed_sections is not None:
        role.allowed_sections = _validate_sections(body.allowed_sections)
    db.commit()
    db.refresh(role)
    return serialize_role(role)


# ---------------------------------------------------------------------------
# Users CRUD (admin only)
# ---------------------------------------------------------------------------

@ui_users_router.get("/")
def list_users(
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin),
):
    users = db.query(AppUser).order_by(AppUser.created_at.desc()).all()
    role_map = {r.code: r for r in db.query(AppRole).all()}
    return [serialize_user(u, role_map.get(u.role_code)) for u in users]


@ui_users_router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateRequest,
    db: Session = Depends(get_db),
    _: AppUser = Depends(require_admin),
):
    try:
        phone = normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    role = _ensure_role_exists(db, body.role_code)

    user = AppUser(
        id=uuid4(),
        phone=phone,
        full_name=(body.full_name or None),
        role_code=role.code,
        is_active=body.is_active,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с таким телефоном уже существует")
    db.refresh(user)
    return serialize_user(user, role)


@ui_users_router.put("/{user_id}")
def update_user(
    user_id: UUID,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    current: AppUser = Depends(require_admin),
):
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if body.phone is not None:
        try:
            user.phone = normalize_phone(body.phone)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.full_name is not None:
        user.full_name = body.full_name or None

    if body.role_code is not None:
        role = _ensure_role_exists(db, body.role_code)
        # Prevent admin demoting themselves if they are the last admin
        if user.id == current.id and role.code != "admin":
            other_admins = (
                db.query(AppUser)
                .filter(AppUser.role_code == "admin", AppUser.id != current.id, AppUser.is_active.is_(True))
                .count()
            )
            if other_admins == 0:
                raise HTTPException(status_code=400, detail="Нельзя снять роль admin с последнего администратора")
        user.role_code = role.code

    if body.is_active is not None:
        if user.id == current.id and not body.is_active:
            raise HTTPException(status_code=400, detail="Нельзя деактивировать собственную учётную запись")
        user.is_active = body.is_active
        if not body.is_active:
            # Drop all active sessions of the disabled user
            db.query(AppSession).filter(AppSession.user_id == user.id).delete(synchronize_session=False)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с таким телефоном уже существует")
    db.refresh(user)
    return serialize_user(user)


@ui_users_router.delete("/{user_id}")
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current: AppUser = Depends(require_admin),
):
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить собственную учётную запись")
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    db.delete(user)
    db.commit()
    return {"ok": True}

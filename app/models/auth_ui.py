"""UI authentication models — phone-based login + editable roles.

Distinct from app/auth.py (API key auth for backend endpoints).
This module powers the frontend login screen and role-based section
visibility in the React SPA.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from ..db import Base


class AppRole(Base):
    __tablename__ = "app_role"

    code = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    allowed_sections = Column(JSONB, nullable=False, default=list)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("AppUser", back_populates="role")


class AppUser(Base):
    __tablename__ = "app_user"

    id = Column(UUID(as_uuid=True), primary_key=True)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    role_code = Column(String(50), ForeignKey("app_role.code", onupdate="CASCADE"), nullable=False)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    role = relationship("AppRole", back_populates="users")
    sessions = relationship("AppSession", back_populates="user", cascade="all, delete-orphan")


class AppSession(Base):
    __tablename__ = "app_session"

    token = Column(String(64), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("AppUser", back_populates="sessions")

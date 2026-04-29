from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, ForeignKey,
    UniqueConstraint, Text, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from ...db import Base


class BonusTeam(Base):
    __tablename__ = "bonus_team"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    positions = relationship("BonusTeamPosition", back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("department_id", "code", name="uq_bonus_team_dept_code"),)


class BonusTeamPosition(Base):
    __tablename__ = "bonus_team_position"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("bonus_team.id", ondelete="CASCADE"), nullable=False, index=True)
    position_id = Column(Integer, ForeignKey("bonus_position.id"), nullable=False)
    slot = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=True)
    distribution_weight = Column(Numeric(8, 6), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    team = relationship("BonusTeam", back_populates="positions")
    position = relationship("BonusPosition")

    __table_args__ = (
        UniqueConstraint("team_id", "slot", "effective_from", name="uq_bonus_team_position_slot"),
    )

from sqlalchemy import (
    Column, Integer, String, DateTime, Date, ForeignKey, Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from ...db import Base


class BonusScheme(Base):
    __tablename__ = "bonus_scheme"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    position_id = Column(Integer, ForeignKey("bonus_position.id"), nullable=True)
    team_id = Column(Integer, ForeignKey("bonus_team.id"), nullable=True)
    calculation_model = Column(String(50), nullable=False)
    config = Column(JSONB, nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    position = relationship("BonusPosition")
    team = relationship("BonusTeam")

from sqlalchemy import (
    Column, Integer, String, DateTime, Date, ForeignKey, Text, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from ...db import Base


class BonusEmployeeAssignment(Base):
    __tablename__ = "bonus_employee_assignment"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    position_id = Column(Integer, ForeignKey("bonus_position.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("bonus_team.id"), nullable=True, index=True)
    team_position_slot = Column(String(100), nullable=True)
    employment_type = Column(String(30), default="permanent", nullable=False)
    probation_until = Column(Date, nullable=True)
    base_salary = Column(Numeric(14, 2), nullable=True)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    position = relationship("BonusPosition")
    team = relationship("BonusTeam")

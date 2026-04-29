from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, SmallInteger, Boolean,
    Text, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from ...db import Base


class BonusCalculation(Base):
    __tablename__ = "bonus_calculation"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    period_year = Column(SmallInteger, nullable=False)
    period_month = Column(SmallInteger, nullable=False)

    scheme_id = Column(Integer, ForeignKey("bonus_scheme.id"), nullable=False)
    scheme_version = Column(Integer, nullable=False)
    scheme_config_snapshot = Column(JSONB, nullable=False)

    team_id = Column(Integer, ForeignKey("bonus_team.id"), nullable=True)
    team_position_slot = Column(String(100), nullable=True)

    kpi_values = Column(JSONB, nullable=True)
    overall_kpi_percent = Column(Numeric(7, 4), nullable=True)

    applied_grade_from = Column(Numeric(5, 2), nullable=True)
    applied_grade_to = Column(Numeric(5, 2), nullable=True)
    applied_coefficient = Column(Numeric(14, 6), nullable=True)
    coefficient_type = Column(String(20), nullable=True)

    revenue_used = Column(Numeric(14, 2), nullable=True)
    revenue_source_used = Column(String(80), nullable=True)
    shifts_worked = Column(Numeric(6, 2), nullable=True)
    shifts_norm = Column(Numeric(6, 2), nullable=True)
    shifts_proration_applied = Column(Boolean, default=False, nullable=False)

    base_bonus = Column(Numeric(14, 2), nullable=False)
    penalties_amount = Column(Numeric(14, 2), default=0, nullable=False)
    final_bonus = Column(Numeric(14, 2), nullable=False)

    breakdown = Column(JSONB, nullable=False)

    status = Column(String(30), default="draft", nullable=False, index=True)

    calculated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    calculated_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(100), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    scheme = relationship("BonusScheme")
    team = relationship("BonusTeam")
    penalties = relationship("BonusCalculationPenalty", back_populates="calculation",
                             cascade="all, delete-orphan")


class BonusCalculationPenalty(Base):
    __tablename__ = "bonus_calculation_penalty"

    id = Column(Integer, primary_key=True, index=True)
    calculation_id = Column(Integer, ForeignKey("bonus_calculation.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    reason_code = Column(String(80), nullable=False)
    reason_text = Column(Text, nullable=False)
    penalty_percent = Column(Numeric(5, 2), nullable=True)
    penalty_amount = Column(Numeric(14, 2), nullable=False)
    document_ref = Column(String(200), nullable=True)
    applied_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    applied_by = Column(String(100), nullable=True)

    calculation = relationship("BonusCalculation", back_populates="penalties")

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, SmallInteger,
    UniqueConstraint, Text, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from ...db import Base


class BonusKpiDefinition(Base):
    __tablename__ = "bonus_kpi_definition"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    data_source_code = Column(String(80), nullable=False)
    direction = Column(String(30), nullable=False)
    default_target = Column(Numeric(14, 4), nullable=True)
    target_metric = Column(String(80), nullable=True)
    cap_at_100_percent = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class BonusManualKpi(Base):
    __tablename__ = "bonus_manual_kpi"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    kpi_code = Column(String(80), nullable=False, index=True)
    period_year = Column(SmallInteger, nullable=False)
    period_month = Column(SmallInteger, nullable=False)
    fact_value = Column(Numeric(14, 4), nullable=False)
    notes = Column(Text, nullable=True)
    document_ref = Column(String(200), nullable=True)
    entered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    entered_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint("department_id", "kpi_code", "period_year", "period_month",
                         name="uq_bonus_manual_kpi_period"),
    )

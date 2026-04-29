from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, SmallInteger,
    UniqueConstraint, Text, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from ...db import Base


class BonusMonthlyPlan(Base):
    __tablename__ = "bonus_monthly_plan"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    metric = Column(String(80), nullable=False)
    year = Column(SmallInteger, nullable=False)
    month = Column(SmallInteger, nullable=False)
    target_value = Column(Numeric(14, 2), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("department_id", "metric", "year", "month",
                         name="uq_bonus_monthly_plan_period"),
    )

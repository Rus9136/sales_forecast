"""Legacy Branch/Sale models and backward-compatible re-exports."""

from sqlalchemy import Column, String, ForeignKey, DateTime, Float, Integer, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from ..db import Base

# Re-export all models so existing `from ..models.branch import X` imports keep working.
from .department import Department  # noqa: F401
from .sales import SalesSummary, SalesByHour, AutoSyncLog  # noqa: F401
from .forecast import Forecast, ForecastAccuracyLog, PostprocessingSettings  # noqa: F401
from .ml import ModelVersion, ModelRetrainingLog  # noqa: F401
from .employee import Employee, SalesByWaiter  # noqa: F401


class Branch(Base):
    __tablename__ = "branches"

    branch_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("branches.branch_id"), nullable=True)
    organization_name = Column(String, nullable=False)
    organization_bin = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sales = relationship("Sale", back_populates="branch")
    forecasts = relationship("Forecast", back_populates="branch")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(String, ForeignKey("branches.branch_id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    branch = relationship("Branch", back_populates="sales")

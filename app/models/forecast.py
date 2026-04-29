from sqlalchemy import Column, String, ForeignKey, DateTime, Float, Integer, Date, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..db import Base


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(String, ForeignKey("branches.branch_id"), nullable=False)
    forecast_date = Column(Date, nullable=False, index=True)
    predicted_amount = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    branch = relationship("Branch", back_populates="forecasts")


class ForecastAccuracyLog(Base):
    __tablename__ = "forecast_accuracy_log"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(String, ForeignKey("branches.branch_id"), nullable=False)
    forecast_date = Column(Date, nullable=False)
    predicted_amount = Column(Float, nullable=False)
    actual_amount = Column(Float, nullable=True)
    mae = Column(Float, nullable=True)
    mape = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PostprocessingSettings(Base):
    __tablename__ = "postprocessing_settings"

    id = Column(Integer, primary_key=True, index=True)

    enable_smoothing = Column(Boolean, default=True, nullable=False)
    max_change_percent = Column(Float, default=50.0, nullable=False)

    enable_business_rules = Column(Boolean, default=True, nullable=False)
    enable_weekend_adjustment = Column(Boolean, default=True, nullable=False)
    enable_holiday_adjustment = Column(Boolean, default=True, nullable=False)

    enable_anomaly_detection = Column(Boolean, default=True, nullable=False)
    anomaly_threshold = Column(Float, default=3.0, nullable=False)

    enable_confidence = Column(Boolean, default=True, nullable=False)
    confidence_level = Column(Float, default=0.95, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

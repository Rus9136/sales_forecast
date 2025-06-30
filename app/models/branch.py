from sqlalchemy import Column, String, ForeignKey, DateTime, Float, Integer, Date, CheckConstraint, Text, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from ..db import Base


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


class Department(Base):
    __tablename__ = "departments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True)
    code = Column(String(50), nullable=True, index=True)
    code_tco = Column(String(50), nullable=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), default='DEPARTMENT', index=True)
    taxpayer_id_number = Column(String(50), nullable=True)
    
    # New segmentation and seasonal fields
    segment_type = Column(
        String(50), 
        default='restaurant', 
        index=True,
        nullable=True
    )
    season_start_date = Column(Date, nullable=True)
    season_end_date = Column(Date, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)
    
    # Self-referential relationship for hierarchy
    children = relationship("Department", back_populates="parent")
    parent = relationship("Department", back_populates="children", remote_side=[id])
    
    # Check constraint for segment_type (already exists in DB)
    __table_args__ = (
        CheckConstraint(
            segment_type.in_([
                'coffeehouse',      # кофейня
                'restaurant',       # ресторан  
                'confectionery',    # кондитерская
                'food_court',       # фудкорт в ТРЦ
                'store',            # магазин
                'fast_food',        # фаст-фуд
                'bakery',           # пекарня
                'cafe',             # кафе
                'bar'               # бар
            ]),
            name='valid_segment_type'
        ),
    )


class SalesSummary(Base):
    __tablename__ = "sales_summary"
    
    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    total_sales = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to Department
    department = relationship("Department")
    
    # Unique constraint to prevent duplicate records per department per day
    __table_args__ = (
        {"schema": None},
    )


class SalesByHour(Base):
    __tablename__ = "sales_by_hour"
    
    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    hour = Column(Integer, nullable=False, index=True)
    sales_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to Department
    department = relationship("Department")
    
    # Unique constraint to prevent duplicate records per department per day per hour
    __table_args__ = (
        {"schema": None},
    )


class AutoSyncLog(Base):
    __tablename__ = "auto_sync_log"
    
    id = Column(Integer, primary_key=True, index=True)
    sync_date = Column(Date, nullable=False, index=True)
    sync_type = Column(String(50), nullable=False)  # 'daily_auto', 'manual', etc.
    status = Column(String(20), nullable=False, index=True)  # 'success', 'error'
    message = Column(String(500), nullable=True)
    summary_records = Column(Integer, default=0)
    hourly_records = Column(Integer, default=0) 
    total_raw_records = Column(Integer, default=0)
    error_details = Column(String(1000), nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(String(100), nullable=False, unique=True, index=True)
    model_type = Column(String(50), nullable=False)  # 'LGBMRegressor', etc.
    is_active = Column(Boolean, default=False, index=True)
    
    # Training details
    training_date = Column(DateTime, nullable=False)
    training_end_date = Column(DateTime, nullable=True)
    deployment_date = Column(DateTime, nullable=True)
    n_features = Column(Integer, nullable=False)
    n_samples = Column(Integer, nullable=False)
    training_days = Column(Integer, nullable=False)
    outlier_method = Column(String(50), nullable=True)
    
    # Performance metrics
    train_mape = Column(Float, nullable=True)
    validation_mape = Column(Float, nullable=True)
    test_mape = Column(Float, nullable=True)
    train_r2 = Column(Float, nullable=True)
    validation_r2 = Column(Float, nullable=True)
    test_r2 = Column(Float, nullable=True)
    
    # Model details
    hyperparameters = Column(Text, nullable=True)
    top_features = Column(Text, nullable=True)
    feature_names = Column(Text, nullable=True)
    model_path = Column(String(255), nullable=False)
    model_size_mb = Column(Float, nullable=True)
    
    # Status and metadata
    status = Column(String(50), nullable=False, index=True)  # 'trained', 'deployed', 'rejected', 'archived'
    created_by = Column(String(50), nullable=False)  # 'scheduled', 'manual', 'performance_degradation'
    created_at = Column(DateTime, default=datetime.utcnow)
    

class ModelRetrainingLog(Base):
    __tablename__ = "model_retraining_log"
    
    id = Column(Integer, primary_key=True, index=True)
    retrain_date = Column(DateTime, nullable=False, index=True)
    trigger_type = Column(String(50), nullable=False, index=True)  # 'scheduled', 'manual', 'performance_degradation'
    trigger_details = Column(Text, nullable=True)
    
    # Model versions
    previous_version_id = Column(String(100), nullable=True)
    previous_mape = Column(Float, nullable=True)
    new_version_id = Column(String(100), nullable=False)
    new_mape = Column(Float, nullable=False)
    mape_improvement = Column(Float, nullable=True)
    
    # Decision details
    decision = Column(String(50), nullable=False, index=True)  # 'deployed', 'rejected'
    decision_reason = Column(Text, nullable=True)
    execution_time_seconds = Column(Integer, nullable=True)
    
    # Status and error handling
    status = Column(String(50), nullable=False, index=True)  # 'completed', 'failed'
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PostprocessingSettings(Base):
    __tablename__ = "postprocessing_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Smoothing settings
    enable_smoothing = Column(Boolean, default=True, nullable=False)
    max_change_percent = Column(Float, default=50.0, nullable=False)
    
    # Business rules settings
    enable_business_rules = Column(Boolean, default=True, nullable=False)
    enable_weekend_adjustment = Column(Boolean, default=True, nullable=False)
    enable_holiday_adjustment = Column(Boolean, default=True, nullable=False)
    
    # Anomaly detection settings
    enable_anomaly_detection = Column(Boolean, default=True, nullable=False)
    anomaly_threshold = Column(Float, default=3.0, nullable=False)
    
    # Confidence intervals settings
    enable_confidence = Column(Boolean, default=True, nullable=False)
    confidence_level = Column(Float, default=0.95, nullable=False)
    
    # Metadata
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
from sqlalchemy import Column, String, DateTime, Float, Integer, Text, Boolean
from datetime import datetime
from ..db import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(String(100), nullable=False, unique=True, index=True)
    model_type = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=False, index=True)

    training_date = Column(DateTime, nullable=False)
    training_end_date = Column(DateTime, nullable=True)
    deployment_date = Column(DateTime, nullable=True)
    n_features = Column(Integer, nullable=False)
    n_samples = Column(Integer, nullable=False)
    training_days = Column(Integer, nullable=False)
    outlier_method = Column(String(50), nullable=True)

    train_mape = Column(Float, nullable=True)
    validation_mape = Column(Float, nullable=True)
    test_mape = Column(Float, nullable=True)
    train_r2 = Column(Float, nullable=True)
    validation_r2 = Column(Float, nullable=True)
    test_r2 = Column(Float, nullable=True)

    hyperparameters = Column(Text, nullable=True)
    top_features = Column(Text, nullable=True)
    feature_names = Column(Text, nullable=True)
    model_path = Column(String(255), nullable=False)
    model_size_mb = Column(Float, nullable=True)

    status = Column(String(50), nullable=False, index=True)
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    revenue_basis = Column(String(20), nullable=True)  # 'price' | 'paid' — база выручки, на которой обучена модель


class ModelRetrainingLog(Base):
    __tablename__ = "model_retraining_log"

    id = Column(Integer, primary_key=True, index=True)
    retrain_date = Column(DateTime, nullable=False, index=True)
    trigger_type = Column(String(50), nullable=False, index=True)
    trigger_details = Column(Text, nullable=True)

    previous_version_id = Column(String(100), nullable=True)
    previous_mape = Column(Float, nullable=True)
    new_version_id = Column(String(100), nullable=False)
    new_mape = Column(Float, nullable=False)
    mape_improvement = Column(Float, nullable=True)

    decision = Column(String(50), nullable=False, index=True)
    decision_reason = Column(Text, nullable=True)
    execution_time_seconds = Column(Integer, nullable=True)

    status = Column(String(50), nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

from sqlalchemy import Column, String, ForeignKey, DateTime, Float, Integer, Date
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)
    
    # Self-referential relationship for hierarchy
    children = relationship("Department", back_populates="parent")
    parent = relationship("Department", back_populates="children", remote_side=[id])


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
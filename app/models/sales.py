from sqlalchemy import Column, String, ForeignKey, DateTime, Float, Integer, Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from ..db import Base


class SalesSummary(Base):
    __tablename__ = "sales_summary"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    total_sales = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department")

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

    department = relationship("Department")

    __table_args__ = (
        {"schema": None},
    )


class AutoSyncLog(Base):
    __tablename__ = "auto_sync_log"

    id = Column(Integer, primary_key=True, index=True)
    sync_date = Column(Date, nullable=False, index=True)
    sync_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    message = Column(String(500), nullable=True)
    summary_records = Column(Integer, default=0)
    hourly_records = Column(Integer, default=0)
    total_raw_records = Column(Integer, default=0)
    error_details = Column(String(1000), nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

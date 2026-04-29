from sqlalchemy import Column, String, ForeignKey, DateTime, Float, Date, Boolean, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from ..db import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    code = Column(String(50), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    login = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    middle_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    main_role_code = Column(String(50), nullable=True, index=True)
    main_role_id = Column(UUID(as_uuid=True), nullable=True)
    main_role_name = Column(String(255), nullable=True, index=True)
    role_codes = Column(JSON, nullable=True)
    department_codes = Column(JSON, nullable=True)
    preferred_department_code = Column(String(50), nullable=True, index=True)
    cell_phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    hire_date = Column(Date, nullable=True)
    fire_date = Column(Date, nullable=True)
    deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)


class SalesByWaiter(Base):
    __tablename__ = "sales_by_waiter"

    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), primary_key=True)
    date = Column(Date, primary_key=True)
    waiter_name = Column(String(255), primary_key=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True, index=True)
    total_sales = Column(Float, nullable=False)
    total_sales_with_discount = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department")
    employee = relationship("Employee")

    __table_args__ = (
        Index("ix_sales_by_waiter_date", "date"),
        Index("ix_sales_by_waiter_dept_date", "department_id", "date"),
    )

"""Receipt and ReceiptItem models — partitioned by open_date.

Relationships between Receipt and ReceiptItem are managed in application
code (not via SQLAlchemy relationship()) to avoid complications with
composite FKs across partitioned tables.
"""

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, Integer, Numeric, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID

from ..db import Base


class Receipt(Base):
    __tablename__ = "receipt"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    open_date = Column(Date, primary_key=True, nullable=False)
    order_num = Column(Integer, nullable=False)
    open_time = Column(DateTime)
    close_time = Column(DateTime, nullable=False)
    order_type = Column(Text)
    table_num = Column(Text)
    waiter_name = Column(Text)
    waiter_employee_id = Column(UUID(as_uuid=True))
    guest_num = Column(Integer)
    total_sum = Column(Numeric(14, 2), nullable=False, default=0)
    discount_sum = Column(Numeric(14, 2), nullable=False, default=0)
    return_sum = Column(Numeric(14, 2), nullable=False, default=0)
    items_count = Column(Integer, nullable=False, default=0)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = {"postgresql_partition_by": "RANGE (open_date)"}


class ReceiptItem(Base):
    __tablename__ = "receipt_item"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    receipt_id = Column(BigInteger, nullable=False)
    open_date = Column(Date, primary_key=True, nullable=False)
    product_id = Column(BigInteger, nullable=True)
    iiko_dish_id = Column(UUID(as_uuid=True))
    dish_name = Column(Text, nullable=False)
    dish_code = Column(Text)
    dish_group = Column(Text)
    dish_category = Column(Text)
    qty = Column(Numeric(12, 3), nullable=False)
    price_per_unit = Column(Numeric(14, 2))
    dish_sum = Column(Numeric(14, 2), nullable=False, default=0)
    discount_sum = Column(Numeric(14, 2), nullable=False, default=0)
    return_sum = Column(Numeric(14, 2), nullable=False, default=0)
    cost_price = Column(Numeric(14, 2))
    food_cost_percent = Column(Numeric(7, 4))

    __table_args__ = {"postgresql_partition_by": "RANGE (open_date)"}

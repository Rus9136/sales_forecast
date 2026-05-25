"""SKU-level daily sales aggregation and forecast storage."""

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, Integer, Numeric, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID

from ..db import Base


class SkuDailySales(Base):
    __tablename__ = "sku_daily_sales"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    sale_date = Column(Date, nullable=False, index=True)
    total_qty = Column(Numeric(14, 3), nullable=False, default=0)
    total_sum = Column(Numeric(16, 2), nullable=False, default=0)
    receipt_count = Column(Integer, nullable=False, default=0)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class SkuForecast(Base):
    __tablename__ = "sku_forecasts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    forecast_date = Column(Date, nullable=False)
    predicted_qty = Column(Numeric(12, 3), nullable=False)
    model_version = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

"""Pricing analytics models: price history, SKU weekly, department weekly, menu roles."""

from sqlalchemy import (
    Boolean, BigInteger, Column, Computed, Date, DateTime, Integer, Numeric, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..db import Base


class SkuPriceHistory(Base):
    __tablename__ = "sku_price_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    department_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    price = Column(Numeric(14, 2), nullable=False)
    prev_price = Column(Numeric(14, 2))
    change_pct = Column(Numeric(10, 4))
    first_seen_date = Column(Date, nullable=False)
    last_seen_date = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class SkuCatalogPrice(Base):
    """Real menu prices from iiko orders (GET /resto/api/v2/price)."""
    __tablename__ = "sku_catalog_price"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_id = Column(UUID(as_uuid=True), nullable=False)
    iiko_product_id = Column(UUID(as_uuid=True), nullable=False)
    product_id = Column(BigInteger)
    product_size_id = Column(UUID(as_uuid=True))
    price = Column(Numeric(14, 2), nullable=False)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    price_type = Column(Text, nullable=False, default="BASE")
    document_id = Column(UUID(as_uuid=True))
    included = Column(Boolean)
    is_dish_of_day = Column(Boolean)
    iiko_source_domain = Column(Text)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class SkuWeeklySummary(Base):
    __tablename__ = "sku_weekly_summary"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    department_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)
    total_qty = Column(Numeric(14, 3), nullable=False, default=0)
    total_revenue = Column(Numeric(16, 2), nullable=False, default=0)
    total_cost = Column(Numeric(16, 2), nullable=False, default=0)
    gross_profit = Column(Numeric(16, 2), nullable=False, default=0)
    gp_margin = Column(Numeric(7, 4))
    avg_price = Column(Numeric(14, 2))
    avg_daily_qty = Column(Numeric(14, 3))
    unique_receipts = Column(Integer, nullable=False, default=0)
    days_with_sales = Column(Integer, nullable=False, default=0)
    qty_cv = Column(Numeric(7, 4))
    cost_coverage = Column(Numeric(7, 4))
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class DepartmentWeeklySummary(Base):
    __tablename__ = "department_weekly_summary"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)
    total_revenue = Column(Numeric(16, 2), nullable=False, default=0)
    total_cost = Column(Numeric(16, 2), nullable=False, default=0)
    gross_profit = Column(Numeric(16, 2), nullable=False, default=0)
    gp_margin = Column(Numeric(7, 4))
    total_receipts = Column(Integer, nullable=False, default=0)
    avg_receipt_sum = Column(Numeric(14, 2))
    unique_guests = Column(Integer, nullable=False, default=0)
    cost_coverage = Column(Numeric(7, 4))
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class SkuMenuRole(Base):
    __tablename__ = "sku_menu_role"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    department_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    auto_role = Column(Text, nullable=False)
    manual_role = Column(Text)
    effective_role = Column(
        Text, Computed("COALESCE(manual_role, auto_role)", persisted=True),
    )
    features = Column(JSONB)
    cluster_meta = Column(JSONB)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class PricingReport(Base):
    """C4: сгенерированный LLM еженедельный/ежемесячный отчёт по ценообразованию.

    `department_id IS NULL` → отчёт уровня сети (network); иначе — по точке.
    `data` — снимок собранных метрик за период (для воспроизводимости),
    `kpis` — заголовочные KPI, `narrative` — текст от LLM.
    """

    __tablename__ = "pricing_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    report_type = Column(Text, nullable=False)               # 'weekly' | 'monthly'
    scope = Column(Text, nullable=False, default="network")  # 'network' | 'department'
    department_id = Column(UUID(as_uuid=True), index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    data = Column(JSONB, nullable=False)
    kpis = Column(JSONB)
    narrative = Column(Text)
    provider = Column(Text, nullable=False, default="claude")
    model = Column(Text)
    status = Column(Text, nullable=False, default="ok")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)

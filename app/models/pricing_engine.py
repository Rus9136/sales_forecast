"""Pricing engine models: elasticity, rules, recommendations."""

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Integer, Numeric, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from ..db import Base


class SkuElasticity(Base):
    __tablename__ = "sku_elasticity"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, nullable=False)
    department_id = Column(UUID(as_uuid=True), nullable=False)
    elasticity_mean = Column(Numeric(8, 4), nullable=False)
    elasticity_ci_lower = Column(Numeric(8, 4), nullable=False)
    elasticity_ci_upper = Column(Numeric(8, 4), nullable=False)
    elasticity_se = Column(Numeric(8, 4))
    n_price_events = Column(Integer, nullable=False, default=0)
    n_observations = Column(Integer, nullable=False, default=0)
    estimation_level = Column(Text, nullable=False)
    reliability_grade = Column(Text, nullable=False)
    group_key = Column(Text)
    model_r_squared = Column(Numeric(6, 4))
    model_version = Column(Text, nullable=False)
    diagnostics = Column(JSONB)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class PricingRule(Base):
    __tablename__ = "pricing_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_type = Column(Text, nullable=False)
    scope_type = Column(Text, nullable=False)
    scope_id = Column(Text)
    params = Column(JSONB, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    configured_by_role = Column(Text)
    effective_from = Column(Date, nullable=False, server_default=func.current_date())
    effective_to = Column(Date)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime)


class PriceRecommendation(Base):
    __tablename__ = "price_recommendation"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, nullable=False)
    department_id = Column(UUID(as_uuid=True), nullable=False)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    current_price = Column(Numeric(14, 2), nullable=False)
    recommended_price = Column(Numeric(14, 2), nullable=False)
    delta_pct = Column(Numeric(6, 2))
    cogs = Column(Numeric(14, 2))
    current_qty_forecast = Column(Numeric(12, 3))
    new_qty_forecast = Column(Numeric(12, 3))
    current_gp = Column(Numeric(14, 2))
    expected_gp = Column(Numeric(14, 2))
    delta_gp = Column(Numeric(14, 2))
    elasticity_used = Column(Numeric(8, 4))
    elasticity_grade = Column(Text)
    menu_role = Column(Text)
    constraints_applied = Column(ARRAY(Text))
    llm_explanation = Column(Text)
    status = Column(Text, nullable=False, default="new")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)
    review_comment = Column(Text)

"""Pricing engine models: elasticity, rules, recommendations, outcomes, baseline, audit."""

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from ..db import Base


class SkuElasticity(Base):
    __tablename__ = "sku_elasticity"
    __table_args__ = (
        UniqueConstraint("product_id", "department_id"),
    )

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
    __table_args__ = (
        UniqueConstraint("rule_type", "scope_type", "scope_id"),
        # глобальные правила: scope_id IS NULL не ловится обычным UNIQUE
        Index(
            "uq_pricing_rule_global", "rule_type",
            unique=True,
            postgresql_where=text("scope_type = 'global' AND scope_id IS NULL"),
        ),
    )

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
    __table_args__ = (
        UniqueConstraint("batch_id", "product_id", "department_id"),
        # не больше одной открытой рекомендации на SKU (миграция 029)
        Index(
            "uq_price_rec_open", "product_id", "department_id",
            unique=True,
            postgresql_where=text("status = 'new'"),
        ),
    )

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
    rec_type = Column(Text, nullable=False, default="optimizer", server_default=text("'optimizer'"))
    # миграция 041: откат подтверждённо убыточного решения — какое решение отменяет
    reverses_recommendation_id = Column(BigInteger, ForeignKey("price_recommendation.id"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)
    review_comment = Column(Text)
    applied_at = Column(Date)
    applied_price = Column(Numeric(14, 2))
    # миграция 039: приказ, которым цена уехала в iiko. Не статус —
    # applied по-прежнему ставит detect_applied по факту каталога.
    order_id = Column(BigInteger, ForeignKey("price_change_order.id"))
    pushed_at = Column(DateTime)


class PriceChangeOrder(Base):
    """Приказ об изменении меню в iiko (миграция 039).

    Один приказ = одна точка × одна дата вступления в силу. Партия
    утверждённых рекомендаций уезжает в iiko документом menuChange —
    тем же, что заводят руками в бэк-офисе.
    """
    __tablename__ = "price_change_order"
    __table_args__ = (
        # один живой приказ на точку и дату (миграция 039)
        Index(
            "uq_price_order_open", "department_id", "effective_date",
            unique=True,
            postgresql_where=text("status IN ('draft', 'sending', 'sent')"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False)
    iiko_source_domain = Column(Text, nullable=False)
    effective_date = Column(Date, nullable=False)
    status = Column(Text, nullable=False, default="draft", server_default=text("'draft'"))
    iiko_status = Column(Text)
    iiko_document_id = Column(UUID(as_uuid=True))
    iiko_document_number = Column(Text)
    n_items = Column(Integer, nullable=False, default=0)
    request_payload = Column(JSONB, nullable=False)
    response_payload = Column(JSONB)
    error_message = Column(Text)
    reverses_order_id = Column(BigInteger, ForeignKey("price_change_order.id"))
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    sent_at = Column(DateTime)
    cancelled_at = Column(DateTime)


class PriceChangeOrderItem(Base):
    """Позиция приказа (миграция 039). `old_price` — базис решения, по нему
    строится обратный приказ при откате."""
    __tablename__ = "price_change_order_item"
    __table_args__ = (
        Index(
            "uq_price_order_item_rec", "recommendation_id",
            unique=True,
            postgresql_where=text("recommendation_id IS NOT NULL"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("price_change_order.id", ondelete="CASCADE"),
                      nullable=False)
    recommendation_id = Column(BigInteger, ForeignKey("price_recommendation.id"))
    product_id = Column(BigInteger, nullable=False)
    iiko_product_id = Column(UUID(as_uuid=True), nullable=False)
    old_price = Column(Numeric(14, 2), nullable=False)
    new_price = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class PriceRecommendationOutcome(Base):
    """FB: 14-дневная before/after оценка каждой applied-рекомендации (миграция 026)."""
    __tablename__ = "price_recommendation_outcome"
    __table_args__ = (
        UniqueConstraint("recommendation_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    recommendation_id = Column(BigInteger, ForeignKey("price_recommendation.id"), nullable=False)
    product_id = Column(BigInteger, nullable=False)
    department_id = Column(UUID(as_uuid=True), nullable=False)
    applied_at = Column(Date, nullable=False)
    eval_window_days = Column(Integer, nullable=False, default=14)
    baseline_from = Column(Date, nullable=False)
    baseline_to = Column(Date, nullable=False)
    eval_from = Column(Date, nullable=False)
    eval_to = Column(Date, nullable=False)
    old_price = Column(Numeric(14, 2))
    new_price = Column(Numeric(14, 2))
    qty_before = Column(Numeric(12, 3))
    qty_after = Column(Numeric(12, 3))
    revenue_before = Column(Numeric(14, 2))
    revenue_after = Column(Numeric(14, 2))
    gp_before = Column(Numeric(14, 2))
    gp_after = Column(Numeric(14, 2))
    expected_delta_gp = Column(Numeric(14, 2))
    actual_delta_gp = Column(Numeric(14, 2))
    qty_change_pct = Column(Numeric(8, 4))
    control_qty_change_pct = Column(Numeric(8, 4))
    adj_qty_change_pct = Column(Numeric(8, 4))
    realized_elasticity = Column(Numeric(8, 4))
    n_control_skus = Column(Integer)
    # миграция 036: нормировка на рабочие дни точки + эффект, очищенный от фона
    days_before = Column(Integer)
    days_after = Column(Integer)
    counterfactual_qty = Column(Numeric(12, 3))
    incremental_delta_gp = Column(Numeric(14, 2))
    significance_z = Column(Numeric(8, 4))
    # миграция 037: контроль «тот же товар в других точках» + интервал
    control_method = Column(Text)
    measurable = Column(Boolean)
    not_measurable_reason = Column(Text)
    n_control_stores = Column(Integer)
    control_qty_before = Column(Numeric(14, 3))
    control_qty_after = Column(Numeric(14, 3))
    control_trend = Column(Numeric(10, 4))
    store_trend_adj = Column(Numeric(10, 4))
    effect_ci_low = Column(Numeric(14, 2))
    effect_ci_high = Column(Numeric(14, 2))
    p_negative = Column(Numeric(5, 4))
    concept = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class PriceOutcomeBatch(Base):
    """Эффект приказа целиком (точка × дата применения) — миграция 037.

    Главная цифра пилота: отдельная штучная позиция при 1–2 продажах в день
    неизмерима почти всегда, а приказ из полутора десятков позиций — измерим.
    Интервал считается совместной перетасовкой дней, а не сложением интервалов
    позиций: дни у позиций общие, ошибки скоррелированы.
    """
    __tablename__ = "price_outcome_batch"
    __table_args__ = (
        UniqueConstraint("department_id", "applied_at", "eval_window_days",
                         name="uq_price_outcome_batch"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False)
    applied_at = Column(Date, nullable=False)
    concept = Column(Text)
    eval_window_days = Column(Integer, nullable=False)
    n_positions = Column(Integer, nullable=False)
    n_measurable = Column(Integer, nullable=False)
    gp_before = Column(Numeric(14, 2))
    gp_after = Column(Numeric(14, 2))
    actual_delta_gp = Column(Numeric(14, 2))
    expected_delta_gp = Column(Numeric(14, 2))
    effect_gp = Column(Numeric(14, 2))
    effect_ci_low = Column(Numeric(14, 2))
    effect_ci_high = Column(Numeric(14, 2))
    p_negative = Column(Numeric(5, 4))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class PricingBaselineKpi(Base):
    """A3: замороженный пред-пилотный KPI-снимок (миграция 026)."""
    __tablename__ = "pricing_baseline_kpi"
    __table_args__ = (
        UniqueConstraint("label", "scope", "department_id",
                         postgresql_nulls_not_distinct=True),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    label = Column(Text, nullable=False)
    scope = Column(Text, nullable=False, default="department")
    department_id = Column(UUID(as_uuid=True))
    baseline_from = Column(Date, nullable=False)
    baseline_to = Column(Date, nullable=False)
    weeks = Column(Integer, nullable=False)
    total_revenue = Column(Numeric(16, 2))
    total_cost = Column(Numeric(16, 2))
    gross_profit = Column(Numeric(16, 2))
    gp_margin = Column(Numeric(6, 4))
    total_receipts = Column(Integer)
    avg_receipt_sum = Column(Numeric(14, 2))
    weekly_gp_avg = Column(Numeric(16, 2))
    weekly_gp_stddev = Column(Numeric(16, 2))
    active_skus = Column(Integer)
    cost_coverage = Column(Numeric(6, 4))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class PricingAuditLog(Base):
    """AU: append-only журнал действий (миграция 027; защита триггером — 029)."""
    __tablename__ = "pricing_audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(Text)
    action = Column(Text, nullable=False)
    actor = Column(Text)
    department_id = Column(UUID(as_uuid=True))
    details = Column(JSONB)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

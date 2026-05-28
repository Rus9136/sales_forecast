"""Pydantic schemas for pricing engine (B2 + B3 + B4)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# --- B2: Elasticity ---

class SkuElasticityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    department_id: str
    product_name: Optional[str] = None
    elasticity_mean: float
    elasticity_ci_lower: float
    elasticity_ci_upper: float
    elasticity_se: Optional[float] = None
    n_price_events: int
    n_observations: int
    estimation_level: str
    reliability_grade: str
    group_key: Optional[str] = None
    model_r_squared: Optional[float] = None
    model_version: str
    updated_at: datetime


class SkuElasticityResponse(BaseModel):
    items: list[SkuElasticityItem]
    total: int


class ElasticitySummaryResponse(BaseModel):
    by_grade: dict[str, int]
    by_level: dict[str, int]
    total: int
    global_prior: Optional[float] = None


# --- B4: Rules ---

class PricingRuleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_type: str
    scope_type: str
    scope_id: Optional[str] = None
    params: dict[str, Any]
    is_active: bool
    configured_by_role: Optional[str] = None
    effective_from: date
    effective_to: Optional[date] = None


class PricingRuleCreate(BaseModel):
    rule_type: str
    scope_type: str
    scope_id: Optional[str] = None
    params: dict[str, Any]
    configured_by_role: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class PricingRuleUpdate(BaseModel):
    params: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class EffectiveRulesResponse(BaseModel):
    rules: dict[str, dict[str, Any]]


# --- B3: Recommendations ---

class PriceRecommendationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    department_id: str
    department_name: Optional[str] = None
    batch_id: str
    current_price: float
    recommended_price: float
    delta_pct: Optional[float] = None
    cogs: Optional[float] = None
    current_qty_forecast: Optional[float] = None
    new_qty_forecast: Optional[float] = None
    current_gp: Optional[float] = None
    expected_gp: Optional[float] = None
    delta_gp: Optional[float] = None
    elasticity_used: Optional[float] = None
    elasticity_grade: Optional[str] = None
    menu_role: Optional[str] = None
    constraints_applied: Optional[list[str]] = None
    llm_explanation: Optional[str] = None
    status: str
    created_at: datetime
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None


class PriceRecommendationResponse(BaseModel):
    items: list[PriceRecommendationItem]
    total: int


class RecommendationReviewRequest(BaseModel):
    status: str
    comment: Optional[str] = None


class RecommendationSummaryResponse(BaseModel):
    by_status: dict[str, int]
    total: int
    total_delta_gp_new: Optional[float] = None


class OptimizationResultResponse(BaseModel):
    status: str
    department_id: str
    recommendations_created: int
    skus_processed: int
    batch_id: Optional[str] = None
    errors: list[str] = []

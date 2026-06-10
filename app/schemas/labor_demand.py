"""Schemas for the labor-demand signal API (Sales Forecast → TCO).

Read-only enrichment payloads. See docs/LABOR_OPTIMIZATION_ARCHITECTURE.md §2.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class RoleStat(BaseModel):
    """Aggregate for one menu role over the forecast period."""
    sku_count: int
    qty_share: float
    revenue_share: float


class TopDish(BaseModel):
    """A single dish in the forecast-ranked top list."""
    product_id: int
    product_name: Optional[str] = None
    product_type: Optional[str] = None
    category_name: Optional[str] = None
    group_name: Optional[str] = None
    menu_role: Optional[str] = None
    predicted_qty: float
    qty_share: float
    revenue_share: float
    avg_price: Optional[float] = None
    gp_margin: Optional[float] = None
    demand_cv: Optional[float] = None
    rank: int


class CategoryLoad(BaseModel):
    """Forecast load for one category — proxy for kitchen-station load."""
    category_name: Optional[str] = None
    predicted_qty: float
    qty_share: float
    sku_count: int


class MenuDataQuality(BaseModel):
    """Reliability flags so TCO can degrade gracefully."""
    cost_coverage: Optional[float] = None
    clustering_silhouette: Optional[float] = None
    menu_roles_run_date: Optional[str] = None
    sku_model_trained: bool


class MenuMixResponse(BaseModel):
    """§2.1 — menu intelligence: roles, top dishes, category load."""
    department_id: str
    department_name: Optional[str] = None
    period: Dict[str, str]
    role_distribution: Dict[str, RoleStat]
    top_dishes: List[TopDish]
    category_load: List[CategoryLoad]
    data_quality: MenuDataQuality


# ---------- §2.2 forecast ----------

class HourlyBucket(BaseModel):
    """One hour of the intraday revenue curve.

    Only `revenue_share` is provided — `sales_by_hour` tracks revenue, not qty.
    """
    hour: int
    revenue_share: float


class ForecastDay(BaseModel):
    date: str
    day_of_week: str
    is_weekend: bool
    predicted_revenue: Optional[float] = None
    predicted_receipts: Optional[int] = None
    predicted_total_qty: Optional[float] = None
    confidence: str
    hourly_profile: List[HourlyBucket]


class ForecastResponse(BaseModel):
    """§2.2 — daily demand signal + intraday revenue curve."""
    department_id: str
    department_name: Optional[str] = None
    segment_type: Optional[str] = None
    model_version: Optional[str] = None
    days: List[ForecastDay]


# ---------- §2.3 elasticity-signal ----------

class ElasticityItem(BaseModel):
    product_id: int
    product_name: Optional[str] = None
    menu_role: Optional[str] = None
    elasticity_mean: float
    elasticity_ci_lower: Optional[float] = None
    elasticity_ci_upper: Optional[float] = None
    elasticity_se: Optional[float] = None
    # True when the 95% CI lies entirely below 0 — the price→demand effect is
    # statistically distinguishable from "no effect". When False, elasticity_mean
    # near 0 means "no measurable signal", not real inelasticity.
    significant: bool
    reliability_grade: str
    estimation_level: str


class ElasticitySignalResponse(BaseModel):
    """§2.3 — economic context: where staffing cuts hurt revenue most."""
    department_id: str
    global_prior: Optional[float] = None
    items: List[ElasticityItem]

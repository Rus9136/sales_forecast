"""Pydantic schemas for pricing analytics API."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SkuPriceHistoryItem(BaseModel):
    id: int
    product_id: int
    department_id: str
    price: float
    prev_price: Optional[float] = None
    change_pct: Optional[float] = None
    first_seen_date: date
    last_seen_date: date

    class Config:
        from_attributes = True


class SkuPriceHistoryResponse(BaseModel):
    items: List[SkuPriceHistoryItem]
    total: int


class SkuWeeklySummaryItem(BaseModel):
    product_id: int
    product_name: Optional[str] = None
    department_id: str
    department_name: Optional[str] = None
    week_start: date
    total_qty: float
    total_revenue: float
    total_cost: float
    gross_profit: float
    gp_margin: Optional[float] = None
    avg_price: Optional[float] = None
    avg_daily_qty: Optional[float] = None
    unique_receipts: int
    days_with_sales: int
    qty_cv: Optional[float] = None
    cost_coverage: Optional[float] = None

    class Config:
        from_attributes = True


class SkuWeeklySummaryResponse(BaseModel):
    items: List[SkuWeeklySummaryItem]
    total: int


class DeptWeeklySummaryItem(BaseModel):
    department_id: str
    department_name: Optional[str] = None
    week_start: date
    total_revenue: float
    total_cost: float
    gross_profit: float
    gp_margin: Optional[float] = None
    total_receipts: int
    avg_receipt_sum: Optional[float] = None
    unique_guests: int
    cost_coverage: Optional[float] = None

    class Config:
        from_attributes = True


class DeptWeeklySummaryResponse(BaseModel):
    items: List[DeptWeeklySummaryItem]
    total: int


class AggregationResultResponse(BaseModel):
    status: str = "ok"
    price_history: Optional[dict] = None
    sku_weekly: Optional[dict] = None
    department_weekly: Optional[dict] = None


class SkuMenuRoleItem(BaseModel):
    product_id: int
    product_name: Optional[str] = None
    department_id: str
    department_name: Optional[str] = None
    auto_role: str
    manual_role: Optional[str] = None
    effective_role: str
    features: Optional[Dict[str, Any]] = None
    cluster_meta: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class SkuMenuRoleUpdateRequest(BaseModel):
    manual_role: Optional[str] = None


class ClusteringResultResponse(BaseModel):
    status: str
    skus_classified: int = 0
    silhouette_score: Optional[float] = None
    role_distribution: Optional[Dict[str, int]] = None
    lookback_days: Optional[int] = None

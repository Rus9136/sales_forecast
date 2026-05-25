"""Pydantic schemas for SKU-level forecast endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SkuForecastItem(BaseModel):
    product_id: int
    product_name: str
    product_type: str
    group_name: Optional[str] = None
    category_name: Optional[str] = None
    predicted_qty: float
    avg_price: Optional[float] = None
    estimated_revenue: Optional[float] = None


class SkuForecastBatchResponse(BaseModel):
    department_id: str
    department_name: str
    forecast_date: str
    items: List[SkuForecastItem]
    total_predicted_qty: float
    total_estimated_revenue: Optional[float] = None
    model_version: Optional[str] = None


class SkuForecastRangeResponse(BaseModel):
    department_id: str
    department_name: str
    from_date: str
    to_date: str
    daily_forecasts: List[SkuForecastBatchResponse]


class SkuTopNItem(BaseModel):
    product_id: int
    product_name: str
    product_type: str
    group_name: Optional[str] = None
    total_revenue: float
    total_qty: float
    avg_daily_qty: float
    rank: int


class SkuTopNResponse(BaseModel):
    department_id: Optional[str] = None
    period_days: int
    items: List[SkuTopNItem]


class SkuRetrainRequest(BaseModel):
    days: Optional[int] = Field(None, description="Training window in days (default: all available)")
    active_window_days: int = Field(30, description="SKU must have sold in this window to be 'active'")


class SkuRetrainResponse(BaseModel):
    status: str
    message: str
    metrics: Dict[str, Any]
    timestamp: str
    training_samples: int
    n_features: int
    n_unique_skus: int
    n_unique_departments: int


class SkuModelInfoResponse(BaseModel):
    status: str
    model_path: str
    n_features: int = 0
    training_metrics: Optional[Dict[str, Any]] = None
    trained_at: Optional[str] = None
    target_transform: Optional[str] = None


class SkuComparisonItem(BaseModel):
    date: str
    product_id: int
    product_name: str
    department_id: str
    department_name: str
    predicted_qty: Optional[float] = None
    actual_qty: float
    error: Optional[float] = None
    error_pct: Optional[float] = None


class SkuComparisonResponse(BaseModel):
    items: List[SkuComparisonItem]
    summary: Dict[str, Any]

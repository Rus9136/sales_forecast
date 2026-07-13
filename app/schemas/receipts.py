"""Pydantic schemas for receipts API."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class ReceiptItemResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    iiko_dish_id: Optional[str] = None
    dish_name: str
    dish_code: Optional[str] = None
    dish_group: Optional[str] = None
    dish_category: Optional[str] = None
    qty: float
    price_per_unit: Optional[float] = None
    dish_sum: float
    discount_sum: float
    return_sum: float
    cost_price: Optional[float] = None
    food_cost_percent: Optional[float] = None
    margin: Optional[float] = None

    class Config:
        from_attributes = True


class ReceiptResponse(BaseModel):
    id: int
    department_id: str
    department_name: Optional[str] = None
    open_date: date
    order_num: int
    open_time: Optional[datetime] = None
    close_time: datetime
    order_type: Optional[str] = None
    table_num: Optional[str] = None
    waiter_name: Optional[str] = None
    guest_num: Optional[int] = None
    total_sum: float
    discount_sum: float
    return_sum: float
    items_count: int
    synced_at: datetime


class ReceiptDetailResponse(ReceiptResponse):
    items: List[ReceiptItemResponse] = []


class ReceiptSyncResponse(BaseModel):
    status: str
    total_receipts: int
    total_items: int
    per_domain: list
    errors: list


class ProductSalesStats(BaseModel):
    product_id: Optional[int] = None
    iiko_dish_id: Optional[str] = None
    dish_name: str
    dish_group: Optional[str] = None
    dish_category: Optional[str] = None
    total_qty: float
    total_sum: float
    total_discount: float
    total_cost: Optional[float] = None
    receipts_count: int
    avg_price: Optional[float] = None
    avg_cost: Optional[float] = None
    avg_food_cost_pct: Optional[float] = None
    margin: Optional[float] = None


class ProductSalesStatsResponse(BaseModel):
    period_start: date
    period_end: date
    department_id: Optional[str] = None
    items: List[ProductSalesStats]
    total_revenue: float
    total_cost: float
    total_margin: float
    total_items_sold: float

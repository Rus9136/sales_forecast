"""Receipts API — list, detail, stats, sync."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..auth import get_api_key_or_bypass
from ..db import get_db
from ..models.receipts import Receipt, ReceiptItem
from ..models.department import Department
from ..schemas.receipts import (
    ProductSalesStats,
    ProductSalesStatsResponse,
    ReceiptDetailResponse,
    ReceiptItemResponse,
    ReceiptResponse,
    ReceiptSyncResponse,
)
from ..services.iiko_receipts_loader import IikoReceiptsLoaderService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/receipts", tags=["receipts"], dependencies=[Depends(get_api_key_or_bypass)])


def _serialize_receipt(r: Receipt, dept_name: Optional[str] = None) -> dict:
    return {
        "id": r.id,
        "department_id": str(r.department_id),
        "department_name": dept_name,
        "open_date": r.open_date,
        "order_num": r.order_num,
        "close_time": r.close_time,
        "order_type": r.order_type,
        "table_num": r.table_num,
        "waiter_name": r.waiter_name,
        "guest_num": r.guest_num,
        "total_sum": float(r.total_sum or 0),
        "discount_sum": float(r.discount_sum or 0),
        "return_sum": float(r.return_sum or 0),
        "items_count": r.items_count or 0,
        "synced_at": r.synced_at,
    }


def _serialize_item(it: ReceiptItem) -> dict:
    dish_sum = float(it.dish_sum or 0)
    cost = float(it.cost_price) if it.cost_price else None
    margin = round(dish_sum - cost, 2) if cost is not None else None
    return {
        "id": it.id,
        "product_id": it.product_id,
        "iiko_dish_id": str(it.iiko_dish_id) if it.iiko_dish_id else None,
        "dish_name": it.dish_name,
        "dish_code": it.dish_code,
        "dish_group": it.dish_group,
        "dish_category": it.dish_category,
        "qty": float(it.qty or 0),
        "price_per_unit": float(it.price_per_unit) if it.price_per_unit else None,
        "dish_sum": dish_sum,
        "discount_sum": float(it.discount_sum or 0),
        "return_sum": float(it.return_sum or 0),
        "cost_price": cost,
        "food_cost_percent": float(it.food_cost_percent) if it.food_cost_percent else None,
        "margin": margin,
    }


@router.get("", response_model=list[ReceiptResponse])
def list_receipts(
    from_date: date = Query(..., description="Start date (inclusive)"),
    to_date: date = Query(..., description="End date (inclusive)"),
    department_id: Optional[UUID] = Query(None),
    iiko_source_domain: Optional[str] = Query(None),
    waiter_name: Optional[str] = Query(None),
    min_sum: Optional[float] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Receipt, Department.name)
        .join(Department, Receipt.department_id == Department.id)
        .filter(Receipt.open_date >= from_date, Receipt.open_date <= to_date)
    )
    if department_id:
        q = q.filter(Receipt.department_id == department_id)
    if iiko_source_domain:
        q = q.filter(Department.iiko_source_domain == iiko_source_domain)
    if waiter_name:
        q = q.filter(Receipt.waiter_name.ilike(f"%{waiter_name}%"))
    if min_sum is not None:
        q = q.filter(Receipt.total_sum >= min_sum)

    q = q.order_by(Receipt.close_time.desc()).offset(offset).limit(limit)
    return [_serialize_receipt(r, dn) for r, dn in q.all()]


@router.get("/{receipt_id}", response_model=ReceiptDetailResponse)
def get_receipt(
    receipt_id: int,
    open_date: date = Query(..., description="Required for partition pruning"),
    db: Session = Depends(get_db),
):
    row = (
        db.query(Receipt, Department.name)
        .join(Department, Receipt.department_id == Department.id)
        .filter(Receipt.id == receipt_id, Receipt.open_date == open_date)
        .first()
    )
    if not row:
        raise HTTPException(404, "Receipt not found")
    receipt, dept_name = row
    items_q = (
        db.query(ReceiptItem)
        .filter(ReceiptItem.receipt_id == receipt_id, ReceiptItem.open_date == open_date)
        .order_by(ReceiptItem.id)
        .all()
    )
    data = _serialize_receipt(receipt, dept_name)
    data["items"] = [_serialize_item(it) for it in items_q]
    return data


@router.get("/stats/by-product", response_model=ProductSalesStatsResponse)
def stats_by_product(
    from_date: date = Query(...),
    to_date: date = Query(...),
    department_id: Optional[UUID] = Query(None),
    iiko_source_domain: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Top products by revenue for the period."""
    params: dict = {"from_date": from_date, "to_date": to_date, "lim": limit}
    extra_filters = ""
    if department_id:
        extra_filters += " AND r.department_id = :dept_id"
        params["dept_id"] = str(department_id)
    if iiko_source_domain:
        extra_filters += " AND d.iiko_source_domain = :source"
        params["source"] = iiko_source_domain

    sql = text(f"""
        SELECT
            ri.product_id,
            ri.iiko_dish_id::text,
            ri.dish_name,
            ri.dish_group,
            ri.dish_category,
            SUM(ri.qty) AS total_qty,
            SUM(ri.dish_sum) AS total_sum,
            SUM(ri.discount_sum) AS total_discount,
            SUM(ri.cost_price) AS total_cost,
            COUNT(DISTINCT ri.receipt_id) AS receipts_count
        FROM receipt_item ri
        JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
        JOIN departments d ON d.id = r.department_id
        WHERE ri.open_date >= :from_date AND ri.open_date <= :to_date
            {extra_filters}
        GROUP BY ri.product_id, ri.iiko_dish_id, ri.dish_name, ri.dish_group, ri.dish_category
        ORDER BY total_sum DESC
        LIMIT :lim
    """)
    rows = db.execute(sql, params).fetchall()

    items = []
    total_revenue = 0.0
    total_cost_sum = 0.0
    total_qty = 0.0
    for r in rows:
        s = float(r.total_sum or 0)
        q = float(r.total_qty or 0)
        c = float(r.total_cost or 0)
        avg_cost = round(c / q, 2) if q > 0 and c > 0 else None
        food_pct = round(c / s * 100, 1) if s > 0 and c > 0 else None
        margin = round(s - c, 2) if c > 0 else None
        items.append(ProductSalesStats(
            product_id=r.product_id,
            iiko_dish_id=r.iiko_dish_id,
            dish_name=r.dish_name,
            dish_group=r.dish_group,
            dish_category=r.dish_category,
            total_qty=q,
            total_sum=s,
            total_discount=float(r.total_discount or 0),
            total_cost=c if c > 0 else None,
            receipts_count=r.receipts_count,
            avg_price=round(s / q, 2) if q > 0 else None,
            avg_cost=avg_cost,
            avg_food_cost_pct=food_pct,
            margin=margin,
        ))
        total_revenue += s
        total_cost_sum += c
        total_qty += q

    return ProductSalesStatsResponse(
        period_start=from_date,
        period_end=to_date,
        department_id=str(department_id) if department_id else None,
        items=items,
        total_revenue=total_revenue,
        total_cost=total_cost_sum,
        total_margin=round(total_revenue - total_cost_sum, 2),
        total_items_sold=total_qty,
    )


@router.post("/sync", response_model=ReceiptSyncResponse)
async def sync_receipts(
    from_date: date = Query(...),
    to_date: date = Query(...),
    department_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
    svc = IikoReceiptsLoaderService(db)
    result = await svc.sync(from_date, to_date, str(department_id) if department_id else None)
    return result

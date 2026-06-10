"""Pricing analytics API — price history, weekly summaries, backfill trigger."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import get_api_key_or_bypass
from ..db import get_db
from ..services.pricing_analytics_service import PricingAnalyticsService
from ..services.menu_clustering_service import MenuClusteringService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pricing-analytics",
    tags=["pricing-analytics"],
    dependencies=[Depends(get_api_key_or_bypass)],
)


# ---------- GET: price history ----------

@router.get("/price-history")
async def get_price_history(
    product_id: Optional[int] = Query(None),
    department_id: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if product_id:
        conditions.append("sph.product_id = :product_id")
        params["product_id"] = product_id
    if department_id:
        conditions.append("sph.department_id = CAST(:department_id AS uuid)")
        params["department_id"] = department_id
    if from_date:
        conditions.append("sph.first_seen_date >= :from_date")
        params["from_date"] = from_date
    if to_date:
        conditions.append("sph.last_seen_date <= :to_date")
        params["to_date"] = to_date

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM sku_price_history sph {where}"), params
    ).scalar()

    rows = db.execute(text(f"""
        SELECT sph.id, sph.product_id, sph.department_id::text,
               sph.price, sph.prev_price, sph.change_pct,
               sph.first_seen_date, sph.last_seen_date,
               p.name AS product_name
        FROM sku_price_history sph
        LEFT JOIN product p ON p.id = sph.product_id
        {where}
        ORDER BY sph.first_seen_date DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    return {
        "items": [
            {
                "id": r.id,
                "product_id": r.product_id,
                "product_name": r.product_name,
                "department_id": r.department_id,
                "price": float(r.price),
                "prev_price": float(r.prev_price) if r.prev_price is not None else None,
                "change_pct": float(r.change_pct) if r.change_pct is not None else None,
                "first_seen_date": r.first_seen_date,
                "last_seen_date": r.last_seen_date,
            }
            for r in rows
        ],
        "total": count_row,
    }


# ---------- GET: SKU weekly summary ----------

@router.get("/sku-weekly")
async def get_sku_weekly(
    product_id: Optional[int] = Query(None),
    department_id: Optional[str] = Query(None),
    from_week: Optional[date] = Query(None),
    to_week: Optional[date] = Query(None),
    limit: int = Query(200, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if product_id:
        conditions.append("sw.product_id = :product_id")
        params["product_id"] = product_id
    if department_id:
        conditions.append("sw.department_id = CAST(:department_id AS uuid)")
        params["department_id"] = department_id
    if from_week:
        conditions.append("sw.week_start >= :from_week")
        params["from_week"] = from_week
    if to_week:
        conditions.append("sw.week_start <= :to_week")
        params["to_week"] = to_week

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM sku_weekly_summary sw {where}"), params
    ).scalar()

    rows = db.execute(text(f"""
        SELECT sw.product_id, p.name AS product_name,
               sw.department_id::text, d.name AS department_name,
               sw.week_start, sw.total_qty, sw.total_revenue, sw.total_cost,
               sw.gross_profit, sw.gp_margin, sw.avg_price, sw.avg_daily_qty,
               sw.unique_receipts, sw.days_with_sales, sw.qty_cv, sw.cost_coverage
        FROM sku_weekly_summary sw
        LEFT JOIN product p ON p.id = sw.product_id
        LEFT JOIN departments d ON d.id = sw.department_id
        {where}
        ORDER BY sw.week_start DESC, sw.total_revenue DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    return {
        "items": [
            {
                "product_id": r.product_id,
                "product_name": r.product_name,
                "department_id": r.department_id,
                "department_name": r.department_name,
                "week_start": r.week_start,
                "total_qty": float(r.total_qty),
                "total_revenue": float(r.total_revenue),
                "total_cost": float(r.total_cost),
                "gross_profit": float(r.gross_profit),
                "gp_margin": float(r.gp_margin) if r.gp_margin is not None else None,
                "avg_price": float(r.avg_price) if r.avg_price is not None else None,
                "avg_daily_qty": float(r.avg_daily_qty) if r.avg_daily_qty is not None else None,
                "unique_receipts": r.unique_receipts,
                "days_with_sales": r.days_with_sales,
                "qty_cv": float(r.qty_cv) if r.qty_cv is not None else None,
                "cost_coverage": float(r.cost_coverage) if r.cost_coverage is not None else None,
            }
            for r in rows
        ],
        "total": count_row,
    }


# ---------- GET: department weekly summary ----------

@router.get("/department-weekly")
async def get_department_weekly(
    department_id: Optional[str] = Query(None),
    from_week: Optional[date] = Query(None),
    to_week: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    conditions = []
    params: dict = {}

    if department_id:
        conditions.append("dw.department_id = CAST(:department_id AS uuid)")
        params["department_id"] = department_id
    if from_week:
        conditions.append("dw.week_start >= :from_week")
        params["from_week"] = from_week
    if to_week:
        conditions.append("dw.week_start <= :to_week")
        params["to_week"] = to_week

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = db.execute(text(f"""
        SELECT dw.department_id::text, d.name AS department_name,
               dw.week_start, dw.total_revenue, dw.total_cost,
               dw.gross_profit, dw.gp_margin, dw.total_receipts,
               dw.avg_receipt_sum, dw.unique_guests, dw.cost_coverage
        FROM department_weekly_summary dw
        LEFT JOIN departments d ON d.id = dw.department_id
        {where}
        ORDER BY dw.week_start DESC, dw.total_revenue DESC
    """), params).fetchall()

    return {
        "items": [
            {
                "department_id": r.department_id,
                "department_name": r.department_name,
                "week_start": r.week_start,
                "total_revenue": float(r.total_revenue),
                "total_cost": float(r.total_cost),
                "gross_profit": float(r.gross_profit),
                "gp_margin": float(r.gp_margin) if r.gp_margin is not None else None,
                "total_receipts": r.total_receipts,
                "avg_receipt_sum": float(r.avg_receipt_sum) if r.avg_receipt_sum is not None else None,
                "unique_guests": r.unique_guests,
                "cost_coverage": float(r.cost_coverage) if r.cost_coverage is not None else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ---------- POST: manual aggregation ----------

@router.post("/aggregate")
def run_aggregate(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: Session = Depends(get_db),
):
    """Sync def → threadpool: тяжёлая агрегация не блокирует event loop."""
    svc = PricingAnalyticsService(db)
    result = svc.aggregate_all(from_date, to_date)
    return {"status": "ok", **result}


# ---------- POST: full backfill ----------

@router.post("/backfill")
def run_backfill(db: Session = Depends(get_db)):
    """Sync def → threadpool: полный пересчёт витрин занимает минуты."""
    svc = PricingAnalyticsService(db)
    result = svc.backfill_all()
    return {"status": "ok", **result}


# ---------- GET: menu roles ----------

VALID_ROLES = {"premium_anchor", "margin_driver", "traffic_driver", "image_rare", "tail"}


@router.get("/menu-roles")
async def get_menu_roles(
    department_id: Optional[str] = Query(None),
    effective_role: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    limit: int = Query(200, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if department_id:
        conditions.append("mr.department_id = CAST(:department_id AS uuid)")
        params["department_id"] = department_id
    if effective_role:
        conditions.append("mr.effective_role = :effective_role")
        params["effective_role"] = effective_role
    if product_id:
        conditions.append("mr.product_id = :product_id")
        params["product_id"] = product_id

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM sku_menu_role mr {where}"), params
    ).scalar()

    rows = db.execute(text(f"""
        SELECT mr.product_id, p.name AS product_name,
               mr.department_id::text, d.name AS department_name,
               mr.auto_role, mr.manual_role, mr.effective_role,
               mr.features, mr.cluster_meta
        FROM sku_menu_role mr
        LEFT JOIN product p ON p.id = mr.product_id
        LEFT JOIN departments d ON d.id = mr.department_id
        {where}
        ORDER BY mr.effective_role, p.name
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    return {
        "items": [
            {
                "product_id": r.product_id,
                "product_name": r.product_name,
                "department_id": r.department_id,
                "department_name": r.department_name,
                "auto_role": r.auto_role,
                "manual_role": r.manual_role,
                "effective_role": r.effective_role,
                "features": r.features,
                "cluster_meta": r.cluster_meta,
            }
            for r in rows
        ],
        "total": count_row,
    }


@router.get("/menu-roles/summary")
async def get_menu_roles_summary(
    department_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    params: dict = {}
    dept_filter = ""
    if department_id:
        dept_filter = "WHERE department_id = CAST(:department_id AS uuid)"
        params["department_id"] = department_id

    rows = db.execute(text(f"""
        SELECT effective_role, COUNT(*) AS count
        FROM sku_menu_role
        {dept_filter}
        GROUP BY effective_role
        ORDER BY count DESC
    """), params).fetchall()

    return {
        "distribution": {r.effective_role: r.count for r in rows},
        "total": sum(r.count for r in rows),
    }


# ---------- PUT: manual override ----------

@router.put("/menu-roles/{product_id}/{department_id}")
async def update_menu_role(
    product_id: int,
    department_id: str,
    manual_role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if manual_role is not None and manual_role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")

    result = db.execute(text("""
        UPDATE sku_menu_role
        SET manual_role = :manual_role, updated_at = NOW()
        WHERE product_id = :product_id
          AND department_id = CAST(:department_id AS uuid)
        RETURNING effective_role
    """), {"product_id": product_id, "department_id": department_id, "manual_role": manual_role})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "SKU menu role not found")
    db.commit()
    return {"status": "ok", "effective_role": row.effective_role}


# ---------- POST: trigger clustering ----------

@router.post("/menu-roles/cluster")
def run_clustering_now(
    lookback_days: int = Query(90, ge=30, le=365),
    db: Session = Depends(get_db),
):
    """Sync def → threadpool: KMeans-кластеризация не блокирует event loop."""
    svc = MenuClusteringService(db)
    return svc.run_clustering(lookback_days=lookback_days)

"""Складской контур: списания, поставки и рекомендация заявки на цех."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import get_api_key_or_bypass
from ..db import get_db
from ..services.inventory_analytics_service import InventoryAnalyticsService
from ..services.iiko_inventory_loader import IikoInventoryLoaderService
from ..services.procurement_recommendation_service import (
    DEFAULT_LOOKBACK_DAYS, ProcurementRecommendationService,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/inventory", tags=["inventory"],
    dependencies=[Depends(get_api_key_or_bypass)],
)


def _default_period(from_date: Optional[date], to_date: Optional[date]):
    to_d = to_date or date.today()
    from_d = from_date or (to_d - timedelta(days=29))
    if from_d > to_d:
        raise HTTPException(400, "from_date позже to_date")
    return from_d, to_d


def _check_department(db: Session, department_id: UUID) -> None:
    exists = db.execute(
        text("SELECT 1 FROM departments WHERE id = :id ::uuid"),
        {"id": str(department_id)},
    ).first()
    if not exists:
        raise HTTPException(404, "Подразделение не найдено")


# ---------------------------------------------------------------- аналитика

@router.get("/writeoffs/summary")
def writeoff_summary(
    department_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Списания в разрезе склад × причина + доля от выручки и от поставки."""
    f, t = _default_period(from_date, to_date)
    _check_department(db, department_id)
    return InventoryAnalyticsService(db).writeoff_summary(str(department_id), f, t)


@router.get("/writeoffs/by-product")
def writeoff_by_product(
    department_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    store_id: Optional[UUID] = None,
    reason_id: Optional[UUID] = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Топ позиций по стоимости списаний с долей потерь от поставки."""
    f, t = _default_period(from_date, to_date)
    _check_department(db, department_id)
    return InventoryAnalyticsService(db).writeoff_by_product(
        str(department_id), f, t,
        str(store_id) if store_id else None,
        str(reason_id) if reason_id else None,
        limit,
    )


@router.get("/writeoffs/trend")
def writeoff_trend(
    department_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Понедельная динамика списаний и их доли в выручке."""
    f, t = _default_period(from_date, to_date)
    _check_department(db, department_id)
    return InventoryAnalyticsService(db).writeoff_trend(str(department_id), f, t)


@router.get("/supply-loop")
def supply_loop(
    department_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    supplier_id: Optional[UUID] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """По каждому SKU: поставлено → продано → списано за период."""
    f, t = _default_period(from_date, to_date)
    _check_department(db, department_id)
    return InventoryAnalyticsService(db).supply_loop(
        str(department_id), f, t, str(supplier_id) if supplier_id else None, limit,
    )


@router.get("/suppliers")
def suppliers(
    department_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Поставщики точки за период. is_internal — поставка изнутри сети (цех)."""
    f, t = _default_period(from_date, to_date)
    _check_department(db, department_id)
    return InventoryAnalyticsService(db).suppliers_of_department(str(department_id), f, t)


@router.get("/stores")
def stores(
    department_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Склады: все или по одному подразделению."""
    rows = db.execute(
        text("""
            SELECT s.id::text, s.name, s.code, s.department_id::text, d.name AS department_name
            FROM store s
            LEFT JOIN departments d ON d.id = s.department_id
            WHERE (:dept ::uuid IS NULL OR s.department_id = :dept ::uuid)
              AND s.is_deleted = FALSE
            ORDER BY d.name NULLS LAST, s.name
        """),
        {"dept": str(department_id) if department_id else None},
    ).fetchall()
    return [{
        "id": r[0], "name": r[1], "code": r[2],
        "department_id": r[3], "department_name": r[4],
    } for r in rows]


# ------------------------------------------------------------ рекомендация

@router.get("/order-recommendation")
def order_recommendation(
    department_id: UUID,
    target_date: Optional[date] = None,
    supplier_id: Optional[UUID] = None,
    lookback_days: int = Query(DEFAULT_LOOKBACK_DAYS, ge=14, le=180),
    min_supplied_sum: float = Query(0.0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Рекомендуемая заявка на цех на указанную дату.

    Объём считается по newsvendor-модели: целевой уровень сервиса равен
    наценке позиции, спрос берётся по тому же дню недели за окно истории.
    """
    _check_department(db, department_id)
    target = target_date or (date.today() + timedelta(days=1))
    return ProcurementRecommendationService(db).recommend_order(
        str(department_id), target,
        str(supplier_id) if supplier_id else None,
        lookback_days, min_supplied_sum,
    )


# ------------------------------------------------------------------- sync

@router.post("/sync")
async def sync_inventory(
    from_date: date,
    to_date: date,
    department_id: Optional[UUID] = None,
    include_references: bool = True,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Загрузить списания и приходные накладные из iiko за период.

    Без ``department_id`` грузится вся сеть — ответ iiko по накладным
    измеряется десятками мегабайт, поэтому период стоит держать коротким.
    """
    if from_date > to_date:
        raise HTTPException(400, "from_date позже to_date")

    svc = IikoInventoryLoaderService(db)
    depts = [str(department_id)] if department_id else None

    result: Dict[str, Any] = {}
    if include_references:
        result["references"] = await svc.sync_references()
    result["writeoffs"] = await svc.sync_writeoffs(from_date, to_date, depts)
    result["invoices"] = await svc.sync_incoming_invoices(from_date, to_date, depts)
    return result


@router.post("/stock/sync")
async def sync_stock_balances(
    from_date: date,
    to_date: date,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Снять остатки по складам за каждый день периода.

    iiko отдаёт остатки только срезом на момент времени — за прошлые даты
    снимок ещё можно достать, но истории у отчёта нет, поэтому дальше их
    держит наша таблица. Один день по сети — около секунды.
    """
    from ..services.iiko_stock_loader import IikoStockLoaderService

    if from_date > to_date:
        raise HTTPException(400, "from_date позже to_date")
    if (to_date - from_date).days > 400:
        raise HTTPException(400, "период больше 400 дней")

    return await IikoStockLoaderService(db).sync_range(from_date, to_date)


@router.get("/stock/coverage")
def stock_coverage(
    department_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """За какие дни остатки вообще сняты. Без этого «нет остатка» и «нет
    снимка» выглядят на графике одинаково."""
    row = db.execute(
        text("""
            SELECT MIN(balance_date), MAX(balance_date), COUNT(DISTINCT balance_date)
            FROM sku_stock_balance
            WHERE (:dept IS NULL OR department_id = CAST(:dept AS uuid))
        """),
        {"dept": str(department_id) if department_id else None},
    ).fetchone()
    return {"from_date": str(row[0]) if row[0] else None,
            "to_date": str(row[1]) if row[1] else None,
            "days": row[2] or 0}


@router.get("/sync/log")
def sync_log(
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT sync_type, department_id::text, from_date, to_date,
                   documents, items, unresolved, status, error_message,
                   duration_sec, created_at
            FROM inventory_sync_log
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()
    return [{
        "sync_type": r[0], "department_id": r[1],
        "from_date": r[2].isoformat() if r[2] else None,
        "to_date": r[3].isoformat() if r[3] else None,
        "documents": r[4], "items": r[5], "unresolved": r[6],
        "status": r[7], "error_message": r[8],
        "duration_sec": float(r[9]) if r[9] is not None else None,
        "created_at": r[10].isoformat(),
    } for r in rows]

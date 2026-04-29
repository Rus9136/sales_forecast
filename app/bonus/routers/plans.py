from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ..models.monthly_plan import BonusMonthlyPlan

router = APIRouter()


class PlanUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: str
    metric: str  # 'sales', 'profitability', 'shifts_norm'
    year: int
    month: int
    target_value: Decimal
    notes: Optional[str] = None


def _serialize(p: BonusMonthlyPlan) -> dict:
    return {
        "id": p.id,
        "department_id": str(p.department_id),
        "metric": p.metric, "year": p.year, "month": p.month,
        "target_value": str(p.target_value),
        "notes": p.notes,
    }


@router.get("/monthly-plans")
def list_plans(
    department_id: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    metric: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    q = db.query(BonusMonthlyPlan)
    if department_id:
        q = q.filter(BonusMonthlyPlan.department_id == department_id)
    if year is not None:
        q = q.filter(BonusMonthlyPlan.year == year)
    if metric:
        q = q.filter(BonusMonthlyPlan.metric == metric)
    return [_serialize(p) for p in q.order_by(BonusMonthlyPlan.year, BonusMonthlyPlan.month).all()]


@router.post("/monthly-plans")
def upsert_plan(
    payload: PlanUpsert,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    if not (1 <= payload.month <= 12):
        raise HTTPException(status_code=422, detail="month must be 1..12")

    obj = (
        db.query(BonusMonthlyPlan)
        .filter_by(
            department_id=payload.department_id,
            metric=payload.metric,
            year=payload.year,
            month=payload.month,
        )
        .first()
    )
    if obj is None:
        obj = BonusMonthlyPlan(
            department_id=payload.department_id,
            metric=payload.metric,
            year=payload.year,
            month=payload.month,
            target_value=payload.target_value,
            notes=payload.notes,
        )
        db.add(obj)
    else:
        obj.target_value = payload.target_value
        obj.notes = payload.notes
    db.commit()
    db.refresh(obj)
    return _serialize(obj)

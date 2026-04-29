from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ..models.kpi import BonusManualKpi

router = APIRouter()


class ManualKpiUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: str
    kpi_code: str
    period_year: int
    period_month: int
    fact_value: Decimal
    notes: Optional[str] = None
    document_ref: Optional[str] = None
    entered_by: Optional[str] = None


def _serialize(m: BonusManualKpi) -> dict:
    return {
        "id": m.id,
        "department_id": str(m.department_id),
        "kpi_code": m.kpi_code,
        "period_year": m.period_year,
        "period_month": m.period_month,
        "fact_value": str(m.fact_value),
        "notes": m.notes,
        "document_ref": m.document_ref,
        "entered_at": m.entered_at.isoformat() if m.entered_at else None,
        "entered_by": m.entered_by,
    }


@router.get("/manual-kpi")
def list_manual_kpi(
    department_id: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    q = db.query(BonusManualKpi)
    if department_id:
        q = q.filter(BonusManualKpi.department_id == department_id)
    if year is not None:
        q = q.filter(BonusManualKpi.period_year == year)
    if month is not None:
        q = q.filter(BonusManualKpi.period_month == month)
    return [_serialize(r) for r in q.order_by(BonusManualKpi.period_year.desc(),
                                              BonusManualKpi.period_month.desc(),
                                              BonusManualKpi.kpi_code).all()]


@router.post("/manual-kpi")
def upsert_manual_kpi(
    payload: ManualKpiUpsert,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    if not (1 <= payload.period_month <= 12):
        raise HTTPException(status_code=422, detail="period_month must be 1..12")

    obj = (
        db.query(BonusManualKpi)
        .filter_by(
            department_id=payload.department_id,
            kpi_code=payload.kpi_code,
            period_year=payload.period_year,
            period_month=payload.period_month,
        )
        .first()
    )
    if obj is None:
        obj = BonusManualKpi(
            department_id=payload.department_id,
            kpi_code=payload.kpi_code,
            period_year=payload.period_year,
            period_month=payload.period_month,
            fact_value=payload.fact_value,
            notes=payload.notes,
            document_ref=payload.document_ref,
            entered_by=payload.entered_by,
        )
        db.add(obj)
    else:
        obj.fact_value = payload.fact_value
        obj.notes = payload.notes
        obj.document_ref = payload.document_ref
        obj.entered_by = payload.entered_by
        obj.entered_at = datetime.utcnow()
    db.commit()
    db.refresh(obj)
    return _serialize(obj)


@router.delete("/manual-kpi/{kpi_id}", status_code=204)
def delete_manual_kpi(
    kpi_id: int,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    obj = db.query(BonusManualKpi).filter_by(id=kpi_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Manual KPI not found")
    db.delete(obj)
    db.commit()

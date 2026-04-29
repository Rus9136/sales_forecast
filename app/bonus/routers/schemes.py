from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ..models.scheme import BonusScheme
from ..repositories.scheme_repository import (
    find_active_scheme_for_position,
    find_active_scheme_for_team,
)
from ..services.scheme_service import SchemeService, SchemeServiceError

router = APIRouter()


def _serialize(s: BonusScheme) -> dict:
    return {
        "id": s.id,
        "department_id": str(s.department_id),
        "position_id": s.position_id,
        "team_id": s.team_id,
        "calculation_model": s.calculation_model,
        "version": s.version,
        "effective_from": s.effective_from.isoformat() if s.effective_from else None,
        "effective_to": s.effective_to.isoformat() if s.effective_to else None,
        "config": s.config,
        "notes": s.notes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


class SchemeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: str
    position_id: Optional[int] = None
    team_id: Optional[int] = None
    calculation_model: str
    config: dict[str, Any]
    effective_from: date
    effective_to: Optional[date] = None
    notes: Optional[str] = None


class SchemeValidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calculation_model: str
    config: dict[str, Any]


@router.get("/schemes")
def list_schemes(
    department_id: Optional[str] = Query(None),
    position_id: Optional[int] = Query(None),
    team_id: Optional[int] = Query(None),
    active_on: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    q = db.query(BonusScheme)
    if department_id:
        q = q.filter(BonusScheme.department_id == department_id)
    if position_id is not None:
        q = q.filter(BonusScheme.position_id == position_id)
    if team_id is not None:
        q = q.filter(BonusScheme.team_id == team_id)
    if active_on:
        q = q.filter(BonusScheme.effective_from <= active_on)
        from sqlalchemy import or_
        q = q.filter(or_(BonusScheme.effective_to.is_(None),
                         BonusScheme.effective_to >= active_on))
    rows = q.order_by(BonusScheme.department_id, BonusScheme.effective_from.desc()).all()
    return [_serialize(s) for s in rows]


@router.get("/schemes/{scheme_id}")
def get_scheme(
    scheme_id: int,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    s = db.query(BonusScheme).filter_by(id=scheme_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return _serialize(s)


@router.post("/schemes", status_code=201)
def create_scheme(
    payload: SchemeCreate,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    try:
        scheme = SchemeService(db).create(
            department_id=payload.department_id,
            position_id=payload.position_id,
            team_id=payload.team_id,
            calculation_model=payload.calculation_model,
            config=payload.config,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            notes=payload.notes,
        )
    except SchemeServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _serialize(scheme)


@router.post("/schemes/validate")
def validate_scheme(
    payload: SchemeValidate,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    try:
        normalized = SchemeService(db).validate_only(payload.calculation_model, payload.config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "normalized_config": normalized}


@router.get("/schemes/active/by-position")
def get_active_for_position(
    department_id: str,
    position_id: int,
    on_date: date,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    s = find_active_scheme_for_position(db, department_id, position_id, on_date)
    if not s:
        raise HTTPException(status_code=404, detail="No active scheme")
    return _serialize(s)

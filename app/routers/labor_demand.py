"""Labor-demand signal endpoints for TCO (Time Tracking).

Read-only enrichment: menu-mix (P1), forecast (P2), elasticity-signal (P3).
Sales Forecast is the demand-signal provider only — the solver, demand_by_role
and the schedule LLM agents live in TCO.

See docs/LABOR_OPTIMIZATION_ARCHITECTURE.md §2.
"""

from __future__ import annotations

import logging
import uuid as uuidlib
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_api_key_or_bypass
from ..db import get_db
from ..schemas.labor_demand import (
    ElasticitySignalResponse,
    ForecastResponse,
    MenuMixResponse,
)
from ..services.labor_demand_service import LaborDemandService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/labor-demand",
    tags=["labor-demand"],
    dependencies=[Depends(get_api_key_or_bypass)],
)


def _validate_uuid(department_id: str) -> None:
    try:
        uuidlib.UUID(department_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="department_id must be a valid UUID")


# ------------------------------------------------------------------
# §2.1 menu-mix (P1)
# ------------------------------------------------------------------

@router.get("/{department_id}/menu-mix", response_model=MenuMixResponse)
async def get_menu_mix(
    department_id: str,
    from_date: date = Query(..., description="Start of the forecast period"),
    to_date: Optional[date] = Query(None, description="End of the period (default = from_date)"),
    top_n: int = Query(25, ge=1, le=200, description="Max dishes in top_dishes"),
    db: Session = Depends(get_db),
):
    """Menu intelligence for one department over a period.

    Returns role distribution, top dishes and category load so TCO's agents
    can recommend *which* staff (hot-kitchen cook / pastry / barista), not just
    headcount. `data_quality` flags let TCO degrade gracefully while the SKU
    model is still being trained.
    """
    _validate_uuid(department_id)

    if to_date is None:
        to_date = from_date
    if to_date < from_date:
        raise HTTPException(status_code=400, detail="to_date must be >= from_date")
    if (to_date - from_date).days > 31:
        raise HTTPException(status_code=400, detail="Max range is 31 days")

    try:
        return LaborDemandService(db).menu_mix(department_id, from_date, to_date, top_n)
    except LookupError:
        raise HTTPException(status_code=404, detail="Department not found")


# ------------------------------------------------------------------
# §2.2 forecast (P2)
# ------------------------------------------------------------------

@router.get("/{department_id}/forecast", response_model=ForecastResponse)
async def get_forecast(
    department_id: str,
    from_date: date = Query(..., description="Start of the forecast period"),
    to_date: Optional[date] = Query(None, description="End of the period (default = from_date)"),
    db: Session = Depends(get_db),
):
    """Daily demand signal (revenue / receipts / qty) + intraday revenue curve.

    `hourly_profile` is the historical revenue share by hour for the weekday
    (sales_by_hour averaged over 8 weeks) — TCO multiplies it by
    `predicted_revenue` to get a forward intraday curve.
    """
    _validate_uuid(department_id)

    if to_date is None:
        to_date = from_date
    if to_date < from_date:
        raise HTTPException(status_code=400, detail="to_date must be >= from_date")
    if (to_date - from_date).days > 31:
        raise HTTPException(status_code=400, detail="Max range is 31 days")

    try:
        return LaborDemandService(db).forecast_signal(department_id, from_date, to_date)
    except LookupError:
        raise HTTPException(status_code=404, detail="Department not found")


# ------------------------------------------------------------------
# §2.3 elasticity-signal (P3)
# ------------------------------------------------------------------

_VALID_GRADES = {"A", "B", "C", "D"}


@router.get("/{department_id}/elasticity-signal", response_model=ElasticitySignalResponse)
async def get_elasticity_signal(
    department_id: str,
    grade: Optional[str] = Query(
        None, description="Comma-separated reliability grades to keep, e.g. 'A,B'"
    ),
    db: Session = Depends(get_db),
):
    """Per-SKU price elasticity for a department + network global prior.

    Ordered least-elastic first — those dishes are least price/quality
    sensitive, i.e. where understaffing hurts revenue most.
    """
    _validate_uuid(department_id)

    grades: Optional[list[str]] = None
    if grade:
        grades = [g.strip().upper() for g in grade.split(",") if g.strip()]
        invalid = set(grades) - _VALID_GRADES
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid grade(s): {', '.join(sorted(invalid))}. Allowed: A, B, C, D",
            )

    try:
        return LaborDemandService(db).elasticity_signal(department_id, grades)
    except LookupError:
        raise HTTPException(status_code=404, detail="Department not found")

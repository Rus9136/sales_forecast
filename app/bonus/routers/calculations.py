from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ...models.employee import Employee
from ..models.assignment import BonusEmployeeAssignment
from ..models.calculation import BonusCalculation, BonusCalculationPenalty
from ..models.position import BonusPosition
from ..services.runner import CalculationError, CalculatorRunner
from ..utils.decimal_utils import round_money, to_decimal
from ..utils.period import PeriodKey
from ._deps import parse_period

router = APIRouter()


# ---------------------------------------------------------------------------
# Run calculation
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: str
    year: int
    month: int
    scope: str = "all"  # 'all' | 'employee:<uuid>' | 'position:<code>' | 'team:<code>'


def _serialize_calc(c: BonusCalculation, *, include_breakdown: bool = False) -> dict:
    out = {
        "id": c.id,
        "employee_id": str(c.employee_id),
        "department_id": str(c.department_id),
        "period_year": c.period_year,
        "period_month": c.period_month,
        "scheme_id": c.scheme_id,
        "scheme_version": c.scheme_version,
        "team_id": c.team_id,
        "team_position_slot": c.team_position_slot,
        "overall_kpi_percent": str(c.overall_kpi_percent) if c.overall_kpi_percent is not None else None,
        "applied_grade_from": str(c.applied_grade_from) if c.applied_grade_from is not None else None,
        "applied_grade_to": str(c.applied_grade_to) if c.applied_grade_to is not None else None,
        "applied_coefficient": str(c.applied_coefficient) if c.applied_coefficient is not None else None,
        "coefficient_type": c.coefficient_type,
        "revenue_used": str(c.revenue_used) if c.revenue_used is not None else None,
        "revenue_source_used": c.revenue_source_used,
        "shifts_worked": str(c.shifts_worked) if c.shifts_worked is not None else None,
        "shifts_norm": str(c.shifts_norm) if c.shifts_norm is not None else None,
        "shifts_proration_applied": c.shifts_proration_applied,
        "base_bonus": str(c.base_bonus),
        "penalties_amount": str(c.penalties_amount),
        "final_bonus": str(c.final_bonus),
        "status": c.status,
        "calculated_at": c.calculated_at.isoformat() if c.calculated_at else None,
        "approved_at": c.approved_at.isoformat() if c.approved_at else None,
        "paid_at": c.paid_at.isoformat() if c.paid_at else None,
        "notes": c.notes,
    }
    if include_breakdown:
        out["scheme_config_snapshot"] = c.scheme_config_snapshot
        out["kpi_values"] = c.kpi_values
        out["breakdown"] = c.breakdown
    return out


@router.post("/calculations/run")
def run_calculations(
    payload: RunRequest,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    period = parse_period(payload.year, payload.month)
    runner = CalculatorRunner(db)

    targets = _resolve_targets(db, payload.department_id, period, payload.scope)
    if not targets:
        return {"requested": 0, "calculated": 0, "errors": [], "ids": []}

    ids: list[int] = []
    errors: list[dict[str, Any]] = []
    for emp_id, emp_name in targets:
        try:
            calc = runner.run_for_employee(
                employee_id=emp_id, department_id=payload.department_id,
                period=period, employee_name=emp_name,
            )
            ids.append(calc.id)
        except CalculationError as e:
            errors.append({"employee_id": emp_id, "error": str(e)})
        except Exception as e:  # noqa: BLE001 — bubble up specific message but don't crash batch
            db.rollback()
            errors.append({"employee_id": emp_id, "error": f"{type(e).__name__}: {e}"})

    return {
        "requested": len(targets),
        "calculated": len(ids),
        "errors": errors,
        "ids": ids,
    }


def _resolve_targets(db: Session, department_id: str, period: PeriodKey, scope: str):
    """Return [(employee_id, employee_name), ...] for the given scope."""
    from sqlalchemy import or_

    if scope.startswith("employee:"):
        emp_id = scope.split(":", 1)[1]
        row = db.query(Employee.id, Employee.name).filter(Employee.id == emp_id).first()
        return [(str(row[0]), row[1])] if row else []

    base_q = (
        db.query(BonusEmployeeAssignment.employee_id, Employee.name)
        .join(Employee, Employee.id == BonusEmployeeAssignment.employee_id)
        .filter(
            BonusEmployeeAssignment.department_id == department_id,
            BonusEmployeeAssignment.effective_from <= period.end,
            or_(
                BonusEmployeeAssignment.effective_to.is_(None),
                BonusEmployeeAssignment.effective_to >= period.end,
            ),
        )
    )

    if scope.startswith("position:"):
        code = scope.split(":", 1)[1]
        pos = db.query(BonusPosition.id).filter(BonusPosition.code == code).scalar()
        if pos is None:
            return []
        base_q = base_q.filter(BonusEmployeeAssignment.position_id == pos)

    rows = base_q.all()
    return [(str(eid), name) for eid, name in rows]


# ---------------------------------------------------------------------------
# List / detail
# ---------------------------------------------------------------------------
@router.get("/calculations")
def list_calculations(
    department_id: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    q = db.query(BonusCalculation)
    if department_id:
        q = q.filter(BonusCalculation.department_id == department_id)
    if year is not None:
        q = q.filter(BonusCalculation.period_year == year)
    if month is not None:
        q = q.filter(BonusCalculation.period_month == month)
    if employee_id:
        q = q.filter(BonusCalculation.employee_id == employee_id)
    if status:
        q = q.filter(BonusCalculation.status == status)
    rows = q.order_by(
        BonusCalculation.period_year.desc(),
        BonusCalculation.period_month.desc(),
        BonusCalculation.id.desc(),
    ).all()
    return [_serialize_calc(c) for c in rows]


@router.get("/calculations/{calc_id}")
def get_calculation(
    calc_id: int,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    c = db.query(BonusCalculation).filter_by(id=calc_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Calculation not found")
    out = _serialize_calc(c, include_breakdown=True)
    out["penalties"] = [
        {
            "id": p.id, "reason_code": p.reason_code, "reason_text": p.reason_text,
            "penalty_percent": str(p.penalty_percent) if p.penalty_percent is not None else None,
            "penalty_amount": str(p.penalty_amount),
            "document_ref": p.document_ref,
            "applied_at": p.applied_at.isoformat() if p.applied_at else None,
            "applied_by": p.applied_by,
        }
        for p in c.penalties
    ]
    return out


# ---------------------------------------------------------------------------
# Penalties / approve / reject
# ---------------------------------------------------------------------------
class PenaltyAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str
    reason_text: str
    penalty_percent: Optional[Decimal] = None
    penalty_amount: Optional[Decimal] = None
    document_ref: Optional[str] = None
    applied_by: Optional[str] = None


@router.post("/calculations/{calc_id}/penalties", status_code=201)
def add_penalty(
    calc_id: int,
    payload: PenaltyAdd,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    c = db.query(BonusCalculation).filter_by(id=calc_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Calculation not found")
    if c.status in ("paid",):
        raise HTTPException(status_code=409, detail="Cannot add penalty to a paid calculation")

    if payload.penalty_amount is None and payload.penalty_percent is None:
        raise HTTPException(status_code=422, detail="penalty_percent or penalty_amount required")

    base = to_decimal(c.base_bonus)
    if payload.penalty_amount is not None:
        amount = to_decimal(payload.penalty_amount)
    else:
        amount = (base * to_decimal(payload.penalty_percent) / Decimal(100))

    p = BonusCalculationPenalty(
        calculation_id=calc_id,
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        penalty_percent=payload.penalty_percent,
        penalty_amount=round_money(amount),
        document_ref=payload.document_ref,
        applied_by=payload.applied_by,
    )
    db.add(p)
    # Recompute totals
    c.penalties_amount = round_money(
        sum((to_decimal(x.penalty_amount) for x in c.penalties), Decimal(0)) + round_money(amount)
    )
    new_final = max(round_money(base) - c.penalties_amount, Decimal(0))
    c.final_bonus = round_money(new_final)
    db.commit()
    db.refresh(c)
    return {"penalty_id": p.id, "final_bonus": str(c.final_bonus),
            "penalties_amount": str(c.penalties_amount)}


@router.post("/calculations/{calc_id}/approve")
def approve(
    calc_id: int,
    actor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    c = db.query(BonusCalculation).filter_by(id=calc_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Calculation not found")
    if c.status not in ("draft", "review", "recalculated"):
        raise HTTPException(status_code=409, detail=f"Cannot approve from status {c.status!r}")
    c.status = "approved"
    c.approved_at = datetime.utcnow()
    c.approved_by = actor
    db.commit()
    return {"id": c.id, "status": c.status}


@router.post("/calculations/{calc_id}/reject")
def reject(
    calc_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    c = db.query(BonusCalculation).filter_by(id=calc_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Calculation not found")
    c.status = "rejected"
    if reason:
        c.notes = (c.notes + "\n" if c.notes else "") + f"REJECTED: {reason}"
    db.commit()
    return {"id": c.id, "status": c.status}


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
@router.get("/reports/summary")
def report_summary(
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    rows = (
        db.query(
            BonusCalculation.department_id,
            func.count(BonusCalculation.id),
            func.sum(BonusCalculation.final_bonus),
            func.avg(BonusCalculation.final_bonus),
        )
        .filter(
            BonusCalculation.period_year == year,
            BonusCalculation.period_month == month,
            BonusCalculation.status.in_(("draft", "review", "approved", "paid", "recalculated")),
        )
        .group_by(BonusCalculation.department_id)
        .all()
    )
    return [
        {
            "department_id": str(d), "count": cnt,
            "total": str(round_money(to_decimal(total))) if total is not None else "0",
            "average": str(round_money(to_decimal(avg))) if avg is not None else "0",
        }
        for d, cnt, total, avg in rows
    ]

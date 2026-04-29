"""APScheduler entry point for monthly bonus auto-calculation.

Runs once a month (5th day, 05:00) — calculates DRAFT bonuses for all
employees with an active assignment in the previous month. Existing
draft/review records get superseded; approved/paid records are left alone.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import or_

from ...db import SessionLocal
from ..models.assignment import BonusEmployeeAssignment
from ..services.runner import CalculationError, CalculatorRunner
from ..utils.period import PeriodKey

logger = logging.getLogger(__name__)


def _previous_month(today: date) -> PeriodKey:
    if today.month == 1:
        return PeriodKey(today.year - 1, 12)
    return PeriodKey(today.year, today.month - 1)


def run_monthly_auto_calc() -> dict:
    """Calculate bonuses for the previous month for every employee that has an
    active assignment.
    """
    today = date.today()
    period = _previous_month(today)
    logger.info("Bonus auto-calc starting for period %s", period)

    db = SessionLocal()
    try:
        targets = (
            db.query(BonusEmployeeAssignment.employee_id, BonusEmployeeAssignment.department_id)
            .filter(
                BonusEmployeeAssignment.effective_from <= period.end,
                or_(
                    BonusEmployeeAssignment.effective_to.is_(None),
                    BonusEmployeeAssignment.effective_to >= period.end,
                ),
            )
            .all()
        )
        runner = CalculatorRunner(db)
        ok, errors = 0, []
        for emp_id, dept_id in targets:
            try:
                runner.run_for_employee(
                    employee_id=str(emp_id),
                    department_id=str(dept_id),
                    period=period,
                    actor="scheduler",
                )
                ok += 1
            except CalculationError as e:
                errors.append({"employee_id": str(emp_id), "error": str(e)})
            except Exception as e:  # noqa: BLE001
                db.rollback()
                errors.append({"employee_id": str(emp_id), "error": f"{type(e).__name__}: {e}"})

        logger.info(
            "Bonus auto-calc done: period=%s targets=%d ok=%d errors=%d",
            period, len(targets), ok, len(errors),
        )
        return {
            "status": "success",
            "period": str(period),
            "targets": len(targets),
            "calculated": ok,
            "errors": errors[:50],
            "error_count": len(errors),
        }
    finally:
        db.close()

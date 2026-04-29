"""CalculatorRunner — orchestrates a single bonus calculation end to end.

Pipeline:
  1. Resolve active scheme for (department, position) or (department, team) on period_end
  2. Preload context
  3. Get model from registry, validate config, calculate
  4. Persist BonusCalculation with full snapshot

Idempotent: re-running for the same (employee, period) marks any prior `draft`
as `superseded` and creates a new draft. `approved`/`paid` calculations are
left untouched and the new one is saved with status `recalculated`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..calculator import get_model
from ..calculator.context import CalculationContext
from ..calculator.result import BonusResult
from ..models.assignment import BonusEmployeeAssignment
from ..models.calculation import BonusCalculation
from ..models.scheme import BonusScheme
from ..repositories.scheme_repository import (
    find_active_scheme_for_position,
    find_active_scheme_for_team,
)
from ..utils.decimal_utils import round_money, to_decimal
from ..utils.period import PeriodKey
from .preloader import CalculationPreloader

logger = logging.getLogger(__name__)


class CalculationError(Exception):
    pass


class CalculatorRunner:
    """Run a bonus calculation for one (employee, period) pair."""

    def __init__(self, db: Session):
        self.db = db
        self.preloader = CalculationPreloader(db)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run_for_employee(
        self,
        employee_id: str,
        department_id: str,
        period: PeriodKey,
        *,
        scheme: Optional[BonusScheme] = None,
        employee_name: str = "",
        department_name: str = "",
        actor: Optional[str] = None,
    ) -> BonusCalculation:
        """Calculate and persist a bonus for one employee.

        If `scheme` is None, the active assignment + scheme are auto-resolved.
        """
        assignment = self._resolve_assignment(employee_id, department_id, period)

        if scheme is None:
            scheme = self._resolve_scheme(department_id, assignment, period)
        if scheme is None:
            raise CalculationError(
                f"No active bonus scheme for employee {employee_id} "
                f"on {period} (dept={department_id}, position={assignment.position_id if assignment else None})"
            )

        ctx = self.preloader.preload(
            scheme_config=scheme.config,
            period=period,
            department_id=department_id,
            department_name=department_name,
            employee_id=employee_id,
            employee_name=employee_name,
            team_id=scheme.team_id or (assignment.team_id if assignment else None),
            team_position_slot=assignment.team_position_slot if assignment else None,
            employment_type=assignment.employment_type if assignment else "permanent",
            probation_until=assignment.probation_until if assignment else None,
        )

        model = get_model(scheme.calculation_model)
        model.validate_config(scheme.config)
        result = model.calculate(scheme.config, ctx)

        return self._persist(employee_id, department_id, period, scheme, ctx, result, actor=actor)

    # ------------------------------------------------------------------ #
    # Resolution helpers
    # ------------------------------------------------------------------ #

    def _resolve_assignment(
        self,
        employee_id: str,
        department_id: str,
        period: PeriodKey,
    ) -> Optional[BonusEmployeeAssignment]:
        from sqlalchemy import or_
        return (
            self.db.query(BonusEmployeeAssignment)
            .filter(
                BonusEmployeeAssignment.employee_id == employee_id,
                BonusEmployeeAssignment.department_id == department_id,
                BonusEmployeeAssignment.effective_from <= period.end,
                or_(
                    BonusEmployeeAssignment.effective_to.is_(None),
                    BonusEmployeeAssignment.effective_to >= period.end,
                ),
            )
            .order_by(BonusEmployeeAssignment.effective_from.desc())
            .first()
        )

    def _resolve_scheme(
        self,
        department_id: str,
        assignment: Optional[BonusEmployeeAssignment],
        period: PeriodKey,
    ) -> Optional[BonusScheme]:
        if assignment is None:
            return None
        # Team scheme takes precedence (KITCHEN-style collective)
        if assignment.team_id is not None:
            team_scheme = find_active_scheme_for_team(
                self.db, department_id, assignment.team_id, period.end,
            )
            if team_scheme is not None:
                return team_scheme
        return find_active_scheme_for_position(
            self.db, department_id, assignment.position_id, period.end,
        )

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _persist(
        self,
        employee_id: str,
        department_id: str,
        period: PeriodKey,
        scheme: BonusScheme,
        ctx: CalculationContext,
        result: BonusResult,
        *,
        actor: Optional[str],
    ) -> BonusCalculation:
        # Supersede prior active calculations for this employee+period
        prior = (
            self.db.query(BonusCalculation)
            .filter(
                BonusCalculation.employee_id == employee_id,
                BonusCalculation.period_year == period.year,
                BonusCalculation.period_month == period.month,
                BonusCalculation.status.in_(["draft", "review"]),
            )
            .all()
        )
        for p in prior:
            p.status = "superseded"

        # If an approved/paid one already exists, keep it; new one becomes 'recalculated'.
        has_approved = (
            self.db.query(BonusCalculation.id)
            .filter(
                BonusCalculation.employee_id == employee_id,
                BonusCalculation.period_year == period.year,
                BonusCalculation.period_month == period.month,
                BonusCalculation.status.in_(["approved", "paid"]),
            )
            .first()
        )
        new_status = "recalculated" if has_approved else "draft"

        kpi_values_json = result.kpi_values_snapshot or [
            {"code": code, "fact": str(fact.fact) if fact.fact is not None else None,
             "target": str(fact.target) if fact.target is not None else None,
             "percent": str(fact.percent), "direction": fact.direction}
            for code, fact in ctx.kpi_values.items()
        ]

        # JSONB columns require JSON-serialisable structures
        scheme_config_snapshot = _json_safe(scheme.config)
        breakdown_dump = _json_safe(result.breakdown.to_dict())
        kpi_values_dump = _json_safe(kpi_values_json)

        calc = BonusCalculation(
            employee_id=employee_id,
            department_id=department_id,
            period_year=period.year,
            period_month=period.month,

            scheme_id=scheme.id,
            scheme_version=scheme.version,
            scheme_config_snapshot=scheme_config_snapshot,

            team_id=ctx.team_id,
            team_position_slot=ctx.team_position_slot,

            kpi_values=kpi_values_dump,
            overall_kpi_percent=result.overall_kpi_percent,

            applied_grade_from=result.applied_grade_from,
            applied_grade_to=result.applied_grade_to,
            applied_coefficient=result.applied_coefficient,
            coefficient_type=result.coefficient_type,

            revenue_used=to_decimal(result.revenue_used) if result.revenue_used is not None else None,
            revenue_source_used=result.revenue_source_used,
            shifts_worked=result.shifts_worked,
            shifts_norm=result.shifts_norm,
            shifts_proration_applied=result.shifts_proration_applied,

            base_bonus=round_money(result.base_bonus),
            penalties_amount=Decimal(0),
            final_bonus=result.final_bonus,
            breakdown=breakdown_dump,

            status=new_status,
            calculated_at=datetime.utcnow(),
            calculated_by=actor,
        )
        self.db.add(calc)
        self.db.commit()
        self.db.refresh(calc)
        logger.info(
            "Bonus calculated: emp=%s dept=%s period=%s scheme=%s status=%s final=%s",
            employee_id, department_id, period, scheme.id, new_status, calc.final_bonus,
        )
        return calc


def _json_safe(value):
    """Coerce Decimals/dates into JSON-serialisable types for JSONB storage."""
    return json.loads(json.dumps(value, default=_default))


def _default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj).__name__}")

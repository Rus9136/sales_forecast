"""Helpers shared by all seed modules. Idempotent upserts."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.company import BonusCompany
from ..models.kpi import BonusKpiDefinition
from ..models.position import BonusPosition
from ..models.scheme import BonusScheme
from ..models.team import BonusTeam, BonusTeamPosition

logger = logging.getLogger(__name__)


def upsert_company(db: Session, *, code: str, name: str, bin: Optional[str] = None) -> BonusCompany:
    obj = db.query(BonusCompany).filter_by(code=code).first()
    if obj is None:
        obj = BonusCompany(code=code, name=name, bin=bin)
        db.add(obj)
    else:
        obj.name = name
        obj.bin = bin
    db.flush()
    return obj


def upsert_position(
    db: Session, *,
    code: str, name: str, category: str,
    iiko_role_code: Optional[str] = None,
    iiko_role_name: Optional[str] = None,
) -> BonusPosition:
    obj = db.query(BonusPosition).filter_by(code=code).first()
    if obj is None:
        obj = BonusPosition(
            code=code, name=name, category=category,
            iiko_role_code=iiko_role_code, iiko_role_name=iiko_role_name,
        )
        db.add(obj)
    else:
        obj.name = name
        obj.category = category
        obj.iiko_role_code = iiko_role_code
        obj.iiko_role_name = iiko_role_name
    db.flush()
    return obj


def upsert_kpi_definition(
    db: Session, *,
    code: str, name: str, data_source_code: str, direction: str,
    default_target=None, target_metric=None, cap_at_100_percent: bool = True,
    description: Optional[str] = None,
) -> BonusKpiDefinition:
    obj = db.query(BonusKpiDefinition).filter_by(code=code).first()
    if obj is None:
        obj = BonusKpiDefinition(
            code=code, name=name, data_source_code=data_source_code,
            direction=direction, default_target=default_target,
            target_metric=target_metric, cap_at_100_percent=cap_at_100_percent,
            description=description,
        )
        db.add(obj)
    else:
        obj.name = name
        obj.data_source_code = data_source_code
        obj.direction = direction
        obj.default_target = default_target
        obj.target_metric = target_metric
        obj.cap_at_100_percent = cap_at_100_percent
        obj.description = description
    db.flush()
    return obj


def upsert_team(db: Session, *, department_id: str, code: str, name: str) -> BonusTeam:
    obj = db.query(BonusTeam).filter_by(department_id=department_id, code=code).first()
    if obj is None:
        obj = BonusTeam(department_id=department_id, code=code, name=name)
        db.add(obj)
    else:
        obj.name = name
    db.flush()
    return obj


def upsert_team_position(
    db: Session, *,
    team_id: int, position_id: int, slot: str,
    display_name: str, distribution_weight,
    sort_order: int, effective_from: date,
) -> BonusTeamPosition:
    obj = (
        db.query(BonusTeamPosition)
        .filter_by(team_id=team_id, slot=slot, effective_from=effective_from)
        .first()
    )
    if obj is None:
        obj = BonusTeamPosition(
            team_id=team_id, position_id=position_id, slot=slot,
            display_name=display_name, distribution_weight=distribution_weight,
            sort_order=sort_order, effective_from=effective_from,
        )
        db.add(obj)
    else:
        obj.position_id = position_id
        obj.display_name = display_name
        obj.distribution_weight = distribution_weight
        obj.sort_order = sort_order
    db.flush()
    return obj


def upsert_scheme(
    db: Session, *,
    department_id: str,
    position_id: Optional[int],
    team_id: Optional[int],
    calculation_model: str,
    config: dict[str, Any],
    effective_from: date,
    notes: Optional[str] = None,
) -> BonusScheme:
    """Create-or-update a scheme. Validates config via SchemeService.

    For idempotent re-runs: if a scheme with the same target and
    effective_from exists, replace its config in place instead of versioning.
    """
    from ..schemas.calc_configs import validate_config
    normalized = validate_config(calculation_model, config)

    obj = (
        db.query(BonusScheme)
        .filter_by(
            department_id=department_id,
            position_id=position_id,
            team_id=team_id,
            effective_from=effective_from,
        )
        .first()
    )
    if obj is None:
        obj = BonusScheme(
            department_id=department_id,
            position_id=position_id,
            team_id=team_id,
            calculation_model=calculation_model,
            config=normalized,
            effective_from=effective_from,
            notes=notes,
            version=1,
        )
        db.add(obj)
    else:
        obj.calculation_model = calculation_model
        obj.config = normalized
        obj.notes = notes
    db.flush()
    return obj


def find_department_by_name(db: Session, name_substring: str):
    """Best-effort department lookup. Returns None if not found.

    `name_substring` may be a partial match (case-insensitive). Multiple matches
    cause a warning and return the first.
    """
    from ...models.department import Department
    rows = (
        db.query(Department.id, Department.name)
        .filter(Department.type == "DEPARTMENT")
        .filter(Department.name.ilike(f"%{name_substring}%"))
        .all()
    )
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "Department lookup '%s' matched %d rows: %s — using the first",
            name_substring, len(rows), [r[1] for r in rows],
        )
    return rows[0][0]

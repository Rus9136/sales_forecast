from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models.scheme import BonusScheme


def find_active_scheme_for_position(
    db: Session,
    department_id: str,
    position_id: int,
    on_date: date,
) -> Optional[BonusScheme]:
    """Return the bonus_scheme active on `on_date` for (department, position), if any."""
    return (
        db.query(BonusScheme)
        .filter(
            BonusScheme.department_id == department_id,
            BonusScheme.position_id == position_id,
            BonusScheme.team_id.is_(None),
            BonusScheme.effective_from <= on_date,
            or_(BonusScheme.effective_to.is_(None), BonusScheme.effective_to >= on_date),
        )
        .order_by(BonusScheme.version.desc())
        .first()
    )


def find_active_scheme_for_team(
    db: Session,
    department_id: str,
    team_id: int,
    on_date: date,
) -> Optional[BonusScheme]:
    return (
        db.query(BonusScheme)
        .filter(
            BonusScheme.department_id == department_id,
            BonusScheme.team_id == team_id,
            BonusScheme.position_id.is_(None),
            BonusScheme.effective_from <= on_date,
            or_(BonusScheme.effective_to.is_(None), BonusScheme.effective_to >= on_date),
        )
        .order_by(BonusScheme.version.desc())
        .first()
    )


def list_overlapping_versions(
    db: Session,
    department_id: str,
    position_id: Optional[int],
    team_id: Optional[int],
    effective_from: date,
    effective_to: Optional[date],
    exclude_id: Optional[int] = None,
) -> list[BonusScheme]:
    """Schemes for the same target whose validity period overlaps the given range."""
    end = effective_to if effective_to else date.max
    q = db.query(BonusScheme).filter(
        BonusScheme.department_id == department_id,
        BonusScheme.position_id == position_id,
        BonusScheme.team_id == team_id,
        BonusScheme.effective_from <= end,
        or_(BonusScheme.effective_to.is_(None), BonusScheme.effective_to >= effective_from),
    )
    if exclude_id is not None:
        q = q.filter(BonusScheme.id != exclude_id)
    return q.all()

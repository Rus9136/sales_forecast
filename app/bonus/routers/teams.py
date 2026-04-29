from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ..models.team import BonusTeam, BonusTeamPosition

router = APIRouter()


def _serialize_team(t: BonusTeam) -> dict:
    return {
        "id": t.id, "department_id": str(t.department_id),
        "code": t.code, "name": t.name, "is_active": t.is_active,
    }


def _serialize_slot(s: BonusTeamPosition) -> dict:
    return {
        "id": s.id, "team_id": s.team_id, "position_id": s.position_id,
        "slot": s.slot, "display_name": s.display_name,
        "distribution_weight": str(s.distribution_weight),
        "sort_order": s.sort_order,
        "effective_from": s.effective_from.isoformat() if s.effective_from else None,
        "effective_to": s.effective_to.isoformat() if s.effective_to else None,
    }


@router.get("/teams")
def list_teams(
    department_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    q = db.query(BonusTeam).filter_by(is_active=True)
    if department_id:
        q = q.filter(BonusTeam.department_id == department_id)
    return [_serialize_team(t) for t in q.order_by(BonusTeam.name).all()]


@router.get("/teams/{team_id}")
def get_team(
    team_id: int,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    t = db.query(BonusTeam).filter_by(id=team_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    slots = (
        db.query(BonusTeamPosition)
        .filter_by(team_id=team_id)
        .order_by(BonusTeamPosition.sort_order, BonusTeamPosition.slot)
        .all()
    )
    return {**_serialize_team(t), "positions": [_serialize_slot(s) for s in slots]}

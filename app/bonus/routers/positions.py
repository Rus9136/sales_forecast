from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ..models.position import BonusPosition

router = APIRouter()


def _serialize(p: BonusPosition) -> dict:
    return {
        "id": p.id, "code": p.code, "name": p.name, "category": p.category,
        "iiko_role_code": p.iiko_role_code, "iiko_role_name": p.iiko_role_name,
        "description": p.description, "is_active": p.is_active,
    }


@router.get("/positions")
def list_positions(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    q = db.query(BonusPosition).filter_by(is_active=True)
    if category:
        q = q.filter_by(category=category)
    return [_serialize(p) for p in q.order_by(BonusPosition.category, BonusPosition.name).all()]

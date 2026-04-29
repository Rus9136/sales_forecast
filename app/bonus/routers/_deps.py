"""Common router helpers (auth pass-through, period parsing)."""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from ..utils.period import PeriodKey


def parse_period(year: int, month: int) -> PeriodKey:
    try:
        return PeriodKey(year, month)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def parse_uuid_or_400(value: str, name: str = "id") -> str:
    """Light validation — keep DB-layer typing happy."""
    import uuid as _uuid
    try:
        _uuid.UUID(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {name}: not a UUID")
    return value

"""Scheme service — create/version/validate bonus_scheme rows."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.scheme import BonusScheme
from ..repositories.scheme_repository import list_overlapping_versions
from ..schemas.calc_configs import validate_config

logger = logging.getLogger(__name__)


class SchemeServiceError(Exception):
    pass


class SchemeService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        department_id: str,
        position_id: Optional[int],
        team_id: Optional[int],
        calculation_model: str,
        config: dict[str, Any],
        effective_from: date,
        effective_to: Optional[date] = None,
        notes: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> BonusScheme:
        """Create a scheme. If an active scheme exists for the same target, it is
        closed at (effective_from - 1 day). The new scheme becomes version+1.
        """
        if (position_id is None) == (team_id is None):
            raise SchemeServiceError("Exactly one of position_id / team_id must be set")

        # Validate config shape
        normalized = validate_config(calculation_model, config)

        # Close overlapping prior schemes
        overlapping = list_overlapping_versions(
            self.db, department_id, position_id, team_id, effective_from, effective_to,
        )
        max_version = 0
        for prev in overlapping:
            if prev.version > max_version:
                max_version = prev.version
            if prev.effective_to is None or prev.effective_to >= effective_from:
                prev.effective_to = effective_from - timedelta(days=1)
                logger.info("Closed prior scheme id=%s on %s (new version starts %s)",
                            prev.id, prev.effective_to, effective_from)

        scheme = BonusScheme(
            department_id=department_id,
            position_id=position_id,
            team_id=team_id,
            calculation_model=calculation_model,
            config=normalized,
            effective_from=effective_from,
            effective_to=effective_to,
            version=max_version + 1,
            notes=notes,
            created_by=created_by,
        )
        self.db.add(scheme)
        self.db.commit()
        self.db.refresh(scheme)
        return scheme

    def validate_only(self, calculation_model: str, config: dict[str, Any]) -> dict:
        """Validate config without persisting. Raises ValueError on failure."""
        return validate_config(calculation_model, config)

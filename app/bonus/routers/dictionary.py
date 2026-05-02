"""Reference catalogues — companies, KPI defs, calculation models, data sources."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ..calculator import CALCULATION_MODELS
from ..data_sources.registry import DataSourceRegistry
from ..models.company import BonusCompany
from ..models.kpi import BonusKpiDefinition

router = APIRouter()


@router.get("/companies")
def list_companies(
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    rows = db.query(BonusCompany).filter_by(is_active=True).order_by(BonusCompany.name).all()
    return [
        {"id": c.id, "code": c.code, "name": c.name, "bin": c.bin, "is_active": c.is_active}
        for c in rows
    ]


@router.get("/kpi-definitions")
def list_kpi_definitions(
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    rows = db.query(BonusKpiDefinition).filter_by(is_active=True).order_by(BonusKpiDefinition.code).all()
    return [
        {
            "id": k.id, "code": k.code, "name": k.name, "description": k.description,
            "data_source_code": k.data_source_code, "direction": k.direction,
            "default_target": str(k.default_target) if k.default_target is not None else None,
            "target_metric": k.target_metric,
            "cap_at_100_percent": k.cap_at_100_percent,
        }
        for k in rows
    ]


@router.get("/config/calculation-models")
def list_calculation_models(_: Optional[ApiKey] = Depends(get_api_key_or_bypass)):
    """Return calculation models with metadata describing required config blocks.

    The UI uses this to render the appropriate scheme editor sections.
    """
    from ..calculator.metadata import CALCULATION_MODEL_METADATA
    return [
        CALCULATION_MODEL_METADATA[code]
        for code in sorted(CALCULATION_MODELS.keys())
        if code in CALCULATION_MODEL_METADATA
    ]


@router.get("/config/data-sources")
def list_data_sources(_: Optional[ApiKey] = Depends(get_api_key_or_bypass)):
    """Return all registered data sources with human-readable metadata."""
    return DataSourceRegistry.list_metadata()

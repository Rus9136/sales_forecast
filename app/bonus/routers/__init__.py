"""FastAPI routers for the bonus subsystem.

All endpoints live under /api/bonus/*. Authentication is delegated to the
existing get_api_key_or_bypass dependency from the parent app — no new
auth scheme.
"""

from fastapi import APIRouter

from . import schemes, teams, positions, kpi, plans, calculations, dictionary

bonus_api = APIRouter(prefix="/bonus", tags=["bonus"])

bonus_api.include_router(dictionary.router)
bonus_api.include_router(positions.router)
bonus_api.include_router(schemes.router)
bonus_api.include_router(teams.router)
bonus_api.include_router(kpi.router)
bonus_api.include_router(plans.router)
bonus_api.include_router(calculations.router)

"""API router for the AI Recommendations subsystem.

Endpoints mirror the hr-miniapp ones (with FastAPI conventions). All routes
require a valid Bearer token via the standard `get_api_key_or_bypass` dep.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from ..auth import ApiKey, get_api_key_or_bypass
from ..db import get_db
from ..models.ai import AIPromptLog, AIRecommendation
from ..models.department import Department
from ..schemas.ai import (
    AnalysisDetailResponse,
    AnalysisPromptsResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    HistoryItem,
    PromptInfo,
    RerunAgentRequest,
    UpdatePromptsRequest,
)
from ..services.ai.data_collector import collect_dashboard_data
from ..services.ai.engines import get_dispatcher
from ..services.ai.multi_agent_system import (
    AGENTS,
    get_multi_agent_system,
)
from ..services.ai.prompts import (
    DEFAULT_PROMPTS,
    list_all_prompts,
    upsert_prompt,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-recommendations", tags=["ai-recommendations"])


@router.get("/providers")
def get_providers(_: Optional[ApiKey] = Depends(get_api_key_or_bypass)) -> dict:
    """Return information about configured AI providers."""
    return get_dispatcher().providers_info()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> AnalyzeResponse:
    """Run multi-agent analysis for a department/period."""
    if payload.date_start > payload.date_end:
        raise HTTPException(status_code=400, detail="date_start must be <= date_end")

    department = db.query(Department).filter(Department.id == payload.department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    raw_data = collect_dashboard_data(
        db,
        payload.department_id,
        payload.date_start,
        payload.date_end,
    )

    record = AIRecommendation(
        department_id=payload.department_id,
        date_start=payload.date_start,
        date_end=payload.date_end,
        mcp_response=raw_data,
        agent_results={},
        provider=payload.provider,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    system = get_multi_agent_system()
    outcome = await system.run_analysis(
        db,
        analysis_id=record.id,
        raw_data=raw_data,
        provider=payload.provider,
    )

    record.agent_results = outcome.results
    db.commit()
    db.refresh(record)

    return AnalyzeResponse(
        analysis_id=record.id,
        department_id=record.department_id,
        date_start=record.date_start,
        date_end=record.date_end,
        provider=record.provider,
        success=outcome.success,
        results=outcome.results,
        errors=outcome.errors,
        skipped=outcome.skipped,
        metadata=outcome.metadata,
        created_at=record.created_at,
    )


@router.get("/history", response_model=list[HistoryItem])
def get_history(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> list[HistoryItem]:
    query = db.query(AIRecommendation).options(joinedload(AIRecommendation.department))
    if department_id:
        query = query.filter(AIRecommendation.department_id == department_id)
    rows = (
        query.order_by(desc(AIRecommendation.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        HistoryItem(
            id=r.id,
            department_id=r.department_id,
            department_name=r.department.name if r.department else None,
            date_start=r.date_start,
            date_end=r.date_end,
            provider=r.provider,
            agent_count=len(r.agent_results or {}),
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/analysis/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> AnalysisDetailResponse:
    row = (
        db.query(AIRecommendation)
        .options(joinedload(AIRecommendation.department))
        .filter(AIRecommendation.id == analysis_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisDetailResponse(
        id=row.id,
        department_id=row.department_id,
        department_name=row.department.name if row.department else None,
        date_start=row.date_start,
        date_end=row.date_end,
        provider=row.provider,
        agent_results=row.agent_results or {},
        created_at=row.created_at,
    )


@router.get("/prompts/{analysis_id}", response_model=AnalysisPromptsResponse)
def get_analysis_prompts(
    analysis_id: int,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> AnalysisPromptsResponse:
    """Return UI-shaped data for the per-analysis tabs view.

    Includes: analysis info + per-agent result + the prompt log for that
    agent so the UI can show 'Result' / 'Prompt' subtabs.
    """
    rec = (
        db.query(AIRecommendation)
        .options(joinedload(AIRecommendation.department))
        .filter(AIRecommendation.id == analysis_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Analysis not found")

    logs = (
        db.query(AIPromptLog)
        .filter(AIPromptLog.analysis_id == analysis_id)
        .order_by(AIPromptLog.request_timestamp)
        .all()
    )
    logs_by_agent: dict[str, AIPromptLog] = {}
    for log in logs:
        # Keep latest log per agent (rerun-agent overwrites the displayed entry)
        logs_by_agent[log.agent_name] = log

    agents_payload: list[dict] = []
    for agent_name, cfg in AGENTS.items():
        if not cfg.enabled and agent_name not in (rec.agent_results or {}):
            continue
        result_text = (rec.agent_results or {}).get(agent_name)
        log = logs_by_agent.get(agent_name)
        prompt_block: Optional[dict[str, Any]] = None
        if log:
            response_time = None
            if log.response_timestamp and log.request_timestamp:
                response_time = (
                    log.response_timestamp - log.request_timestamp
                ).total_seconds()
            prompt_block = {
                "full_prompt": log.full_prompt,
                "system_prompt": log.system_prompt,
                "provider": log.provider,
                "success": log.success,
                "tokens_used": log.tokens_used or 0,
                "request_timestamp": log.request_timestamp.isoformat(),
                "response_timestamp": log.response_timestamp.isoformat()
                if log.response_timestamp
                else None,
                "response_time_seconds": response_time,
                "error_message": log.error_message,
            }
        agents_payload.append(
            {
                "agent_name": agent_name,
                "title": cfg.description,
                "enabled": cfg.enabled,
                "result": result_text,
                "has_result": bool(result_text),
                "prompt": prompt_block,
            }
        )

    return AnalysisPromptsResponse(
        analysis=AnalysisDetailResponse(
            id=rec.id,
            department_id=rec.department_id,
            department_name=rec.department.name if rec.department else None,
            date_start=rec.date_start,
            date_end=rec.date_end,
            provider=rec.provider,
            agent_results=rec.agent_results or {},
            created_at=rec.created_at,
        ),
        agents=agents_payload,
    )


@router.get("/prompts", response_model=list[PromptInfo])
def get_prompts(
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> list[PromptInfo]:
    rows = list_all_prompts(db)
    items: list[PromptInfo] = []
    for agent_name, info in rows.items():
        updated_at = info["updated_at"]
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        items.append(
            PromptInfo(
                agent_name=agent_name,
                prompt=info["prompt"],
                source=info["source"],
                updated_at=updated_at,
            )
        )
    return items


@router.put("/prompts")
def update_prompts(
    payload: UpdatePromptsRequest,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> dict:
    if not payload.prompts:
        raise HTTPException(status_code=400, detail="No prompts provided")
    updated = []
    for agent_name, text in payload.prompts.items():
        if agent_name not in DEFAULT_PROMPTS and agent_name not in AGENTS:
            raise HTTPException(
                status_code=400, detail=f"Unknown agent '{agent_name}'"
            )
        if not text or not text.strip():
            raise HTTPException(
                status_code=400, detail=f"Empty prompt for '{agent_name}'"
            )
        upsert_prompt(db, agent_name, text)
        updated.append(agent_name)
    return {"updated": updated, "count": len(updated)}


@router.post("/rerun-agent")
async def rerun_agent(
    payload: RerunAgentRequest,
    db: Session = Depends(get_db),
    _: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> dict:
    rec = (
        db.query(AIRecommendation)
        .filter(AIRecommendation.id == payload.analysis_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if payload.agent_name not in AGENTS:
        raise HTTPException(
            status_code=400, detail=f"Unknown agent '{payload.agent_name}'"
        )

    raw_data = rec.mcp_response
    previous_results = rec.agent_results or {}

    system = get_multi_agent_system()
    outcome = await system.run_single_agent(
        db,
        analysis_id=rec.id,
        agent_name=payload.agent_name,
        raw_data=raw_data,
        previous_results=previous_results,
        prompt_override=payload.new_prompt,
        provider=payload.provider,
    )

    if outcome.success and outcome.content:
        # Persist the new result back into agent_results JSONB.
        merged = dict(rec.agent_results or {})
        merged[payload.agent_name] = outcome.content
        rec.agent_results = merged
        # SQLAlchemy needs a flag for in-place JSONB mutation
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(rec, "agent_results")
        db.commit()
        db.refresh(rec)

    return {
        "success": outcome.success,
        "agent_name": outcome.agent_name,
        "result": outcome.content,
        "error": outcome.error,
        "tokens_used": outcome.tokens_used,
    }

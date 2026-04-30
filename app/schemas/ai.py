"""Pydantic schemas for the AI Recommendations API."""

from __future__ import annotations

from datetime import date as date_type, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    department_id: UUID
    date_start: date_type
    date_end: date_type
    provider: str = Field(default="claude", pattern="^(claude|openai|gemini)$")


class AgentResultItem(BaseModel):
    agent_name: str
    title: str
    description: str
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None


class AnalyzeResponse(BaseModel):
    analysis_id: int
    department_id: UUID
    date_start: date_type
    date_end: date_type
    provider: str
    success: bool
    results: dict[str, str]
    errors: dict[str, str]
    skipped: list[str]
    metadata: dict[str, Any]
    created_at: datetime


class HistoryItem(BaseModel):
    id: int
    department_id: UUID
    department_name: Optional[str] = None
    date_start: date_type
    date_end: date_type
    provider: str
    agent_count: int
    created_at: datetime


class PromptInfo(BaseModel):
    agent_name: str
    prompt: str
    source: str  # "db" or "default"
    updated_at: Optional[datetime] = None


class UpdatePromptsRequest(BaseModel):
    prompts: dict[str, str]


class RerunAgentRequest(BaseModel):
    analysis_id: int
    agent_name: str
    new_prompt: Optional[str] = None
    provider: str = Field(default="claude", pattern="^(claude|openai|gemini)$")


class PromptLogItem(BaseModel):
    agent_name: str
    provider: str
    full_prompt: str
    system_prompt: Optional[str] = None
    response_text: Optional[str] = None
    success: bool
    tokens_used: int
    request_timestamp: datetime
    response_timestamp: Optional[datetime] = None
    response_time_seconds: Optional[float] = None
    error_message: Optional[str] = None


class AnalysisDetailResponse(BaseModel):
    id: int
    department_id: UUID
    department_name: Optional[str] = None
    date_start: date_type
    date_end: date_type
    provider: str
    agent_results: dict[str, str]
    created_at: datetime


class AnalysisPromptsResponse(BaseModel):
    analysis: AnalysisDetailResponse
    agents: list[dict]

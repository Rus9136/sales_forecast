"""Shared prompt-logging helper for engines.

Writes a row into ai_prompt_logs. Failures are swallowed and logged — the AI
call has already happened, we don't want to break the analysis just because
audit logging failed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ....models.ai import AIPromptLog

logger = logging.getLogger(__name__)


def log_prompt(
    db: Optional[Session],
    *,
    analysis_id: Optional[int],
    agent_name: str,
    provider: str,
    full_prompt: str,
    system_prompt: Optional[str],
    response_text: Optional[str],
    success: bool,
    tokens_used: int,
    request_timestamp: datetime,
    response_timestamp: Optional[datetime],
    error_message: Optional[str] = None,
) -> Optional[int]:
    """Persist a prompt log entry. Returns inserted id or None on failure."""
    if db is None:
        return None
    try:
        entry = AIPromptLog(
            analysis_id=analysis_id,
            agent_name=agent_name,
            provider=provider,
            full_prompt=full_prompt,
            prompt_length=len(full_prompt),
            system_prompt=system_prompt,
            response_text=response_text,
            response_length=len(response_text) if response_text else 0,
            request_timestamp=request_timestamp,
            response_timestamp=response_timestamp,
            success=success,
            tokens_used=tokens_used,
            error_message=error_message,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry.id
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to log AI prompt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None

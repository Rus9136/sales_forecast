"""Gemini engine — placeholder, not implemented yet."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .base import AgentResult, BaseEngine


class GeminiEngine(BaseEngine):
    provider_name = "gemini"

    def is_configured(self) -> bool:
        return False

    async def analyze_with_agent(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        *,
        analysis_id: Optional[int] = None,
        db: Optional[Session] = None,
        api_key_override: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> AgentResult:
        return AgentResult(
            success=False,
            agent_name=agent_name,
            provider=self.provider_name,
            error="Gemini engine is not implemented yet",
        )

    def info(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": False,
            "status": "not_implemented",
        }

"""Base interface for AI engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session


@dataclass
class AgentResult:
    """Unified result returned by every engine."""

    success: bool
    agent_name: str
    provider: str
    content: Optional[str] = None
    error: Optional[str] = None
    tokens_used: int = 0
    request_timestamp: Optional[datetime] = None
    response_timestamp: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


class BaseEngine(ABC):
    """Abstract base class for AI provider engines."""

    provider_name: str = "base"

    @abstractmethod
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
        """Run a single agent and return the result.

        Implementations are responsible for:
        - calling the provider's API with retry/backoff
        - logging the prompt/response into ai_prompt_logs (if db is given)
        """

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the engine has a usable default API key."""

    def info(self) -> dict[str, Any]:
        """Lightweight summary used by GET /providers."""
        return {
            "provider": self.provider_name,
            "configured": self.is_configured(),
        }

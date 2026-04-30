"""Claude (Anthropic) engine.

Supports per-agent isolated API keys: each agent can have its own key
(payroll/staffing/narrative/reputation) so independent rate limits apply.
Falls back to the default ANTHROPIC_API_KEY when an agent-specific key
isn't configured.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ....config import settings
from ._logging import log_prompt
from .base import AgentResult, BaseEngine

logger = logging.getLogger(__name__)


# Map agent name -> env-key attribute on settings. Missing entries fall back
# to the default ANTHROPIC_API_KEY.
AGENT_KEY_MAP: dict[str, str] = {
    "PayrollAnalysisAgent": "ANTHROPIC_API_KEY_PAYROLL",
    "StaffingAgent": "ANTHROPIC_API_KEY_STAFFING",
    "NarrativeAgent": "ANTHROPIC_API_KEY_NARRATIVE",
    "ReputationAgent": "ANTHROPIC_API_KEY_REPUTATION",
}


class ClaudeEngine(BaseEngine):
    provider_name = "claude"

    def __init__(self) -> None:
        self.default_key = settings.ANTHROPIC_API_KEY or ""
        self.model = settings.CLAUDE_MODEL or "claude-sonnet-4-20250514"
        # Cache resolved keys per agent so logs print which key got picked.
        self._resolved_keys: dict[str, str] = {}

    def is_configured(self) -> bool:
        return bool(self.default_key)

    def _resolve_key(self, agent_name: str, override: Optional[str]) -> str:
        if override:
            return override
        cached = self._resolved_keys.get(agent_name)
        if cached:
            return cached
        attr = AGENT_KEY_MAP.get(agent_name)
        agent_key = getattr(settings, attr, "") if attr else ""
        key = agent_key or self.default_key
        self._resolved_keys[agent_name] = key
        return key

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
        api_key = self._resolve_key(agent_name, api_key_override)
        if not api_key:
            err = "ANTHROPIC_API_KEY is not configured"
            log_prompt(
                db,
                analysis_id=analysis_id,
                agent_name=agent_name,
                provider=self.provider_name,
                full_prompt=user_prompt,
                system_prompt=system_prompt,
                response_text=None,
                success=False,
                tokens_used=0,
                request_timestamp=datetime.utcnow(),
                response_timestamp=None,
                error_message=err,
            )
            return AgentResult(
                success=False,
                agent_name=agent_name,
                provider=self.provider_name,
                error=err,
            )

        try:
            from anthropic import APIStatusError, AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            err = f"anthropic SDK is not installed: {exc}"
            return AgentResult(
                success=False,
                agent_name=agent_name,
                provider=self.provider_name,
                error=err,
            )

        client = AsyncAnthropic(api_key=api_key)

        max_retries = 5
        request_started = datetime.utcnow()
        last_error: Optional[str] = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Claude call: agent=%s attempt=%d prompt_len=%d",
                    agent_name,
                    attempt,
                    len(user_prompt),
                )
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                response_received = datetime.utcnow()

                if not response.content:
                    last_error = "Empty response from Claude"
                    break

                content = response.content[0].text
                tokens = (response.usage.input_tokens or 0) + (
                    response.usage.output_tokens or 0
                )

                log_prompt(
                    db,
                    analysis_id=analysis_id,
                    agent_name=agent_name,
                    provider=self.provider_name,
                    full_prompt=user_prompt,
                    system_prompt=system_prompt,
                    response_text=content,
                    success=True,
                    tokens_used=tokens,
                    request_timestamp=request_started,
                    response_timestamp=response_received,
                )

                return AgentResult(
                    success=True,
                    agent_name=agent_name,
                    provider=self.provider_name,
                    content=content,
                    tokens_used=tokens,
                    request_timestamp=request_started,
                    response_timestamp=response_received,
                    metadata={
                        "model": response.model,
                        "stop_reason": response.stop_reason,
                        "attempts": attempt,
                    },
                )

            except APIStatusError as exc:
                status_code = getattr(exc, "status_code", None)
                last_error = f"APIStatusError {status_code}: {exc}"
                logger.warning(
                    "Claude API error (status=%s) on attempt %d/%d for %s",
                    status_code,
                    attempt,
                    max_retries,
                    agent_name,
                )
                if not self._should_retry(status_code, attempt, max_retries):
                    break
                await asyncio.sleep(self._retry_delay(attempt, status_code))

            except Exception as exc:  # pragma: no cover - network/timeouts
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Claude transient error on attempt %d/%d for %s: %s",
                    attempt,
                    max_retries,
                    agent_name,
                    exc,
                )
                if attempt >= max_retries:
                    break
                await asyncio.sleep(self._retry_delay(attempt, None))

        log_prompt(
            db,
            analysis_id=analysis_id,
            agent_name=agent_name,
            provider=self.provider_name,
            full_prompt=user_prompt,
            system_prompt=system_prompt,
            response_text=None,
            success=False,
            tokens_used=0,
            request_timestamp=request_started,
            response_timestamp=None,
            error_message=last_error,
        )

        return AgentResult(
            success=False,
            agent_name=agent_name,
            provider=self.provider_name,
            error=last_error or "Unknown error",
            request_timestamp=request_started,
        )

    @staticmethod
    def _should_retry(status: Optional[int], attempt: int, max_retries: int) -> bool:
        if attempt >= max_retries:
            return False
        if status is None:
            return True  # network-level error, retry
        if status == 529:
            return True
        if 500 <= status < 600:
            return True
        if 400 <= status < 500:
            return False
        return False

    @staticmethod
    def _retry_delay(attempt: int, status: Optional[int]) -> float:
        if status == 529:
            # Aggressive backoff for overload: 30s, 90s, 180s, 360s, 600s
            schedule = [30, 90, 180, 360, 600]
            base = schedule[min(attempt - 1, len(schedule) - 1)]
            jitter = random.uniform(0, 15)
            return base + jitter
        # Generic exponential backoff capped at 30s
        delay = 5 * (2 ** (attempt - 1))
        jitter = random.uniform(0, 1)
        return min(delay + jitter, 30.0)

    def info(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": self.is_configured(),
            "model": self.model,
            "isolated_keys": {
                agent: bool(getattr(settings, attr, ""))
                for agent, attr in AGENT_KEY_MAP.items()
            },
        }

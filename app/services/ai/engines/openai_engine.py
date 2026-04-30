"""OpenAI engine using the official `openai` SDK."""

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


class OpenAIEngine(BaseEngine):
    provider_name = "openai"

    def __init__(self) -> None:
        self.api_key = settings.OPENAI_API_KEY or ""
        self.model = settings.OPENAI_MODEL or "gpt-4o"

    def is_configured(self) -> bool:
        return bool(self.api_key)

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
        api_key = api_key_override or self.api_key
        if not api_key:
            err = "OPENAI_API_KEY is not configured"
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
            from openai import AsyncOpenAI
            from openai import APIStatusError, RateLimitError
        except ImportError as exc:  # pragma: no cover
            return AgentResult(
                success=False,
                agent_name=agent_name,
                provider=self.provider_name,
                error=f"openai SDK is not installed: {exc}",
            )

        client = AsyncOpenAI(api_key=api_key)

        max_retries = 5
        request_started = datetime.utcnow()
        last_error: Optional[str] = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "OpenAI call: agent=%s attempt=%d prompt_len=%d model=%s",
                    agent_name,
                    attempt,
                    len(user_prompt),
                    self.model,
                )
                response = await client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                response_received = datetime.utcnow()

                content = response.choices[0].message.content if response.choices else None
                if not content:
                    last_error = "Empty response from OpenAI"
                    break

                tokens = response.usage.total_tokens if response.usage else 0

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
                        "finish_reason": response.choices[0].finish_reason
                        if response.choices
                        else None,
                        "attempts": attempt,
                    },
                )

            except RateLimitError as exc:
                last_error = f"RateLimitError: {exc}"
                logger.warning(
                    "OpenAI rate limited on attempt %d/%d for %s",
                    attempt,
                    max_retries,
                    agent_name,
                )
                if attempt >= max_retries:
                    break
                await asyncio.sleep(self._retry_delay(attempt, 429))

            except APIStatusError as exc:
                status_code = getattr(exc, "status_code", None)
                last_error = f"APIStatusError {status_code}: {exc}"
                logger.warning(
                    "OpenAI API error (status=%s) on attempt %d/%d for %s",
                    status_code,
                    attempt,
                    max_retries,
                    agent_name,
                )
                if status_code and 400 <= status_code < 500 and status_code != 429:
                    break
                if attempt >= max_retries:
                    break
                await asyncio.sleep(self._retry_delay(attempt, status_code))

            except Exception as exc:  # pragma: no cover
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "OpenAI transient error on attempt %d/%d: %s",
                    attempt,
                    max_retries,
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
    def _retry_delay(attempt: int, status: Optional[int]) -> float:
        if status == 429:
            base = min(15 * (2 ** (attempt - 1)), 240)
            return base + random.uniform(0, 5)
        delay = 5 * (2 ** (attempt - 1))
        return min(delay + random.uniform(0, 1), 30.0)

    def info(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": self.is_configured(),
            "model": self.model,
        }

"""Engine dispatcher — picks the right engine for a provider name."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from ....config import settings
from .base import BaseEngine
from .claude_engine import ClaudeEngine
from .gemini_engine import GeminiEngine
from .openai_engine import OpenAIEngine
from .openrouter_engine import OpenRouterEngine


class EngineDispatcher:
    SUPPORTED = ("claude", "openai", "openrouter", "gemini")

    def __init__(self) -> None:
        self._engines: dict[str, BaseEngine] = {
            "claude": ClaudeEngine(),
            "openai": OpenAIEngine(),
            "openrouter": OpenRouterEngine(),
            "gemini": GeminiEngine(),
        }

    @property
    def DEFAULT_PROVIDER(self) -> str:
        name = (settings.AI_DEFAULT_PROVIDER or "claude").lower()
        return name if name in self._engines else "claude"

    def get_engine(self, provider: Optional[str] = None) -> BaseEngine:
        name = (provider or self.DEFAULT_PROVIDER).lower()
        if name not in self._engines:
            raise ValueError(
                f"Unsupported provider '{provider}'. Supported: {self.SUPPORTED}"
            )
        return self._engines[name]

    def providers_info(self) -> dict:
        return {
            "supported_providers": list(self.SUPPORTED),
            "default_provider": self.DEFAULT_PROVIDER,
            "providers": {
                name: engine.info() for name, engine in self._engines.items()
            },
        }


@lru_cache(maxsize=1)
def get_dispatcher() -> EngineDispatcher:
    return EngineDispatcher()

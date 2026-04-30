"""Engine dispatcher — picks the right engine for a provider name."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .base import BaseEngine
from .claude_engine import ClaudeEngine
from .gemini_engine import GeminiEngine
from .openai_engine import OpenAIEngine


class EngineDispatcher:
    SUPPORTED = ("claude", "openai", "gemini")
    DEFAULT_PROVIDER = "claude"

    def __init__(self) -> None:
        self._engines: dict[str, BaseEngine] = {
            "claude": ClaudeEngine(),
            "openai": OpenAIEngine(),
            "gemini": GeminiEngine(),
        }

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

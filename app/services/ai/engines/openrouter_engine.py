"""OpenRouter engine — OpenAI-совместимый API-шлюз (https://openrouter.ai).

Наследует весь retry/логирующий код OpenAIEngine: OpenRouter принимает
запросы в формате OpenAI Chat Completions, отличаются только base_url,
ключ и слаг модели (`vendor/model`, напр. `anthropic/claude-sonnet-4.6`).
Заголовки HTTP-Referer / X-Title — атрибуция приложения в рейтинге
OpenRouter (опциональны, на работу API не влияют).
"""

from __future__ import annotations

from ....config import settings
from .openai_engine import OpenAIEngine


class OpenRouterEngine(OpenAIEngine):
    provider_name = "openrouter"

    def __init__(self) -> None:
        self.api_key = settings.OPENROUTER_API_KEY or ""
        self.model = settings.OPENROUTER_MODEL or "anthropic/claude-sonnet-4.6"
        self.base_url = settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
        self.default_headers = {
            "HTTP-Referer": "https://aqniet.space",
            "X-Title": "Sales Forecast",
        }
        self.key_env_name = "OPENROUTER_API_KEY"

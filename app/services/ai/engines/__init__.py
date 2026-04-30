"""AI engine implementations.

Each provider (Claude, OpenAI, Gemini) has its own engine class that
implements the BaseEngine interface. The dispatcher routes requests
to the right engine based on the requested provider name.
"""

from .base import AgentResult, BaseEngine
from .dispatcher import EngineDispatcher, get_dispatcher

__all__ = ["AgentResult", "BaseEngine", "EngineDispatcher", "get_dispatcher"]

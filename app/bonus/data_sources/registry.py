from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BonusDataSource

logger = logging.getLogger(__name__)


class DataSourceRegistry:
    """Process-wide registry of bonus data sources.

    Sources register themselves at import time (via register_*() helpers in
    each adapter package). The runner asks the registry by string code.
    """

    _sources: dict[str, "BonusDataSource"] = {}

    @classmethod
    def register(cls, source: "BonusDataSource") -> None:
        if not source.code:
            raise ValueError(f"Data source {source!r} has no code attribute")
        if source.code in cls._sources:
            logger.debug("Replacing data source %s with %s", source.code, type(source).__name__)
        cls._sources[source.code] = source

    @classmethod
    def get(cls, code: str) -> "BonusDataSource":
        if code not in cls._sources:
            raise ValueError(
                f"Unknown bonus data source: {code!r}. "
                f"Registered: {sorted(cls._sources)}"
            )
        return cls._sources[code]

    @classmethod
    def has(cls, code: str) -> bool:
        return code in cls._sources

    @classmethod
    def list_codes(cls) -> list[str]:
        return sorted(cls._sources.keys())

    @classmethod
    def list_metadata(cls) -> list[dict]:
        """Return metadata for every registered source, sorted by code."""
        return [cls._sources[code].metadata() for code in sorted(cls._sources.keys())]

    @classmethod
    def clear(cls) -> None:
        cls._sources.clear()

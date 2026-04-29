"""Single entry-point that registers every bonus data source.

Called once at FastAPI startup. Idempotent: calling it twice replaces
existing registrations with the same instances.
"""

from __future__ import annotations

import logging

from .iiko import register_iiko_sources
from .manual import register_manual_sources
from .registry import DataSourceRegistry
from .tco import register_tco_sources

logger = logging.getLogger(__name__)


def register_all_sources() -> None:
    register_iiko_sources()
    register_tco_sources()
    register_manual_sources()
    logger.info("Bonus data sources registered: %d", len(DataSourceRegistry.list_codes()))

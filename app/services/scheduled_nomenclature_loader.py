"""APScheduler wrapper around IikoNomenclatureLoaderService.

Mirrors the structure of `scheduled_sales_loader` / `scheduled_waiter_loader`:
opens its own DB session and bridges async loader → sync scheduler thread.
"""

from __future__ import annotations

import asyncio
import logging

from ..db import SessionLocal
from .iiko_nomenclature_loader import IikoNomenclatureLoaderService

logger = logging.getLogger(__name__)


def run_nomenclature_sync() -> dict:
    """Entry point for APScheduler. Runs daily at 01:00 so the catalog is
    fresh before sales/receipts sync (02:00 / 02:15) needs it for SKU resolution.
    """
    db = SessionLocal()
    try:
        service = IikoNomenclatureLoaderService(db)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(service.sync())
        finally:
            loop.close()
        logger.info(f"Scheduled nomenclature sync result: {result}")
        return result
    except Exception as e:
        logger.error(f"Scheduled nomenclature sync failed: {e}", exc_info=True)
        raise
    finally:
        db.close()

"""APScheduler wrapper around IikoDepartmentLoaderService.

Справочник точек не синхронизировался ничем, кроме ручной кнопки. Открылись
две новые точки (Madlen TT Flora, Cinotti Semey) — и загрузка чеков всей сети
падала на FK три недели: iiko отдаёт продажи по точке, которой у нас нет.
Ставим синк раньше номенклатуры (01:00) и продаж (02:00), чтобы к моменту
загрузки чеков справочник уже знал про новые точки.
"""

from __future__ import annotations

import asyncio
import logging

from ..db import SessionLocal
from .iiko_department_loader import IikoDepartmentLoaderService

logger = logging.getLogger(__name__)


def run_department_sync() -> dict:
    """Entry point for APScheduler. Runs daily at 00:45."""
    db = SessionLocal()
    try:
        service = IikoDepartmentLoaderService(db)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            processed = loop.run_until_complete(service.sync_departments())
        finally:
            loop.close()
        logger.info("Scheduled department sync: %s departments processed", processed)
        return {"status": "ok", "processed": processed}
    except Exception as e:
        logger.error(f"Scheduled department sync failed: {e}", exc_info=True)
        raise
    finally:
        db.close()

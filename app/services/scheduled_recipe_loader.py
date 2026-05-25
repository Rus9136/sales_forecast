"""APScheduler wrapper for recipe (assembly charts) sync."""

import asyncio
import concurrent.futures
import logging

from ..db import get_db
from .iiko_recipe_loader import IikoRecipeLoaderService

logger = logging.getLogger(__name__)


def run_recipe_sync():
    """Weekly sync: fetch all assembly charts from all iiko domains."""
    logger.info("Scheduler triggered: recipe sync")
    try:
        db = next(get_db())
        try:
            svc = IikoRecipeLoaderService(db)
            try:
                asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        lambda: asyncio.new_event_loop().run_until_complete(svc.sync())
                    ).result(timeout=600)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(svc.sync())
                finally:
                    loop.close()
            logger.info(f"Recipe sync done: {result.get('total_recipes')} recipes, {result.get('total_ingredients')} ingredients")
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Recipe sync failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

"""Auto-retrain wrapper for SKU-level LightGBM model.

Called by APScheduler weekly (Sunday 04:00) and can be triggered manually.
Follows the same pattern as model_retraining_service.py.
"""

import logging
import os
import shutil
from datetime import datetime

from ..db import get_db
from ..agents.sku_forecaster_agent import get_sku_forecaster_agent

logger = logging.getLogger(__name__)

ARCHIVE_DIR = "models/sku_archive"
MAX_MAPE_THRESHOLD = 80.0


def run_sku_auto_retrain():
    """APScheduler entry point — train/retrain the global SKU model."""
    logger.info("Scheduler triggered: SKU model auto-retrain")
    try:
        db = next(get_db())
        try:
            agent = get_sku_forecaster_agent()
            old_metrics = agent._training_metrics

            _, metrics = agent.train_model(db=db, active_window_days=30)

            test_mape = metrics.get('test_mape', 999)
            if test_mape > MAX_MAPE_THRESHOLD:
                logger.warning(
                    f"SKU model MAPE {test_mape:.1f}% exceeds threshold {MAX_MAPE_THRESHOLD}% — "
                    "keeping new model anyway (first baseline or data quality issue)"
                )

            _archive_model(agent.model_path)

            logger.info(
                f"SKU auto-retrain done: test_mape={test_mape:.1f}%, "
                f"samples={metrics.get('train_samples', 0)}, "
                f"SKUs={metrics.get('n_unique_skus', 0)}"
            )
            return {"status": "success", "metrics": metrics}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"SKU auto-retrain failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _archive_model(model_path: str):
    """Copy current model to archive dir with timestamp."""
    if not os.path.exists(model_path):
        return
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(model_path)
    name, ext = os.path.splitext(base)
    dest = os.path.join(ARCHIVE_DIR, f"{name}_{ts}{ext}")
    shutil.copy2(model_path, dest)
    logger.info(f"Archived SKU model to {dest}")

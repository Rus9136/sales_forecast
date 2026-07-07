"""Auto-retrain wrapper for SKU-level LightGBM model (Фаза 2.2/2.3).

Раньше обучение шло в процессе FastAPI и OOM-убивало API (аудит P0-2).
Теперь scheduler-обёртка ЗАПУСКАЕТ ОТДЕЛЬНЫЙ ПРОЦЕСС `python -m
app.jobs.sku_retrain`: его OOM/падение изолированы от API, память ограничена
RLIMIT_AS. Guardrails (hold-out сравнение, атомарный деплой) — внутри джоба.

После успешного деплоя serving-синглтон API перечитывает новую модель через
reload_sku_forecaster_agent().
"""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

# Достаточно для обучения (~3-5 мин) с запасом; джоб сам ставит RLIMIT_AS
SUBPROCESS_TIMEOUT_SEC = 1800


def run_sku_auto_retrain() -> dict:
    """APScheduler entry point — запускает retrain в отдельном процессе."""
    logger.info("Scheduler triggered: SKU model auto-retrain (out-of-process)")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "app.jobs.sku_retrain"],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SEC,
        )
        # stdout/stderr джоба — в логи API для наблюдаемости
        for line in (proc.stderr or "").splitlines()[-40:]:
            logger.info(f"[sku_retrain] {line}")

        # exit codes джоба: 0 = deployed, 2 = rejected, 1 = failed
        if proc.returncode == 0:
            logger.info("SKU retrain: model DEPLOYED — reloading serving singleton")
            _reload_serving_singleton()
            return {"status": "success", "decision": "deployed"}
        if proc.returncode == 2:
            logger.info("SKU retrain: candidate REJECTED — production model kept")
            return {"status": "success", "decision": "rejected"}
        logger.error(f"SKU retrain subprocess failed (exit {proc.returncode})")
        return {"status": "error", "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        logger.error(f"SKU retrain subprocess timed out after {SUBPROCESS_TIMEOUT_SEC}s")
        return {"status": "error", "message": "timeout"}
    except Exception as e:
        logger.error(f"SKU auto-retrain launcher failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _reload_serving_singleton():
    try:
        from ..agents.sku_forecaster_agent import reload_sku_forecaster_agent
        reload_sku_forecaster_agent()
    except Exception as e:
        logger.error(f"Failed to reload SKU singleton after deploy: {e}")

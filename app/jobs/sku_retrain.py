"""Out-of-process SKU-retrain entrypoint (ML_AUDIT_REPORT.md P0-2/2.2/2.3).

Запускается как ОТДЕЛЬНЫЙ процесс (`python -m app.jobs.sku_retrain`), а не
внутри API. Раньше воскресный retrain строил сетку ~2.1M строк в процессе
FastAPI и OOM-убивал весь API. Теперь:

- субпроцесс изолирован: при OOM ядро убивает ЕГО (главный потребитель
  памяти в этот момент), а uvicorn продолжает работать;
- RLIMIT_AS ограничивает адресное пространство джоба (env
  SKU_RETRAIN_MEM_LIMIT_MB, деф. 3000) — belt-and-suspenders;
- пиковый RSS логируется (resource.getrusage) для контроля запаса;
- память датасета снижена в builder'е (float32, без cross-join метаданных).

Guardrails (2.3, зеркало dept-модели 1.2):
- кандидат обучается на данных БЕЗ hold-out окна и деплоится сам (single
  train — SKU-обучение дорогое по памяти/времени; цена — модель на момент
  деплоя знает данные до today-holdout_days, для недельного ретрейна ок);
- решение — сравнение с текущей прод-моделью на общем hold-out (WAPE +
  MedAPE tolerance); sanity WAPE>MAX → reject;
- запись атомарна: temp-path → архив старого ДО замены → os.replace;
- serving-синглтон НЕ мутируется во время обучения (отдельный процесс);
  API перечитает новый .pkl при следующем рестарте / через reload-хук.

Exit codes: 0 = deployed, 2 = rejected (не ошибка), 1 = сбой.
"""

import gc
import logging
import os
import resource
import shutil
import sys
from datetime import date, timedelta

from ..config import settings
from ..db import get_db

logger = logging.getLogger("app.jobs.sku_retrain")

PROD_PATH = "models/sku_lgbm_model.pkl"
ARCHIVE_DIR = "models/sku_archive"
HOLDOUT_DAYS = 21
MEDAPE_TOLERANCE_PCT = 10.0
MAX_WAPE = 80.0
# 90 дней (вместо 180): zero-expansion даёт ~1M строк вместо 2.1M — прямое
# снижение пикового RSS (P0-2) на тесном 3.8GB-хосте, 3 месяца достаточно
# для недельной сезонности qty. Регулируется env SKU_RETRAIN_TRAIN_DAYS.
TRAIN_DAYS = int(os.environ.get("SKU_RETRAIN_TRAIN_DAYS", "90"))
# RLIMIT_AS ограничивает ВИРТУАЛЬНУЮ память, а у LightGBM/OpenMP она ~2×
# резидентной — поэтому дефолт щедрый (backstop от runaway, не тонкий кап).
# Реальная защита — сокращённый RSS (float32, 120д) + изоляция субпроцесса.
DEFAULT_MEM_LIMIT_MB = 6000


def _set_memory_limit():
    """RLIMIT_AS best-effort — при превышении процесс упадёт с MemoryError,
    а не утащит хост в OOM (P0-2)."""
    limit_mb = int(os.environ.get("SKU_RETRAIN_MEM_LIMIT_MB", str(DEFAULT_MEM_LIMIT_MB)))
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new = limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (new, hard if hard != resource.RLIM_INFINITY else new))
        logger.info(f"RLIMIT_AS (virtual) set to {limit_mb} MB — backstop; real guard is subprocess isolation")
    except (ValueError, OSError) as e:
        logger.warning(f"Could not set RLIMIT_AS: {e}")


def _peak_rss_mb() -> float:
    # ru_maxrss на Linux — в килобайтах
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _archive(path: str):
    if not os.path.exists(path):
        return
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    # timestamp из последнего дня данных, не из now() (детерминизм в тестах не
    # нужен, но избегаем коллизий) — используем mtime исходника
    ts = date.today().strftime("%Y%m%d")
    base = os.path.basename(path)
    name, ext = os.path.splitext(base)
    dest = os.path.join(ARCHIVE_DIR, f"{name}_{ts}{ext}")
    shutil.copy2(path, dest)
    logger.info(f"Archived SKU model → {dest}")


def run(objective: str = "log1p") -> dict:
    """Основная логика (импортируема для тестов).

    objective: 'log1p' (текущий) или 'tweedie' (эксперимент 2.5).
    Возвращает {status, decision, metrics, peak_rss_mb}.
    """
    from ..agents.sku_forecaster_agent import SkuForecasterAgent
    from ..services.sku_model_comparison import compare_sku_on_holdout
    from ..services.sku_training_service import SkuTrainingDataService

    db = next(get_db())
    try:
        # 1. Кандидат обучается на данных БЕЗ hold-out окна (out-of-sample
        # для честного сравнения). end = вчера - holdout_days.
        decision_end = date.today() - timedelta(days=1 + HOLDOUT_DAYS)
        svc = SkuTrainingDataService(db)
        df = svc.prepare_training_data(days=TRAIN_DAYS, end_date=decision_end)
        if df.empty:
            raise ValueError("No SKU training data (pre-holdout window)")

        train_df, val_df, test_df = svc.split_train_validation_test(df)
        # split вернул независимые копии — освобождаем 1M-строчный featured df
        # ДО обучения, иначе он висит в памяти поверх сплит-копий и X-матриц
        # (пик RSS, P0-2a)
        del df
        gc.collect()

        version = date.today().strftime("v_%Y%m%d")
        temp_path = f"models/temp_sku_{version}.pkl"
        candidate = SkuForecasterAgent(model_path=temp_path)
        candidate.feature_columns = svc.get_feature_columns()
        candidate._encoding_maps = svc.encoding_maps
        if objective == "tweedie":
            candidate._objective = "tweedie"
        _, metrics = candidate.train_model(train_df, val_df, test_df, save_model=True)

        # освобождаем сплит-кадры до сравнения (пик памяти)
        del train_df, val_df, test_df
        gc.collect()

        # 2. Решение на общем hold-out против текущей прод-модели
        if not os.path.exists(PROD_PATH):
            decision = {"decision": "deployed",
                        "reason": "No production SKU model — deploying first baseline",
                        "b": {"wape": metrics.get("test_wape")}}
        else:
            prod_agent = SkuForecasterAgent(model_path=PROD_PATH)
            decision = compare_sku_on_holdout(
                db, prod_agent, candidate,
                holdout_days=HOLDOUT_DAYS,
                medape_tolerance_pct=MEDAPE_TOLERANCE_PCT,
                max_wape=MAX_WAPE,
            )

        peak = _peak_rss_mb()
        result = {
            "status": "success",
            "decision": decision["decision"],
            "reason": decision["reason"],
            "objective": objective,
            "peak_rss_mb": round(peak, 1),
            "candidate_metrics": {
                k: metrics[k] for k in (
                    "test_wape", "test_median_ape", "test_mape", "test_r2",
                    "test_zero_day_share", "test_zero_day_mean_pred",
                    "test_nonzero_wape", "train_samples", "n_unique_skus",
                ) if k in metrics
            },
            "holdout": {"a": decision.get("a"), "b": decision.get("b")},
        }

        # 3. Атомарный деплой / архив
        if decision["decision"] == "deployed":
            _archive(PROD_PATH)  # архив старого ДО замены
            staging = PROD_PATH + ".staging"
            shutil.copy2(temp_path, staging)
            os.replace(staging, PROD_PATH)
            os.remove(temp_path)
            logger.info(f"✅ SKU model deployed. {decision['reason']}")
            # reload serving-синглтона, если джоб бежит внутри API-процесса
            # (при subprocess-запуске это no-op в чужом процессе — API
            # перечитает при следующем forecast-обращении через свой reload)
        else:
            archive_rejected = os.path.join(ARCHIVE_DIR, f"rejected_sku_{version}.pkl")
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            shutil.move(temp_path, archive_rejected)
            logger.warning(f"⚠️ SKU model rejected. {decision['reason']}")

        logger.info(
            f"SKU retrain done: decision={decision['decision']}, "
            f"peak RSS={peak:.0f} MB, objective={objective}"
        )
        return result
    finally:
        db.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _set_memory_limit()
    objective = os.environ.get("SKU_RETRAIN_OBJECTIVE", "log1p")
    try:
        result = run(objective=objective)
    except MemoryError:
        logger.critical("SKU retrain OOM — job killed, API unaffected (P0-2)")
        return 1
    except Exception as e:
        logger.error(f"SKU retrain failed: {e}", exc_info=True)
        return 1

    # Резидентный бюджет = безопасный порог RSS на хосте (env, деф. 2500MB):
    # столько джоб может держать, не рискуя OOM самого хоста рядом с API.
    rss_budget_mb = int(os.environ.get("SKU_RETRAIN_RSS_BUDGET_MB", "2500"))
    headroom = 1 - result["peak_rss_mb"] / rss_budget_mb
    logger.info(f"Peak RSS {result['peak_rss_mb']:.0f} MB / budget {rss_budget_mb} MB "
                f"(headroom {headroom:+.0%})")
    return 0 if result["decision"] == "deployed" else 2


if __name__ == "__main__":
    sys.exit(main())

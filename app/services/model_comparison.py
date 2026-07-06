"""Like-for-like сравнение двух department-level моделей на общем hold-out.

Аудит P0-3 (Фаза 1.2): deployment decision раньше сравнивал прод-MAPE за
7 дней (3-4 точки, после smoothing) с offline test-MAPE кандидата — метрики
из разных вселенных, reject/deploy был лотереей. Здесь обе модели прогоняются
по ОДНОМУ hold-out (последние N дней, все точки), фичи строятся тем же
TrainingDataService, `is_outlier_day=0` (паритет с продом — инференс никогда
не видит оракульный флаг, P1-1).

Потребители: scripts/compare_models_holdout.py (CLI) и
ModelRetrainingService._make_holdout_deployment_decision.
"""

import logging
from typing import Dict

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from .forecast_metrics import mape, median_ape, wape

logger = logging.getLogger(__name__)


def build_holdout(db: Session, holdout_days: int = 28, history_days: int = 120) -> pd.DataFrame:
    """Строит фичи тем же кодом, что и обучение, и возвращает последние N дней.

    history_days > holdout_days, чтобы rolling/lag-фичи первых hold-out строк
    имели полную предысторию. Rolling-фичи past-only (training_service.py,
    инвариант «строго прошлое»), поэтому общий датафрейм не даёт утечки.
    """
    from .training_service import TrainingDataService

    svc = TrainingDataService(db)
    df = svc.prepare_training_data(days=history_days, handle_outliers=False)
    if df.empty:
        raise ValueError("No sales data available to build hold-out")
    df["date"] = pd.to_datetime(df["date"])
    cutoff = df["date"].max() - pd.Timedelta(days=holdout_days - 1)
    holdout = df[df["date"] >= cutoff].copy()
    # Паритет с продом: инференс никогда не знает, что день окажется выбросом
    holdout["is_outlier_day"] = 0
    return holdout


def evaluate_model(pkl_path: str, holdout: pd.DataFrame) -> Dict:
    """Оценивает один .pkl на готовом hold-out (свои feature_columns и transform)."""
    data = joblib.load(pkl_path)
    model = data["model"]
    cols = data["feature_columns"]
    transform = data.get("target_transform", "identity")

    X = holdout.copy()
    missing = [c for c in cols if c not in X.columns]
    for c in missing:
        X[c] = 0

    preds = model.predict(X[cols])
    if transform == "log1p":
        preds = np.expm1(preds)
    preds = np.maximum(preds, 0.0)

    y = holdout["total_sales"].values.astype(float)
    return {
        "model_path": pkl_path,
        "trained_at": data.get("trained_at", "unknown"),
        "n_rows": int(len(y)),
        "n_departments": int(holdout["department_id"].nunique()),
        "wape": round(wape(y, preds), 2),
        "median_ape": round(median_ape(y, preds), 2),
        "mape": round(mape(y, preds), 2),
        "missing_features_filled_0": missing,
    }


def compare_on_holdout(db: Session, path_a: str, path_b: str,
                       holdout_days: int = 28) -> Dict:
    """Возвращает {'a': metrics, 'b': metrics, 'winner': path, 'holdout': {...}}.

    Победитель — по WAPE (критерий деплоя с MedAPE-толерансом применяет
    вызывающая сторона).
    """
    holdout = build_holdout(db, holdout_days=holdout_days)
    res_a = evaluate_model(path_a, holdout)
    res_b = evaluate_model(path_b, holdout)
    winner = path_a if res_a["wape"] <= res_b["wape"] else path_b
    result = {
        "a": res_a,
        "b": res_b,
        "winner": winner,
        "holdout": {
            "days": holdout_days,
            "from": str(holdout["date"].min().date()),
            "to": str(holdout["date"].max().date()),
            "rows": int(len(holdout)),
        },
    }
    logger.info(
        f"Hold-out comparison ({result['holdout']['from']}..{result['holdout']['to']}): "
        f"A={res_a['wape']:.2f}% WAPE vs B={res_b['wape']:.2f}% WAPE → winner {winner}"
    )
    return result

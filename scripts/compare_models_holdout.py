"""Like-for-like сравнение двух department-level моделей на общем hold-out.

Контекст: ML_AUDIT_REPORT.md P0-3 — deployment decision сравнивал прод-MAPE
(7 дней, 4 точки, после smoothing) с offline test-MAPE кандидата (все точки,
без smoothing). Этот скрипт — замена: обе модели прогоняются по ОДНОМУ
hold-out (последние N дней, все точки), фичи строятся одним и тем же
TrainingDataService, `is_outlier_day` принудительно 0 (паритет с продом —
инференс никогда не видит оракульный флаг, см. P1-1).

Запуск (внутри контейнера, читает прод-БД read-only):
    docker cp scripts/compare_models_holdout.py sales-forecast-app:/tmp/
    docker exec -w /app -e PYTHONPATH=/app sales-forecast-app \
        python /tmp/compare_models_holdout.py \
        --model-a models/lgbm_model.pkl \
        --model-b models/backup_lgbm_model_20260621_030006.pkl

Используется также деплой-контуром (Фаза 1.2) через evaluate_on_holdout().
"""

import argparse
import json
import sys

import joblib
import numpy as np
import pandas as pd


def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Weighted APE: sum|err| / sum(y). Headline-метрика (устойчива к малым знаменателям)."""
    return float(np.abs(y_true - y_pred).sum() / y_true.sum() * 100)


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def median_ape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    return float(np.median(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def build_holdout(db, holdout_days: int = 28, history_days: int = 120) -> pd.DataFrame:
    """Строит фичи тем же кодом, что и обучение, и возвращает последние N дней.

    history_days > holdout_days, чтобы rolling/lag-фичи первых hold-out строк
    имели полную предысторию. Rolling-фичи past-only (training_service.py:430-500),
    поэтому использование общего датафрейма не даёт утечки.
    """
    from app.services.training_service import TrainingDataService

    svc = TrainingDataService(db)
    df = svc.prepare_training_data(days=history_days, handle_outliers=False)
    if df.empty:
        raise SystemExit("No training data available")
    df["date"] = pd.to_datetime(df["date"])
    cutoff = df["date"].max() - pd.Timedelta(days=holdout_days - 1)
    holdout = df[df["date"] >= cutoff].copy()
    # Паритет с продом: инференс никогда не знает, что день окажется выбросом
    holdout["is_outlier_day"] = 0
    return holdout


def evaluate_model(pkl_path: str, holdout: pd.DataFrame) -> dict:
    """Оценивает один .pkl на готовом hold-out. Свои feature_columns и transform."""
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


def compare_on_holdout(db, path_a: str, path_b: str,
                       holdout_days: int = 28) -> dict:
    """Возвращает {'a': metrics, 'b': metrics, 'winner': path, 'holdout': {...}}.

    Победитель — по WAPE. Используется деплой-контуром (Фаза 1.2).
    """
    holdout = build_holdout(db, holdout_days=holdout_days)
    res_a = evaluate_model(path_a, holdout)
    res_b = evaluate_model(path_b, holdout)
    winner = path_a if res_a["wape"] <= res_b["wape"] else path_b
    return {
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-a", required=True)
    parser.add_argument("--model-b", required=True)
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--json", help="Путь для JSON-результата (опционально)")
    args = parser.parse_args()

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        result = compare_on_holdout(db, args.model_a, args.model_b, holdout_days=args.days)
    finally:
        db.close()

    h = result["holdout"]
    print(f"\nHold-out: {h['from']} .. {h['to']} ({h['days']}д, {h['rows']} строк)")
    print(f"{'модель':<55} {'trained_at':<28} {'WAPE':>7} {'MedAPE':>7} {'MAPE':>7}")
    for key in ("a", "b"):
        r = result[key]
        print(f"{r['model_path']:<55} {str(r['trained_at']):<28} "
              f"{r['wape']:>6.2f}% {r['median_ape']:>6.2f}% {r['mape']:>6.2f}%")
        if r["missing_features_filled_0"]:
            print(f"    ⚠ отсутствующие фичи заполнены 0: {r['missing_features_filled_0']}")
    print(f"\nПобедитель по WAPE: {result['winner']}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())

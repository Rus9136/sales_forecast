"""Like-for-like сравнение двух SKU-моделей на общем hold-out (Фаза 2.3).

Зеркало model_comparison.py для department-модели, но с поправкой на то,
что признаки SKU зависят от encoding_maps (свои у каждой модели). Поэтому
общей делается СЕТКА фактов (qty/sum за окно), а признаки для каждой модели
строятся её собственными encodings — обе модели оцениваются на одних и тех
же (dept, product, date)-строках с одинаковым таргетом.

Headline — WAPE; дополнительно intermittent-разрез (нулевые/ненулевые дни).
Любой сбой сравнения → reject (safe default, прод-модель остаётся).
"""

import logging
from datetime import date, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from .forecast_metrics import median_ape, wape
from .sku_feature_builder import build_features, expand_zero_days
from .sku_training_service import SkuTrainingDataService

logger = logging.getLogger(__name__)


def load_holdout_world(
    db: Session, holdout_days: int = 21, history_days: int = 75,
):
    """Общая сетка фактов + метаданные для hold-out.

    history_days > holdout_days, чтобы rolling/lag hold-out строк имели полную
    предысторию. Возвращает (grid, product_meta, dept_meta, holdout_start).
    """
    svc = SkuTrainingDataService(db)
    end = date.today() - timedelta(days=1)  # последний полный день
    start = end - timedelta(days=history_days)

    raw_values = svc._load_values(start, end)
    if raw_values.empty:
        raise ValueError("No SKU sales data for hold-out")
    active_pairs = svc._get_active_pairs(end, 30)
    if active_pairs.empty:
        raise ValueError("No active SKU pairs for hold-out")

    grid = expand_zero_days(raw_values, active_pairs, start, end)
    product_meta = svc._load_product_meta()
    dept_meta = svc._load_dept_meta()
    holdout_start = end - timedelta(days=holdout_days - 1)
    return grid, product_meta, dept_meta, holdout_start


def evaluate_agent(agent, grid, product_meta, dept_meta, holdout_start: date) -> Dict:
    """Оценивает SKU-агента на hold-out строках (features его encodings)."""
    feats, _ = build_features(
        grid.copy(), product_meta, dept_meta,
        encoding_maps=getattr(agent, "_encoding_maps", None) or None,
    )
    hold = feats[feats["date"] >= pd.Timestamp(holdout_start)].copy()
    if hold.empty:
        raise ValueError("Empty hold-out after feature build")

    cols = agent.feature_columns
    missing = [c for c in cols if c not in hold.columns]
    for c in missing:
        hold[c] = 0
    X = hold[cols].astype("float32").fillna(0).replace([np.inf, -np.inf], 0)
    y = hold["total_qty"].to_numpy(dtype=float)
    preds = np.asarray(agent.predict(X), dtype=float)

    nonzero = y > 0
    return {
        "n_rows": int(len(y)),
        "wape": round(wape(y, preds), 2),
        "median_ape": round(median_ape(y, preds), 2),
        "nonzero_wape": round(wape(y[nonzero], preds[nonzero]), 2) if nonzero.any() else 0.0,
        "zero_day_mean_pred": round(float(preds[~nonzero].mean()), 3) if (~nonzero).any() else 0.0,
        "trained_at": getattr(agent, "_trained_at", "unknown"),
    }


def compare_sku_on_holdout(
    db: Session,
    production_agent,
    candidate_agent,
    holdout_days: int = 21,
    medape_tolerance_pct: float = 10.0,
    max_wape: float = 80.0,
) -> Dict:
    """Решение о деплое SKU-кандидата. Критерий как в 1.2:
    кандидат лучше по WAPE И MedAPE в пределах толеранса; sanity WAPE>max → reject.
    """
    grid, product_meta, dept_meta, holdout_start = load_holdout_world(db, holdout_days)

    prod_m = evaluate_agent(production_agent, grid, product_meta, dept_meta, holdout_start)
    cand_m = evaluate_agent(candidate_agent, grid, product_meta, dept_meta, holdout_start)

    detail = (
        f"hold-out {holdout_start}..+{holdout_days}d ({cand_m['n_rows']} rows): "
        f"candidate WAPE {cand_m['wape']:.2f}% / MedAPE {cand_m['median_ape']:.2f}% "
        f"vs production WAPE {prod_m['wape']:.2f}% / MedAPE {prod_m['median_ape']:.2f}%"
    )
    result = {"a": prod_m, "b": cand_m, "detail": detail}

    if cand_m["wape"] > max_wape:
        return {**result, "decision": "rejected",
                "reason": f"Sanity check failed: candidate WAPE {cand_m['wape']:.1f}% > {max_wape}% ({detail})"}

    wape_better = cand_m["wape"] < prod_m["wape"]
    medape_ok = cand_m["median_ape"] <= prod_m["median_ape"] * (1 + medape_tolerance_pct / 100.0)
    if wape_better and medape_ok:
        return {**result, "decision": "deployed",
                "reason": f"Candidate better on WAPE, MedAPE within {medape_tolerance_pct:.0f}% tolerance ({detail})"}
    if not wape_better:
        return {**result, "decision": "rejected", "reason": f"Candidate not better on WAPE ({detail})"}
    return {**result, "decision": "rejected", "reason": f"Candidate MedAPE beyond tolerance ({detail})"}

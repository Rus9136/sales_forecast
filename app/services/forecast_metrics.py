"""Общие метрики качества прогноза (ML_AUDIT_REPORT.md P1-7, Фаза 1.1).

Headline-метрика — WAPE: sum|err| / sum(actual). На данных со смешанным
масштабом точек (5k..3M ₸/день) MAPE взрывается на малых знаменателях
(контрольный замер аудита: MAPE 43-51% при WAPE 18-19%), поэтому решения
(деплой, алерты) принимаются по WAPE + MedianAPE; MAPE остаётся для
преемственности отчётов.

Используется агентами (train-метрики), model_comparison (deployment
decision), мониторингом и backtest-скриптами — одна реализация везде.
"""

from typing import Dict

import numpy as np


def _as_arrays(y_true, y_pred):
    return np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)


def wape(y_true, y_pred) -> float:
    """Weighted APE, %: sum|err| / sum|actual|. Устойчива к малым знаменателям."""
    y_true, y_pred = _as_arrays(y_true, y_pred)
    denom = np.abs(y_true).sum()
    if denom == 0:
        return 0.0
    return float(np.abs(y_true - y_pred).sum() / denom * 100)


def mape(y_true, y_pred) -> float:
    """Mean APE, % (только строки с y_true != 0)."""
    y_true, y_pred = _as_arrays(y_true, y_pred)
    mask = y_true != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def median_ape(y_true, y_pred) -> float:
    """Median APE, % (только строки с y_true != 0)."""
    y_true, y_pred = _as_arrays(y_true, y_pred)
    mask = y_true != 0
    if not mask.any():
        return 0.0
    return float(np.median(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def bias_pct(y_true, y_pred) -> float:
    """Систематическое смещение, %: sum(pred - actual) / sum(actual). >0 = завышение."""
    y_true, y_pred = _as_arrays(y_true, y_pred)
    denom = y_true.sum()
    if denom == 0:
        return 0.0
    return float((y_pred - y_true).sum() / denom * 100)


def regression_report(y_true, y_pred) -> Dict[str, float]:
    """Полный набор метрик одной строкой (для метрик обучения и мониторинга)."""
    y_true, y_pred = _as_arrays(y_true, y_pred)
    return {
        "wape": wape(y_true, y_pred),
        "median_ape": median_ape(y_true, y_pred),
        "mape": mape(y_true, y_pred),
        "mae": float(np.mean(np.abs(y_true - y_pred))) if len(y_true) else 0.0,
        "bias_pct": bias_pct(y_true, y_pred),
    }

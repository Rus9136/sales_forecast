"""Паритет dept-модели: train == inference (ML_AUDIT_REPORT.md P1-3, P1-6, Фаза 3.2).

Тема всего аудита — тихая деградация от рассинхрона фичей train vs inference.
Для dept-модели это было в rolling_30d (train последние 30 / inference вся
история), std (ddof) и календаре праздников (3 реализации). Тест строит
признаки обоими путями для синтетического ряда и сверяет rolling/lag/std/
holiday-фичи на прогнозной дате.

Соответствие: признаки train-строки для даты d (окна из дней < d) ==
inference для forecast_date=d с историей строго до d.
"""

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from app.agents.sales_forecaster_agent import SalesForecasterAgent
from app.services.training_service import TrainingDataService

# Признаки, которые обязаны совпадать (динамические + календарные).
# Статические dept-фичи (brand/location/name) тривиально совпадают.
CHECK_FEATURES = [
    "rolling_3d_avg_sales", "rolling_7d_avg_sales", "rolling_14d_avg_sales",
    "rolling_30d_avg_sales", "rolling_3d_std_sales", "rolling_7d_std_sales",
    "rolling_14d_std_sales", "rolling_7d_sum_sales", "rolling_14d_sum_sales",
    "lag_1d_sales", "lag_2d_sales", "lag_7d_sales", "lag_14d_sales",
    "pct_change_1d", "pct_change_7d", "pct_change_14d",
    "rolling_7d_min_sales", "rolling_7d_max_sales",
    "sales_momentum_7d", "sales_momentum_14d",
    "is_holiday", "is_pre_holiday", "is_post_holiday",
    "is_ramadan", "is_payday_window",
    "day_of_week", "is_weekend", "month",
]


@pytest.fixture()
def synthetic_history():
    """60 дней продаж одного подразделения с недельным паттерном + шум."""
    rng = np.random.default_rng(42)
    start = pd.Timestamp("2026-04-01")
    dates = pd.date_range(start, periods=60, freq="D")
    dow = dates.dayofweek.values
    base = 500_000 + 200_000 * (dow >= 5)  # выше в выходные
    sales = base * rng.uniform(0.9, 1.1, len(dates))
    df = pd.DataFrame({
        "department_id": "dept-1",
        "date": dates,
        "total_sales": sales.astype(float),
        "department_name": "Tary Burabay",
        "department_code": "t1",
        "department_type": "DEPARTMENT",
        "segment_type": "coffeehouse",
        "parent_id": None,
        "brand": "tary",
        "location_type": "resort_lake",
        "tourist_traffic_dependent": True,
        "is_24_7_flag": True,
        "opening_hour": None,
        "closing_hour": None,
        "seasonality_intensity": "high",
        "opened_date": pd.Timestamp("2024-05-01"),
        "season_start_month": 5,
        "season_end_month": 9,
    })
    return df


def test_dept_train_inference_parity(synthetic_history):
    df = synthetic_history
    svc = TrainingDataService(None)

    # train-путь: фичи для каждой строки
    feat = svc._add_time_features(df.copy())
    feat = svc._add_rolling_features(feat)

    agent = SalesForecasterAgent.__new__(SalesForecasterAgent)

    # Берём несколько прогнозных дат (нужно ≥15 дней истории для lag_14/pct_14)
    for target_pos in (20, 35, 50, 59):
        target_date = df["date"].iloc[target_pos]
        history = df[df["date"] < target_date].copy()

        inf = agent._create_prediction_features(target_date.date(), history)
        train_row = feat[feat["date"] == target_date].iloc[0]

        mism = []
        for f in CHECK_FEATURES:
            tv = float(train_row[f])
            iv = float(inf[f])
            if not np.isclose(tv, iv, rtol=1e-6, atol=1e-3, equal_nan=True):
                mism.append((target_date.date(), f, tv, iv))
        assert not mism, f"train≠inference: {mism[:8]}"


def test_ramadan_and_payday_features_present(synthetic_history):
    """Новые календарные фичи (3.1) реально строятся в train-пути."""
    svc = TrainingDataService(None)
    feat = svc._add_time_features(synthetic_history.copy())
    assert "is_ramadan" in feat.columns
    assert "is_payday_window" in feat.columns
    # 1-5 и 25 числа помечены как payday
    assert feat[feat["date"].dt.day == 3]["is_payday_window"].iloc[0] == 1
    assert feat[feat["date"].dt.day == 15]["is_payday_window"].iloc[0] == 0

"""Тест-инвариант SKU feature-builder: train == inference (P0-5, Фаза 2.1).

Главная причина непригодности SKU-модели (test R² 0.10) — признаки на
инференсе считались другим кодом с 8 расхождениями (a-h из ML_AUDIT_REPORT).
Этот тест закрепляет контракт НАВСЕГДА: для случайных (dept, product) и
даты D признаки, построенные train-путём (сетка за весь период обучения)
и inference-путём (сетка за INFERENCE_WINDOW_DAYS до D), совпадают
поэлементно.

Дополнительно фиксируются точечные свойства: отсутствие утечки таргета
(признаки строки не зависят от её собственного qty), изоляция rolling внутри
групп, календарная семантика same_weekday и days_since_last_sale.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.sku_feature_builder import (
    INFERENCE_WINDOW_DAYS,
    build_features,
    build_inference_grid,
    expand_zero_days,
    fit_encoding_maps,
)
from app.services.sku_training_service import SkuTrainingDataService

FEATURES = SkuTrainingDataService.get_feature_columns()

N_DEPTS = 3
N_PRODUCTS = 12
HISTORY_DAYS = 90
TARGET = date(2026, 7, 1)
START = TARGET - timedelta(days=HISTORY_DAYS)


def _synthetic_world(seed: int = 7):
    """Синтетика: разреженные продажи (интермиттент), метаданные, активные пары."""
    rng = np.random.default_rng(seed)
    dept_ids = [f"dept-{i}" for i in range(N_DEPTS)]
    product_ids = list(range(101, 101 + N_PRODUCTS))

    rows = []
    for d in dept_ids:
        for p in product_ids:
            # у каждого SKU своя интенсивность: от «каждый день» до «раз в неделю»
            p_sale = rng.uniform(0.15, 0.95)
            for k in range(HISTORY_DAYS + 1):  # включая TARGET (факт есть)
                day = START + timedelta(days=k)
                if rng.random() < p_sale:
                    qty = float(rng.integers(1, 20))
                    rows.append({
                        "department_id": d, "product_id": p, "date": day,
                        "total_qty": qty, "total_sum": qty * (100 + p),
                    })
    raw = pd.DataFrame(rows)

    product_meta = pd.DataFrame({
        "product_id": product_ids,
        "product_name": [f"dish-{p}" for p in product_ids],
        "product_type": ["DISH" if p % 2 else "GOODS" for p in product_ids],
        "default_sale_price": [100.0 + p if p % 3 else None for p in product_ids],
        "weight_kg": [0.2 * (p % 4) for p in product_ids],
        "is_included_in_menu": [p % 5 != 0 for p in product_ids],
        "group_id": [f"g-{p % 4}" if p % 7 else None for p in product_ids],
        "category_id": [f"c-{p % 3}" for p in product_ids],
        "group_name": [f"Группа {p % 4}" for p in product_ids],
        "category_name": [f"Категория {p % 3}" for p in product_ids],
    })

    dept_meta = pd.DataFrame({
        "department_id": dept_ids,
        "department_name": ["Tary Burabay", "Sandyq Алматы Plaza", "Madlen ТРЦ Mall"],
        "department_code": ["t1", "s1", "m1"],
        "department_type": ["DEPARTMENT"] * N_DEPTS,
        "segment_type": ["coffeehouse", "restaurant", "cafe"],
        "parent_id": [None, "root", None],
        "brand": ["tary", "sandyq", None],
        "location_type": ["resort_lake", "city_center", None],
        "tourist_traffic_dependent": [True, False, False],
        "is_24_7_flag": [True, False, False],
        "opening_hour": [None, 10, 8],
        "closing_hour": [None, 23, 20],
        "seasonality_intensity": ["high", "none", "low"],
        "city": ["Бурабай", "Алматы", "Астана"],
        "opened_date": [date(2024, 5, 1), None, date(2026, 5, 1)],
        "season_start_month": [5, None, None],
        "season_end_month": [9, None, None],
    })

    active_pairs = raw[["department_id", "product_id"]].drop_duplicates()
    return raw, product_meta, dept_meta, active_pairs


@pytest.fixture(scope="module")
def world():
    return _synthetic_world()


@pytest.fixture(scope="module")
def train_features(world):
    """Train-путь: полная сетка START..TARGET, fit encodings."""
    raw, product_meta, dept_meta, active_pairs = world
    grid = expand_zero_days(raw, active_pairs, START, TARGET)
    df, maps = build_features(grid, product_meta, dept_meta, fit_encodings=True)
    return df, maps


@pytest.fixture(scope="module")
def inference_features(world, train_features):
    """Inference-путь: окно INFERENCE_WINDOW_DAYS до TARGET, encodings из train."""
    raw, product_meta, dept_meta, active_pairs = world
    _, maps = train_features
    raw_window = raw[raw["date"] < TARGET]  # инференс не видит target-день
    grid = build_inference_grid(raw_window, active_pairs, TARGET)
    df, _ = build_features(grid, product_meta, dept_meta, encoding_maps=maps)
    return df


def test_invariant_train_equals_inference_for_random_points(train_features, inference_features):
    """ГЛАВНЫЙ ИНВАРИАНТ (2.1): 20+ случайных (dept, product) на дату D —
    поэлементное совпадение всех фичей train- и inference-пути."""
    train_df, _ = train_features
    t_rows = train_df[train_df["date"] == pd.Timestamp(TARGET)].set_index(
        ["department_id", "product_id"])
    i_rows = inference_features[
        inference_features["date"] == pd.Timestamp(TARGET)
    ].set_index(["department_id", "product_id"])

    common = list(t_rows.index.intersection(i_rows.index))
    assert len(common) >= 20, f"мало общих пар для проверки: {len(common)}"

    rng = np.random.default_rng(42)
    sample = [common[i] for i in rng.choice(len(common), size=20, replace=False)]

    mismatches = []
    for key in sample:
        for col in FEATURES:
            tv = float(t_rows.loc[key, col])
            iv = float(i_rows.loc[key, col])
            if not np.isclose(tv, iv, rtol=1e-5, atol=1e-6, equal_nan=True):
                mismatches.append((key, col, tv, iv))
    assert not mismatches, (
        f"{len(mismatches)} расхождений train vs inference, первые 10: {mismatches[:10]}"
    )


def test_no_target_leakage_own_day_qty(world, train_features):
    """Признаки строки не зависят от её собственного total_qty (все окна
    strictly past): обнуляем qty target-дня в сырых данных — фичи неизменны."""
    raw, product_meta, dept_meta, active_pairs = world
    _, maps = train_features

    raw_zeroed = raw.copy()
    raw_zeroed.loc[raw_zeroed["date"] == TARGET, ["total_qty", "total_sum"]] = 0.0

    grid_a = expand_zero_days(raw, active_pairs, START, TARGET)
    grid_b = expand_zero_days(raw_zeroed, active_pairs, START, TARGET)
    df_a, _ = build_features(grid_a, product_meta, dept_meta, encoding_maps=maps)
    df_b, _ = build_features(grid_b, product_meta, dept_meta, encoding_maps=maps)

    a = df_a[df_a["date"] == pd.Timestamp(TARGET)].sort_values(
        ["department_id", "product_id"])[FEATURES].reset_index(drop=True)
    b = df_b[df_b["date"] == pd.Timestamp(TARGET)].sort_values(
        ["department_id", "product_id"])[FEATURES].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_rolling_does_not_cross_group_boundaries(world, train_features):
    """P0-5b: у первого дня каждой группы rolling-фичи = 0 (нет прошлого),
    а не хвост чужого продукта."""
    train_df, _ = train_features
    first_rows = train_df[train_df["date"] == pd.Timestamp(START)]
    for col in ["sku_rolling_7d_avg_qty", "sku_rolling_30d_avg_qty",
                "sku_lag_1d_qty", "dept_total_qty_7d"]:
        assert (first_rows[col] == 0).all(), f"{col} у первого дня групп должен быть 0"


def test_same_weekday_avg_is_calendar_correct(world, train_features):
    """P0-5f: same_weekday_avg = среднее qty той же группы ровно 7/14/21/28
    дней назад."""
    train_df, _ = train_features
    row = train_df[
        (train_df["date"] == pd.Timestamp(TARGET))
    ].iloc[0]
    dept, prod = row["department_id"], row["product_id"]
    g = train_df[(train_df["department_id"] == dept) & (train_df["product_id"] == prod)]
    expected = np.mean([
        float(g[g["date"] == pd.Timestamp(TARGET - timedelta(days=k))]["total_qty"].iloc[0])
        for k in (7, 14, 21, 28)
    ])
    assert np.isclose(float(row["sku_same_weekday_avg_qty"]), expected, rtol=1e-5)


def test_days_since_last_sale_calendar_and_capped(world, train_features):
    """P0-5h: календарные дни с последней продажи, cap на 30."""
    train_df, _ = train_features
    col = train_df["sku_days_since_last_sale"]
    assert col.max() <= 30.0
    assert col.min() >= 1.0 or (col.min() >= 0.0)

    # ручная проверка одной точки
    row = train_df[train_df["date"] == pd.Timestamp(TARGET)].iloc[3]
    dept, prod = row["department_id"], row["product_id"]
    g = train_df[
        (train_df["department_id"] == dept) & (train_df["product_id"] == prod)
    ].sort_values("date")
    past = g[(g["date"] < pd.Timestamp(TARGET)) & (g["total_qty"] > 0)]
    expected = (pd.Timestamp(TARGET) - past["date"].max()).days if len(past) else 30
    assert float(row["sku_days_since_last_sale"]) == min(expected, 30)


def test_rank_uses_past_week_not_current_day(world, train_features):
    """P0-5c: ранг считается по выручке ПРОШЛЫХ 7 дней — обнуление продаж
    target-дня не меняет ранги этого дня (утечки текущего дня нет)."""
    raw, product_meta, dept_meta, active_pairs = world
    _, maps = train_features

    raw_zeroed = raw.copy()
    raw_zeroed.loc[raw_zeroed["date"] == TARGET, ["total_qty", "total_sum"]] = 0.0
    grid = expand_zero_days(raw_zeroed, active_pairs, START, TARGET)
    df_b, _ = build_features(grid, product_meta, dept_meta, encoding_maps=maps)

    train_df, _ = train_features
    a = train_df[train_df["date"] == pd.Timestamp(TARGET)].sort_values(
        ["department_id", "product_id"])["sku_rank_in_dept"].to_numpy()
    b = df_b[df_b["date"] == pd.Timestamp(TARGET)].sort_values(
        ["department_id", "product_id"])["sku_rank_in_dept"].to_numpy()
    assert (a == b).all()


def test_encodings_stable_and_from_train(world, train_features):
    """P0-5d: коды групп/категорий детерминированы и переиспользуемы."""
    raw, product_meta, dept_meta, active_pairs = world
    _, maps = train_features

    maps2 = fit_encoding_maps(product_meta)
    assert maps["group_id"] == maps2["group_id"]
    assert maps["category_id"] == maps2["category_id"]
    assert maps["price_median"] > 0

    # неизвестная группа на инференсе → -1, не падение
    pm_new = product_meta.copy()
    pm_new.loc[pm_new.index[0], "group_id"] = "g-UNSEEN"
    grid = build_inference_grid(raw[raw["date"] < TARGET], active_pairs, TARGET)
    df, _ = build_features(grid, pm_new, dept_meta, encoding_maps=maps)
    pid = product_meta["product_id"].iloc[0]
    enc = df[df["product_id"] == pid]["sku_group_encoded"].iloc[0]
    assert enc == -1

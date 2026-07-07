"""Единый feature-builder SKU-модели (ML_AUDIT_REPORT.md P0-5, Фаза 2.1).

До Фазы 2 train и inference считали признаки РАЗНЫМ кодом с 8 расхождениями
(a-h из аудита): инференс без zero-fill дней, rolling через Series.transform
поверх границ групп, утечка sku_rank_in_dept (ранг по total_sum текущего дня),
нестабильные Categorical-коды, константы вместо реальных значений, сломанный
same_weekday_avg, dept_total_qty_7d по строкам вместо дней. Итог — модель с
test R² 0.10 и непригодным инференсом.

Теперь ОДИН код строит признаки для обоих путей:
- train:     сетка за период обучения → build_features(fit_encodings=True)
- inference: сетка за INFERENCE_WINDOW_DAYS до target-даты (+ сама дата) →
             build_features(encoding_maps из .pkl)

Инварианты:
- «строго прошлое»: каждый lag/rolling построен на shift(1) — строка своей
  target-даты не участвует в собственных признаках;
- rolling не пересекает границы (department_id, product_id)-групп —
  только groupby(...).rolling()/shift(), никаких Series.transform;
- сетка календарная с нулями (zero-expansion) — интермиттент-ряды видят
  дни без продаж и в train, и в inference;
- категориальные коды и медиана цены фиксируются на train
  (fit_encoding_maps) и переиспользуются на inference из .pkl;
- память (P0-2a): сетка несёт только ключи + float32-значения, календарные /
  департаментные / продуктовые признаки считаются на МАЛЕНЬКИХ уникальных
  срезах и мерджатся, метаданные не тащатся через cross-join.

Тест-инвариант train == inference: tests/unit/test_sku_feature_parity.py.
"""

import logging
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

GROUP_COLS = ["department_id", "product_id"]

# Максимальная глубина lookback среди всех признаков:
# rolling_30d (30), same_weekday shift 28, lag_14 + rolling_14 (28), dept 7d (8)
MAX_LOOKBACK_DAYS = 30
# Окно реконструкции сетки на инференсе: lookback + запас
INFERENCE_WINDOW_DAYS = 45
# days_since_last_sale насыщается (train-сетка длиннее inference-окна;
# без капа значения > окна инференса невоспроизводимы)
DAYS_SINCE_SALE_CAP = 30.0


# ---------------------------------------------------------------------------
# Сетка
# ---------------------------------------------------------------------------

def expand_zero_days(
    raw_values: pd.DataFrame,
    active_pairs: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Календарная сетка (dept, product, date) с нулями для дней без продаж.

    raw_values: [department_id, product_id, date, total_qty, total_sum].
    Возвращает ТОЛЬКО ключи + float32-значения — метаданные мерджатся после
    расчёта признаков (память, аудит P0-2a).
    """
    all_dates = pd.DataFrame({"date": pd.date_range(start_date, end_date, freq="D")})
    skeleton = active_pairs[GROUP_COLS].drop_duplicates().merge(all_dates, how="cross")

    vals = raw_values[GROUP_COLS + ["date", "total_qty", "total_sum"]].copy()
    vals["date"] = pd.to_datetime(vals["date"])

    grid = skeleton.merge(vals, on=GROUP_COLS + ["date"], how="left")
    grid["total_qty"] = grid["total_qty"].fillna(0).astype("float32")
    grid["total_sum"] = grid["total_sum"].fillna(0).astype("float32")
    return grid


def build_inference_grid(
    raw_values: pd.DataFrame,
    active_pairs: pd.DataFrame,
    target_date: date,
    window_days: int = INFERENCE_WINDOW_DAYS,
) -> pd.DataFrame:
    """Сетка для инференса: [target-window .. target] включительно.

    Строка target-даты получает qty=0 (или факт, если дата в прошлом —
    признаки от этого не зависят: все окна strictly past через shift).
    """
    start = target_date - timedelta(days=window_days)
    return expand_zero_days(raw_values, active_pairs, start, target_date)


# ---------------------------------------------------------------------------
# Encodings (P0-5d): fit на train, живут в .pkl модели
# ---------------------------------------------------------------------------

def fit_encoding_maps(product_meta: pd.DataFrame) -> Dict:
    """Стабильные категориальные коды + медиана цены.

    Раньше train использовал pd.Categorical(...).codes (коды зависят от
    состава датасета), а inference подставлял константу 0.
    """
    def _codes(series: pd.Series) -> Dict:
        values = sorted(str(v) for v in series.dropna().unique())
        return {v: i for i, v in enumerate(values)}

    prices = pd.to_numeric(product_meta["default_sale_price"], errors="coerce")
    positive = prices[prices > 0]
    return {
        "group_id": _codes(product_meta["group_id"]),
        "category_id": _codes(product_meta["category_id"]),
        "price_median": float(positive.median()) if len(positive) else 0.0,
    }


# ---------------------------------------------------------------------------
# Признаки
# ---------------------------------------------------------------------------

def _add_dynamic_features(grid: pd.DataFrame) -> pd.DataFrame:
    """Lag/rolling/cross признаки на нулевой сетке, строго внутри групп."""
    grid = grid.sort_values(GROUP_COLS + ["date"]).reset_index(drop=True)

    g_qty = grid.groupby(GROUP_COLS, sort=False)["total_qty"]

    # Лаги (P0-5a: по календарным дням сетки, не по «дням с продажами»)
    grid["sku_lag_1d_qty"] = g_qty.shift(1)
    grid["sku_lag_7d_qty"] = g_qty.shift(7)
    grid["sku_lag_14d_qty"] = g_qty.shift(14)

    # Rolling по прошлому: shift(1) + groupby().rolling() — окна не пересекают
    # границы групп (P0-5b: раньше Series.transform катился по всему df)
    grid["_past_qty"] = g_qty.shift(1)
    gb_past = grid.groupby(GROUP_COLS, sort=False)["_past_qty"]
    for window, name in ((3, "3d"), (7, "7d"), (14, "14d"), (30, "30d")):
        grid[f"sku_rolling_{name}_avg_qty"] = (
            gb_past.rolling(window, min_periods=1).mean().droplevel(list(range(len(GROUP_COLS))))
        )
    grid["sku_rolling_7d_std_qty"] = (
        gb_past.rolling(7, min_periods=1).std().droplevel(list(range(len(GROUP_COLS))))
    )

    # Средний qty того же дня недели за 4 прошлые недели (P0-5f: раньше —
    # позиционная арифметика, не связанная с реальным днём недели)
    grid["sku_same_weekday_avg_qty"] = pd.concat(
        [g_qty.shift(k) for k in (7, 14, 21, 28)], axis=1
    ).mean(axis=1)

    # Календарные дни с последней продажи, строго до текущего дня (P0-5h);
    # cap = DAYS_SINCE_SALE_CAP, чтобы train (длинная история) и inference
    # (окно 45д) давали одинаковые значения
    pos = grid.groupby(GROUP_COLS, sort=False).cumcount().astype("float32")
    grid["_sold_pos"] = pos.where(grid["total_qty"].values > 0)
    grid["_sold_pos_prev"] = grid.groupby(GROUP_COLS, sort=False)["_sold_pos"].shift(1)
    last_sold = grid.groupby(GROUP_COLS, sort=False)["_sold_pos_prev"].ffill()
    grid["sku_days_since_last_sale"] = (
        (pos - last_sold).fillna(DAYS_SINCE_SALE_CAP).clip(upper=DAYS_SINCE_SALE_CAP)
    )

    # --- Департаментные агрегаты по КАЛЕНДАРНЫМ дням (P0-5g: раньше train
    # катил rolling по строкам product-day, inference брал tail(7) строк) ---
    dept_daily = (
        grid.groupby(["department_id", "date"], as_index=False)
        .agg(_dept_qty=("total_qty", "sum"), _dept_sum=("total_sum", "sum"))
        .sort_values(["department_id", "date"])
        .reset_index(drop=True)
    )
    dd_g = dept_daily.groupby("department_id", sort=False)
    dept_daily["_dept_qty_prev"] = dd_g["_dept_qty"].shift(1)
    dept_daily["_dept_sum_prev"] = dd_g["_dept_sum"].shift(1)
    dept_daily["dept_total_qty_7d"] = (
        dept_daily.groupby("department_id", sort=False)["_dept_qty_prev"]
        .rolling(7, min_periods=1).sum().droplevel(0)
    )
    dept_daily["_dept_sum_7d"] = (
        dept_daily.groupby("department_id", sort=False)["_dept_sum_prev"]
        .rolling(7, min_periods=1).sum().droplevel(0)
    )
    grid = grid.merge(
        dept_daily[["department_id", "date", "dept_total_qty_7d", "_dept_sum_7d"]],
        on=["department_id", "date"], how="left",
    )

    # Выручка SKU за прошлые 7 дней и её доля в выручке подразделения
    grid["_past_sum"] = grid.groupby(GROUP_COLS, sort=False)["total_sum"].shift(1)
    grid["_sku_sum_7d"] = (
        grid.groupby(GROUP_COLS, sort=False)["_past_sum"]
        .rolling(7, min_periods=1).sum().droplevel(list(range(len(GROUP_COLS))))
    )
    dept_sum_7d = grid["_dept_sum_7d"].to_numpy()
    sku_sum_7d = grid["_sku_sum_7d"].to_numpy()
    safe = dept_sum_7d > 0
    share = np.zeros(len(grid), dtype="float32")
    np.divide(sku_sum_7d, dept_sum_7d, out=share, where=safe)
    grid["sku_revenue_share_7d"] = share

    # Ранг SKU в подразделении по выручке ПРОШЛОЙ недели (P0-5c: раньше —
    # ранг по total_sum текущего дня за весь датасет = утечка таргета,
    # а на инференсе — константа 50)
    grid["sku_rank_in_dept"] = (
        grid.groupby(["department_id", "date"], sort=False)["_sku_sum_7d"]
        .rank(ascending=False, method="dense")
        .fillna(999)
        .clip(upper=100)
        .astype("int16")
    )

    # fillna(0) для lag/rolling (первые строки групп)
    fill_zero = [
        "sku_lag_1d_qty", "sku_lag_7d_qty", "sku_lag_14d_qty",
        "sku_rolling_3d_avg_qty", "sku_rolling_7d_avg_qty",
        "sku_rolling_14d_avg_qty", "sku_rolling_30d_avg_qty",
        "sku_rolling_7d_std_qty", "sku_same_weekday_avg_qty",
        "dept_total_qty_7d", "sku_revenue_share_7d",
    ]
    for c in fill_zero:
        grid[c] = grid[c].fillna(0).astype("float32")

    return grid.drop(columns=[
        "_past_qty", "_sold_pos", "_sold_pos_prev", "_past_sum",
        "_sku_sum_7d", "_dept_sum_7d",
    ])


def _add_static_sku_features(
    grid: pd.DataFrame, product_meta: pd.DataFrame, encoding_maps: Dict,
) -> pd.DataFrame:
    """Статические признаки SKU из product_meta (P0-5d/e: реальные значения
    и стабильные коды на обоих путях; раньше inference подставлял константы)."""
    meta = product_meta.drop_duplicates("product_id").set_index("product_id")

    ptype = grid["product_id"].map(meta["product_type"])
    grid["product_type_dish"] = (ptype == "DISH").astype("int8")
    grid["product_type_goods"] = (ptype == "GOODS").astype("int8")

    price = pd.to_numeric(grid["product_id"].map(meta["default_sale_price"]), errors="coerce")
    grid["sku_default_price"] = price.fillna(encoding_maps.get("price_median", 0.0)).astype("float32")

    grid["sku_weight_kg"] = (
        pd.to_numeric(grid["product_id"].map(meta["weight_kg"]), errors="coerce")
        .fillna(0).astype("float32")
    )
    grid["sku_is_in_menu"] = (
        grid["product_id"].map(meta["is_included_in_menu"]).fillna(True).astype(bool).astype("int8")
    )

    group_ids = grid["product_id"].map(meta["group_id"])
    category_ids = grid["product_id"].map(meta["category_id"])
    gmap = encoding_maps.get("group_id", {})
    cmap = encoding_maps.get("category_id", {})
    grid["sku_group_encoded"] = (
        group_ids.map(lambda v: gmap.get(str(v), -1) if pd.notna(v) else -1).astype("int32")
    )
    grid["sku_category_encoded"] = (
        category_ids.map(lambda v: cmap.get(str(v), -1) if pd.notna(v) else -1).astype("int32")
    )
    # Исторически «глубина группы» вырождалась во флаг наличия группы —
    # сохраняем семантику явно
    grid["sku_group_depth"] = group_ids.notna().astype("int8")
    return grid


def _add_calendar_and_dept_features(grid: pd.DataFrame, dept_meta: pd.DataFrame) -> pd.DataFrame:
    """Календарные и департаментные признаки на МАЛЕНЬКИХ уникальных срезах.

    Использует те же методы TrainingDataService, что и department-модель, —
    единый календарь праздников и operational-логика.
    """
    from .training_service import TrainingDataService

    dept_svc = TrainingDataService(None)  # db не нужен для этих методов

    # Календарь: уникальные даты (~181 строка вместо 2.1M)
    dates = pd.DataFrame({"date": pd.to_datetime(sorted(grid["date"].unique()))})
    dates = dept_svc._add_time_features(dates)
    time_cols = [c for c in dates.columns if c not in ("date", "season")]
    grid = grid.merge(dates[["date"] + time_cols], on="date", how="left")

    # Департамент × дата (дата нужна для days_since_opening / is_in_season)
    dept_dates = grid[["department_id", "date"]].drop_duplicates()
    dm = dept_meta.drop_duplicates("department_id").copy()
    dept_frame = dept_dates.merge(dm, on="department_id", how="left")
    dept_frame["date"] = pd.to_datetime(dept_frame["date"])
    dept_frame = dept_svc._add_department_features(dept_frame)
    dept_frame = dept_svc._add_operational_features(dept_frame)
    # Отбираем dept/operational ФИЧИ по авторитетному списку, а НЕ по разнице
    # с сырыми колонками: имена вроде `is_24_7` есть и в сырых метаданных, и
    # среди operational-фичей — set-difference молча терял их (баг, найден в
    # эксперименте 2.5: «Missing features: is_24_7»).
    from .sku_training_service import SkuTrainingDataService
    wanted = set(SkuTrainingDataService.get_feature_columns())
    already = set(grid.columns)
    dept_feature_cols = [
        c for c in dept_frame.columns
        if c in wanted and c not in already and c not in ("department_id", "date")
    ]
    grid = grid.merge(
        dept_frame[["department_id", "date"] + dept_feature_cols],
        on=["department_id", "date"], how="left",
    )
    return grid


def build_features(
    grid: pd.DataFrame,
    product_meta: pd.DataFrame,
    dept_meta: pd.DataFrame,
    encoding_maps: Optional[Dict] = None,
    fit_encodings: bool = False,
) -> Tuple[pd.DataFrame, Dict]:
    """Полный набор SKU-признаков на нулевой сетке. ЕДИНСТВЕННАЯ точка
    расчёта для train и inference (аудит P0-5).

    Возвращает (df_с_признаками, encoding_maps).
    """
    if fit_encodings:
        encoding_maps = fit_encoding_maps(product_meta)
    elif not encoding_maps:
        logger.warning(
            "build_features: encoding_maps отсутствуют (старый .pkl?) — "
            "коды будут -1, price_median из текущих метаданных"
        )
        encoding_maps = fit_encoding_maps(product_meta)

    grid = _add_dynamic_features(grid)
    grid = _add_static_sku_features(grid, product_meta, encoding_maps)
    grid = _add_calendar_and_dept_features(grid, dept_meta)

    # Память (P0-2a): календарные/департаментные merge приходят float64/int64.
    # Даункастим числовые признаки до float32 — на 2M+ строках это экономит
    # ~половину RAM матрицы фичей без потери точности для LightGBM.
    from .sku_training_service import SkuTrainingDataService
    feature_cols = [c for c in SkuTrainingDataService.get_feature_columns() if c in grid.columns]
    grid[feature_cols] = grid[feature_cols].astype("float32")
    return grid, encoding_maps

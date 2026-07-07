"""Feature engineering for SKU-level quantity forecasting.

С Фазы 2.1 (аудит P0-5) ВСЕ признаки строятся единым feature-builder'ом
(`sku_feature_builder.build_features`) — тем же кодом, что и инференс
SkuForecasterAgent. Здесь остались только: загрузка данных (тремя лёгкими
запросами — значения, метаданные продуктов, метаданные подразделений),
zero-expansion через builder и хронологический сплит.

Память (аудит P0-2a): сетка 2M+ строк несёт только ключи + float32-значения;
метаданные НЕ тащатся через cross-join (раньше это давало OOM всего API
каждое воскресенье).
"""

import logging
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from .sku_feature_builder import build_features, expand_zero_days

logger = logging.getLogger(__name__)

VALUES_SQL = text("""
    SELECT
        sds.department_id,
        sds.product_id,
        sds.sale_date AS date,
        sds.total_qty,
        sds.total_sum
    FROM sku_daily_sales sds
    JOIN product p ON p.id = sds.product_id
    WHERE sds.sale_date >= :start_date
      AND sds.sale_date <= :end_date
      AND p.is_deleted = false
""")

PRODUCT_META_SQL = text("""
    SELECT
        p.id AS product_id,
        p.name AS product_name,
        p.type AS product_type,
        p.default_sale_price,
        p.weight_kg,
        p.is_included_in_menu,
        p.group_id,
        p.category_id,
        ng.name AS group_name,
        nc.name AS category_name
    FROM product p
    LEFT JOIN nomenclature_group ng ON ng.id = p.group_id
    LEFT JOIN nomenclature_category nc ON nc.id = p.category_id
    WHERE p.is_deleted = false
""")

DEPT_META_SQL = text("""
    SELECT
        d.id AS department_id,
        d.name AS department_name,
        d.code AS department_code,
        d.type AS department_type,
        d.segment_type,
        d.parent_id,
        d.brand,
        d.location_type,
        d.tourist_traffic_dependent,
        d.is_24_7,
        d.opening_hour,
        d.closing_hour,
        d.seasonality_intensity,
        d.city,
        d.opened_date,
        d.season_start_month,
        d.season_end_month
    FROM departments d
""")

ACTIVE_SKUS_SQL = text("""
    SELECT DISTINCT department_id, product_id
    FROM sku_daily_sales
    WHERE sale_date >= :cutoff_date
      AND sale_date <= :end_date
""")


class SkuTrainingDataService:
    """Prepare training data for SKU-level (per-dish) quantity forecasting."""

    def __init__(self, db: Session):
        self.db = db
        # Заполняется prepare_training_data (fit на train); агент сохраняет
        # их в .pkl и переиспользует на инференсе (P0-5d)
        self.encoding_maps: Dict = {}

    def prepare_training_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        days: Optional[int] = None,
        active_window_days: int = 30,
    ) -> pd.DataFrame:
        if end_date is None:
            end_date = date.today()
        if days is not None:
            start_date = end_date - timedelta(days=days)
        elif start_date is None:
            start_date = end_date - timedelta(days=180)

        logger.info(f"SKU training data: {start_date} → {end_date}, active_window={active_window_days}d")

        raw_values = self._load_values(start_date, end_date)
        if raw_values.empty:
            logger.warning("No SKU sales data found")
            return pd.DataFrame()

        active_pairs = self._get_active_pairs(end_date, active_window_days)
        if active_pairs.empty:
            logger.warning("No active SKU-department pairs")
            return pd.DataFrame()

        logger.info(f"Raw rows: {len(raw_values)}, active pairs: {len(active_pairs)}")

        grid = expand_zero_days(raw_values, active_pairs, start_date, end_date)
        logger.info(f"After zero-expansion: {len(grid)} rows")

        product_meta = self._load_product_meta()
        dept_meta = self._load_dept_meta()

        df, self.encoding_maps = build_features(
            grid, product_meta, dept_meta, fit_encodings=True,
        )

        feature_cols = self.get_feature_columns()
        check_cols = [c for c in feature_cols if c in df.columns] + ["total_qty"]
        initial = len(df)
        df = df.dropna(subset=check_cols)
        logger.info(f"Dropped {initial - len(df)} NaN rows, final: {len(df)}")

        # Проекция только нужных колонок ДО возврата (P0-2a): split делает
        # 3 копии кадра — тащить через них total_sum, helper- и meta-колонки
        # значит утроить лишнюю память. Оставляем фичи + таргет + ключи/дату.
        keep = [c for c in feature_cols if c in df.columns] + [
            "total_qty", "date", "department_id", "product_id",
        ]
        df = df[[c for c in keep if c in df.columns]].copy()

        df = df.sort_values(["department_id", "product_id", "date"]).reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    # Загрузка (три лёгких запроса вместо одного тяжёлого с метаданными)
    # ------------------------------------------------------------------

    def _load_values(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows = self.db.execute(
            VALUES_SQL, {"start_date": start_date, "end_date": end_date}
        ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=[
            "department_id", "product_id", "date", "total_qty", "total_sum",
        ])
        df["department_id"] = df["department_id"].astype(str)
        df["total_qty"] = df["total_qty"].astype("float32")
        df["total_sum"] = df["total_sum"].astype("float32")
        return df

    def _load_product_meta(self) -> pd.DataFrame:
        rows = self.db.execute(PRODUCT_META_SQL).fetchall()
        return pd.DataFrame(rows, columns=[
            "product_id", "product_name", "product_type", "default_sale_price",
            "weight_kg", "is_included_in_menu", "group_id", "category_id",
            "group_name", "category_name",
        ])

    def _load_dept_meta(self) -> pd.DataFrame:
        rows = self.db.execute(DEPT_META_SQL).fetchall()
        df = pd.DataFrame(rows, columns=[
            "department_id", "department_name", "department_code",
            "department_type", "segment_type", "parent_id", "brand",
            "location_type", "tourist_traffic_dependent", "is_24_7",
            "opening_hour", "closing_hour", "seasonality_intensity", "city",
            "opened_date", "season_start_month", "season_end_month",
        ])
        df["department_id"] = df["department_id"].astype(str)
        df["tourist_traffic_dependent"] = df["tourist_traffic_dependent"].fillna(False).astype(bool)
        df["is_24_7_flag"] = df["is_24_7"].fillna(False).astype(bool)
        df["seasonality_intensity"] = df["seasonality_intensity"].fillna("none")
        return df

    def _get_active_pairs(self, end_date: date, window_days: int) -> pd.DataFrame:
        cutoff = end_date - timedelta(days=window_days)
        rows = self.db.execute(ACTIVE_SKUS_SQL, {"cutoff_date": cutoff, "end_date": end_date}).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["department_id", "product_id"])
        df["department_id"] = df["department_id"].astype(str)
        return df

    # ------------------------------------------------------------------
    # Схема
    # ------------------------------------------------------------------

    @staticmethod
    def get_feature_columns() -> list:
        return [
            # Time (23)
            'day_of_week', 'month', 'day_of_month', 'year',
            'is_weekend', 'is_friday', 'is_monday', 'is_saturday', 'is_sunday',
            'weekend_multiplier',
            'quarter', 'is_quarter_start', 'is_quarter_end',
            'week_of_year', 'is_month_start', 'is_month_end',
            'is_winter', 'is_spring', 'is_summer', 'is_autumn',
            'is_holiday', 'is_pre_holiday', 'is_post_holiday',
            # Department (18)
            'is_department', 'is_organization',
            'is_coffeehouse', 'is_restaurant', 'is_confectionery',
            'is_food_court', 'is_store', 'is_fast_food',
            'is_bakery', 'is_cafe', 'is_bar',
            'has_parent', 'dept_name_length',
            'has_plaza_in_name', 'has_center_in_name', 'has_mall_in_name',
            'is_almaty', 'is_astana', 'is_shymkent',
            # Operational (11)
            'is_brand_tary', 'is_brand_sandyq', 'is_brand_madlen', 'is_brand_shopan',
            'is_loc_city_center', 'is_loc_mall', 'is_loc_business_district',
            'is_loc_resort_mountain', 'is_loc_resort_lake', 'is_loc_visit_center', 'is_loc_other',
            'is_tourist_dependent', 'is_24_7', 'working_hours_count',
            'days_since_opening', 'is_new_department',
            'seasonality_score', 'is_in_season',
            # SKU static (8)
            'product_type_dish', 'product_type_goods',
            'sku_default_price', 'sku_weight_kg', 'sku_is_in_menu',
            'sku_group_encoded', 'sku_category_encoded', 'sku_group_depth',
            # SKU rolling (11)
            'sku_lag_1d_qty', 'sku_lag_7d_qty', 'sku_lag_14d_qty',
            'sku_rolling_3d_avg_qty', 'sku_rolling_7d_avg_qty',
            'sku_rolling_14d_avg_qty', 'sku_rolling_30d_avg_qty',
            'sku_rolling_7d_std_qty',
            'sku_same_weekday_avg_qty', 'sku_days_since_last_sale',
            # Cross (4)
            'dept_total_qty_7d', 'sku_revenue_share_7d',
            'sku_rank_in_dept',
        ]

    @staticmethod
    def get_target_column() -> str:
        return 'total_qty'

    def split_train_validation_test(
        self, df: pd.DataFrame,
        val_size: float = 0.15, test_size: float = 0.15,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Chronological 70/15/15 split."""
        df = df.sort_values('date')
        train_end = int(len(df) * (1 - val_size - test_size))
        val_end = int(len(df) * (1 - test_size))
        train_df = df.iloc[:train_end].copy()
        val_df = df.iloc[train_end:val_end].copy()
        test_df = df.iloc[val_end:].copy()
        logger.info(
            f"Split: train={len(train_df)} ({len(train_df)/len(df)*100:.0f}%), "
            f"val={len(val_df)} ({len(val_df)/len(df)*100:.0f}%), "
            f"test={len(test_df)} ({len(test_df)/len(df)*100:.0f}%)"
        )
        return train_df, val_df, test_df

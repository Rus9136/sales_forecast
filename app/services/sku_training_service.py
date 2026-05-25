"""Feature engineering for SKU-level quantity forecasting.

Builds a DataFrame where each row = (department_id, product_id, date)
with ~74 features and target = total_qty.

Reuses time/department/operational feature logic from the existing
TrainingDataService (department-level revenue forecaster) and adds
SKU-specific features on top.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from .training_service import TrainingDataService

logger = logging.getLogger(__name__)

LOAD_SKU_SQL = text("""
    SELECT
        sds.department_id,
        sds.product_id,
        sds.sale_date         AS date,
        sds.total_qty,
        sds.total_sum,
        sds.receipt_count,
        p.name                AS product_name,
        p.type                AS product_type,
        p.default_sale_price,
        p.weight_kg,
        p.is_included_in_menu,
        p.group_id,
        p.category_id,
        ng.name               AS group_name,
        nc.name               AS category_name,
        d.name                AS department_name,
        d.code                AS department_code,
        d.type                AS department_type,
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
    FROM sku_daily_sales sds
    JOIN product p ON p.id = sds.product_id
    LEFT JOIN nomenclature_group ng ON ng.id = p.group_id
    LEFT JOIN nomenclature_category nc ON nc.id = p.category_id
    JOIN departments d ON d.id = sds.department_id
    WHERE sds.sale_date >= :start_date
      AND sds.sale_date <= :end_date
      AND p.is_deleted = false
    ORDER BY sds.department_id, sds.product_id, sds.sale_date
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
        self._dept_svc = TrainingDataService(db)

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

        raw_df = self._load_raw_data(start_date, end_date)
        if raw_df.empty:
            logger.warning("No SKU sales data found")
            return pd.DataFrame()

        active_pairs = self._get_active_pairs(end_date, active_window_days)
        if active_pairs.empty:
            logger.warning("No active SKU-department pairs")
            return pd.DataFrame()

        logger.info(f"Raw rows: {len(raw_df)}, active pairs: {len(active_pairs)}")

        df = self._expand_zero_days(raw_df, active_pairs, start_date, end_date)
        logger.info(f"After zero-expansion: {len(df)} rows")

        df['date'] = pd.to_datetime(df['date'])

        df = self._dept_svc._add_time_features(df)
        df = self._dept_svc._add_department_features(df)
        df = self._dept_svc._add_operational_features(df)
        df = self._add_sku_static_features(df)
        df = self._add_sku_rolling_features(df)
        df = self._add_cross_features(df)

        feature_cols = self.get_feature_columns()
        check_cols = [c for c in feature_cols if c in df.columns] + ['total_qty']
        initial = len(df)
        df = df.dropna(subset=check_cols)
        logger.info(f"Dropped {initial - len(df)} NaN rows, final: {len(df)}")

        df = df.sort_values(['department_id', 'product_id', 'date'])
        return df

    def _load_raw_data(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows = self.db.execute(LOAD_SKU_SQL, {"start_date": start_date, "end_date": end_date}).fetchall()
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=[
            'department_id', 'product_id', 'date', 'total_qty', 'total_sum',
            'receipt_count', 'product_name', 'product_type', 'default_sale_price',
            'weight_kg', 'is_included_in_menu', 'group_id', 'category_id',
            'group_name', 'category_name', 'department_name', 'department_code',
            'department_type', 'segment_type', 'parent_id', 'brand',
            'location_type', 'tourist_traffic_dependent', 'is_24_7',
            'opening_hour', 'closing_hour', 'seasonality_intensity', 'city',
            'opened_date', 'season_start_month', 'season_end_month',
        ])
        df['department_id'] = df['department_id'].astype(str)
        df['total_qty'] = df['total_qty'].astype(float)
        df['total_sum'] = df['total_sum'].astype(float)
        df['tourist_traffic_dependent'] = df['tourist_traffic_dependent'].fillna(False).astype(bool)
        df['is_24_7_flag'] = df['is_24_7'].fillna(False).astype(bool)
        df['seasonality_intensity'] = df['seasonality_intensity'].fillna('none')
        return df

    def _get_active_pairs(self, end_date: date, window_days: int) -> pd.DataFrame:
        cutoff = end_date - timedelta(days=window_days)
        rows = self.db.execute(ACTIVE_SKUS_SQL, {"cutoff_date": cutoff, "end_date": end_date}).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=['department_id', 'product_id'])
        df['department_id'] = df['department_id'].astype(str)
        return df

    def _expand_zero_days(
        self, raw_df: pd.DataFrame, active_pairs: pd.DataFrame,
        start_date: date, end_date: date,
    ) -> pd.DataFrame:
        """For each active (dept, product) pair, ensure every date has a row (fill 0 for missing days)."""
        all_dates = pd.date_range(start_date, end_date, freq='D')
        date_df = pd.DataFrame({'date': all_dates})
        date_df['date'] = date_df['date'].dt.date

        skeleton = active_pairs.merge(date_df, how='cross')

        raw_df['date'] = pd.to_datetime(raw_df['date']).dt.date

        meta_cols = [
            'product_name', 'product_type', 'default_sale_price', 'weight_kg',
            'is_included_in_menu', 'group_id', 'category_id', 'group_name',
            'category_name', 'department_name', 'department_code', 'department_type',
            'segment_type', 'parent_id', 'brand', 'location_type',
            'tourist_traffic_dependent', 'is_24_7_flag', 'opening_hour',
            'closing_hour', 'seasonality_intensity', 'city', 'opened_date',
            'season_start_month', 'season_end_month',
        ]

        product_meta = raw_df.drop_duplicates('product_id')[['product_id'] + [
            c for c in meta_cols if c in [
                'product_name', 'product_type', 'default_sale_price', 'weight_kg',
                'is_included_in_menu', 'group_id', 'category_id', 'group_name',
                'category_name',
            ]
        ]]

        dept_meta = raw_df.drop_duplicates('department_id')[['department_id'] + [
            c for c in meta_cols if c in [
                'department_name', 'department_code', 'department_type',
                'segment_type', 'parent_id', 'brand', 'location_type',
                'tourist_traffic_dependent', 'is_24_7_flag', 'opening_hour',
                'closing_hour', 'seasonality_intensity', 'city', 'opened_date',
                'season_start_month', 'season_end_month',
            ]
        ]]

        value_cols = ['total_qty', 'total_sum', 'receipt_count']
        raw_values = raw_df[['department_id', 'product_id', 'date'] + value_cols]

        merged = skeleton.merge(
            raw_values,
            on=['department_id', 'product_id', 'date'],
            how='left',
        )
        for c in value_cols:
            merged[c] = merged[c].fillna(0)

        merged = merged.merge(product_meta, on='product_id', how='left')
        merged = merged.merge(dept_meta, on='department_id', how='left')

        return merged

    def _add_sku_static_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['product_type_dish'] = (df['product_type'] == 'DISH').astype(int)
        df['product_type_goods'] = (df['product_type'] == 'GOODS').astype(int)

        df['sku_default_price'] = pd.to_numeric(df['default_sale_price'], errors='coerce')
        median_price = df.loc[df['sku_default_price'] > 0, 'sku_default_price'].median()
        df['sku_default_price'] = df['sku_default_price'].fillna(median_price if median_price else 0)

        df['sku_weight_kg'] = pd.to_numeric(df['weight_kg'], errors='coerce').fillna(0)

        df['sku_is_in_menu'] = df['is_included_in_menu'].fillna(True).astype(int)

        df['sku_group_encoded'] = pd.Categorical(df['group_id']).codes
        df['sku_category_encoded'] = pd.Categorical(df['category_id']).codes

        group_depth = {}
        if 'group_name' in df.columns:
            for gid in df['group_id'].dropna().unique():
                group_depth[gid] = 1
        df['sku_group_depth'] = df['group_id'].map(group_depth).fillna(0).astype(int)

        return df

    def _add_sku_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Per-(department, product) rolling/lag features on total_qty."""
        df = df.copy()
        df = df.sort_values(['department_id', 'product_id', 'date'])

        group_cols = ['department_id', 'product_id']
        grouped = df.groupby(group_cols, sort=False)

        qty = grouped['total_qty']
        past_qty = qty.shift(1)

        df['sku_lag_1d_qty'] = qty.shift(1)
        df['sku_lag_7d_qty'] = qty.shift(7)
        df['sku_lag_14d_qty'] = qty.shift(14)

        df['sku_rolling_3d_avg_qty'] = past_qty.transform(lambda x: x.rolling(3, min_periods=1).mean())
        df['sku_rolling_7d_avg_qty'] = past_qty.transform(lambda x: x.rolling(7, min_periods=1).mean())
        df['sku_rolling_14d_avg_qty'] = past_qty.transform(lambda x: x.rolling(14, min_periods=1).mean())
        df['sku_rolling_30d_avg_qty'] = past_qty.transform(lambda x: x.rolling(30, min_periods=1).mean())

        df['sku_rolling_7d_std_qty'] = past_qty.transform(lambda x: x.rolling(7, min_periods=1).std())

        def same_weekday_avg(group):
            result = pd.Series(np.nan, index=group.index)
            vals = group.values
            for i in range(len(vals)):
                if i < 7:
                    result.iloc[i] = np.nan
                else:
                    lookback = vals[max(0, i - 28):i]
                    dow_vals = lookback[np.arange(len(lookback)) % 7 == (len(lookback) - 1) % 7]
                    if len(dow_vals) > 0:
                        result.iloc[i] = dow_vals.mean()
            return result

        df['sku_same_weekday_avg_qty'] = qty.transform(same_weekday_avg)

        def days_since_last_sale(group):
            result = pd.Series(0, index=group.index, dtype=float)
            vals = group.values
            last_sold = -1
            for i in range(len(vals)):
                if i > 0 and vals[i - 1] > 0:
                    last_sold = i - 1
                if last_sold >= 0:
                    result.iloc[i] = i - last_sold
                else:
                    result.iloc[i] = 30
            return result

        df['sku_days_since_last_sale'] = qty.transform(days_since_last_sale)

        rolling_cols = [c for c in df.columns if c.startswith('sku_') and ('rolling' in c or 'lag' in c or 'weekday' in c)]
        for c in rolling_cols:
            df[c] = df[c].fillna(0)

        return df

    def _add_cross_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Features combining department-level and SKU-level signals."""
        df = df.copy()

        dept_daily = df.groupby(['department_id', 'date'])['total_qty'].transform('sum')
        df['dept_total_qty_day'] = dept_daily

        dept_past = df.sort_values(['department_id', 'date']).groupby('department_id')['total_qty']
        df['dept_total_qty_7d'] = dept_past.transform(
            lambda x: x.shift(1).rolling(7, min_periods=1).sum()
        ).fillna(0)

        sku_sum_7d = df.sort_values(['department_id', 'product_id', 'date']).groupby(
            ['department_id', 'product_id']
        )['total_sum'].transform(lambda x: x.shift(1).rolling(7, min_periods=1).sum()).fillna(0)
        dept_sum_7d = df.sort_values(['department_id', 'date']).groupby(
            'department_id'
        )['total_sum'].transform(lambda x: x.shift(1).rolling(7, min_periods=1).sum()).fillna(0)
        df['sku_revenue_share_7d'] = np.where(
            dept_sum_7d > 0, sku_sum_7d / dept_sum_7d, 0
        )

        df['sku_rank_in_dept'] = df.groupby('department_id')['total_sum'].rank(
            ascending=False, method='dense'
        ).fillna(999).clip(upper=100).astype(int)

        return df

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

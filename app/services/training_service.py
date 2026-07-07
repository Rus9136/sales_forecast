import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import Optional, Tuple
import logging

from ..models.branch import SalesSummary, Department
from ..db import get_db
from . import kz_calendar

logger = logging.getLogger(__name__)


class TrainingDataService:
    """Service for preparing training data for ML models"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def prepare_training_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_sales_threshold: float = 0.0,
        days: Optional[int] = None,
        handle_outliers: bool = False,
        outlier_method: str = 'flag'
    ) -> pd.DataFrame:
        """
        Prepare training data with feature engineering
        
        Args:
            start_date: Start date for data extraction 
            end_date: End date for data extraction (default: today)
            min_sales_threshold: Minimum sales amount to include (default: 0)
            days: Number of days back from end_date (overrides start_date if provided)
            handle_outliers: Whether to handle outliers (default: True)
            outlier_method: Method for outlier handling ('winsorize', 'cap', 'remove')
            
        Returns:
            DataFrame with features and target variable
        """
        # Set default dates if not provided
        if end_date is None:
            end_date = datetime.now().date()
            
        # Handle days parameter (overrides start_date)
        if days is not None:
            start_date = end_date - timedelta(days=days)
        elif start_date is None:
            # Default to 365 days for better quality (recent data)
            start_date = end_date - timedelta(days=365)
            logger.info(f"Using default period: last 365 days for better quality")
            
        logger.info(f"Preparing training data from {start_date} to {end_date}")
        
        # Load sales data
        sales_df = self._load_sales_data(start_date, end_date)
        
        if sales_df.empty:
            logger.warning("No sales data found for the specified period")
            return pd.DataFrame()
        
        # Filter out zero or negative sales
        sales_df = sales_df[sales_df['total_sales'] > min_sales_threshold]
        
        # Add time-based features
        sales_df = self._add_time_features(sales_df)
        
        # Add rolling features
        sales_df = self._add_rolling_features(sales_df)
        
        # Add department features
        sales_df = self._add_department_features(sales_df)

        # Add operational metadata features (brand, location_type, hours,
        # seasonality, days since opening). Sparse for unenriched depts —
        # these features stay constant=0/default until UI is filled.
        sales_df = self._add_operational_features(sales_df)

        # Outlier handling — default is now `flag` (non-destructive). Adds an
        # `is_outlier_day` column instead of clipping the target so the model
        # can learn to predict spikes (holidays, promos, payday) rather than
        # forgetting them. Legacy `winsorize`/`cap`/`remove` modes are still
        # available via `outlier_method` for ablation studies.
        sales_df = self._add_outlier_flag(sales_df)
        if handle_outliers and outlier_method in {'winsorize', 'cap', 'remove'}:
            sales_df = self._handle_outliers(sales_df, method=outlier_method)

        # Remove rows with NaN values — but ONLY in feature columns and target.
        # Raw metadata columns (brand, opened_date, opening_hour, ...) are kept
        # in the df for traceability but most are NULL until user enriches them
        # in the UI. Dropping by all columns would discard 100% of data when
        # any single dept has unfilled metadata.
        initial_rows = len(sales_df)
        feature_cols = self.get_feature_columns()
        check_cols = [c for c in feature_cols if c in sales_df.columns] + ['total_sales']
        sales_df = sales_df.dropna(subset=check_cols)
        logger.info(f"Dropped {initial_rows - len(sales_df)} rows with NaN values (subset of {len(check_cols)} cols)")
        
        # Sort by department and date for consistency
        sales_df = sales_df.sort_values(['department_id', 'date'])
        
        logger.info(f"Prepared training data with {len(sales_df)} samples and {len(sales_df.columns)} features")
        
        return sales_df
    
    def _add_outlier_flag(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add `is_outlier_day` boolean feature per department using IQR method.

        Why a flag instead of clipping target values (winsorize):
            Holidays, payday spikes, promo days are real signal — clipping
            erases that signal and forces the model to predict average days
            on extreme dates. A flag lets the model condition its output on
            the day's anomaly status while keeping the true sales target.
        """
        df = df.copy()
        df['is_outlier_day'] = 0

        for dept_id in df['department_id'].unique():
            dept_mask = df['department_id'] == dept_id
            dept_sales = df.loc[dept_mask, 'total_sales']

            if len(dept_sales) < 8:
                continue

            q1 = dept_sales.quantile(0.25)
            q3 = dept_sales.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr

            outlier_mask = (dept_sales < lower) | (dept_sales > upper)
            if outlier_mask.any():
                df.loc[dept_mask & outlier_mask, 'is_outlier_day'] = 1

        n_flagged = int(df['is_outlier_day'].sum())
        logger.info(f"Flagged {n_flagged} outlier days ({n_flagged / len(df) * 100:.1f}%)")
        return df

    def _handle_outliers(self, df: pd.DataFrame, method: str = 'winsorize') -> pd.DataFrame:
        """
        Handle outliers in sales data
        
        Args:
            df: DataFrame with sales data
            method: Method for handling outliers ('winsorize', 'cap', 'remove')
        
        Returns:
            DataFrame with outliers handled
        """
        df = df.copy()
        outliers_handled = 0
        
        for dept_id in df['department_id'].unique():
            dept_mask = df['department_id'] == dept_id
            dept_sales = df.loc[dept_mask, 'total_sales']
            
            # IQR method for outlier detection
            Q1 = dept_sales.quantile(0.25)
            Q3 = dept_sales.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            outliers_mask = (dept_sales < lower_bound) | (dept_sales > upper_bound)
            n_outliers = outliers_mask.sum()
            
            if n_outliers > 0:
                outliers_handled += n_outliers
                
                if method == 'winsorize':
                    # Cap outliers at bounds
                    df.loc[dept_mask & (df['total_sales'] < lower_bound), 'total_sales'] = lower_bound
                    df.loc[dept_mask & (df['total_sales'] > upper_bound), 'total_sales'] = upper_bound
                    
                elif method == 'cap':
                    # Cap at 5th and 95th percentiles
                    p5 = dept_sales.quantile(0.05)
                    p95 = dept_sales.quantile(0.95)
                    df.loc[dept_mask & (df['total_sales'] < p5), 'total_sales'] = p5
                    df.loc[dept_mask & (df['total_sales'] > p95), 'total_sales'] = p95
                    
                elif method == 'remove':
                    # Remove outliers completely
                    df = df[~(dept_mask & outliers_mask)]
        
        logger.info(f"Handled {outliers_handled} outliers using method: {method}")
        return df
    
    def _load_sales_data(self, start_date: Optional[datetime], end_date: datetime) -> pd.DataFrame:
        """Load sales data from database"""
        query = self.db.query(
            SalesSummary.department_id,
            SalesSummary.date,
            SalesSummary.total_sales,
            Department.name.label('department_name'),
            Department.code.label('department_code'),
            Department.type.label('department_type'),
            Department.segment_type.label('segment_type'),
            Department.parent_id.label('parent_id'),
            # Operational metadata (manual-only, populated via UI).
            # NULL/default values = department not yet enriched — features
            # degrade gracefully (treated as 0/baseline).
            Department.brand.label('brand'),
            Department.location_type.label('location_type'),
            Department.tourist_traffic_dependent.label('tourist_traffic_dependent'),
            Department.is_24_7.label('is_24_7'),
            Department.opening_hour.label('opening_hour'),
            Department.closing_hour.label('closing_hour'),
            Department.seasonality_intensity.label('seasonality_intensity'),
            Department.city.label('city'),
            Department.opened_date.label('opened_date'),
            Department.season_start_month.label('season_start_month'),
            Department.season_end_month.label('season_end_month'),
        ).join(
            Department,
            SalesSummary.department_id == Department.id
        )
        
        # Add date filter only if start_date is provided
        if start_date is not None:
            query = query.filter(
                and_(
                    SalesSummary.date >= start_date,
                    SalesSummary.date <= end_date
                )
            )
        else:
            query = query.filter(SalesSummary.date <= end_date)
        
        # Convert to pandas DataFrame
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame([
            {
                'department_id': str(r.department_id),
                'date': r.date,
                'total_sales': float(r.total_sales),
                'department_name': r.department_name,
                'department_code': r.department_code,
                'department_type': r.department_type,
                'segment_type': r.segment_type,
                'parent_id': str(r.parent_id) if r.parent_id else None,
                'brand': r.brand,
                'location_type': r.location_type,
                'tourist_traffic_dependent': bool(r.tourist_traffic_dependent),
                'is_24_7_flag': bool(r.is_24_7),
                'opening_hour': r.opening_hour,
                'closing_hour': r.closing_hour,
                'seasonality_intensity': r.seasonality_intensity or 'none',
                'city': r.city,
                'opened_date': r.opened_date,
                'season_start_month': r.season_start_month,
                'season_end_month': r.season_end_month,
            }
            for r in results
        ])
        
        # Ensure date column is datetime
        df['date'] = pd.to_datetime(df['date'])
        
        return df
    
    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add time-based features to the dataframe"""
        df = df.copy()
        
        # Basic time features
        # ВАЖНО: Используем PostgreSQL совместимую нумерацию (0=Sunday, 1=Monday, ..., 6=Saturday)
        python_dow = df['date'].dt.dayofweek  # 0=Monday, ..., 6=Sunday
        df['day_of_week'] = (python_dow + 1) % 7  # Конвертируем: 0=Sunday, 1=Monday, ..., 6=Saturday
        df['month'] = df['date'].dt.month
        df['day_of_month'] = df['date'].dt.day
        df['year'] = df['date'].dt.year
        
        # Weekend and workday features (PostgreSQL логика)
        df['is_weekend'] = ((df['day_of_week'] == 0) | (df['day_of_week'] == 6)).astype(int)  # Воскресенье=0, Суббота=6
        df['is_friday'] = (df['day_of_week'] == 5).astype(int)  # Пятница=5
        df['is_monday'] = (df['day_of_week'] == 1).astype(int)  # Понедельник=1
        
        # Дополнительные weekend features для усиления эффекта
        df['is_saturday'] = (df['day_of_week'] == 6).astype(int)  # Суббота=6
        df['is_sunday'] = (df['day_of_week'] == 0).astype(int)  # Воскресенье=0
        df['weekend_multiplier'] = ((df['day_of_week'] == 0) | (df['day_of_week'] == 6)).astype(float) * 0.2 + 1.0  # 1.2 для выходных, 1.0 для будних
        
        # Quarter features
        df['quarter'] = df['date'].dt.quarter
        df['is_quarter_start'] = df['date'].dt.is_quarter_start.astype(int)
        df['is_quarter_end'] = df['date'].dt.is_quarter_end.astype(int)
        
        # Week and month features
        df['week_of_year'] = df['date'].dt.isocalendar().week
        df['is_month_start'] = df['date'].dt.is_month_start.astype(int)
        df['is_month_end'] = df['date'].dt.is_month_end.astype(int)
        
        # Season features
        df['season'] = df['month'].apply(self._get_season)
        df['is_winter'] = (df['season'] == 'winter').astype(int)
        df['is_spring'] = (df['season'] == 'spring').astype(int)
        df['is_summer'] = (df['season'] == 'summer').astype(int)
        df['is_autumn'] = (df['season'] == 'autumn').astype(int)
        
        # Kazakhstan holidays — единый календарь (P1-3): один источник для
        # train и inference, Курбан-айт/Рамадан/зарплатные до 2030
        df['is_holiday'] = df['date'].apply(kz_calendar.is_holiday).astype(int)
        df['is_pre_holiday'] = df['date'].apply(kz_calendar.is_pre_holiday).astype(int)
        df['is_post_holiday'] = df['date'].apply(kz_calendar.is_post_holiday).astype(int)
        df['is_ramadan'] = df['date'].apply(kz_calendar.is_ramadan).astype(int)
        df['is_payday_window'] = df['date'].apply(kz_calendar.is_payday_window).astype(int)

        # Days from/to important dates
        df['days_from_new_year'] = (df['date'] - pd.to_datetime(df['year'].astype(str) + '-01-01')).dt.days
        df['days_to_new_year'] = (pd.to_datetime((df['year'] + 1).astype(str) + '-01-01') - df['date']).dt.days

        return df
    
    def _add_department_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add department-specific features"""
        df = df.copy()
        
        # Department type features
        df['is_department'] = (df['department_type'] == 'DEPARTMENT').astype(int)
        df['is_organization'] = (df['department_type'] == 'ORGANIZATION').astype(int)
        
        # Segment type features (one-hot encoding)
        segment_types = ['coffeehouse', 'restaurant', 'confectionery', 'food_court', 
                        'store', 'fast_food', 'bakery', 'cafe', 'bar']
        
        for segment in segment_types:
            df[f'is_{segment}'] = (df['segment_type'] == segment).astype(int)
        
        # Has parent (hierarchy feature)
        df['has_parent'] = df['parent_id'].notna().astype(int)
        
        # Department name features (size indicators)
        df['dept_name_length'] = df['department_name'].str.len()
        df['has_plaza_in_name'] = df['department_name'].str.contains('Plaza|PLAZA', na=False).astype(int)
        df['has_center_in_name'] = df['department_name'].str.contains('Center|CENTER|Центр', na=False).astype(int)
        df['has_mall_in_name'] = df['department_name'].str.contains('Mall|MALL|ТРЦ|ТРК', na=False).astype(int)
        
        # Location-based features (from department name patterns)
        df['is_almaty'] = df['department_name'].str.contains('Алматы|Almaty', na=False).astype(int)
        df['is_astana'] = df['department_name'].str.contains('Астана|Astana|Нур-Султан', na=False).astype(int)
        df['is_shymkent'] = df['department_name'].str.contains('Шымкент|Shymkent', na=False).astype(int)

        return df

    # Canonical brand/location_type vocabularies — must match agent.py
    # so training and inference produce identical feature columns.
    OPERATIONAL_BRANDS = ['tary', 'sandyq', 'madlen', 'shopan']
    OPERATIONAL_LOCATIONS = [
        'city_center', 'mall', 'business_district',
        'resort_mountain', 'resort_lake', 'visit_center', 'other'
    ]
    SEASONALITY_SCORE = {'none': 0, 'low': 1, 'medium': 2, 'high': 3}

    def _add_operational_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert operational metadata (brand, location_type, hours, seasonality)
        into ML features.

        Defaults for unenriched departments:
            - brand/location_type one-hots: all 0
            - tourist_dependent / is_24_7: 0 (DB defaults to false)
            - working_hours_count: 24 if is_24_7, else (close - open) handling
              wrap (e.g. open=22, close=3 → 5h), else 12 (sensible median)
            - days_since_opening: -1 if opened_date is NULL
            - seasonality_score: 0 for 'none'
            - is_in_season: 1 (in-season-by-default for non-seasonal depts)
        """
        df = df.copy()

        # --- Brand one-hot (case-insensitive match) ---
        brand_lower = df['brand'].fillna('').str.lower()
        for b in self.OPERATIONAL_BRANDS:
            df[f'is_brand_{b}'] = (brand_lower == b).astype(int)

        # --- Location type one-hot ---
        loc = df['location_type'].fillna('').str.lower()
        for lt in self.OPERATIONAL_LOCATIONS:
            df[f'is_loc_{lt}'] = (loc == lt).astype(int)

        # --- Boolean operational flags ---
        df['is_tourist_dependent'] = df['tourist_traffic_dependent'].fillna(False).astype(int)
        df['is_24_7'] = df['is_24_7_flag'].fillna(False).astype(int)

        # --- Working hours count ---
        def _working_hours(row):
            if row['is_24_7']:
                return 24
            o, c = row['opening_hour'], row['closing_hour']
            if pd.isna(o) or pd.isna(c) or o is None or c is None:
                return 12  # sensible default for unenriched
            o, c = int(o), int(c)
            if c > o:
                return c - o
            # wrap-around (e.g. open 22, close 3 → 5 hours)
            return (24 - o) + c
        df['working_hours_count'] = df.apply(_working_hours, axis=1)

        # --- Days since opening (capped at 5 years to avoid skew) ---
        opened = pd.to_datetime(df['opened_date'], errors='coerce')
        date_dt = pd.to_datetime(df['date'])
        days_since = (date_dt - opened).dt.days
        df['days_since_opening'] = days_since.fillna(-1).clip(lower=-1, upper=1825).astype(int)
        df['is_new_department'] = ((days_since >= 0) & (days_since < 90)).astype(int)

        # --- Seasonality intensity score ---
        df['seasonality_score'] = (
            df['seasonality_intensity'].fillna('none').map(self.SEASONALITY_SCORE).fillna(0).astype(int)
        )

        # --- Is in season (handles wrap-around like Nov-Mar) ---
        month = date_dt.dt.month
        s_start = pd.to_numeric(df['season_start_month'], errors='coerce')
        s_end = pd.to_numeric(df['season_end_month'], errors='coerce')

        # No season data → assume always in season (default 1, doesn't hurt non-seasonal depts)
        no_season = s_start.isna() | s_end.isna()
        # Normal range: start <= end (e.g. Mar=3, Oct=10 → Mar..Oct in season)
        normal = ~no_season & (s_start <= s_end) & (month >= s_start) & (month <= s_end)
        # Wrap range: start > end (e.g. Nov=11, Mar=3 → Nov,Dec,Jan,Feb,Mar in season)
        wrap = ~no_season & (s_start > s_end) & ((month >= s_start) | (month <= s_end))
        df['is_in_season'] = (no_season | normal | wrap).astype(int)

        return df

    def _add_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rolling window features per department.

        IMPORTANT — no target leakage:
            Pandas `Series.rolling(N)` at row d includes day d in the window,
            which leaks the training target into the feature. Inference
            (`_create_prediction_features` in agent.py) only ever sees days
            before the forecast date, so any rolling/pct_change/momentum
            feature must use ONLY past values during training as well.

            Concretely we apply `.shift(1)` to every rolling output and use
            past-only formulas for momentum / pct_change. Without this the
            model achieves ~6% in-sample MAPE while collapsing to ~50%
            out-of-sample (the "5x gap" observed in stage 2).
        """
        df = df.copy()

        # Sort by department and date
        df = df.sort_values(['department_id', 'date'])

        # Group by department for rolling calculations
        for dept_id in df['department_id'].unique():
            dept_mask = df['department_id'] == dept_id
            dept_sales = df.loc[dept_mask, 'total_sales']
            past_sales = dept_sales.shift(1)  # values strictly before day d

            # Rolling averages — past-only via .shift(1)
            df.loc[dept_mask, 'rolling_3d_avg_sales'] = past_sales.rolling(window=3, min_periods=1).mean()
            df.loc[dept_mask, 'rolling_7d_avg_sales'] = past_sales.rolling(window=7, min_periods=1).mean()
            df.loc[dept_mask, 'rolling_14d_avg_sales'] = past_sales.rolling(window=14, min_periods=1).mean()
            df.loc[dept_mask, 'rolling_30d_avg_sales'] = past_sales.rolling(window=30, min_periods=1).mean()

            # Rolling standard deviations — past-only
            df.loc[dept_mask, 'rolling_3d_std_sales'] = past_sales.rolling(window=3, min_periods=1).std()
            df.loc[dept_mask, 'rolling_7d_std_sales'] = past_sales.rolling(window=7, min_periods=1).std()
            df.loc[dept_mask, 'rolling_14d_std_sales'] = past_sales.rolling(window=14, min_periods=1).std()

            # Rolling sums — past-only
            df.loc[dept_mask, 'rolling_7d_sum_sales'] = past_sales.rolling(window=7, min_periods=1).sum()
            df.loc[dept_mask, 'rolling_14d_sum_sales'] = past_sales.rolling(window=14, min_periods=1).sum()

            # Lag features (already past-only via shift)
            df.loc[dept_mask, 'lag_1d_sales'] = dept_sales.shift(1)
            df.loc[dept_mask, 'lag_2d_sales'] = dept_sales.shift(2)
            df.loc[dept_mask, 'lag_7d_sales'] = dept_sales.shift(7)
            df.loc[dept_mask, 'lag_14d_sales'] = dept_sales.shift(14)

            # Percentage changes — match inference: (d-1 - d-k) / d-k.
            # Pandas `pct_change()` uses (d - d-1) / d-1 which leaks d.
            lag_1 = dept_sales.shift(1)
            lag_2 = dept_sales.shift(2)
            lag_8 = dept_sales.shift(8)
            lag_15 = dept_sales.shift(15)
            df.loc[dept_mask, 'pct_change_1d'] = (lag_1 - lag_2) / lag_2.replace(0, np.nan)
            df.loc[dept_mask, 'pct_change_7d'] = (lag_1 - lag_8) / lag_8.replace(0, np.nan)
            df.loc[dept_mask, 'pct_change_14d'] = (lag_1 - lag_15) / lag_15.replace(0, np.nan)

            # Rolling min/max — past-only
            df.loc[dept_mask, 'rolling_7d_min_sales'] = past_sales.rolling(window=7, min_periods=1).min()
            df.loc[dept_mask, 'rolling_7d_max_sales'] = past_sales.rolling(window=7, min_periods=1).max()

            # Sales momentum — match inference: (mean of last K days) - (mean of prior K days),
            # both windows strictly in the past.
            df.loc[dept_mask, 'sales_momentum_7d'] = (
                past_sales.rolling(window=7, min_periods=1).mean()
                - past_sales.shift(7).rolling(window=7, min_periods=1).mean()
            )
            df.loc[dept_mask, 'sales_momentum_14d'] = (
                past_sales.rolling(window=14, min_periods=1).mean()
                - past_sales.shift(14).rolling(window=14, min_periods=1).mean()
            )

        # Fill NaN values in rolling features with 0
        rolling_cols = [col for col in df.columns if 'rolling_' in col or 'sales_momentum' in col]
        for col in rolling_cols:
            df[col] = df[col].fillna(0)

        return df
    
    def get_target_column(self) -> str:
        """Get target column name"""
        return 'total_sales'
    
    @staticmethod
    def get_feature_columns() -> list:
        """Get list of feature column names"""
        return [
            # Time-based features
            'day_of_week',
            'month',
            'day_of_month',
            'year',
            'is_weekend',
            'is_friday',
            'is_monday',
            'is_saturday',
            'is_sunday',
            'weekend_multiplier',
            'quarter',
            'is_quarter_start',
            'is_quarter_end',
            'week_of_year',
            'is_month_start',
            'is_month_end',
            
            # Seasonal features
            'is_winter',
            'is_spring', 
            'is_summer',
            'is_autumn',
            
            # Holiday features (единый kz_calendar, P1-3/P2-7)
            'is_holiday',
            'is_pre_holiday',
            'is_post_holiday',
            'is_ramadan',
            'is_payday_window',
            'days_from_new_year',
            'days_to_new_year',
            
            # Rolling averages
            'rolling_3d_avg_sales',
            'rolling_7d_avg_sales',
            'rolling_14d_avg_sales',
            'rolling_30d_avg_sales',
            
            # Rolling standard deviations
            'rolling_3d_std_sales',
            'rolling_7d_std_sales',
            'rolling_14d_std_sales',
            
            # Rolling sums
            'rolling_7d_sum_sales',
            'rolling_14d_sum_sales',
            
            # Lag features
            'lag_1d_sales',
            'lag_2d_sales',
            'lag_7d_sales',
            'lag_14d_sales',
            
            # Percentage changes
            'pct_change_1d',
            'pct_change_7d',
            'pct_change_14d',
            
            # Rolling min/max
            'rolling_7d_min_sales',
            'rolling_7d_max_sales',
            
            # Sales momentum
            'sales_momentum_7d',
            'sales_momentum_14d',
            
            # Department type features
            'is_department',
            'is_organization',
            
            # Segment type features
            'is_coffeehouse',
            'is_restaurant',
            'is_confectionery', 
            'is_food_court',
            'is_store',
            'is_fast_food',
            'is_bakery',
            'is_cafe',
            'is_bar',
            
            # Department hierarchy
            'has_parent',
            
            # Department size indicators
            'dept_name_length',
            'has_plaza_in_name',
            'has_center_in_name',
            'has_mall_in_name',
            
            # Location features
            'is_almaty',
            'is_astana',
            'is_shymkent',

            # Outlier flag (replaces destructive winsorize)
            'is_outlier_day',

            # Operational metadata (manual UI-entered) — sparse for unenriched depts.
            # Brand one-hot
            'is_brand_tary',
            'is_brand_sandyq',
            'is_brand_madlen',
            'is_brand_shopan',
            # Location type one-hot
            'is_loc_city_center',
            'is_loc_mall',
            'is_loc_business_district',
            'is_loc_resort_mountain',
            'is_loc_resort_lake',
            'is_loc_visit_center',
            'is_loc_other',
            # Operational flags
            'is_tourist_dependent',
            'is_24_7',
            'working_hours_count',
            # Lifecycle
            'days_since_opening',
            'is_new_department',
            # Seasonality
            'seasonality_score',
            'is_in_season',
        ]
    
    def split_train_validation_test(
        self,
        df: pd.DataFrame,
        val_size: float = 0.15,
        test_size: float = 0.15,
        random_state: int = 42
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Split data into train, validation and test sets
        
        Uses time-based split to respect temporal order:
        - Train: 70% (oldest data)
        - Validation: 15% (middle data) - for early stopping and hyperparameter tuning
        - Test: 15% (newest data) - for final honest evaluation
        
        Args:
            val_size: Proportion of data for validation set
            test_size: Proportion of data for test set
            
        Returns:
            Tuple of (train_df, val_df, test_df)
        """
        # Sort by date
        df = df.sort_values('date')
        
        # Calculate split indices
        train_size = 1 - val_size - test_size
        train_split = int(len(df) * train_size)
        val_split = int(len(df) * (train_size + val_size))
        
        # Split data
        train_df = df.iloc[:train_split].copy()
        val_df = df.iloc[train_split:val_split].copy()
        test_df = df.iloc[val_split:].copy()
        
        logger.info(f"Train set: {len(train_df)} samples ({len(train_df)/len(df)*100:.1f}%)")
        logger.info(f"Validation set: {len(val_df)} samples ({len(val_df)/len(df)*100:.1f}%)")
        logger.info(f"Test set: {len(test_df)} samples ({len(test_df)/len(df)*100:.1f}%)")
        
        return train_df, val_df, test_df
    
    def split_train_test(
        self,
        df: pd.DataFrame,
        test_size: float = 0.2,
        random_state: int = 42
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split data into train and test sets (legacy method)
        
        Uses time-based split to respect temporal order
        """
        # Sort by date
        df = df.sort_values('date')
        
        # Calculate split index
        split_index = int(len(df) * (1 - test_size))
        
        # Split data
        train_df = df.iloc[:split_index].copy()
        test_df = df.iloc[split_index:].copy()
        
        logger.info(f"Train set: {len(train_df)} samples, Test set: {len(test_df)} samples")
        
        return train_df, test_df
    
    def _get_season(self, month: int) -> str:
        """Get season based on month (Northern Hemisphere)"""
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'spring'
        elif month in [6, 7, 8]:
            return 'summer'
        else:  # [9, 10, 11]
            return 'autumn'
    
    # Праздничные методы делегируют в единый kz_calendar (P1-3). Оставлены
    # для обратной совместимости вызовов; новый код зовёт kz_calendar напрямую.
    def _is_kazakhstan_holiday(self, date: pd.Timestamp) -> bool:
        return kz_calendar.is_holiday(date)

    def _is_pre_holiday(self, date: pd.Timestamp) -> bool:
        return kz_calendar.is_pre_holiday(date)

    def _is_post_holiday(self, date: pd.Timestamp) -> bool:
        return kz_calendar.is_post_holiday(date)


def get_training_data_service(db: Session = None) -> TrainingDataService:
    """Factory function to get TrainingDataService instance"""
    if db is None:
        db = next(get_db())
    return TrainingDataService(db)
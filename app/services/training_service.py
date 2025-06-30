import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import Optional, Tuple
import logging

from ..models.branch import SalesSummary, Department
from ..db import get_db

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
        handle_outliers: bool = True,
        outlier_method: str = 'winsorize'
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
        
        # Handle outliers if requested
        if handle_outliers:
            sales_df = self._handle_outliers(sales_df, method=outlier_method)
        
        # Remove rows with NaN values (from rolling features)
        initial_rows = len(sales_df)
        sales_df = sales_df.dropna()
        logger.info(f"Dropped {initial_rows - len(sales_df)} rows with NaN values")
        
        # Sort by department and date for consistency
        sales_df = sales_df.sort_values(['department_id', 'date'])
        
        logger.info(f"Prepared training data with {len(sales_df)} samples and {len(sales_df.columns)} features")
        
        return sales_df
    
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
        logger.info(f"DEBUG: self.db type: {type(self.db)}")
        logger.info(f"DEBUG: self.db has query attr: {hasattr(self.db, 'query')}")
        if hasattr(self.db, 'query'):
            logger.info(f"DEBUG: self.db.query type: {type(self.db.query)}")
        
        query = self.db.query(
            SalesSummary.department_id,
            SalesSummary.date,
            SalesSummary.total_sales,
            Department.name.label('department_name'),
            Department.code.label('department_code'),
            Department.type.label('department_type'),
            Department.segment_type.label('segment_type'),
            Department.parent_id.label('parent_id')
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
                'parent_id': str(r.parent_id) if r.parent_id else None
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
        df['day_of_week'] = df['date'].dt.dayofweek
        df['month'] = df['date'].dt.month
        df['day_of_month'] = df['date'].dt.day
        df['year'] = df['date'].dt.year
        
        # Weekend and workday features
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        df['is_friday'] = (df['day_of_week'] == 4).astype(int)
        df['is_monday'] = (df['day_of_week'] == 0).astype(int)
        
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
        
        # Kazakhstan holidays
        df['is_holiday'] = df['date'].apply(self._is_kazakhstan_holiday).astype(int)
        df['is_pre_holiday'] = df['date'].apply(self._is_pre_holiday).astype(int)
        df['is_post_holiday'] = df['date'].apply(self._is_post_holiday).astype(int)
        
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
    
    def _add_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rolling window features per department"""
        df = df.copy()
        
        # Sort by department and date
        df = df.sort_values(['department_id', 'date'])
        
        # Group by department for rolling calculations
        for dept_id in df['department_id'].unique():
            dept_mask = df['department_id'] == dept_id
            dept_sales = df.loc[dept_mask, 'total_sales']
            
            # Rolling averages (expanded)
            df.loc[dept_mask, 'rolling_3d_avg_sales'] = dept_sales.rolling(
                window=3, min_periods=1
            ).mean()
            
            df.loc[dept_mask, 'rolling_7d_avg_sales'] = dept_sales.rolling(
                window=7, min_periods=1
            ).mean()
            
            df.loc[dept_mask, 'rolling_14d_avg_sales'] = dept_sales.rolling(
                window=14, min_periods=1
            ).mean()
            
            df.loc[dept_mask, 'rolling_30d_avg_sales'] = dept_sales.rolling(
                window=30, min_periods=1
            ).mean()
            
            # Rolling standard deviations (expanded)
            df.loc[dept_mask, 'rolling_3d_std_sales'] = dept_sales.rolling(
                window=3, min_periods=1
            ).std()
            
            df.loc[dept_mask, 'rolling_7d_std_sales'] = dept_sales.rolling(
                window=7, min_periods=1
            ).std()
            
            df.loc[dept_mask, 'rolling_14d_std_sales'] = dept_sales.rolling(
                window=14, min_periods=1
            ).std()
            
            # Rolling sums (new feature type)
            df.loc[dept_mask, 'rolling_7d_sum_sales'] = dept_sales.rolling(
                window=7, min_periods=1
            ).sum()
            
            df.loc[dept_mask, 'rolling_14d_sum_sales'] = dept_sales.rolling(
                window=14, min_periods=1
            ).sum()
            
            # Lag features (expanded)
            df.loc[dept_mask, 'lag_1d_sales'] = dept_sales.shift(1)
            df.loc[dept_mask, 'lag_2d_sales'] = dept_sales.shift(2)
            df.loc[dept_mask, 'lag_7d_sales'] = dept_sales.shift(7)
            df.loc[dept_mask, 'lag_14d_sales'] = dept_sales.shift(14)
            
            # Percentage changes (expanded)
            df.loc[dept_mask, 'pct_change_1d'] = dept_sales.pct_change()
            df.loc[dept_mask, 'pct_change_7d'] = dept_sales.pct_change(periods=7)
            df.loc[dept_mask, 'pct_change_14d'] = dept_sales.pct_change(periods=14)
            
            # Rolling min/max for volatility
            df.loc[dept_mask, 'rolling_7d_min_sales'] = dept_sales.rolling(
                window=7, min_periods=1
            ).min()
            
            df.loc[dept_mask, 'rolling_7d_max_sales'] = dept_sales.rolling(
                window=7, min_periods=1
            ).max()
            
            # Sales momentum (current vs rolling average)
            df.loc[dept_mask, 'sales_momentum_7d'] = dept_sales / df.loc[dept_mask, 'rolling_7d_avg_sales']
            df.loc[dept_mask, 'sales_momentum_14d'] = dept_sales / df.loc[dept_mask, 'rolling_14d_avg_sales']
            
        # Fill NaN values in rolling features with 0
        rolling_cols = [col for col in df.columns if 'rolling_' in col or 'sales_momentum' in col]
        for col in rolling_cols:
            df[col] = df[col].fillna(0)
        
        return df
    
    def get_feature_columns(self) -> list:
        """Get list of feature column names for model training"""
        return [
            # Basic time features
            'day_of_week',
            'month',
            'day_of_month',
            'year',
            
            # Weekend and workday features
            'is_weekend',
            'is_friday',
            'is_monday',
            
            # Quarter features
            'quarter',
            'is_quarter_start',
            'is_quarter_end',
            
            # Week and month features
            'week_of_year',
            'is_month_start',
            'is_month_end',
            
            # Season features
            'is_winter',
            'is_spring',
            'is_summer',
            'is_autumn',
            
            # Holiday features
            'is_holiday',
            'is_pre_holiday',
            'is_post_holiday',
            
            # Days from/to important dates
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
            'is_shymkent'
        ]
    
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
            
            # Holiday features
            'is_holiday',
            'is_pre_holiday',
            'is_post_holiday',
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
            'is_shymkent'
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
    
    def _is_kazakhstan_holiday(self, date: pd.Timestamp) -> bool:
        """Check if date is a Kazakhstan holiday"""
        month = date.month
        day = date.day
        year = date.year
        
        # Fixed holidays
        fixed_holidays = [
            (1, 1),   # New Year's Day
            (1, 2),   # New Year's Day (extended)
            (3, 8),   # International Women's Day
            (3, 21),  # Nauryz Holiday
            (3, 22),  # Nauryz Holiday
            (3, 23),  # Nauryz Holiday
            (5, 1),   # Unity Day of the People of Kazakhstan
            (5, 7),   # Defender of the Fatherland Day
            (5, 9),   # Victory Day
            (7, 6),   # Capital City Day
            (8, 30),  # Constitution Day
            (12, 1),  # First President Day
            (12, 16), # Independence Day
            (12, 17)  # Independence Day (extended)
        ]
        
        if (month, day) in fixed_holidays:
            return True
            
        # Kurban Ait (variable date - approximate)
        # This is a simplified version, in reality it follows lunar calendar
        if year >= 2022:
            kurban_dates = {
                2022: (7, 10),
                2023: (6, 29),
                2024: (6, 17),
                2025: (6, 7),
                2026: (5, 27)
            }
            if year in kurban_dates and (month, day) == kurban_dates[year]:
                return True
        
        return False
    
    def _is_pre_holiday(self, date: pd.Timestamp) -> bool:
        """Check if date is day before a holiday"""
        next_day = date + pd.Timedelta(days=1)
        return self._is_kazakhstan_holiday(next_day)
    
    def _is_post_holiday(self, date: pd.Timestamp) -> bool:
        """Check if date is day after a holiday"""
        prev_day = date - pd.Timedelta(days=1)
        return self._is_kazakhstan_holiday(prev_day)


def get_training_data_service(db: Session = None) -> TrainingDataService:
    """Factory function to get TrainingDataService instance"""
    if db is None:
        db = next(get_db())
    return TrainingDataService(db)
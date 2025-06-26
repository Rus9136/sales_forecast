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
        min_sales_threshold: float = 0.0
    ) -> pd.DataFrame:
        """
        Prepare training data with feature engineering
        
        Args:
            start_date: Start date for data extraction (default: 90 days ago)
            end_date: End date for data extraction (default: today)
            min_sales_threshold: Minimum sales amount to include (default: 0)
            
        Returns:
            DataFrame with features and target variable
        """
        # Set default dates if not provided
        if end_date is None:
            end_date = datetime.now().date()
        if start_date is None:
            start_date = end_date - timedelta(days=180)  # Увеличиваем до 6 месяцев для максимального качества модели
            
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
        
        # Remove rows with NaN values (from rolling features)
        initial_rows = len(sales_df)
        sales_df = sales_df.dropna()
        logger.info(f"Dropped {initial_rows - len(sales_df)} rows with NaN values")
        
        # Sort by department and date for consistency
        sales_df = sales_df.sort_values(['department_id', 'date'])
        
        logger.info(f"Prepared training data with {len(sales_df)} samples and {len(sales_df.columns)} features")
        
        return sales_df
    
    def _load_sales_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
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
            Department.code.label('department_code')
        ).join(
            Department,
            SalesSummary.department_id == Department.id
        ).filter(
            and_(
                SalesSummary.date >= start_date,
                SalesSummary.date <= end_date
            )
        )
        
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
                'department_code': r.department_code
            }
            for r in results
        ])
        
        # Ensure date column is datetime
        df['date'] = pd.to_datetime(df['date'])
        
        return df
    
    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add time-based features to the dataframe"""
        df = df.copy()
        
        # Day of week (0 = Monday, 6 = Sunday)
        df['day_of_week'] = df['date'].dt.dayofweek
        
        # Month
        df['month'] = df['date'].dt.month
        
        # Day of month
        df['day_of_month'] = df['date'].dt.day
        
        # Is weekend (Saturday = 5, Sunday = 6)
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        # Quarter
        df['quarter'] = df['date'].dt.quarter
        
        # Week of year
        df['week_of_year'] = df['date'].dt.isocalendar().week
        
        # Is month start/end
        df['is_month_start'] = df['date'].dt.is_month_start.astype(int)
        df['is_month_end'] = df['date'].dt.is_month_end.astype(int)
        
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
            
            # 7-day rolling average
            df.loc[dept_mask, 'rolling_7d_avg_sales'] = dept_sales.rolling(
                window=7, min_periods=1
            ).mean()
            
            # 14-day rolling average
            df.loc[dept_mask, 'rolling_14d_avg_sales'] = dept_sales.rolling(
                window=14, min_periods=1
            ).mean()
            
            # 30-day rolling average
            df.loc[dept_mask, 'rolling_30d_avg_sales'] = dept_sales.rolling(
                window=30, min_periods=1
            ).mean()
            
            # 7-day rolling std
            df.loc[dept_mask, 'rolling_7d_std_sales'] = dept_sales.rolling(
                window=7, min_periods=1
            ).std()
            
            # Lag features (previous day sales)
            df.loc[dept_mask, 'lag_1d_sales'] = dept_sales.shift(1)
            df.loc[dept_mask, 'lag_7d_sales'] = dept_sales.shift(7)
            
            # Percentage change from previous day
            df.loc[dept_mask, 'pct_change_1d'] = dept_sales.pct_change()
            
        # Fill NaN values in rolling std with 0
        df['rolling_7d_std_sales'] = df['rolling_7d_std_sales'].fillna(0)
        
        return df
    
    def get_feature_columns(self) -> list:
        """Get list of feature column names for model training"""
        return [
            'day_of_week',
            'month',
            'day_of_month',
            'is_weekend',
            'quarter',
            'week_of_year',
            'is_month_start',
            'is_month_end',
            'rolling_7d_avg_sales',
            'rolling_14d_avg_sales',
            'rolling_30d_avg_sales',
            'rolling_7d_std_sales',
            'lag_1d_sales',
            'lag_7d_sales',
            'pct_change_1d'
        ]
    
    def get_target_column(self) -> str:
        """Get target column name"""
        return 'total_sales'
    
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


def get_training_data_service(db: Session = None) -> TrainingDataService:
    """Factory function to get TrainingDataService instance"""
    if db is None:
        db = next(get_db())
    return TrainingDataService(db)
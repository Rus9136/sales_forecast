import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import and_
import joblib
import logging
import os
from typing import Optional, Dict, Any, Tuple

from ..services.training_service import TrainingDataService
from ..models.branch import SalesSummary, Department
from ..db import get_db

logger = logging.getLogger(__name__)


class SalesForecasterAgent:
    """Agent for training and using LightGBM sales forecasting model"""
    
    def __init__(self, model_path: str = "models/lgbm_model.pkl"):
        self.model_path = model_path
        self.model = None
        self.feature_columns = None
        self._training_metrics = None
        self._load_model()
    
    def train_model(
        self, 
        train_df: Optional[pd.DataFrame] = None,
        val_df: Optional[pd.DataFrame] = None,
        test_df: Optional[pd.DataFrame] = None,
        db: Optional[Session] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        val_size: float = 0.15,
        test_size: float = 0.15,
        save_model: bool = True
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Train LightGBM model on historical sales data with proper train/validation/test split
        
        Args:
            val_size: Proportion for validation set (used for early stopping)
            test_size: Proportion for test set (used for honest evaluation)
        
        Returns:
            Dictionary with comprehensive training and evaluation metrics
        """
        logger.info("Starting model training with train/validation/test split...")
        
        # Handle data preparation
        if train_df is None or val_df is None or test_df is None:
            if db is None:
                raise ValueError("Either pre-split dataframes or database session must be provided")
            
            # Initialize training service
            training_service = TrainingDataService(db)
            
            # Prepare training data
            df = training_service.prepare_training_data(start_date, end_date)
            
            if df.empty:
                raise ValueError("No training data available")
            
            # Split data into train/validation/test
            train_df, val_df, test_df = training_service.split_train_validation_test(
                df, val_size=val_size, test_size=test_size
            )
            
            # Get feature columns and target
            self.feature_columns = training_service.get_feature_columns()
            target_column = training_service.get_target_column()
        else:
            # Use pre-split data
            training_service = TrainingDataService(db) if db else None
            if training_service:
                self.feature_columns = training_service.get_feature_columns()
                target_column = training_service.get_target_column()
            else:
                # Create a temporary training service to get updated feature columns
                from ..db import get_db
                temp_db = next(get_db())
                temp_training_service = TrainingDataService(temp_db)
                self.feature_columns = temp_training_service.get_feature_columns()
                target_column = temp_training_service.get_target_column()
        
        # Prepare datasets
        X_train = train_df[self.feature_columns]
        y_train = train_df[target_column]
        X_val = val_df[self.feature_columns]
        y_val = val_df[target_column]
        X_test = test_df[self.feature_columns]
        y_test = test_df[target_column]
        
        logger.info(f"Dataset sizes - Train: {len(X_train)}, Validation: {len(X_val)}, Test: {len(X_test)}")
        
        # Initialize and train model
        self.model = lgb.LGBMRegressor(
            n_estimators=200,  # Увеличиваем для better performance
            learning_rate=0.1,
            max_depth=5,
            num_leaves=31,
            random_state=42,
            n_jobs=-1,
            verbosity=-1
        )
        
        # Train model with validation set for early stopping
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],  # Используем validation set для early stopping
            eval_metric='rmse',
            callbacks=[lgb.early_stopping(15), lgb.log_evaluation(0)]
        )
        
        # Evaluate on validation set (for monitoring during training)
        y_val_pred = self.model.predict(X_val)
        val_mae = mean_absolute_error(y_val, y_val_pred)
        val_mape = self._calculate_mape(y_val, y_val_pred)
        val_r2 = r2_score(y_val, y_val_pred)
        val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))
        
        # Evaluate on test set (honest evaluation - never seen during training)
        y_test_pred = self.model.predict(X_test)
        test_mae = mean_absolute_error(y_test, y_test_pred)
        test_mape = self._calculate_mape(y_test, y_test_pred)
        test_r2 = r2_score(y_test, y_test_pred)
        test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
        
        # Comprehensive metrics
        metrics = {
            # Dataset sizes
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'test_samples': len(X_test),
            
            # Validation metrics (used during training)
            'val_mae': val_mae,
            'val_mape': val_mape,
            'val_r2': val_r2,
            'val_rmse': val_rmse,
            
            # Test metrics (honest evaluation)
            'test_mae': test_mae,
            'test_mape': test_mape,
            'test_r2': test_r2,
            'test_rmse': test_rmse,
            
            # Legacy fields for backward compatibility
            'mae': test_mae,  # Используем test метрики как основные
            'mape': test_mape,
            'r2': test_r2,
            'rmse': test_rmse
        }
        
        logger.info("=== MODEL TRAINING RESULTS ===")
        logger.info(f"📊 VALIDATION METRICS (используется для early stopping):")
        logger.info(f"   MAE: {val_mae:.2f}, MAPE: {val_mape:.2f}%, R²: {val_r2:.4f}, RMSE: {val_rmse:.2f}")
        logger.info(f"")
        logger.info(f"🎯 TEST METRICS (честная оценка обобщающей способности):")
        logger.info(f"   MAE: {test_mae:.2f}, MAPE: {test_mape:.2f}%, R²: {test_r2:.4f}, RMSE: {test_rmse:.2f}")
        logger.info(f"")
        logger.info(f"📈 Разница между validation и test показывает склонность к переобучению")
        logger.info(f"   MAPE разница: {abs(val_mape - test_mape):.2f}% ({'переобучение' if val_mape < test_mape else 'недообучение'})")
        
        # Save model if requested
        if save_model:
            self._save_model(metrics)
            
        # Print feature importance
        feature_importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        logger.info("\n🔍 Top 5 most important features:")
        for _, row in feature_importance.head().iterrows():
            logger.info(f"  {row['feature']}: {row['importance']:.4f}")
        
        return self.model, metrics
    
    def forecast(self, branch_id: str, forecast_date: date, db: Session = None) -> Optional[float]:
        """
        Forecast sales for a specific branch and date
        
        Args:
            branch_id: Department/branch ID (UUID as string)
            forecast_date: Date to forecast
            db: Database session (will create one if not provided)
            
        Returns:
            Predicted sales amount or None if cannot forecast
        """
        if self.model is None:
            logger.error("Model not loaded. Please train the model first.")
            return None
        
        # Get database session
        if db is None:
            db = next(get_db())
        
        try:
            # Find the latest available sales data for this department
            latest_sales_query = db.query(
                SalesSummary.date
            ).filter(
                SalesSummary.department_id == branch_id
            ).order_by(SalesSummary.date.desc()).limit(1)
            
            latest_sales_date = latest_sales_query.first()
            
            if latest_sales_date is None:
                logger.warning(f"No sales data found for branch {branch_id}")
                return None
            
            # Возврат к оригинальной логике: используем fresh data для коротких прогнозов
            days_ahead = (forecast_date - latest_sales_date.date).days
            
            if days_ahead <= 7:
                # Short-term: используем традиционный подход с fresh data
                end_date = forecast_date - timedelta(days=1)
                start_date = end_date - timedelta(days=30)
                logger.info(f"Short-term forecast ({days_ahead} days ahead): using traditional approach")
            else:
                # Long-term: используем latest available data
                end_date = latest_sales_date.date
                start_date = end_date - timedelta(days=45)
                logger.info(f"Long-term forecast ({days_ahead} days ahead): using extended approach")
            
            # Query historical sales with department info
            sales_query = db.query(
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
            ).filter(
                and_(
                    SalesSummary.department_id == branch_id,
                    SalesSummary.date >= start_date,
                    SalesSummary.date <= end_date
                )
            ).order_by(SalesSummary.date)
            
            sales_data = sales_query.all()
            
            min_days_required = 14 if days_ahead <= 7 else 7
            if len(sales_data) < min_days_required:
                logger.warning(f"Insufficient historical data for branch {branch_id}. Found {len(sales_data)} days, need at least {min_days_required}.")
                return None
            
            # Create DataFrame
            df = pd.DataFrame([{
                'date': r.date,
                'total_sales': float(r.total_sales),
                'department_name': r.department_name,
                'department_code': r.department_code,
                'department_type': r.department_type,
                'segment_type': r.segment_type,
                'parent_id': str(r.parent_id) if r.parent_id else None
            } for r in sales_data])
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # Create feature vector using the same logic as TrainingDataService
            logger.info(f"Creating features for {forecast_date} with {len(df)} historical days")
            features = self._create_prediction_features(forecast_date, df)
            
            if not features:
                logger.error(f"Failed to create features for {forecast_date}")
                return None
            
            # Create DataFrame with features in correct order
            X = pd.DataFrame([features])[self.feature_columns]
            
            logger.info(f"Feature vector created with {len(features)} features")
            
            # Make prediction
            prediction = self.model.predict(X)[0]
            
            # Weekend boost correction (временная мера)
            forecast_datetime = pd.to_datetime(forecast_date)
            python_dow = forecast_datetime.dayofweek
            postgres_dow = (python_dow + 1) % 7
            
            if postgres_dow == 0 or postgres_dow == 6:  # Выходные
                weekend_boost = 1.4  # Увеличиваем на 40%
                prediction *= weekend_boost
                logger.info(f"Applied weekend boost: {weekend_boost}x for {forecast_date}")
            
            # Применяем временное сглаживание
            prediction = self._apply_temporal_smoothing(branch_id, forecast_date, prediction, db)
            
            # Ensure non-negative prediction
            prediction = max(0, prediction)
            
            logger.info(f"Forecast for branch {branch_id} on {forecast_date}: {prediction:.2f}")
            
            return float(prediction)
            
        except Exception as e:
            logger.error(f"Error during forecasting: {str(e)}")
            return None
    
    def _create_prediction_features(self, forecast_date: date, historical_df: pd.DataFrame) -> dict:
        """
        Create all 61 features for prediction using the same logic as TrainingDataService
        """
        forecast_datetime = pd.to_datetime(forecast_date)
        
        # Get the last row for department info
        dept_info = historical_df.iloc[-1]
        
        # Initialize features dictionary
        features = {}
        
        # 1. Time-based features (23 features)
        # ВАЖНО: Используем PostgreSQL совместимую нумерацию (0=Sunday, 1=Monday, ..., 6=Saturday)
        python_dow = forecast_datetime.dayofweek  # 0=Monday, ..., 6=Sunday
        postgres_dow = (python_dow + 1) % 7  # Конвертируем: 0=Sunday, 1=Monday, ..., 6=Saturday
        features['day_of_week'] = postgres_dow
        features['month'] = forecast_datetime.month
        features['day_of_month'] = forecast_datetime.day
        features['year'] = forecast_datetime.year
        # PostgreSQL логика: выходные = суббота (6) и воскресенье (0)
        features['is_weekend'] = 1 if postgres_dow == 0 or postgres_dow == 6 else 0
        # PostgreSQL логика: пятница = 5, понедельник = 1
        features['is_friday'] = 1 if postgres_dow == 5 else 0
        features['is_monday'] = 1 if postgres_dow == 1 else 0
        
        # Дополнительные weekend features для усиления эффекта
        features['is_saturday'] = 1 if postgres_dow == 6 else 0
        features['is_sunday'] = 1 if postgres_dow == 0 else 0
        features['weekend_multiplier'] = 1.2 if postgres_dow == 0 or postgres_dow == 6 else 1.0
        features['quarter'] = forecast_datetime.quarter
        features['is_quarter_start'] = 1 if forecast_datetime.is_quarter_start else 0
        features['is_quarter_end'] = 1 if forecast_datetime.is_quarter_end else 0
        features['week_of_year'] = forecast_datetime.isocalendar().week
        features['is_month_start'] = 1 if forecast_datetime.is_month_start else 0
        features['is_month_end'] = 1 if forecast_datetime.is_month_end else 0
        
        # Season features
        season = self._get_season(forecast_datetime.month)
        features['is_winter'] = 1 if season == 'winter' else 0
        features['is_spring'] = 1 if season == 'spring' else 0
        features['is_summer'] = 1 if season == 'summer' else 0
        features['is_autumn'] = 1 if season == 'autumn' else 0
        
        # Holiday features (Kazakhstan holidays)
        features['is_holiday'] = 1 if self._is_kazakhstan_holiday(forecast_datetime) else 0
        features['is_pre_holiday'] = 1 if self._is_pre_holiday(forecast_datetime) else 0
        features['is_post_holiday'] = 1 if self._is_post_holiday(forecast_datetime) else 0
        
        # Days from/to important dates
        new_year = pd.to_datetime(f"{forecast_datetime.year}-01-01")
        next_new_year = pd.to_datetime(f"{forecast_datetime.year + 1}-01-01")
        features['days_from_new_year'] = (forecast_datetime - new_year).days
        features['days_to_new_year'] = (next_new_year - forecast_datetime).days
        
        # 2. Rolling features (20 features)
        sales_values = historical_df['total_sales'].values
        
        # Rolling averages
        features['rolling_3d_avg_sales'] = np.mean(sales_values[-3:]) if len(sales_values) >= 3 else np.mean(sales_values)
        features['rolling_7d_avg_sales'] = np.mean(sales_values[-7:]) if len(sales_values) >= 7 else np.mean(sales_values)
        features['rolling_14d_avg_sales'] = np.mean(sales_values[-14:]) if len(sales_values) >= 14 else np.mean(sales_values)
        features['rolling_30d_avg_sales'] = np.mean(sales_values)
        
        # Rolling standard deviations
        features['rolling_3d_std_sales'] = np.std(sales_values[-3:]) if len(sales_values) >= 3 else 0
        features['rolling_7d_std_sales'] = np.std(sales_values[-7:]) if len(sales_values) >= 7 else 0
        features['rolling_14d_std_sales'] = np.std(sales_values[-14:]) if len(sales_values) >= 14 else 0
        
        # Rolling sums
        features['rolling_7d_sum_sales'] = np.sum(sales_values[-7:]) if len(sales_values) >= 7 else np.sum(sales_values)
        features['rolling_14d_sum_sales'] = np.sum(sales_values[-14:]) if len(sales_values) >= 14 else np.sum(sales_values)
        
        # Lag features
        features['lag_1d_sales'] = sales_values[-1] if len(sales_values) >= 1 else 0
        features['lag_2d_sales'] = sales_values[-2] if len(sales_values) >= 2 else features['lag_1d_sales']
        features['lag_7d_sales'] = sales_values[-7] if len(sales_values) >= 7 else features['lag_1d_sales']
        features['lag_14d_sales'] = sales_values[-14] if len(sales_values) >= 14 else features['lag_1d_sales']
        
        # Percentage changes
        if len(sales_values) >= 2 and sales_values[-2] != 0:
            features['pct_change_1d'] = (sales_values[-1] - sales_values[-2]) / sales_values[-2]
        else:
            features['pct_change_1d'] = 0
            
        if len(sales_values) >= 8 and sales_values[-8] != 0:
            features['pct_change_7d'] = (sales_values[-1] - sales_values[-8]) / sales_values[-8]
        else:
            features['pct_change_7d'] = 0
            
        if len(sales_values) >= 15 and sales_values[-15] != 0:
            features['pct_change_14d'] = (sales_values[-1] - sales_values[-15]) / sales_values[-15]
        else:
            features['pct_change_14d'] = 0
        
        # Rolling min/max
        features['rolling_7d_min_sales'] = np.min(sales_values[-7:]) if len(sales_values) >= 7 else np.min(sales_values)
        features['rolling_7d_max_sales'] = np.max(sales_values[-7:]) if len(sales_values) >= 7 else np.max(sales_values)
        
        # Sales momentum
        if len(sales_values) >= 14:
            features['sales_momentum_7d'] = np.mean(sales_values[-7:]) - np.mean(sales_values[-14:-7])
        else:
            features['sales_momentum_7d'] = 0
            
        if len(sales_values) >= 28:
            features['sales_momentum_14d'] = np.mean(sales_values[-14:]) - np.mean(sales_values[-28:-14])
        else:
            features['sales_momentum_14d'] = 0
        
        # 3. Department features (18 features)
        # Department type
        features['is_department'] = 1 if dept_info.get('department_type') == 'DEPARTMENT' else 0
        features['is_organization'] = 1 if dept_info.get('department_type') == 'ORGANIZATION' else 0
        
        # Segment type features
        segment_type = dept_info.get('segment_type', '').lower() if dept_info.get('segment_type') else ''
        features['is_coffeehouse'] = 1 if 'кофейня' in segment_type or 'coffee' in segment_type else 0
        features['is_restaurant'] = 1 if 'ресторан' in segment_type or 'restaurant' in segment_type else 0
        features['is_confectionery'] = 1 if 'кондитерская' in segment_type or 'confectionery' in segment_type else 0
        features['is_food_court'] = 1 if 'фуд-корт' in segment_type or 'food court' in segment_type else 0
        features['is_store'] = 1 if 'магазин' in segment_type or 'store' in segment_type else 0
        features['is_fast_food'] = 1 if 'фаст-фуд' in segment_type or 'fast food' in segment_type else 0
        features['is_bakery'] = 1 if 'пекарня' in segment_type or 'bakery' in segment_type else 0
        features['is_cafe'] = 1 if 'кафе' in segment_type or 'cafe' in segment_type else 0
        features['is_bar'] = 1 if 'бар' in segment_type or 'bar' in segment_type else 0
        
        # Department hierarchy
        features['has_parent'] = 1 if dept_info.get('parent_id') is not None else 0
        
        # Department size indicators
        dept_name = dept_info.get('department_name', '').lower()
        features['dept_name_length'] = len(dept_name)
        features['has_plaza_in_name'] = 1 if 'plaza' in dept_name or 'плаза' in dept_name else 0
        features['has_center_in_name'] = 1 if 'center' in dept_name or 'центр' in dept_name else 0
        features['has_mall_in_name'] = 1 if 'mall' in dept_name or 'мол' in dept_name or 'мол' in dept_name else 0
        
        # Location features
        features['is_almaty'] = 1 if 'алмат' in dept_name or 'almaty' in dept_name else 0
        features['is_astana'] = 1 if 'астан' in dept_name or 'astana' in dept_name else 0
        features['is_shymkent'] = 1 if 'шымкент' in dept_name or 'shymkent' in dept_name else 0
        
        return features
    
    def _get_season(self, month: int) -> str:
        """Get season from month"""
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'spring'
        elif month in [6, 7, 8]:
            return 'summer'
        else:
            return 'autumn'
    
    def _is_kazakhstan_holiday(self, date_val) -> bool:
        """Check if date is a Kazakhstan holiday"""
        month_day = (date_val.month, date_val.day)
        holidays = [
            (1, 1), (1, 2),  # New Year
            (3, 8),          # International Women's Day
            (3, 21), (3, 22), (3, 23), (3, 24),  # Nauryz
            (5, 1),          # Unity Day
            (5, 7),          # Defender of the Fatherland Day
            (5, 9),          # Victory Day
            (7, 6),          # Capital City Day
            (8, 30),         # Constitution Day
            (12, 1),         # First President Day
            (12, 16), (12, 17), (12, 18)  # Independence Day
        ]
        return month_day in holidays
    
    def _is_pre_holiday(self, date_val) -> bool:
        """Check if date is before a holiday"""
        next_day = date_val + timedelta(days=1)
        return self._is_kazakhstan_holiday(next_day)
    
    def _is_post_holiday(self, date_val) -> bool:
        """Check if date is after a holiday"""
        prev_day = date_val - timedelta(days=1)
        return self._is_kazakhstan_holiday(prev_day)
    
    def _calculate_mape(self, y_true, y_pred) -> float:
        """Calculate Mean Absolute Percentage Error"""
        mask = y_true != 0
        return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
    
    def _apply_temporal_smoothing(self, branch_id: str, forecast_date: date, raw_prediction: float, db: Session, 
                                  max_change_threshold: float = 0.5) -> float:
        """
        Применить временное сглаживание для предотвращения аномальных скачков
        
        Args:
            branch_id: ID филиала
            forecast_date: Дата прогноза
            raw_prediction: Исходный прогноз модели
            db: Сессия БД
            
        Returns:
            Сглаженный прогноз
        """
        try:
            # Определяем день недели для поиска исторических данных
            forecast_datetime = pd.to_datetime(forecast_date)
            python_dow = forecast_datetime.dayofweek
            postgres_dow = (python_dow + 1) % 7
            
            # Ищем продажи за последние 4 недели для расчета базовой линии
            recent_sales = db.query(SalesSummary.total_sales, SalesSummary.date).filter(
                and_(
                    SalesSummary.department_id == branch_id,
                    SalesSummary.date >= forecast_date - timedelta(days=28),  # 4 недели назад
                    SalesSummary.date < forecast_date
                )
            ).order_by(SalesSummary.date.desc()).all()
            
            # Фильтруем по тому же дню недели
            same_weekday_sales = []
            for row in recent_sales:
                row_datetime = pd.to_datetime(row.date)
                row_python_dow = row_datetime.dayofweek
                row_postgres_dow = (row_python_dow + 1) % 7
                if row_postgres_dow == postgres_dow:
                    same_weekday_sales.append(float(row.total_sales))
            
            if not same_weekday_sales:
                logger.info(f"No historical data for smoothing {forecast_date}, using raw prediction")
                return raw_prediction
            
            # Вычисляем среднее и стандартное отклонение за последние недели
            historical_values = same_weekday_sales
            avg_historical = np.mean(historical_values)
            std_historical = np.std(historical_values) if len(historical_values) > 1 else avg_historical * 0.2
            
            # Проверяем, является ли прогноз аномальным (больше чем ±threshold от среднего)
            min_allowed = avg_historical * (1 - max_change_threshold)
            max_allowed = avg_historical * (1 + max_change_threshold)
            
            if raw_prediction < min_allowed or raw_prediction > max_allowed:
                # Применяем сглаживание
                if raw_prediction > max_allowed:
                    smoothed_prediction = max_allowed
                    logger.info(f"Smoothing high anomaly: {raw_prediction:.0f} -> {smoothed_prediction:.0f} (max allowed: {max_allowed:.0f})")
                else:
                    smoothed_prediction = min_allowed
                    logger.info(f"Smoothing low anomaly: {raw_prediction:.0f} -> {smoothed_prediction:.0f} (min allowed: {min_allowed:.0f})")
                
                return smoothed_prediction
            else:
                logger.info(f"Prediction within normal range: {raw_prediction:.0f} (range: {min_allowed:.0f} - {max_allowed:.0f})")
                return raw_prediction
                
        except Exception as e:
            logger.error(f"Error in temporal smoothing: {str(e)}")
            return raw_prediction
    
    def _save_model(self, metrics=None):
        """Save trained model to disk"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        model_data = {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'version': '2.0',  # Обновляем версию для train/val/test split
            'trained_at': datetime.now().isoformat(),
            'training_metrics': metrics  # Теперь включает validation и test метрики
        }
        
        joblib.dump(model_data, self.model_path)
        logger.info(f"✅ Model v2.0 saved to {self.model_path}")
        logger.info(f"📊 Saved metrics include both validation and test performance")
    
    def _load_model(self):
        """Load model from disk if exists"""
        if os.path.exists(self.model_path):
            try:
                model_data = joblib.load(self.model_path)
                self.model = model_data['model']
                self.feature_columns = model_data['feature_columns']
                self._training_metrics = model_data.get('training_metrics', None)
                logger.info(f"Model loaded from {self.model_path}")
                logger.info(f"Model version: {model_data.get('version', 'unknown')}")
                logger.info(f"Trained at: {model_data.get('trained_at', 'unknown')}")
                if self._training_metrics:
                    logger.info(f"Training metrics: MAE={self._training_metrics.get('mae', 'N/A'):.2f}, MAPE={self._training_metrics.get('mape', 'N/A'):.2f}%")
            except Exception as e:
                logger.error(f"Error loading model: {str(e)}")
                self.model = None
                self.feature_columns = None
                self._training_metrics = None
        else:
            logger.info(f"No saved model found at {self.model_path}")
            self._training_metrics = None
    
    def retrain_model(self, db: Session) -> Dict[str, float]:
        """
        Retrain model with latest data
        
        This is a convenience method that calls train_model with default parameters
        """
        logger.info("Retraining model with latest data...")
        metrics = self.train_model(db, save_model=True)
        # Обновляем метрики в памяти после переобучения
        self._training_metrics = metrics
        return metrics
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model"""
        if self.model is None:
            return {'status': 'not_loaded', 'model_path': self.model_path}
        
        info = {
            'status': 'loaded',
            'model_path': self.model_path,
            'model_type': type(self.model).__name__,
            'n_features': len(self.feature_columns) if self.feature_columns else 0,
            'feature_names': self.feature_columns
        }
        
        # Добавляем метрики обучения, если они есть
        if hasattr(self, '_training_metrics') and self._training_metrics:
            info['training_metrics'] = self._training_metrics
            
        return info
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance as a dictionary"""
        if self.model is None or self.feature_columns is None:
            return {}
        
        feature_importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        return dict(zip(feature_importance['feature'], feature_importance['importance']))


# Singleton instance
_forecaster_instance = None


def get_forecaster_agent() -> SalesForecasterAgent:
    """Get singleton instance of SalesForecasterAgent"""
    global _forecaster_instance
    if _forecaster_instance is None:
        _forecaster_instance = SalesForecasterAgent()
    return _forecaster_instance


def reset_forecaster_agent():
    """Reset singleton instance - useful for testing or reloading"""
    global _forecaster_instance
    _forecaster_instance = None
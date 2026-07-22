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
import threading
from typing import Optional, Dict, Any, Tuple

from ..services.training_service import TrainingDataService
from ..services.forecast_metrics import wape, median_ape
from ..services import kz_calendar
from ..models.branch import SalesSummary, Department
from ..config import settings
from ..db import get_db

logger = logging.getLogger(__name__)


class SalesForecasterAgent:
    """Agent for training and using LightGBM sales forecasting model"""
    
    SEGMENT_MODELS_DIR = "models/segments"
    MIN_SEGMENT_SAMPLES = 500  # below this, fall back to the global model

    def __init__(self, model_path: str = "models/lgbm_model.pkl"):
        self.model_path = model_path
        self.model = None
        self.feature_columns = None
        self._training_metrics = None
        self._target_transform = "identity"
        # Segment-specific models (one LGBMRegressor per segment_type).
        # Populated by train_segmented_models() and loaded by _load_model().
        self.segment_models: Dict[str, Any] = {}
        self.segment_metrics: Dict[str, Dict[str, Any]] = {}
        self.segment_target_transforms: Dict[str, str] = {}
        self._load_model()
        self._load_segment_models()

    def _normalize_segment(self, segment_type: Optional[str]) -> Optional[str]:
        """Map raw segment_type values to canonical bucket keys used as filenames."""
        if not segment_type:
            return None
        s = segment_type.strip().lower()
        if not s:
            return None
        if 'кофейня' in s or 'coffee' in s:
            return 'coffeehouse'
        if 'фуд-корт' in s or 'food court' in s or 'food_court' in s:
            return 'food_court'
        if 'ресторан' in s or 'restaurant' in s:
            return 'restaurant'
        # Use the raw value if it's already canonical
        if s in ('coffeehouse', 'food_court', 'restaurant'):
            return s
        return None

    def predict(self, X: pd.DataFrame, segment_type: Optional[str] = None) -> np.ndarray:
        """Predict, applying inverse target transform if model was trained on log1p.

        If a per-segment model exists for `segment_type`, it is used; otherwise
        falls back to the global model. Each model carries its own target
        transform metadata so the inverse is applied correctly.
        """
        seg_key = self._normalize_segment(segment_type)
        if seg_key and seg_key in self.segment_models:
            model = self.segment_models[seg_key]
            transform = self.segment_target_transforms.get(seg_key, "identity")
        else:
            model = self.model
            transform = getattr(self, "_target_transform", "identity")

        raw = model.predict(X)
        if transform == "log1p":
            raw = np.expm1(raw)
            raw = np.maximum(raw, 0.0)
        return raw
    
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
            # Pre-split данные: список фичей статичен (staticmethod), сессия БД
            # не нужна (раньше здесь создавался и утекал next(get_db()) — это
            # мешало и юнит-тестам контура деплоя, аудит P0-1d)
            self.feature_columns = TrainingDataService.get_feature_columns()
            target_column = 'total_sales'
        
        # Prepare datasets — train in log1p space to balance loss across
        # vastly different sales scales (500..3M ₸/day). Metrics computed
        # on the original scale via expm1 so they remain interpretable.
        self._target_transform = "log1p"

        X_train = train_df[self.feature_columns]
        y_train = train_df[target_column]
        X_val = val_df[self.feature_columns]
        y_val = val_df[target_column]
        X_test = test_df[self.feature_columns]
        y_test = test_df[target_column]

        y_train_t = np.log1p(y_train)
        y_val_t = np.log1p(y_val)

        logger.info(f"Dataset sizes - Train: {len(X_train)}, Validation: {len(X_val)}, Test: {len(X_test)}")
        logger.info(f"Target transform: {self._target_transform}")

        self.model = lgb.LGBMRegressor(
            n_estimators=500,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            random_state=42,
            n_jobs=-1,
            verbosity=-1,
        )

        self.model.fit(
            X_train, y_train_t,
            eval_set=[(X_val, y_val_t)],
            eval_metric='mae',
            callbacks=[lgb.early_stopping(20), lgb.log_evaluation(0)],
        )

        # Predictions back to original scale
        y_val_pred = np.maximum(np.expm1(self.model.predict(X_val)), 0.0)
        val_mae = mean_absolute_error(y_val, y_val_pred)
        val_mape = self._calculate_mape(y_val, y_val_pred)
        val_r2 = r2_score(y_val, y_val_pred)
        val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))

        y_test_pred = np.maximum(np.expm1(self.model.predict(X_test)), 0.0)
        test_mae = mean_absolute_error(y_test, y_test_pred)
        test_mape = self._calculate_mape(y_test, y_test_pred)
        test_r2 = r2_score(y_test, y_test_pred)
        test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
        
        # WAPE/MedianAPE — headline-метрики (аудит P1-7): MAPE на смешанных
        # масштабах точек взрывается на малых знаменателях
        val_wape = wape(y_val, y_val_pred)
        val_median_ape = median_ape(y_val, y_val_pred)
        test_wape = wape(y_test, y_test_pred)
        test_median_ape = median_ape(y_test, y_test_pred)

        # Comprehensive metrics
        metrics = {
            # Dataset sizes
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'test_samples': len(X_test),

            # Validation metrics (used during training)
            'val_mae': val_mae,
            'val_mape': val_mape,
            'val_wape': val_wape,
            'val_median_ape': val_median_ape,
            'val_r2': val_r2,
            'val_rmse': val_rmse,

            # Test metrics (honest evaluation)
            'test_mae': test_mae,
            'test_mape': test_mape,
            'test_wape': test_wape,
            'test_median_ape': test_median_ape,
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
        logger.info(f"   WAPE: {val_wape:.2f}%, MedAPE: {val_median_ape:.2f}%, MAPE: {val_mape:.2f}%, MAE: {val_mae:.2f}, R²: {val_r2:.4f}")
        logger.info(f"")
        logger.info(f"🎯 TEST METRICS (честная оценка обобщающей способности):")
        logger.info(f"   WAPE: {test_wape:.2f}%, MedAPE: {test_median_ape:.2f}%, MAPE: {test_mape:.2f}%, MAE: {test_mae:.2f}, R²: {test_r2:.4f}")
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
    
    def forecast(
        self,
        branch_id: str,
        forecast_date: date,
        db: Session = None,
        save_to_db: bool = True,
    ) -> Optional[float]:
        """
        Forecast sales for a specific branch and date

        Args:
            branch_id: Department/branch ID (UUID as string)
            forecast_date: Date to forecast
            db: Database session (will create one if not provided)
            save_to_db: If True, UPSERT result into forecasts table for monitoring.
                        Set False from backtest/analytical scripts.

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
            
            # Пункт B: на инференсе история строится в той же базе, что и таргет модели
            # (флаг REVENUE_BASIS), иначе лаги/rolling разойдутся с paid-моделью на ~10%.
            # df-колонка остаётся 'total_sales'. NULL-paid дни исключаем (как в обучении).
            use_paid = settings.REVENUE_BASIS == 'paid'
            revenue_col = SalesSummary.total_paid if use_paid else SalesSummary.total_sales

            # Query historical sales with department info (incl. operational metadata)
            sales_query = db.query(
                SalesSummary.date,
                revenue_col.label('total_sales'),
                Department.name.label('department_name'),
                Department.code.label('department_code'),
                Department.type.label('department_type'),
                Department.segment_type.label('segment_type'),
                Department.parent_id.label('parent_id'),
                Department.brand.label('brand'),
                Department.location_type.label('location_type'),
                Department.tourist_traffic_dependent.label('tourist_traffic_dependent'),
                Department.is_24_7.label('is_24_7_flag'),
                Department.opening_hour.label('opening_hour'),
                Department.closing_hour.label('closing_hour'),
                Department.seasonality_intensity.label('seasonality_intensity'),
                Department.opened_date.label('opened_date'),
                Department.season_start_month.label('season_start_month'),
                Department.season_end_month.label('season_end_month'),
            ).join(
                Department,
                SalesSummary.department_id == Department.id
            ).filter(
                and_(
                    SalesSummary.department_id == branch_id,
                    SalesSummary.date >= start_date,
                    SalesSummary.date <= end_date,
                    revenue_col.isnot(None) if use_paid else True
                )
            ).order_by(SalesSummary.date)

            sales_data = sales_query.all()

            min_days_required = 14 if days_ahead <= 7 else 7
            if len(sales_data) < min_days_required:
                logger.warning(f"Insufficient historical data for branch {branch_id}. Found {len(sales_data)} days, need at least {min_days_required}.")
                return None

            # Create DataFrame (carries department metadata into feature builder)
            df = pd.DataFrame([{
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
                'is_24_7_flag': bool(r.is_24_7_flag),
                'opening_hour': r.opening_hour,
                'closing_hour': r.closing_hour,
                'seasonality_intensity': r.seasonality_intensity or 'none',
                'opened_date': r.opened_date,
                'season_start_month': r.season_start_month,
                'season_end_month': r.season_end_month,
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
            
            # Make prediction (predict() applies inverse target transform)
            # Pass segment_type so the dispatcher picks the per-segment model
            # if one exists, otherwise falls back to the global model.
            segment_type = df.iloc[-1].get('segment_type')
            prediction = float(self.predict(X, segment_type=segment_type)[0])

            # Применяем временное сглаживание
            prediction = self._apply_temporal_smoothing(branch_id, forecast_date, prediction, db)
            
            # Ensure non-negative prediction
            prediction = max(0, prediction)

            logger.info(f"Forecast for branch {branch_id} on {forecast_date}: {prediction:.2f}")

            if save_to_db:
                self._upsert_forecast(db, branch_id, forecast_date, float(prediction))

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
        
        # Holiday features (единый kz_calendar, P1-3 — идентично обучению)
        features['is_holiday'] = 1 if kz_calendar.is_holiday(forecast_datetime) else 0
        features['is_pre_holiday'] = 1 if kz_calendar.is_pre_holiday(forecast_datetime) else 0
        features['is_post_holiday'] = 1 if kz_calendar.is_post_holiday(forecast_datetime) else 0
        features['is_ramadan'] = 1 if kz_calendar.is_ramadan(forecast_datetime) else 0
        features['is_payday_window'] = 1 if kz_calendar.is_payday_window(forecast_datetime) else 0
        
        # Days from/to important dates
        new_year = pd.to_datetime(f"{forecast_datetime.year}-01-01")
        next_new_year = pd.to_datetime(f"{forecast_datetime.year + 1}-01-01")
        features['days_from_new_year'] = (forecast_datetime - new_year).days
        features['days_to_new_year'] = (next_new_year - forecast_datetime).days
        
        # 2. Rolling features (20 features)
        sales_values = historical_df['total_sales'].values
        
        # Rolling averages — окна [-N:] (совпадает с train past_sales.rolling(N)
        # при min_periods=1: если истории <N, [-N:] вернёт всё имеющееся).
        # P1-6: rolling_30d раньше усреднял ВСЮ историю (до 45 дней в long-term
        # запросе), а train — последние 30 → расхождение фичи.
        features['rolling_3d_avg_sales'] = np.mean(sales_values[-3:])
        features['rolling_7d_avg_sales'] = np.mean(sales_values[-7:])
        features['rolling_14d_avg_sales'] = np.mean(sales_values[-14:])
        features['rolling_30d_avg_sales'] = np.mean(sales_values[-30:])

        # Rolling std — ddof=1 как pandas .std() в train (P1-6: было np.std
        # ddof=0). std одного значения → 0 (train fillna(0) после rolling.std()).
        def _std(window):
            return float(np.std(window, ddof=1)) if len(window) >= 2 else 0.0
        features['rolling_3d_std_sales'] = _std(sales_values[-3:])
        features['rolling_7d_std_sales'] = _std(sales_values[-7:])
        features['rolling_14d_std_sales'] = _std(sales_values[-14:])
        
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
        
        # Sales momentum — частичные окна как в train (min_periods=1): пустое
        # окно → 0, иначе mean доступного. P1-6: раньше был жёсткий отсёк
        # (0 при <14/<28 дней), а train считал частичное → расхождение на
        # подразделениях с короткой историей (14-27 дней).
        def _wmean(arr):
            return float(np.mean(arr)) if len(arr) > 0 else 0.0
        features['sales_momentum_7d'] = _wmean(sales_values[-7:]) - _wmean(sales_values[-14:-7])
        features['sales_momentum_14d'] = _wmean(sales_values[-14:]) - _wmean(sales_values[-28:-14])
        
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

        # Outlier flag — at inference we forecast a "normal" day, so flag=0.
        # The flag exists primarily during training so the model isn't forced
        # to average extreme days (paydays, promos, IQR-outliers) into the
        # baseline. Known calendar anomalies (holidays) are already covered
        # by `is_holiday` / `is_pre_holiday` / `is_post_holiday`.
        features['is_outlier_day'] = 0

        # === Operational metadata features ===
        # Must mirror TrainingDataService._add_operational_features so training
        # and inference produce identical feature columns.
        OPERATIONAL_BRANDS = ['tary', 'sandyq', 'madlen', 'shopan']
        OPERATIONAL_LOCATIONS = [
            'city_center', 'mall', 'business_district',
            'resort_mountain', 'resort_lake', 'visit_center', 'other'
        ]
        SEASONALITY_SCORE = {'none': 0, 'low': 1, 'medium': 2, 'high': 3}

        # Brand one-hot
        brand_raw = dept_info.get('brand') or ''
        brand_lower = str(brand_raw).strip().lower()
        for b in OPERATIONAL_BRANDS:
            features[f'is_brand_{b}'] = 1 if brand_lower == b else 0

        # Location type one-hot
        loc_raw = dept_info.get('location_type') or ''
        loc_lower = str(loc_raw).strip().lower()
        for lt in OPERATIONAL_LOCATIONS:
            features[f'is_loc_{lt}'] = 1 if loc_lower == lt else 0

        # Operational booleans
        features['is_tourist_dependent'] = 1 if dept_info.get('tourist_traffic_dependent') else 0
        is_24_7_flag = bool(dept_info.get('is_24_7_flag'))
        features['is_24_7'] = 1 if is_24_7_flag else 0

        # Working hours count
        if is_24_7_flag:
            features['working_hours_count'] = 24
        else:
            o = dept_info.get('opening_hour')
            c = dept_info.get('closing_hour')
            if o is None or c is None or pd.isna(o) or pd.isna(c):
                features['working_hours_count'] = 12
            else:
                o, c = int(o), int(c)
                features['working_hours_count'] = (c - o) if c > o else (24 - o + c)

        # Days since opening
        opened = dept_info.get('opened_date')
        if opened is None or pd.isna(opened):
            features['days_since_opening'] = -1
            features['is_new_department'] = 0
        else:
            opened_ts = pd.to_datetime(opened)
            days_since = (forecast_datetime - opened_ts).days
            features['days_since_opening'] = max(-1, min(int(days_since), 1825))
            features['is_new_department'] = 1 if 0 <= days_since < 90 else 0

        # Seasonality
        intensity = (dept_info.get('seasonality_intensity') or 'none').strip().lower()
        features['seasonality_score'] = SEASONALITY_SCORE.get(intensity, 0)

        s_start = dept_info.get('season_start_month')
        s_end = dept_info.get('season_end_month')
        if s_start is None or s_end is None or pd.isna(s_start) or pd.isna(s_end):
            features['is_in_season'] = 1  # no season data → assume always in-season
        else:
            s_start, s_end = int(s_start), int(s_end)
            month = forecast_datetime.month
            if s_start <= s_end:
                features['is_in_season'] = 1 if (s_start <= month <= s_end) else 0
            else:
                # wrap-around (e.g. Nov-Mar season)
                features['is_in_season'] = 1 if (month >= s_start or month <= s_end) else 0

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
    
    # Праздничные методы делегируют в единый kz_calendar (P1-3) — устраняет
    # прежнее расхождение с обучением (Наурыз 21-24 vs 21-23, без Курбан-айта).
    def _is_kazakhstan_holiday(self, date_val) -> bool:
        return kz_calendar.is_holiday(date_val)

    def _is_pre_holiday(self, date_val) -> bool:
        return kz_calendar.is_pre_holiday(date_val)

    def _is_post_holiday(self, date_val) -> bool:
        return kz_calendar.is_post_holiday(date_val)
    
    def _calculate_mape(self, y_true, y_pred) -> float:
        """Calculate Mean Absolute Percentage Error"""
        mask = y_true != 0
        return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

    def _upsert_forecast(
        self,
        db: Session,
        branch_id: str,
        forecast_date: date,
        predicted_amount: float,
    ) -> None:
        """UPSERT prediction into forecasts table for monitoring sweep."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from ..models.branch import Forecast

        try:
            model_version = str(getattr(self, "_trained_at", "unknown") or "unknown")
            # Горизонт на момент создания прогноза (Фаза 1.1): t+1 и t+7 на одну
            # дату хранятся раздельно — деградация по горизонту измерима.
            # Прошлые даты (например, /comparison) получают 0.
            horizon_days = max(0, (forecast_date - date.today()).days)

            stmt = pg_insert(Forecast).values(
                branch_id=str(branch_id),
                forecast_date=forecast_date,
                predicted_amount=predicted_amount,
                model_version=model_version,
                horizon_days=horizon_days,
            ).on_conflict_do_update(
                index_elements=["branch_id", "forecast_date", "horizon_days"],
                set_={
                    "predicted_amount": predicted_amount,
                    "model_version": model_version,
                    "created_at": datetime.utcnow(),
                },
            )
            db.execute(stmt)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to UPSERT forecast for {branch_id}/{forecast_date}: {e}")
            db.rollback()
    
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
            
            # Базовая линия сглаживания — в той же базе выручки, что и прогноз (флаг REVENUE_BASIS).
            _use_paid = settings.REVENUE_BASIS == 'paid'
            _revenue_col = SalesSummary.total_paid if _use_paid else SalesSummary.total_sales
            # Ищем продажи за последние 4 недели для расчета базовой линии
            recent_sales = db.query(_revenue_col.label('total_sales'), SalesSummary.date).filter(
                and_(
                    SalesSummary.department_id == branch_id,
                    SalesSummary.date >= forecast_date - timedelta(days=28),  # 4 недели назад
                    SalesSummary.date < forecast_date,
                    _revenue_col.isnot(None) if _use_paid else True
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
    
    def train_segmented_models(
        self,
        df: pd.DataFrame,
        val_size: float = 0.15,
        test_size: float = 0.15,
        save: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Train one LightGBM model per `segment_type` on its slice of the data.

        Why segmenting:
            A single model on 500..3M ₸/day scales is dominated by large
            departments under RMSE/MAE loss. Stage-2 retraining proved that
            adding fresh data alone shrinks the in/out-of-sample gap by
            <0.2 п.п. — the bottleneck is structural. Per-segment models
            let each one optimize its own scale and weekly pattern.

        Strategy:
            - Use the same chronological train/val/test split as the global
              pipeline, but applied within each segment.
            - log1p target transform for all (proven win in stage 3.1).
            - Segments with fewer than MIN_SEGMENT_SAMPLES samples are
              skipped — the global model handles them at inference time.

        Returns:
            Dict[segment_key, metrics_dict] for each trained segment.
        """
        if self.feature_columns is None:
            from ..db import get_db
            from ..services.training_service import TrainingDataService
            temp_db = next(get_db())
            self.feature_columns = TrainingDataService(temp_db).get_feature_columns()

        target_column = 'total_sales'
        df = df.sort_values(['date']).reset_index(drop=True)

        # Bucket departments into canonical segment keys
        df['_segment_key'] = df['segment_type'].apply(self._normalize_segment)

        per_segment_metrics: Dict[str, Dict[str, Any]] = {}
        self.segment_models = {}
        self.segment_target_transforms = {}

        for seg_key in sorted(df['_segment_key'].dropna().unique()):
            seg_df = df[df['_segment_key'] == seg_key].copy()
            if len(seg_df) < self.MIN_SEGMENT_SAMPLES:
                logger.info(
                    f"Skipping segment '{seg_key}': only {len(seg_df)} samples "
                    f"(< {self.MIN_SEGMENT_SAMPLES})"
                )
                continue

            seg_df = seg_df.sort_values('date').reset_index(drop=True)
            train_size_frac = 1 - val_size - test_size
            train_split = int(len(seg_df) * train_size_frac)
            val_split = int(len(seg_df) * (train_size_frac + val_size))

            train_df = seg_df.iloc[:train_split]
            val_df = seg_df.iloc[train_split:val_split]
            test_df = seg_df.iloc[val_split:]

            X_train = train_df[self.feature_columns]
            y_train = train_df[target_column]
            X_val = val_df[self.feature_columns]
            y_val = val_df[target_column]
            X_test = test_df[self.feature_columns]
            y_test = test_df[target_column]

            y_train_t = np.log1p(y_train)
            y_val_t = np.log1p(y_val)

            model = lgb.LGBMRegressor(
                n_estimators=500,
                learning_rate=0.05,
                max_depth=6,
                num_leaves=31,
                random_state=42,
                n_jobs=-1,
                verbosity=-1,
            )
            model.fit(
                X_train, y_train_t,
                eval_set=[(X_val, y_val_t)],
                eval_metric='mae',
                callbacks=[lgb.early_stopping(20), lgb.log_evaluation(0)],
            )

            y_val_pred = np.maximum(np.expm1(model.predict(X_val)), 0.0)
            y_test_pred = np.maximum(np.expm1(model.predict(X_test)), 0.0)

            metrics = {
                'segment': seg_key,
                'train_samples': len(X_train),
                'val_samples': len(X_val),
                'test_samples': len(X_test),
                'val_mae': mean_absolute_error(y_val, y_val_pred),
                'val_mape': self._calculate_mape(y_val, y_val_pred),
                'val_r2': r2_score(y_val, y_val_pred),
                'test_mae': mean_absolute_error(y_test, y_test_pred),
                'test_mape': self._calculate_mape(y_test, y_test_pred),
                'test_r2': r2_score(y_test, y_test_pred),
            }
            per_segment_metrics[seg_key] = metrics
            self.segment_models[seg_key] = model
            self.segment_target_transforms[seg_key] = 'log1p'

            logger.info(
                f"[{seg_key}] train={len(X_train)}, val={len(X_val)}, test={len(X_test)}"
                f" → val MAPE {metrics['val_mape']:.2f}%, "
                f"test MAPE {metrics['test_mape']:.2f}%, R² {metrics['test_r2']:.3f}"
            )

            if save:
                self._save_segment_model(seg_key, model, metrics)

        self.segment_metrics = per_segment_metrics
        return per_segment_metrics

    def _save_segment_model(self, seg_key: str, model, metrics: Dict[str, Any]) -> None:
        os.makedirs(self.SEGMENT_MODELS_DIR, exist_ok=True)
        path = os.path.join(self.SEGMENT_MODELS_DIR, f"{seg_key}.pkl")
        joblib.dump({
            'model': model,
            'feature_columns': self.feature_columns,
            'segment': seg_key,
            'trained_at': datetime.now().isoformat(),
            'training_metrics': metrics,
            'target_transform': 'log1p',
            'version': 'segment-1.0',
        }, path)
        logger.info(f"Segment model saved: {path}")

    def _load_segment_models(self) -> None:
        """Load all per-segment models from SEGMENT_MODELS_DIR."""
        self.segment_models = {}
        self.segment_target_transforms = {}
        self.segment_metrics = {}
        if not os.path.isdir(self.SEGMENT_MODELS_DIR):
            logger.info(f"No segment models directory at {self.SEGMENT_MODELS_DIR}")
            return
        for fname in os.listdir(self.SEGMENT_MODELS_DIR):
            if not fname.endswith('.pkl'):
                continue
            seg_key = fname[:-4]
            try:
                data = joblib.load(os.path.join(self.SEGMENT_MODELS_DIR, fname))
                self.segment_models[seg_key] = data['model']
                self.segment_target_transforms[seg_key] = data.get('target_transform', 'identity')
                self.segment_metrics[seg_key] = data.get('training_metrics', {})
                logger.info(
                    f"Loaded segment model '{seg_key}' "
                    f"(trained {data.get('trained_at', 'unknown')})"
                )
            except Exception as e:
                logger.error(f"Failed to load segment model {fname}: {e}")

    def _save_model(self, metrics=None):
        """Save trained model to disk"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

        model_data = {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'version': '2.1',
            'trained_at': datetime.now().isoformat(),
            'training_metrics': metrics,
            'target_transform': getattr(self, '_target_transform', 'identity'),
        }

        joblib.dump(model_data, self.model_path)
        logger.info(f"Model v2.1 saved to {self.model_path}")
    
    def _load_model(self):
        """Load model from disk if exists"""
        if os.path.exists(self.model_path):
            try:
                model_data = joblib.load(self.model_path)
                self.model = model_data['model']
                self.feature_columns = model_data['feature_columns']
                self._training_metrics = model_data.get('training_metrics', None)
                self._trained_at = model_data.get('trained_at', 'unknown')
                self._target_transform = model_data.get('target_transform', 'identity')
                logger.info(f"Model loaded from {self.model_path}")
                logger.info(f"Model version: {model_data.get('version', 'unknown')}")
                logger.info(f"Trained at: {self._trained_at}")
                logger.info(f"Target transform: {self._target_transform}")
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
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model"""
        if self.model is None and not self.segment_models:
            return {'status': 'not_loaded', 'model_path': self.model_path}

        info = {
            'status': 'loaded',
            'model_path': self.model_path,
            'model_type': type(self.model).__name__ if self.model else None,
            'n_features': len(self.feature_columns) if self.feature_columns else 0,
            'feature_names': self.feature_columns,
            'trained_at': getattr(self, '_trained_at', 'unknown'),
            'target_transform': getattr(self, '_target_transform', 'identity'),
            'segment_models': sorted(self.segment_models.keys()),
            'segment_metrics': self.segment_metrics,
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
_forecaster_lock = threading.Lock()


def get_forecaster_agent() -> SalesForecasterAgent:
    """Get singleton instance of SalesForecasterAgent (thread-safe)."""
    global _forecaster_instance
    if _forecaster_instance is None:
        with _forecaster_lock:
            if _forecaster_instance is None:
                _forecaster_instance = SalesForecasterAgent()
    return _forecaster_instance


def reload_forecaster_agent() -> SalesForecasterAgent:
    """Перечитать модель с диска и атомарно подменить синглтон.

    Вызывается после деплоя новой модели (auto_retrain): без этого serving
    работал бы на старой in-memory модели до рестарта контейнера (аудит P0-1c).
    Новый агент собирается полностью (модель + feature_columns + transform)
    ДО подмены ссылки, поэтому конкурентные запросы видят либо старый, либо
    новый агент целиком — никогда полусобранный.
    """
    global _forecaster_instance
    new_agent = SalesForecasterAgent()
    with _forecaster_lock:
        _forecaster_instance = new_agent
    logger.info(
        f"Forecaster singleton reloaded (trained_at={getattr(new_agent, '_trained_at', 'unknown')})"
    )
    return new_agent


def reset_forecaster_agent():
    """Reset singleton instance - useful for testing or reloading"""
    global _forecaster_instance
    _forecaster_instance = None
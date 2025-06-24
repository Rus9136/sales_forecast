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
        self._load_model()
    
    def train_model(
        self, 
        db: Session,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        test_size: float = 0.2,
        save_model: bool = True
    ) -> Dict[str, float]:
        """
        Train LightGBM model on historical sales data
        
        Returns:
            Dictionary with training metrics (MAE, MAPE, R2)
        """
        logger.info("Starting model training...")
        
        # Initialize training service
        training_service = TrainingDataService(db)
        
        # Prepare training data
        df = training_service.prepare_training_data(start_date, end_date)
        
        if df.empty:
            raise ValueError("No training data available")
        
        # Get feature columns and target
        self.feature_columns = training_service.get_feature_columns()
        target_column = training_service.get_target_column()
        
        # Split data
        train_df, test_df = training_service.split_train_test(df, test_size=test_size)
        
        # Prepare training data
        X_train = train_df[self.feature_columns]
        y_train = train_df[target_column]
        X_test = test_df[self.feature_columns]
        y_test = test_df[target_column]
        
        logger.info(f"Training set: {len(X_train)} samples, Test set: {len(X_test)} samples")
        
        # Initialize and train model
        self.model = lgb.LGBMRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            num_leaves=31,
            random_state=42,
            n_jobs=-1,
            verbosity=-1
        )
        
        # Train model
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            eval_metric='rmse',
            callbacks=[lgb.early_stopping(10), lgb.log_evaluation(0)]
        )
        
        # Make predictions
        y_pred = self.model.predict(X_test)
        
        # Calculate metrics
        mae = mean_absolute_error(y_test, y_pred)
        mape = self._calculate_mape(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        
        metrics = {
            'mae': mae,
            'mape': mape,
            'r2': r2,
            'rmse': rmse,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }
        
        logger.info(f"Training completed. MAE: {mae:.2f}, MAPE: {mape:.2f}%, R²: {r2:.4f}")
        
        # Save model if requested
        if save_model:
            self._save_model()
            
        # Print feature importance
        feature_importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        logger.info("\nTop 5 most important features:")
        for _, row in feature_importance.head().iterrows():
            logger.info(f"  {row['feature']}: {row['importance']:.4f}")
        
        return metrics
    
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
            # Calculate date range for historical data (last 30 days)
            end_date = forecast_date - timedelta(days=1)
            start_date = end_date - timedelta(days=30)
            
            # Query historical sales
            sales_query = db.query(
                SalesSummary.date,
                SalesSummary.total_sales
            ).filter(
                and_(
                    SalesSummary.department_id == branch_id,
                    SalesSummary.date >= start_date,
                    SalesSummary.date <= end_date
                )
            ).order_by(SalesSummary.date)
            
            sales_data = sales_query.all()
            
            if len(sales_data) < 7:
                logger.warning(f"Insufficient historical data for branch {branch_id}. Found {len(sales_data)} days, need at least 7.")
                return None
            
            # Create DataFrame
            df = pd.DataFrame(sales_data, columns=['date', 'total_sales'])
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # Calculate rolling features
            rolling_7d = df['total_sales'].tail(7).mean()
            rolling_14d = df['total_sales'].tail(14).mean() if len(df) >= 14 else rolling_7d
            rolling_30d = df['total_sales'].mean()
            rolling_7d_std = df['total_sales'].tail(7).std()
            lag_1d = df['total_sales'].iloc[-1]
            lag_7d = df['total_sales'].iloc[-7] if len(df) >= 7 else lag_1d
            
            # Calculate percentage change
            if len(df) >= 2 and df['total_sales'].iloc[-2] != 0:
                pct_change_1d = (df['total_sales'].iloc[-1] - df['total_sales'].iloc[-2]) / df['total_sales'].iloc[-2]
            else:
                pct_change_1d = 0
            
            # Create feature vector
            forecast_datetime = pd.to_datetime(forecast_date)
            features = {
                'day_of_week': forecast_datetime.dayofweek,
                'month': forecast_datetime.month,
                'day_of_month': forecast_datetime.day,
                'is_weekend': 1 if forecast_datetime.dayofweek >= 5 else 0,
                'quarter': forecast_datetime.quarter,
                'week_of_year': forecast_datetime.isocalendar().week,
                'is_month_start': 1 if forecast_datetime.is_month_start else 0,
                'is_month_end': 1 if forecast_datetime.is_month_end else 0,
                'rolling_7d_avg_sales': rolling_7d,
                'rolling_14d_avg_sales': rolling_14d,
                'rolling_30d_avg_sales': rolling_30d,
                'rolling_7d_std_sales': rolling_7d_std,
                'lag_1d_sales': lag_1d,
                'lag_7d_sales': lag_7d,
                'pct_change_1d': pct_change_1d
            }
            
            # Create DataFrame with features in correct order
            X = pd.DataFrame([features])[self.feature_columns]
            
            # Make prediction
            prediction = self.model.predict(X)[0]
            
            # Ensure non-negative prediction
            prediction = max(0, prediction)
            
            logger.info(f"Forecast for branch {branch_id} on {forecast_date}: {prediction:.2f}")
            
            return float(prediction)
            
        except Exception as e:
            logger.error(f"Error during forecasting: {str(e)}")
            return None
    
    def _calculate_mape(self, y_true, y_pred) -> float:
        """Calculate Mean Absolute Percentage Error"""
        mask = y_true != 0
        return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
    
    def _save_model(self):
        """Save trained model to disk"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        model_data = {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'version': '1.0',
            'trained_at': datetime.now().isoformat()
        }
        
        joblib.dump(model_data, self.model_path)
        logger.info(f"Model saved to {self.model_path}")
    
    def _load_model(self):
        """Load model from disk if exists"""
        if os.path.exists(self.model_path):
            try:
                model_data = joblib.load(self.model_path)
                self.model = model_data['model']
                self.feature_columns = model_data['feature_columns']
                logger.info(f"Model loaded from {self.model_path}")
                logger.info(f"Model version: {model_data.get('version', 'unknown')}")
                logger.info(f"Trained at: {model_data.get('trained_at', 'unknown')}")
            except Exception as e:
                logger.error(f"Error loading model: {str(e)}")
                self.model = None
                self.feature_columns = None
        else:
            logger.info(f"No saved model found at {self.model_path}")
    
    def retrain_model(self, db: Session) -> Dict[str, float]:
        """
        Retrain model with latest data
        
        This is a convenience method that calls train_model with default parameters
        """
        logger.info("Retraining model with latest data...")
        return self.train_model(db, save_model=True)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model"""
        if self.model is None:
            return {'status': 'not_loaded', 'model_path': self.model_path}
        
        return {
            'status': 'loaded',
            'model_path': self.model_path,
            'model_type': type(self.model).__name__,
            'n_features': len(self.feature_columns) if self.feature_columns else 0,
            'feature_names': self.feature_columns
        }


# Singleton instance
_forecaster_instance = None


def get_forecaster_agent() -> SalesForecasterAgent:
    """Get singleton instance of SalesForecasterAgent"""
    global _forecaster_instance
    if _forecaster_instance is None:
        _forecaster_instance = SalesForecasterAgent()
    return _forecaster_instance
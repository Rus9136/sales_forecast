import optuna
import lightgbm as lgb
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from typing import Dict, Any, Tuple, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class HyperparameterTuningService:
    """Service for hyperparameter optimization using Optuna"""
    
    def __init__(self):
        self.best_params = None
        self.best_score = float('inf')
        self.study = None
    
    def optimize_lightgbm(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        n_trials: int = 100,
        timeout: Optional[int] = 1800,  # 30 minutes
        cv_folds: int = 3
    ) -> Dict[str, Any]:
        """
        Optimize LightGBM hyperparameters using Optuna
        
        Args:
            X_train: Training features
            y_train: Training target
            X_val: Validation features  
            y_val: Validation target
            n_trials: Number of optimization trials
            timeout: Timeout in seconds
            cv_folds: Number of cross-validation folds
            
        Returns:
            Dictionary with best parameters and performance metrics
        """
        logger.info(f"Starting LightGBM hyperparameter optimization with {n_trials} trials")
        
        def objective(trial):
            # Define hyperparameter search space
            params = {
                'objective': 'regression',
                'metric': 'mae',
                'boosting_type': 'gbdt',
                'verbose': -1,
                'random_state': 42,
                'n_jobs': -1,
                
                # Key hyperparameters to optimize
                'num_leaves': trial.suggest_int('num_leaves', 10, 300),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                'feature_fraction': trial.suggest_float('feature_fraction', 0.4, 1.0),
                'bagging_fraction': trial.suggest_float('bagging_fraction', 0.4, 1.0),
                'bagging_freq': trial.suggest_int('bagging_freq', 1, 7),
                'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
                'max_depth': trial.suggest_int('max_depth', 3, 15),
                'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 1.0),
                'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 1.0),
                'subsample': trial.suggest_float('subsample', 0.4, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.4, 1.0),
                'min_split_gain': trial.suggest_float('min_split_gain', 0.0, 1.0),
                'min_child_weight': trial.suggest_float('min_child_weight', 0.001, 10.0, log=True),
            }
            
            # Time series cross-validation
            tscv = TimeSeriesSplit(n_splits=cv_folds)
            cv_scores = []
            
            # Combine train and validation for CV
            X_combined = pd.concat([X_train, X_val])
            y_combined = pd.concat([y_train, y_val])
            
            for train_idx, val_idx in tscv.split(X_combined):
                X_cv_train, X_cv_val = X_combined.iloc[train_idx], X_combined.iloc[val_idx]
                y_cv_train, y_cv_val = y_combined.iloc[train_idx], y_combined.iloc[val_idx]
                
                # Create datasets
                train_data = lgb.Dataset(X_cv_train, label=y_cv_train)
                val_data = lgb.Dataset(X_cv_val, label=y_cv_val, reference=train_data)
                
                # Train model
                model = lgb.train(
                    params,
                    train_data,
                    valid_sets=[val_data],
                    num_boost_round=1000,
                    callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)]
                )
                
                # Predict and calculate MAPE
                y_pred = model.predict(X_cv_val, num_iteration=model.best_iteration)
                mape = mean_absolute_percentage_error(y_cv_val, y_pred) * 100
                cv_scores.append(mape)
            
            return np.mean(cv_scores)
        
        # Create and run study
        study = optuna.create_study(
            direction='minimize',
            study_name=f'lightgbm_optimization_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )
        
        study.optimize(
            objective,
            n_trials=n_trials,
            timeout=timeout,
            show_progress_bar=True
        )
        
        self.study = study
        self.best_params = study.best_params
        self.best_score = study.best_value
        
        # Train final model with best parameters
        final_params = {
            'objective': 'regression',
            'metric': 'mae',
            'boosting_type': 'gbdt',
            'verbose': -1,
            'random_state': 42,
            'n_jobs': -1,
            **study.best_params
        }
        
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        final_model = lgb.train(
            final_params,
            train_data,
            valid_sets=[val_data],
            num_boost_round=1000,
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)]
        )
        
        # Evaluate final model
        y_pred_val = final_model.predict(X_val, num_iteration=final_model.best_iteration)
        final_mape = mean_absolute_percentage_error(y_val, y_pred_val) * 100
        final_mae = mean_absolute_error(y_val, y_pred_val)
        
        logger.info(f"Optimization completed. Best MAPE: {study.best_value:.3f}%")
        logger.info(f"Final model MAPE: {final_mape:.3f}%, MAE: {final_mae:.2f}")
        
        return {
            'best_params': study.best_params,
            'best_cv_score': study.best_value,
            'final_model': final_model,
            'final_mape': final_mape,
            'final_mae': final_mae,
            'n_trials': len(study.trials),
            'study': study
        }
    
    def get_optimization_history(self) -> pd.DataFrame:
        """Get optimization history as DataFrame"""
        if self.study is None:
            return pd.DataFrame()
        
        trials_df = self.study.trials_dataframe()
        return trials_df
    
    def plot_optimization_history(self):
        """Plot optimization history (requires matplotlib)"""
        if self.study is None:
            logger.warning("No study available for plotting")
            return
        
        try:
            import matplotlib.pyplot as plt
            optuna.visualization.matplotlib.plot_optimization_history(self.study)
            plt.show()
        except ImportError:
            logger.warning("matplotlib not available for plotting")
    
    def get_feature_importance(self, model, feature_names) -> pd.DataFrame:
        """Get feature importance from trained model"""
        if hasattr(model, 'feature_importance'):
            importance = model.feature_importance(importance_type='gain')
            df = pd.DataFrame({
                'feature': feature_names,
                'importance': importance
            }).sort_values('importance', ascending=False)
            return df
        else:
            logger.warning("Model does not support feature importance")
            return pd.DataFrame()


class ModelComparisonService:
    """Service for comparing different ML models"""
    
    def __init__(self):
        self.results = {}
    
    def compare_models(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        X_test: pd.DataFrame,
        y_test: pd.Series
    ) -> Dict[str, Dict[str, float]]:
        """
        Compare LightGBM, XGBoost, and CatBoost models
        
        Returns:
            Dictionary with model performance metrics
        """
        results = {}
        
        # Test LightGBM (optimized)
        results['LightGBM'] = self._test_lightgbm(X_train, y_train, X_val, y_val, X_test, y_test)
        
        # Test XGBoost
        try:
            results['XGBoost'] = self._test_xgboost(X_train, y_train, X_val, y_val, X_test, y_test)
        except ImportError:
            logger.warning("XGBoost not available")
        
        # Test CatBoost
        try:
            results['CatBoost'] = self._test_catboost(X_train, y_train, X_val, y_val, X_test, y_test)
        except ImportError:
            logger.warning("CatBoost not available")
        
        self.results = results
        return results
    
    def _test_lightgbm(self, X_train, y_train, X_val, y_val, X_test, y_test):
        """Test LightGBM with default parameters"""
        logger.info("Testing LightGBM...")
        
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        params = {
            'objective': 'regression',
            'metric': 'mae',
            'boosting_type': 'gbdt',
            'verbose': -1,
            'random_state': 42,
            'n_jobs': -1,
        }
        
        model = lgb.train(
            params,
            train_data,
            valid_sets=[val_data],
            num_boost_round=1000,
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)]
        )
        
        # Predictions
        y_pred_val = model.predict(X_val, num_iteration=model.best_iteration)
        y_pred_test = model.predict(X_test, num_iteration=model.best_iteration)
        
        return {
            'val_mape': mean_absolute_percentage_error(y_val, y_pred_val) * 100,
            'val_mae': mean_absolute_error(y_val, y_pred_val),
            'test_mape': mean_absolute_percentage_error(y_test, y_pred_test) * 100,
            'test_mae': mean_absolute_error(y_test, y_pred_test),
            'model': model
        }
    
    def _test_xgboost(self, X_train, y_train, X_val, y_val, X_test, y_test):
        """Test XGBoost"""
        import xgboost as xgb
        logger.info("Testing XGBoost...")
        
        model = xgb.XGBRegressor(
            random_state=42,
            n_estimators=1000,
            early_stopping_rounds=50,
            eval_metric='mae'
        )
        
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        
        y_pred_val = model.predict(X_val)
        y_pred_test = model.predict(X_test)
        
        return {
            'val_mape': mean_absolute_percentage_error(y_val, y_pred_val) * 100,
            'val_mae': mean_absolute_error(y_val, y_pred_val),
            'test_mape': mean_absolute_percentage_error(y_test, y_pred_test) * 100,
            'test_mae': mean_absolute_error(y_test, y_pred_test),
            'model': model
        }
    
    def _test_catboost(self, X_train, y_train, X_val, y_val, X_test, y_test):
        """Test CatBoost"""
        from catboost import CatBoostRegressor
        logger.info("Testing CatBoost...")
        
        model = CatBoostRegressor(
            random_state=42,
            iterations=1000,
            early_stopping_rounds=50,
            verbose=False
        )
        
        model.fit(
            X_train, y_train,
            eval_set=(X_val, y_val)
        )
        
        y_pred_val = model.predict(X_val)
        y_pred_test = model.predict(X_test)
        
        return {
            'val_mape': mean_absolute_percentage_error(y_val, y_pred_val) * 100,
            'val_mae': mean_absolute_error(y_val, y_pred_val),
            'test_mape': mean_absolute_percentage_error(y_test, y_pred_test) * 100,
            'test_mae': mean_absolute_error(y_test, y_pred_test),
            'model': model
        }
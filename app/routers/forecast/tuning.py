"""Hyperparameter tuning and model comparison endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import logging
import traceback

from ...db import get_db
from ...auth import get_api_key_or_bypass, ApiKey

logger = logging.getLogger(__name__)

router = APIRouter()


class HyperparameterTuningRequest(BaseModel):
    n_trials: Optional[int] = 50
    timeout: Optional[int] = 1800
    cv_folds: Optional[int] = 3
    days: Optional[int] = 365


class ModelComparisonRequest(BaseModel):
    days: Optional[int] = 365


@router.post("/optimize")
async def optimize_hyperparameters(
    request: Optional[HyperparameterTuningRequest] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Optimize model hyperparameters using Optuna."""
    try:
        from ...services.training_service import TrainingDataService
        from ...services.hyperparameter_tuning_service import HyperparameterTuningService

        training_service = TrainingDataService(db)
        tuning_service = HyperparameterTuningService()

        n_trials = request.n_trials if request else 50
        timeout = request.timeout if request else 1800
        cv_folds = request.cv_folds if request else 3
        days = request.days if request else 365

        logger.info(f"Starting hyperparameter optimization with {n_trials} trials, {timeout}s timeout")

        df = training_service.prepare_training_data(days=days)
        if df.empty:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No training data available")

        feature_columns = training_service.get_feature_columns()
        X = df[feature_columns]
        y = df['total_sales']

        train_size = int(0.7 * len(df))
        val_size = int(0.15 * len(df))

        X_train = X.iloc[:train_size]
        y_train = y.iloc[:train_size]
        X_val = X.iloc[train_size:train_size + val_size]
        y_val = y.iloc[train_size:train_size + val_size]

        results = tuning_service.optimize_lightgbm(
            X_train, y_train, X_val, y_val,
            n_trials=n_trials, timeout=timeout, cv_folds=cv_folds
        )

        logger.info(f"Optimization completed. Best MAPE: {results['best_cv_score']:.3f}%")

        return {
            "status": "success",
            "message": f"Hyperparameter optimization completed with {results['n_trials']} trials",
            "best_params": results['best_params'],
            "best_cv_score": results['best_cv_score'],
            "final_mape": results['final_mape'],
            "final_mae": results['final_mae'],
            "optimization_stats": {
                "n_trials": results['n_trials'],
                "timeout_used": timeout,
                "cv_folds": cv_folds,
                "training_samples": len(X_train),
                "validation_samples": len(X_val)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during hyperparameter optimization: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during hyperparameter optimization: {str(e)}"
        )


@router.post("/compare_models")
async def compare_models(
    request: Optional[ModelComparisonRequest] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Compare LightGBM, XGBoost, and CatBoost models."""
    try:
        from ...services.training_service import TrainingDataService
        from ...services.hyperparameter_tuning_service import ModelComparisonService

        training_service = TrainingDataService(db)
        comparison_service = ModelComparisonService()

        days = request.days if request else 365
        logger.info(f"Starting model comparison using last {days} days of data")

        df = training_service.prepare_training_data(days=days)
        if df.empty:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No training data available")

        feature_columns = training_service.get_feature_columns()
        X = df[feature_columns]
        y = df['total_sales']

        train_size = int(0.7 * len(df))
        val_size = int(0.15 * len(df))

        X_train = X.iloc[:train_size]
        y_train = y.iloc[:train_size]
        X_val = X.iloc[train_size:train_size + val_size]
        y_val = y.iloc[train_size:train_size + val_size]
        X_test = X.iloc[train_size + val_size:]
        y_test = y.iloc[train_size + val_size:]

        results = comparison_service.compare_models(
            X_train, y_train, X_val, y_val, X_test, y_test
        )

        formatted_results = {}
        for model_name, metrics in results.items():
            formatted_results[model_name] = {
                "val_mape": round(metrics['val_mape'], 3),
                "val_mae": round(metrics['val_mae'], 2),
                "test_mape": round(metrics['test_mape'], 3),
                "test_mae": round(metrics['test_mae'], 2)
            }

        best_model = min(results.keys(), key=lambda k: results[k]['test_mape'])
        logger.info(f"Model comparison completed. Best model: {best_model}")

        return {
            "status": "success",
            "message": "Model comparison completed",
            "results": formatted_results,
            "best_model": best_model,
            "best_test_mape": round(results[best_model]['test_mape'], 3),
            "data_stats": {
                "total_samples": len(df),
                "training_samples": len(X_train),
                "validation_samples": len(X_val),
                "test_samples": len(X_test),
                "features": len(feature_columns),
                "days_used": days
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during model comparison: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during model comparison: {str(e)}"
        )

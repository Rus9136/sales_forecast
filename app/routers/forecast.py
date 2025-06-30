from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import logging
import traceback
import csv
import io

from ..db import get_db
from ..agents.sales_forecaster_agent import get_forecaster_agent
from ..models.branch import Department, SalesSummary, PostprocessingSettings
from ..auth import get_api_key_or_bypass, get_optional_api_key, ApiKey, log_api_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecast", tags=["forecast"])


class RetrainRequest(BaseModel):
    handle_outliers: Optional[bool] = True
    outlier_method: Optional[str] = 'winsorize'
    days: Optional[int] = None


class HyperparameterTuningRequest(BaseModel):
    n_trials: Optional[int] = 50
    timeout: Optional[int] = 1800  # 30 minutes
    cv_folds: Optional[int] = 3
    days: Optional[int] = 365  # Use last year of data


class ModelComparisonRequest(BaseModel):
    days: Optional[int] = 365


class PostprocessingSettingsRequest(BaseModel):
    enable_smoothing: bool = True
    max_change_percent: float = 50.0
    enable_business_rules: bool = True
    enable_weekend_adjustment: bool = True
    enable_holiday_adjustment: bool = True
    enable_anomaly_detection: bool = True
    anomaly_threshold: float = 3.0
    enable_confidence: bool = True
    confidence_level: float = 0.95


class PostprocessingSettingsResponse(BaseModel):
    id: int
    enable_smoothing: bool
    max_change_percent: float
    enable_business_rules: bool
    enable_weekend_adjustment: bool
    enable_holiday_adjustment: bool
    enable_anomaly_detection: bool
    anomaly_threshold: float
    enable_confidence: bool
    confidence_level: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


@router.post("/retrain")
async def retrain_model(request: Optional[RetrainRequest] = None, db: Session = Depends(get_db)):
    """
    Retrain the sales forecasting model with latest data
    
    Returns:
        Training results and model metrics
    """
    try:
        from ..services.training_service import TrainingDataService
        
        # Initialize training service
        training_service = TrainingDataService(db)
        
        logger.info("Starting model retraining...")
        
        # Get training data with parameters
        kwargs = {}
        if request:
            if request.handle_outliers is not None:
                kwargs['handle_outliers'] = request.handle_outliers
            if request.outlier_method:
                kwargs['outlier_method'] = request.outlier_method
            if request.days:
                kwargs['days'] = request.days
        
        training_data = training_service.prepare_training_data(**kwargs)
        
        if training_data.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No training data available"
            )
        
        logger.info(f"Training data prepared: {len(training_data)} samples")
        
        # Get forecaster and train
        forecaster = get_forecaster_agent()
        
        # Split data for training
        train_df, val_df, test_df = training_service.split_train_validation_test(training_data)
        
        # Train model
        model, results = forecaster.train_model(train_df, val_df, test_df)
        
        logger.info(f"Model training completed. Metrics: {results}")
        
        return {
            "status": "success",
            "message": "Model retrained successfully",
            "metrics": results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error retraining model: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retraining model: {str(e)}"
        )


@router.get("/model/info")
async def get_model_info():
    """
    Get information about the current model
    
    Returns:
        Model status, features, and metadata
    """
    try:
        forecaster = get_forecaster_agent()
        model_info = forecaster.get_model_info()
        
        # Возвращаем все данные из model_info, включая training_metrics
        return model_info
        
    except Exception as e:
        logger.error(f"Error getting model info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting model info: {str(e)}"
        )


@router.get("/comparison")
async def get_forecast_comparison(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Compare forecasts with actual sales
    
    Returns comparison data with prediction error metrics
    """
    try:
        # Log API usage if authenticated
        if api_key:
            log_api_usage(api_key, "/forecast/comparison", db=db)
        # Get actual sales data
        sales_query = db.query(SalesSummary).filter(
            and_(
                SalesSummary.date >= from_date,
                SalesSummary.date <= to_date
            )
        )
        
        if department_id:
            sales_query = sales_query.filter(SalesSummary.department_id == department_id)
        
        sales_data = sales_query.all()
        
        # Get forecaster
        forecaster = get_forecaster_agent()
        
        results = []
        for sale in sales_data:
            # Get department info
            department = db.query(Department).filter(Department.id == sale.department_id).first()
            
            # Get prediction
            try:
                prediction = forecaster.forecast(str(sale.department_id), sale.date, db)
            except Exception as pred_error:
                logger.warning(f"Failed to get prediction for {sale.date}, {sale.department_id}: {pred_error}")
                prediction = None
            
            # Calculate error if we have both values
            error = None
            error_percentage = None
            if prediction and sale.total_sales:
                error = prediction - sale.total_sales
                error_percentage = (abs(error) / sale.total_sales) * 100
            
            results.append({
                "date": sale.date.isoformat(),
                "department_id": str(sale.department_id),
                "department_name": department.name if department else "Unknown",
                "predicted_sales": round(prediction, 2) if prediction else None,
                "actual_sales": sale.total_sales,
                "error": round(error, 2) if error else None,
                "error_percentage": round(error_percentage, 2) if error_percentage else None
            })
        
        return results
        
    except Exception as e:
        logger.error(f"Error getting forecast comparison: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting forecast comparison: {str(e)}"
        )


@router.get("/batch")
async def get_batch_forecasts(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Get batch forecasts for a date range
    
    Returns:
        List of forecasts for the specified period
    """
    try:
        # Log API usage if authenticated
        if api_key:
            log_api_usage(api_key, "/forecast/batch", db=db)
        # Get departments
        departments_query = db.query(Department)
        if department_id:
            departments_query = departments_query.filter(Department.id == department_id)
        
        departments = departments_query.all()
        
        if not departments:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No departments found"
            )
        
        # Get forecaster
        forecaster = get_forecaster_agent()
        
        results = []
        current_date = from_date
        
        while current_date <= to_date:
            for dept in departments:
                try:
                    prediction = forecaster.forecast(str(dept.id), current_date, db)
                except Exception as pred_error:
                    logger.warning(f"Failed to get prediction for {current_date}, {dept.id}: {pred_error}")
                    prediction = None
                
                logger.info(f"Prediction for {dept.name} on {current_date}: {prediction}")
                
                if prediction is None:
                    logger.warning(
                        f"No prediction available for department {dept.name} on {current_date}"
                    )
                
                results.append({
                    "date": current_date.isoformat(),
                    "department_id": str(dept.id),
                    "department_name": dept.name,
                    "predicted_sales": round(prediction, 2) if prediction else None
                })
            
            current_date += timedelta(days=1)
        
        return results
        
    except Exception as e:
        logger.error(f"Error getting batch forecasts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting batch forecasts: {str(e)}"
        )


@router.get("/export/csv")
async def export_forecasts_csv(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    include_actual: bool = False,
    db: Session = Depends(get_db)
):
    """
    Export forecasts to CSV format
    
    Returns:
        CSV file with forecast data
    """
    try:
        # Get forecast data
        if include_actual:
            # Get comparison data
            comparison_data = await get_forecast_comparison(from_date, to_date, department_id, db)
            
            # Create CSV output
            output = io.StringIO()
            fieldnames = ['date', 'department_name', 'predicted_sales', 'actual_sales', 'error', 'error_percentage']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in comparison_data:
                writer.writerow({
                    'date': row['date'],
                    'department_name': row['department_name'],
                    'predicted_sales': row['predicted_sales'],
                    'actual_sales': row['actual_sales'],
                    'error': row['error'],
                    'error_percentage': row['error_percentage']
                })
            
            filename = f"forecast_comparison_{from_date}_{to_date}.csv"
        else:
            # Get forecast data only
            forecast_data = await get_batch_forecasts(from_date, to_date, department_id, db)
            
            # Create CSV output
            output = io.StringIO()
            fieldnames = ['date', 'department_name', 'predicted_sales']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in forecast_data:
                writer.writerow({
                    'date': row['date'],
                    'department_name': row['department_name'],
                    'predicted_sales': row['predicted_sales']
                })
            
            filename = f"forecast_{from_date}_{to_date}.csv"
        
        # Return CSV response
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error exporting forecasts to CSV: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting forecasts to CSV: {str(e)}"
        )


@router.post("/optimize")
async def optimize_hyperparameters(
    request: Optional[HyperparameterTuningRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Optimize model hyperparameters using Optuna
    
    Returns:
        Best parameters and optimization results
    """
    try:
        from ..services.training_service import TrainingDataService
        from ..services.hyperparameter_tuning_service import HyperparameterTuningService
        
        # Initialize services
        training_service = TrainingDataService(db)
        tuning_service = HyperparameterTuningService()
        
        # Get parameters
        n_trials = request.n_trials if request else 50
        timeout = request.timeout if request else 1800
        cv_folds = request.cv_folds if request else 3
        days = request.days if request else 365
        
        logger.info(f"Starting hyperparameter optimization with {n_trials} trials, {timeout}s timeout")
        
        # Prepare data (limit to recent data for better quality)
        df = training_service.prepare_training_data(days=days)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No training data available"
            )
        
        # Get features  
        feature_columns = training_service.get_feature_columns()
        
        # Prepare features and target
        X = df[feature_columns]
        y = df['total_sales']
        
        # Split data (70% train, 15% val, 15% test)
        train_size = int(0.7 * len(df))
        val_size = int(0.15 * len(df))
        
        X_train = X.iloc[:train_size]
        y_train = y.iloc[:train_size]
        X_val = X.iloc[train_size:train_size + val_size]
        y_val = y.iloc[train_size:train_size + val_size]
        
        # Run optimization
        results = tuning_service.optimize_lightgbm(
            X_train, y_train, X_val, y_val,
            n_trials=n_trials,
            timeout=timeout,
            cv_folds=cv_folds
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
    db: Session = Depends(get_db)
):
    """
    Compare LightGBM, XGBoost, and CatBoost models
    
    Returns:
        Comparison results for different models
    """
    try:
        from ..services.training_service import TrainingDataService
        from ..services.hyperparameter_tuning_service import ModelComparisonService
        
        # Initialize services
        training_service = TrainingDataService(db)
        comparison_service = ModelComparisonService()
        
        # Get parameters
        days = request.days if request else 365
        
        logger.info(f"Starting model comparison using last {days} days of data")
        
        # Prepare data
        df = training_service.prepare_training_data(days=days)
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No training data available"
            )
        
        # Get features  
        feature_columns = training_service.get_feature_columns()
        
        # Prepare features and target
        X = df[feature_columns]
        y = df['total_sales']
        
        # Split data (70% train, 15% val, 15% test)
        train_size = int(0.7 * len(df))
        val_size = int(0.15 * len(df))
        
        X_train = X.iloc[:train_size]
        y_train = y.iloc[:train_size]
        X_val = X.iloc[train_size:train_size + val_size]
        y_val = y.iloc[train_size:train_size + val_size]
        X_test = X.iloc[train_size + val_size:]
        y_test = y.iloc[train_size + val_size:]
        
        # Run comparison
        results = comparison_service.compare_models(
            X_train, y_train, X_val, y_val, X_test, y_test
        )
        
        # Format results for API response
        formatted_results = {}
        for model_name, metrics in results.items():
            formatted_results[model_name] = {
                "val_mape": round(metrics['val_mape'], 3),
                "val_mae": round(metrics['val_mae'], 2),
                "test_mape": round(metrics['test_mape'], 3),
                "test_mae": round(metrics['test_mae'], 2)
            }
        
        # Find best model
        best_model = min(results.keys(), key=lambda k: results[k]['test_mape'])
        
        logger.info(f"Model comparison completed. Best model: {best_model}")
        
        return {
            "status": "success",
            "message": f"Model comparison completed",
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
        
    except Exception as e:
        logger.error(f"Error during model comparison: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during model comparison: {str(e)}"
        )


@router.get("/error-analysis/errors_by_segment")
async def analyze_errors_by_segment(
    from_date: date,
    to_date: date,
    segment_type: str = "department",
    db: Session = Depends(get_db)
):
    """
    Analyze prediction errors by different segments
    
    Args:
        from_date: Start date for analysis
        to_date: End date for analysis
        segment_type: Type of segmentation (department, day_of_week, month, location)
    
    Returns:
        Error analysis by segments
    """
    try:
        from ..services.error_analysis_service import get_error_analysis_service
        
        analysis_service = get_error_analysis_service(db)
        results = analysis_service.analyze_errors_by_segment(from_date, to_date, segment_type)
        
        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "segment_type": segment_type,
            "analysis": results
        }
        
    except Exception as e:
        logger.error(f"Error analyzing errors by segment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing errors by segment: {str(e)}"
        )


@router.get("/error-analysis/problematic_branches")
async def identify_problematic_branches(
    from_date: date,
    to_date: date,
    min_samples: int = 5,
    mape_threshold: float = 15.0,
    db: Session = Depends(get_db)
):
    """
    Identify branches with consistently high prediction errors
    
    Args:
        from_date: Start date for analysis
        to_date: End date for analysis
        min_samples: Minimum number of predictions required
        mape_threshold: MAPE threshold for considering branch problematic
    
    Returns:
        List of problematic branches with error statistics
    """
    try:
        from ..services.error_analysis_service import get_error_analysis_service
        
        analysis_service = get_error_analysis_service(db)
        problematic_branches = analysis_service.identify_problematic_branches(
            from_date, to_date, min_samples, mape_threshold
        )
        
        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "criteria": {
                "min_samples": min_samples,
                "mape_threshold": mape_threshold
            },
            "problematic_branches_count": len(problematic_branches),
            "problematic_branches": problematic_branches
        }
        
    except Exception as e:
        logger.error(f"Error identifying problematic branches: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error identifying problematic branches: {str(e)}"
        )


@router.get("/error-analysis/temporal_errors")
async def analyze_temporal_errors(
    from_date: date,
    to_date: date,
    db: Session = Depends(get_db)
):
    """
    Analyze how prediction errors vary over time
    
    Args:
        from_date: Start date for analysis
        to_date: End date for analysis
    
    Returns:
        Temporal error analysis with trends and patterns
    """
    try:
        from ..services.error_analysis_service import get_error_analysis_service
        
        analysis_service = get_error_analysis_service(db)
        temporal_analysis = analysis_service.analyze_temporal_errors(from_date, to_date)
        
        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "temporal_analysis": temporal_analysis
        }
        
    except Exception as e:
        logger.error(f"Error analyzing temporal errors: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing temporal errors: {str(e)}"
        )


@router.get("/error-analysis/error_distribution")
async def get_error_distribution(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get distribution of prediction errors for statistical analysis
    
    Args:
        from_date: Start date for analysis
        to_date: End date for analysis
        department_id: Optional department ID to filter analysis
    
    Returns:
        Error distribution statistics and percentiles
    """
    try:
        from ..services.error_analysis_service import get_error_analysis_service
        
        analysis_service = get_error_analysis_service(db)
        distribution = analysis_service.get_error_distribution(from_date, to_date, department_id)
        
        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "department_id": department_id,
            "error_distribution": distribution
        }
        
    except Exception as e:
        logger.error(f"Error getting error distribution: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting error distribution: {str(e)}"
        )


# Post-processing endpoints
@router.post("/postprocess")
async def postprocess_forecast(
    branch_id: str,
    forecast_date: date,
    raw_prediction: float,
    apply_smoothing: bool = True,
    apply_business_rules: bool = True,
    apply_anomaly_detection: bool = True,
    calculate_confidence: bool = True,
    db: Session = Depends(get_db)
):
    """
    Apply post-processing to a raw forecast prediction
    
    Args:
        branch_id: Department/branch ID (UUID as string)
        forecast_date: Date being forecasted
        raw_prediction: Raw prediction from ML model
        apply_smoothing: Whether to apply smoothing
        apply_business_rules: Whether to apply business rules
        apply_anomaly_detection: Whether to check for anomalies
        calculate_confidence: Whether to calculate confidence intervals
    
    Returns:
        Post-processed forecast with metadata
    """
    try:
        from ..services.forecast_postprocessing_service import get_forecast_postprocessing_service
        
        postprocessing_service = get_forecast_postprocessing_service(db)
        
        result = postprocessing_service.process_forecast(
            branch_id=branch_id,
            forecast_date=forecast_date,
            raw_prediction=raw_prediction,
            apply_smoothing=apply_smoothing,
            apply_business_rules=apply_business_rules,
            apply_anomaly_detection=apply_anomaly_detection,
            calculate_confidence=calculate_confidence
        )
        
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error in forecast post-processing: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in forecast post-processing: {str(e)}"
        )


@router.post("/postprocess/batch")
async def postprocess_batch_forecasts(
    forecasts: List[Dict[str, Any]],
    apply_smoothing: bool = True,
    apply_business_rules: bool = True,
    apply_anomaly_detection: bool = True,
    calculate_confidence: bool = True,
    db: Session = Depends(get_db)
):
    """
    Apply post-processing to a batch of forecasts
    
    Args:
        forecasts: List of forecast dicts with 'branch_id', 'forecast_date', 'prediction'
        apply_smoothing: Whether to apply smoothing
        apply_business_rules: Whether to apply business rules
        apply_anomaly_detection: Whether to check for anomalies
        calculate_confidence: Whether to calculate confidence intervals
    
    Returns:
        List of post-processed forecasts
    """
    try:
        from ..services.forecast_postprocessing_service import get_forecast_postprocessing_service
        
        postprocessing_service = get_forecast_postprocessing_service(db)
        
        processing_options = {
            'apply_smoothing': apply_smoothing,
            'apply_business_rules': apply_business_rules,
            'apply_anomaly_detection': apply_anomaly_detection,
            'calculate_confidence': calculate_confidence
        }
        
        results = postprocessing_service.batch_process_forecasts(
            forecasts, **processing_options
        )
        
        return {
            "status": "success",
            "processed_count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error in batch forecast post-processing: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in batch forecast post-processing: {str(e)}"
        )


class PostprocessingOptionsRequest(BaseModel):
    apply_smoothing: Optional[bool] = True
    apply_business_rules: Optional[bool] = True
    apply_anomaly_detection: Optional[bool] = True
    calculate_confidence: Optional[bool] = True
    max_change_percent: Optional[float] = 50.0
    confidence_level: Optional[float] = 0.95


@router.get("/batch_with_postprocessing")
async def get_batch_forecasts_with_postprocessing(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    apply_postprocessing: bool = True,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Get batch forecasts with automatic post-processing applied
    
    Returns:
        List of forecasts with post-processing metadata
    """
    try:
        # Log API usage if authenticated
        if api_key:
            log_api_usage(api_key, "/forecast/batch_with_postprocessing", db=db)
        # Get raw forecasts first
        raw_forecasts = await get_batch_forecasts(from_date, to_date, department_id, db)
        
        if not apply_postprocessing:
            return raw_forecasts
        
        # Apply post-processing to all forecasts
        from ..services.forecast_postprocessing_service import get_forecast_postprocessing_service
        
        postprocessing_service = get_forecast_postprocessing_service(db)
        
        # Convert raw forecasts to format expected by post-processing service
        forecast_list = []
        for forecast in raw_forecasts:
            if forecast['predicted_sales'] is not None:
                forecast_list.append({
                    'branch_id': forecast['department_id'],
                    'forecast_date': forecast['date'],
                    'prediction': forecast['predicted_sales']
                })
        
        # Apply post-processing
        processed_results = postprocessing_service.batch_process_forecasts(forecast_list)
        
        # Merge processed results back with original forecast data
        processed_forecasts = []
        for i, original_forecast in enumerate(raw_forecasts):
            if original_forecast['predicted_sales'] is not None and i < len(processed_results):
                processed = processed_results[i]
                enhanced_forecast = original_forecast.copy()
                enhanced_forecast.update({
                    'raw_prediction': processed.get('raw_prediction'),
                    'processed_prediction': processed.get('processed_prediction'),
                    'adjustments_applied': processed.get('adjustments_applied', []),
                    'confidence_interval': processed.get('confidence_interval'),
                    'anomaly_score': processed.get('anomaly_score'),
                    'is_anomaly': processed.get('is_anomaly', False),
                    'business_flags': processed.get('business_flags', [])
                })
                processed_forecasts.append(enhanced_forecast)
            else:
                processed_forecasts.append(original_forecast)
        
        return processed_forecasts
        
    except Exception as e:
        logger.error(f"Error getting batch forecasts with post-processing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting batch forecasts with post-processing: {str(e)}"
        )


# Postprocessing Settings endpoints
@router.get("/postprocessing/settings", response_model=PostprocessingSettingsResponse)
async def get_postprocessing_settings(db: Session = Depends(get_db)):
    """
    Get current active postprocessing settings
    
    Returns:
        Current active postprocessing settings
    """
    try:
        settings = db.query(PostprocessingSettings).filter(
            PostprocessingSettings.is_active == True
        ).first()
        
        if not settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active postprocessing settings found"
            )
        
        return settings
        
    except Exception as e:
        logger.error(f"Error getting postprocessing settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting postprocessing settings: {str(e)}"
        )


@router.post("/postprocessing/settings", response_model=PostprocessingSettingsResponse)
async def save_postprocessing_settings(
    settings_request: PostprocessingSettingsRequest,
    db: Session = Depends(get_db)
):
    """
    Save new postprocessing settings
    
    Args:
        settings_request: New settings to save
        
    Returns:
        Saved settings with ID and timestamps
    """
    try:
        # Deactivate all existing settings
        db.query(PostprocessingSettings).update({"is_active": False})
        
        # Create new active settings
        new_settings = PostprocessingSettings(
            enable_smoothing=settings_request.enable_smoothing,
            max_change_percent=settings_request.max_change_percent,
            enable_business_rules=settings_request.enable_business_rules,
            enable_weekend_adjustment=settings_request.enable_weekend_adjustment,
            enable_holiday_adjustment=settings_request.enable_holiday_adjustment,
            enable_anomaly_detection=settings_request.enable_anomaly_detection,
            anomaly_threshold=settings_request.anomaly_threshold,
            enable_confidence=settings_request.enable_confidence,
            confidence_level=settings_request.confidence_level,
            is_active=True
        )
        
        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)
        
        logger.info(f"Saved new postprocessing settings: ID {new_settings.id}")
        
        return new_settings
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving postprocessing settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving postprocessing settings: {str(e)}"
        )



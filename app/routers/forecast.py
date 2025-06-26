from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict
import logging
import traceback
import csv
import io

from ..db import get_db
from ..agents.sales_forecaster_agent import get_forecaster_agent
from ..models.branch import Department, SalesSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.post("/retrain")
async def retrain_model(db: Session = Depends(get_db)):
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
        
        # Get training data
        training_data = training_service.prepare_training_data()
        
        if training_data.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No training data available"
            )
        
        logger.info(f"Training data prepared: {len(training_data)} samples")
        
        # Get forecaster and train
        forecaster = get_forecaster_agent()
        results = forecaster.train_model(db)
        
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
    db: Session = Depends(get_db)
):
    """
    Compare forecasts with actual sales
    
    Returns comparison data with prediction error metrics
    """
    try:
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
    db: Session = Depends(get_db)
):
    """
    Get batch forecasts for a date range
    
    Returns:
        List of forecasts for the specified period
    """
    try:
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


@router.get("/{forecast_date}/{branch_id}")
async def get_sales_forecast(
    forecast_date: date,
    branch_id: str,
    db: Session = Depends(get_db)
):
    """
    Get sales forecast for a specific branch and date
    
    Args:
        forecast_date: Date to forecast (YYYY-MM-DD format)
        branch_id: Department/Branch UUID
        
    Returns:
        JSON with branch_id, date, and predicted_sales
    """
    try:
        # Validate branch exists
        branch = db.query(Department).filter(Department.id == branch_id).first()
        if not branch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Branch with ID {branch_id} not found"
            )
        
        # Get forecaster agent
        forecaster = get_forecaster_agent()
        
        # Log the forecast request
        logger.info(f"Forecasting sales for branch {branch_id} ({branch.name}) on {forecast_date}")
        
        # Call forecast function
        predicted_sales = forecaster.forecast(branch_id, forecast_date, db)
        
        # Handle case when forecast returns None
        if predicted_sales is None:
            logger.warning(f"Could not generate forecast for branch {branch_id} on {forecast_date}")
            return {
                "branch_id": branch_id,
                "branch_name": branch.name,
                "date": forecast_date.isoformat(),
                "predicted_sales": None,
                "message": "Insufficient historical data for forecast"
            }
        
        # Return successful forecast
        return {
            "branch_id": branch_id,
            "branch_name": branch.name,
            "date": forecast_date.isoformat(),
            "predicted_sales": round(predicted_sales, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Log full traceback
        logger.error(f"Error during forecast: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating forecast: {str(e)}"
        )
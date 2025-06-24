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
        predicted_sales = forecaster.forecast(
            branch_id=branch_id,
            forecast_date=forecast_date,
            db=db
        )
        
        # Handle case when forecast returns None
        if predicted_sales is None:
            logger.warning(f"Could not generate forecast for branch {branch_id} on {forecast_date}")
            # Option 1: Return null in response
            return {
                "branch_id": branch_id,
                "branch_name": branch.name,
                "date": forecast_date.isoformat(),
                "predicted_sales": None,
                "message": "Insufficient historical data for forecast"
            }
            # Option 2: Return 204 No Content
            # return Response(status_code=status.HTTP_204_NO_CONTENT)
        
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
        logger.error(traceback.format_exc())
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating forecast: {str(e)}"
        )


@router.post("/retrain")
async def retrain_model(db: Session = Depends(get_db)):
    """
    Retrain the forecasting model with latest data
    
    Returns:
        Training metrics (MAE, MAPE, R2)
    """
    try:
        # Get forecaster agent
        forecaster = get_forecaster_agent()
        
        logger.info("Starting model retraining...")
        
        # Retrain model
        metrics = forecaster.retrain_model(db)
        
        return {
            "status": "success",
            "message": "Model retrained successfully",
            "metrics": {
                "mae": round(metrics['mae'], 2),
                "mape": round(metrics['mape'], 2),
                "r2": round(metrics['r2'], 4),
                "rmse": round(metrics['rmse'], 2),
                "train_samples": metrics['train_samples'],
                "test_samples": metrics['test_samples']
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error during model retraining: {str(e)}")
        logger.error(traceback.format_exc())
        
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
        
        return {
            "status": model_info['status'],
            "model_path": model_info['model_path'],
            "model_type": model_info.get('model_type', 'unknown'),
            "n_features": model_info.get('n_features', 0),
            "feature_names": model_info.get('feature_names', [])
        }
        
    except Exception as e:
        logger.error(f"Error getting model info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting model info: {str(e)}"
        )


@router.get("/batch")
async def get_batch_forecasts(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get batch forecasts for multiple departments and dates
    
    Query params:
        from_date: Start date for forecasts
        to_date: End date for forecasts
        department_id: Optional specific department filter
    """
    try:
        # Get departments
        query = db.query(Department)
        if department_id:
            query = query.filter(Department.id == department_id)
        departments = query.all()
        
        if not departments:
            return []
        
        # Get forecaster
        forecaster = get_forecaster_agent()
        
        # Generate forecasts
        results = []
        current_date = from_date
        
        while current_date <= to_date:
            for dept in departments:
                prediction = forecaster.forecast(
                    branch_id=str(dept.id),
                    forecast_date=current_date,
                    db=db
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
        
        # Build comparison data
        results = []
        for sale in sales_data:
            # Get department info
            dept = db.query(Department).filter(Department.id == sale.department_id).first()
            if not dept:
                continue
            
            # Get forecast for this date/department
            prediction = forecaster.forecast(
                branch_id=str(sale.department_id),
                forecast_date=sale.date,
                db=db
            )
            
            if prediction is not None:
                actual = float(sale.total_sales)
                error = prediction - actual
                error_pct = (abs(error) / actual * 100) if actual > 0 else 0
                
                results.append({
                    "date": sale.date.isoformat(),
                    "department_id": str(sale.department_id),
                    "department_name": dept.name,
                    "predicted_sales": round(prediction, 2),
                    "actual_sales": round(actual, 2),
                    "error": round(error, 2),
                    "error_percentage": round(error_pct, 2)
                })
        
        return results
        
    except Exception as e:
        logger.error(f"Error comparing forecasts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error comparing forecasts: {str(e)}"
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
    Export forecasts to CSV file
    
    Query params:
        from_date: Start date
        to_date: End date
        department_id: Optional department filter
        include_actual: Include actual sales for comparison
    """
    try:
        # Get data based on include_actual flag
        if include_actual:
            data = await get_forecast_comparison(from_date, to_date, department_id, db)
            headers = ["Date", "Department ID", "Department Name", "Predicted Sales", "Actual Sales", "Error", "Error %"]
        else:
            data = await get_batch_forecasts(from_date, to_date, department_id, db)
            headers = ["Date", "Department ID", "Department Name", "Predicted Sales"]
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(headers)
        
        # Write data
        for row in data:
            if include_actual:
                writer.writerow([
                    row['date'],
                    row['department_id'],
                    row['department_name'],
                    row['predicted_sales'],
                    row['actual_sales'],
                    row['error'],
                    row['error_percentage']
                ])
            else:
                writer.writerow([
                    row['date'],
                    row['department_id'],
                    row['department_name'],
                    row['predicted_sales']
                ])
        
        # Create response
        output.seek(0)
        filename = f"forecast_{from_date}_to_{to_date}.csv"
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error(f"Error exporting forecasts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting forecasts: {str(e)}"
        )
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, datetime, timedelta
from ..db import get_db
from ..models.branch import SalesSummary as SalesSummaryModel, SalesByHour as SalesByHourModel
from ..schemas.branch import SalesSummary, SalesByHour
from ..services.iiko_sales_loader import IikoSalesLoaderService
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("/summary")
def get_sales_summary(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    department_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Get sales summary data with optional filtering"""
    query = db.query(SalesSummaryModel)
    
    if department_id:
        query = query.filter(SalesSummaryModel.department_id == department_id)
    
    if from_date:
        query = query.filter(SalesSummaryModel.date >= from_date)
    
    if to_date:
        query = query.filter(SalesSummaryModel.date <= to_date)
    
    sales_summary = query.order_by(SalesSummaryModel.date.desc()).offset(skip).limit(limit).all()
    
    # Convert to response format
    result = []
    for sale in sales_summary:
        sale_dict = {
            "id": sale.id,
            "department_id": str(sale.department_id),
            "date": sale.date,
            "total_sales": sale.total_sales,
            "created_at": sale.created_at,
            "updated_at": sale.updated_at,
            "synced_at": sale.synced_at
        }
        result.append(sale_dict)
    
    return result


@router.get("/hourly")
def get_sales_by_hour(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    department_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    hour: Optional[int] = Query(None, ge=0, le=23),
    db: Session = Depends(get_db)
):
    """Get hourly sales data with optional filtering"""
    query = db.query(SalesByHourModel)
    
    if department_id:
        query = query.filter(SalesByHourModel.department_id == department_id)
    
    if from_date:
        query = query.filter(SalesByHourModel.date >= from_date)
    
    if to_date:
        query = query.filter(SalesByHourModel.date <= to_date)
    
    if hour is not None:
        query = query.filter(SalesByHourModel.hour == hour)
    
    sales_by_hour = query.order_by(SalesByHourModel.date.desc(), SalesByHourModel.hour).offset(skip).limit(limit).all()
    
    # Convert to response format
    result = []
    for sale in sales_by_hour:
        sale_dict = {
            "id": sale.id,
            "department_id": str(sale.department_id),
            "date": sale.date,
            "hour": sale.hour,
            "sales_amount": sale.sales_amount,
            "created_at": sale.created_at,
            "updated_at": sale.updated_at,
            "synced_at": sale.synced_at
        }
        result.append(sale_dict)
    
    return result


@router.post("/sync")
async def sync_sales(
    from_date: Optional[date] = Query(None, description="Start date for sync (default: yesterday)"),
    to_date: Optional[date] = Query(None, description="End date for sync (default: same as from_date)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Sync sales data from iiko API"""
    try:
        sales_loader = IikoSalesLoaderService(db)
        
        logger.info(f"API endpoint: Starting sales sync from {from_date} to {to_date}")
        
        # Perform sync
        result = await sales_loader.sync_sales(from_date, to_date)
        
        logger.info(f"API endpoint: Sync completed with status: {result.get('status')}")
        
        # Check if sync failed
        if result.get("status") == "error":
            logger.error(f"API endpoint: Sync failed with error: {result.get('message')}")
            # Return error with detailed information
            return {
                "status": "error",
                "message": result.get("message", "Unknown error occurred"),
                "from_date": from_date,
                "to_date": to_date,
                "summary_records": result.get("summary_records", 0),
                "hourly_records": result.get("hourly_records", 0),
                "total_raw_records": result.get("total_raw_records", 0),
                "details": result.get("details", "No additional details available"),
                "error_type": result.get("error_type", "UnknownError")
            }
        
        # Success case
        return {
            "status": "success",
            "message": result.get("message", "Sync completed successfully"),
            "from_date": from_date,
            "to_date": to_date,
            "summary_records": result.get("summary_records", 0),
            "hourly_records": result.get("hourly_records", 0),
            "total_raw_records": result.get("total_raw_records", 0),
            "details": result.get("details", f"Successfully processed {result.get('total_raw_records', 0)} records")
        }
        
    except Exception as e:
        error_msg = f"API endpoint error: {str(e)}"
        logger.error(f"Critical error in sales sync endpoint: {e}", exc_info=True)
        
        # Return detailed error information instead of raising HTTP exception
        return {
            "status": "error",
            "message": f"Critical system error during sync: {str(e)}",
            "from_date": from_date,
            "to_date": to_date,
            "summary_records": 0,
            "hourly_records": 0,
            "total_raw_records": 0,
            "details": f"A critical error occurred in the API endpoint. Error type: {type(e).__name__}. Please check server logs for more information.",
            "error_type": type(e).__name__
        }


@router.get("/stats")
def get_sales_stats(
    department_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Get sales statistics"""
    try:
        # Summary stats
        summary_query = db.query(SalesSummaryModel)
        if department_id:
            summary_query = summary_query.filter(SalesSummaryModel.department_id == department_id)
        if from_date:
            summary_query = summary_query.filter(SalesSummaryModel.date >= from_date)
        if to_date:
            summary_query = summary_query.filter(SalesSummaryModel.date <= to_date)
        
        summary_count = summary_query.count()
        
        # Hourly stats
        hourly_query = db.query(SalesByHourModel)
        if department_id:
            hourly_query = hourly_query.filter(SalesByHourModel.department_id == department_id)
        if from_date:
            hourly_query = hourly_query.filter(SalesByHourModel.date >= from_date)
        if to_date:
            hourly_query = hourly_query.filter(SalesByHourModel.date <= to_date)
        
        hourly_count = hourly_query.count()
        
        # Get total sales amount
        total_sales = db.query(func.sum(SalesSummaryModel.total_sales)).scalar() or 0
        
        # Get latest sync date
        latest_sync = db.query(func.max(SalesSummaryModel.synced_at)).scalar()
        
        return {
            "summary_records": summary_count,
            "hourly_records": hourly_count,
            "total_sales_amount": float(total_sales),
            "latest_sync": latest_sync,
            "date_range": {
                "from": from_date,
                "to": to_date
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting sales stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sales stats: {str(e)}")


@router.delete("/summary/{record_id}")
def delete_sales_summary(record_id: int, db: Session = Depends(get_db)):
    """Delete a sales summary record"""
    record = db.query(SalesSummaryModel).filter(SalesSummaryModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Sales summary record not found")
    
    db.delete(record)
    db.commit()
    return {"message": f"Sales summary record {record_id} deleted successfully"}


@router.delete("/hourly/{record_id}")
def delete_sales_hourly(record_id: int, db: Session = Depends(get_db)):
    """Delete a sales hourly record"""
    record = db.query(SalesByHourModel).filter(SalesByHourModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Sales hourly record not found")
    
    db.delete(record)
    db.commit()
    return {"message": f"Sales hourly record {record_id} deleted successfully"}
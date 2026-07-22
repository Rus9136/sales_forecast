from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer, text
from typing import List, Optional
from datetime import date, datetime, timedelta
import uuid as uuidlib
from ..db import get_db
from ..models.branch import SalesSummary as SalesSummaryModel, SalesByHour as SalesByHourModel, AutoSyncLog
from ..models.employee import SalesByWaiter as SalesByWaiterModel, Employee as EmployeeModel
from ..schemas.branch import SalesSummary, SalesByHour
from ..services.iiko_sales_loader import IikoSalesLoaderService
from ..services.iiko_waiter_sales_loader import IikoWaiterSalesLoaderService
from ..auth import get_api_key_or_bypass, ApiKey
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
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
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
            "total_sales": sale.total_sales,   # прайс (DishSumInt)
            "total_paid": sale.total_paid,     # к оплате (DishDiscountSumInt); NULL до бэкфилла
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
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
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
            "sales_amount": sale.sales_amount,   # прайс
            "paid_amount": sale.paid_amount,     # к оплате; NULL до бэкфилла
            "created_at": sale.created_at,
            "updated_at": sale.updated_at,
            "synced_at": sale.synced_at
        }
        result.append(sale_dict)

    return result


@router.get("/hourly/heatmap")
def get_sales_hourly_heatmap(
    department_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    """Aggregate hourly sales into a 7x24 grid (day-of-week x hour).

    Returns a fixed-size matrix (Mon..Sun rows, 0..23 cols) so the frontend can
    render directly without zero-filling. Values are total sales sums.
    """
    # PostgreSQL DOW: Sunday=0..Saturday=6. Convert to Monday=0..Sunday=6
    # to match the design (rows: Пн..Вс).
    dow_expr = (func.extract('dow', SalesByHourModel.date).cast(Integer) + 6) % 7

    query = db.query(
        dow_expr.label('dow'),
        SalesByHourModel.hour.label('hour'),
        func.sum(SalesByHourModel.sales_amount).label('total'),
        func.sum(SalesByHourModel.paid_amount).label('total_paid'),
    )

    if department_id:
        query = query.filter(SalesByHourModel.department_id == department_id)
    if from_date:
        query = query.filter(SalesByHourModel.date >= from_date)
    if to_date:
        query = query.filter(SalesByHourModel.date <= to_date)

    rows = query.group_by('dow', SalesByHourModel.hour).all()

    grid = [[0.0 for _ in range(24)] for _ in range(7)]        # прайс
    grid_paid = [[0.0 for _ in range(24)] for _ in range(7)]   # к оплате
    for dow, hour, total, total_paid in rows:
        d = int(dow)
        h = int(hour)
        if 0 <= d < 7 and 0 <= h < 24:
            grid[d][h] = float(total or 0)
            grid_paid[d][h] = float(total_paid or 0)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "department_id": department_id,
        "grid": grid,
        "grid_paid": grid_paid,
    }


@router.get("/checks-hourly")
def get_checks_hourly(
    department_id: str = Query(..., description="Department UUID"),
    from_date: date = Query(..., description="Start date (YYYY-MM-DD), inclusive"),
    to_date: date = Query(..., description="End date (YYYY-MM-DD), inclusive"),
    bucket_by: str = Query(
        "open",
        pattern="^(open|close)$",
        description="Bucket each check by its open hour (`open`, default — when "
                    "guests arrive/are seated) or close hour (`close` — when paid)",
    ),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    """Transactional load per hour: closed checks, line positions, guests, avg check.

    Built for TCO staffing calibration — revenue hides load (a 200k banquet is
    one check, 200k of retail is a queue). Counts come from `receipt` headers.

    - `hour` is 0-23 in Asia/Almaty (stored local; same source as `sales_by_hour`).
      The check is bucketed on its accounting day (`open_date`) by:
      - `bucket_by=open` (default) — hour of `open_time` (when guests are seated;
        better proxy for staffing peaks). Falls back to `close_time` for legacy
        receipts synced before `open_time` was captured (`open_time IS NULL`).
      - `bucket_by=close` — hour of `close_time` (when the check is paid).
    - `items_count` = number of line positions (`receipt.items_count`), not unit qty.
    - `guests_count` = sum of per-receipt guest counts; `null` when no receipt in
      the hour carries guest data.
    - Hours with no checks are omitted (no zero-fill).
    """
    try:
        uuidlib.UUID(department_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="department_id must be a valid UUID")
    if to_date < from_date:
        raise HTTPException(status_code=400, detail="to_date must be >= from_date")
    if (to_date - from_date).days > 31:
        raise HTTPException(status_code=400, detail="Max range is 31 days")

    # Bucketing timestamp: open hour (fallback to close for legacy NULLs) or close hour.
    ts_expr = "COALESCE(open_time, close_time)" if bucket_by == "open" else "close_time"

    rows = db.execute(text(f"""
        SELECT open_date AS date,
               EXTRACT(HOUR FROM {ts_expr})::int AS hour,
               COUNT(*) AS checks_count,
               COALESCE(SUM(items_count), 0) AS items_count,
               SUM(guest_num) AS guests_count,
               AVG(total_sum) AS avg_check,
               AVG(paid_sum) AS avg_check_paid
        FROM receipt
        WHERE department_id = CAST(:dept AS uuid)
          AND open_date BETWEEN :from_date AND :to_date
        GROUP BY open_date, EXTRACT(HOUR FROM {ts_expr})
        ORDER BY open_date, hour
    """), {"dept": department_id, "from_date": from_date, "to_date": to_date}).fetchall()

    return [
        {
            "date": str(r.date),
            "hour": int(r.hour),
            "checks_count": int(r.checks_count),
            "items_count": int(r.items_count),
            "guests_count": int(r.guests_count) if r.guests_count is not None else None,
            "avg_check": round(float(r.avg_check), 2) if r.avg_check is not None else None,
            "avg_check_paid": round(float(r.avg_check_paid), 2) if r.avg_check_paid is not None else None,
        }
        for r in rows
    ]


@router.post("/sync")
async def sync_sales(
    from_date: Optional[date] = Query(None, description="Start date for sync (default: yesterday)"),
    to_date: Optional[date] = Query(None, description="End date for sync (default: same as from_date)"),
    department_id: Optional[str] = Query(None, description="Department ID to sync (default: all departments)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Sync sales data from iiko API"""
    try:
        sales_loader = IikoSalesLoaderService(db)

        logger.info(f"API endpoint: Starting sales sync from {from_date} to {to_date}, department_id={department_id}")

        # Perform sync
        result = await sales_loader.sync_sales(from_date, to_date, department_id)
        
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
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
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
        
        # Get total sales amount (прайс + к оплате)
        total_sales = db.query(func.sum(SalesSummaryModel.total_sales)).scalar() or 0
        total_paid = db.query(func.sum(SalesSummaryModel.total_paid)).scalar() or 0

        # Get latest sync date
        latest_sync = db.query(func.max(SalesSummaryModel.synced_at)).scalar()

        return {
            "summary_records": summary_count,
            "hourly_records": hourly_count,
            "total_sales_amount": float(total_sales),
            "total_paid_amount": float(total_paid),
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
def delete_sales_summary(
    record_id: int, 
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Delete a sales summary record"""
    record = db.query(SalesSummaryModel).filter(SalesSummaryModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Sales summary record not found")
    
    db.delete(record)
    db.commit()
    return {"message": f"Sales summary record {record_id} deleted successfully"}


@router.delete("/hourly/{record_id}")
def delete_sales_hourly(
    record_id: int, 
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Delete a sales hourly record"""
    record = db.query(SalesByHourModel).filter(SalesByHourModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Sales hourly record not found")
    
    db.delete(record)
    db.commit()
    return {"message": f"Sales hourly record {record_id} deleted successfully"}


@router.get("/by-waiter")
def get_sales_by_waiter(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    department_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    waiter_name: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    """Get sales aggregated by waiter."""
    query = db.query(SalesByWaiterModel)
    if department_id:
        query = query.filter(SalesByWaiterModel.department_id == department_id)
    if employee_id:
        query = query.filter(SalesByWaiterModel.employee_id == employee_id)
    if waiter_name:
        query = query.filter(SalesByWaiterModel.waiter_name.ilike(f"%{waiter_name}%"))
    if from_date:
        query = query.filter(SalesByWaiterModel.date >= from_date)
    if to_date:
        query = query.filter(SalesByWaiterModel.date <= to_date)

    rows = (
        query.order_by(SalesByWaiterModel.date.desc(), SalesByWaiterModel.waiter_name)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "department_id": str(row.department_id),
            "date": row.date,
            "waiter_name": row.waiter_name,
            "employee_id": str(row.employee_id) if row.employee_id else None,
            "total_sales": row.total_sales,
            "total_sales_with_discount": row.total_sales_with_discount,
            "synced_at": row.synced_at,
        }
        for row in rows
    ]


@router.get("/avg-check-by-waiter")
def get_avg_check_by_waiter(
    department_id: Optional[str] = Query(None, description="Department UUID (optional)"),
    from_date: date = Query(..., description="Start date (YYYY-MM-DD), inclusive"),
    to_date: date = Query(..., description="End date (YYYY-MM-DD), inclusive"),
    waiter_name: Optional[str] = Query(None, description="Filter by waiter name (ILIKE)"),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    """Average check per waiter, computed from `receipt` headers.

    Unlike `sales_by_waiter` (revenue only), this aggregates real check headers,
    so it can divide revenue by check count.

    - `avg_check` = AVG(total_sum) over closed checks in range.
    - `avg_per_guest` = revenue / total guests; `null` when no receipts carry
      guest data.
    - Checks are bucketed by accounting day (`open_date`) for partition pruning.
    - Ordered by revenue desc.
    """
    if department_id is not None:
        try:
            uuidlib.UUID(department_id)
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(status_code=400, detail="department_id must be a valid UUID")
    if to_date < from_date:
        raise HTTPException(status_code=400, detail="to_date must be >= from_date")

    rows = db.execute(text("""
        SELECT waiter_name,
               MAX(CAST(waiter_employee_id AS text)) AS employee_id,
               COUNT(*) AS checks_count,
               SUM(total_sum) AS revenue,
               AVG(total_sum) AS avg_check,
               SUM(paid_sum) AS revenue_paid,
               AVG(paid_sum) AS avg_check_paid,
               SUM(guest_num) AS guests_count
        FROM receipt
        WHERE open_date BETWEEN :from_date AND :to_date
          AND (:dept IS NULL OR department_id = CAST(:dept AS uuid))
          AND (:wname IS NULL OR waiter_name ILIKE :wname_like)
        GROUP BY waiter_name
        ORDER BY revenue DESC
    """), {
        "from_date": from_date,
        "to_date": to_date,
        "dept": department_id,
        "wname": waiter_name,
        "wname_like": f"%{waiter_name}%" if waiter_name else None,
    }).fetchall()

    return [
        {
            "waiter_name": r.waiter_name,
            "employee_id": r.employee_id,
            "checks_count": int(r.checks_count),
            "revenue": round(float(r.revenue), 2) if r.revenue is not None else 0.0,
            "avg_check": round(float(r.avg_check), 2) if r.avg_check is not None else None,
            "revenue_paid": round(float(r.revenue_paid), 2) if r.revenue_paid is not None else 0.0,
            "avg_check_paid": round(float(r.avg_check_paid), 2) if r.avg_check_paid is not None else None,
            "guests_count": int(r.guests_count) if r.guests_count is not None else None,
            "avg_per_guest": (
                round(float(r.revenue) / float(r.guests_count), 2)
                if r.guests_count and float(r.guests_count) > 0 and r.revenue is not None
                else None
            ),
        }
        for r in rows
    ]


@router.post("/sync-waiters")
async def sync_waiter_sales(
    from_date: Optional[date] = Query(None, description="Start date (default: yesterday)"),
    to_date: Optional[date] = Query(None, description="End date (default: same as from_date)"),
    department_id: Optional[str] = Query(None, description="Filter by Department.Id"),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    """Sync per-waiter sales data from iiko OLAP."""
    loader = IikoWaiterSalesLoaderService(db)
    result = await loader.sync(from_date, to_date, department_id)
    result["from_date"] = from_date
    result["to_date"] = to_date
    return result


@router.get("/auto-sync/status")
def get_auto_sync_status(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get automatic sync logs and status"""
    try:
        # Get recent auto sync logs
        logs = db.query(AutoSyncLog).order_by(AutoSyncLog.executed_at.desc()).offset(skip).limit(limit).all()
        
        # Get latest successful sync
        latest_success = db.query(AutoSyncLog).filter(
            AutoSyncLog.status == 'success'
        ).order_by(AutoSyncLog.executed_at.desc()).first()
        
        # Get latest failed sync
        latest_error = db.query(AutoSyncLog).filter(
            AutoSyncLog.status == 'error'
        ).order_by(AutoSyncLog.executed_at.desc()).first()
        
        # Count success vs error syncs in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        success_count = db.query(AutoSyncLog).filter(
            AutoSyncLog.status == 'success',
            AutoSyncLog.executed_at >= thirty_days_ago
        ).count()
        
        error_count = db.query(AutoSyncLog).filter(
            AutoSyncLog.status == 'error',
            AutoSyncLog.executed_at >= thirty_days_ago
        ).count()
        
        # Convert logs to response format
        log_list = []
        for log in logs:
            log_dict = {
                "id": log.id,
                "sync_date": log.sync_date,
                "sync_type": log.sync_type,
                "status": log.status,
                "message": log.message,
                "summary_records": log.summary_records,
                "hourly_records": log.hourly_records,
                "total_raw_records": log.total_raw_records,
                "error_details": log.error_details,
                "executed_at": log.executed_at,
                "created_at": log.created_at
            }
            log_list.append(log_dict)
        
        return {
            "logs": log_list,
            "statistics": {
                "total_logs": len(log_list),
                "success_count_30d": success_count,
                "error_count_30d": error_count,
                "success_rate_30d": round((success_count / (success_count + error_count)) * 100, 1) if (success_count + error_count) > 0 else 0,
                "latest_success": {
                    "date": latest_success.sync_date if latest_success else None,
                    "executed_at": latest_success.executed_at if latest_success else None,
                    "message": latest_success.message if latest_success else None,
                    "records": latest_success.summary_records + latest_success.hourly_records if latest_success else 0
                } if latest_success else None,
                "latest_error": {
                    "date": latest_error.sync_date if latest_error else None,
                    "executed_at": latest_error.executed_at if latest_error else None,
                    "message": latest_error.message if latest_error else None,
                    "error_details": latest_error.error_details if latest_error else None
                } if latest_error else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting auto sync status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get auto sync status: {str(e)}")


@router.post("/auto-sync/test")
async def test_auto_sync(
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Test automatic sync function (for debugging)"""
    try:
        from ..services.scheduled_sales_loader import run_auto_sync
        
        logger.info("Manual test of auto-sync function triggered")
        result = run_auto_sync()
        
        return {
            "message": "Auto-sync test completed",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error testing auto sync: {e}")
        return {
            "status": "error",
            "message": f"Failed to test auto sync: {str(e)}"
        }
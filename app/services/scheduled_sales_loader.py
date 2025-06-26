import asyncio
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from ..db import get_db
from .iiko_sales_loader import IikoSalesLoaderService
from ..models.branch import AutoSyncLog
import logging

logger = logging.getLogger(__name__)


class ScheduledSalesLoaderService:
    """Service for automated sales data loading"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def auto_load_sales(self) -> dict:
        """
        Automatically load sales data for the previous day
        This method is called by the scheduler
        """
        db: Session = next(get_db())
        
        try:
            # Calculate date range (previous day) 
            # iiko API requires different from_date and to_date (409 error if same)
            yesterday = date.today() - timedelta(days=1)
            from_date = yesterday
            # Use today as to_date to avoid 409 error
            to_date = date.today()
            
            self.logger.info(f"Starting automatic sales sync for {from_date}")
            
            # Create sales loader service
            sales_loader = IikoSalesLoaderService(db)
            
            # Perform sync
            result = await sales_loader.sync_sales(from_date, to_date)
            
            # Log the auto-sync attempt
            self._log_auto_sync(db, from_date, to_date, result)
            
            if result.get("status") == "success":
                self.logger.info(f"Automatic sales sync completed successfully: {result.get('message')}")
                self.logger.info(f"Records synced - Summary: {result.get('summary_records', 0)}, Hourly: {result.get('hourly_records', 0)}")
            else:
                self.logger.error(f"Automatic sales sync failed: {result.get('message')}")
                
            return result
            
        except Exception as e:
            error_msg = f"Critical error in automatic sales sync: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            
            # Log the failed attempt
            error_result = {
                "status": "error",
                "message": error_msg,
                "summary_records": 0,
                "hourly_records": 0,
                "total_raw_records": 0,
                "error_type": type(e).__name__
            }
            self._log_auto_sync(db, yesterday, yesterday, error_result)
            
            return error_result
        
        finally:
            db.close()
    
    def _log_auto_sync(self, db: Session, from_date: date, to_date: date, result: dict):
        """Log automatic sync attempt to database"""
        try:
            log_entry = AutoSyncLog(
                sync_date=from_date,
                sync_type="daily_auto",
                status=result.get("status", "unknown"),
                message=result.get("message", "No message"),
                summary_records=result.get("summary_records", 0),
                hourly_records=result.get("hourly_records", 0),
                total_raw_records=result.get("total_raw_records", 0),
                error_details=result.get("details") if result.get("status") == "error" else None,
                executed_at=datetime.utcnow()
            )
            
            db.add(log_entry)
            db.commit()
            
            self.logger.info(f"Auto-sync log entry created for {from_date}")
            
        except Exception as e:
            self.logger.error(f"Failed to log auto-sync attempt: {e}")
            db.rollback()


# Global instance for scheduler
scheduled_loader = ScheduledSalesLoaderService()


def run_auto_sync():
    """
    Wrapper function for scheduler to run async auto_load_sales
    This function will be called by APScheduler
    """
    logger.info("Scheduler triggered: Starting automatic sales sync")
    
    try:
        # Check if there's already a running event loop
        try:
            # If we're in an async context, we need to handle it differently
            existing_loop = asyncio.get_running_loop()
            logger.warning("Event loop already running, creating new thread for sync")
            
            import threading
            import concurrent.futures
            
            def sync_in_thread():
                # Create new event loop in thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(scheduled_loader.auto_load_sales())
                finally:
                    new_loop.close()
            
            # Run in separate thread
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(sync_in_thread)
                result = future.result(timeout=300)  # 5 minute timeout
                
        except RuntimeError:
            # No event loop running, safe to create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(scheduled_loader.auto_load_sales())
            finally:
                loop.close()
        
        logger.info(f"Automatic sync completed with status: {result.get('status')}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to run automatic sync: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Scheduler execution failed: {str(e)}",
            "summary_records": 0,
            "hourly_records": 0,
            "total_raw_records": 0
        }
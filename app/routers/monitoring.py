"""
Model Monitoring and Retraining API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel
import logging

from ..db import get_db
from ..services.model_monitoring_service import get_model_monitoring_service
from ..services.model_retraining_service import model_retrainer
from ..auth import get_api_key_or_bypass, ApiKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["model-monitoring"])


class ManualRetrainRequest(BaseModel):
    reason: Optional[str] = "Manual trigger via API"
    force_deploy: Optional[bool] = False
    performance_threshold: Optional[float] = 10.0


@router.get("/health")
async def get_model_health(
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Get comprehensive model health status
    
    Returns:
        Model health checks and overall status
    """
    try:
        monitoring_service = get_model_monitoring_service()
        health_status = monitoring_service.check_model_health(db)
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error checking model health: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking model health: {str(e)}"
        )


@router.get("/performance/summary")
async def get_performance_summary(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Get model performance summary for the specified period
    
    Args:
        days: Number of days to analyze (1-365)
        
    Returns:
        Performance metrics and time series data
    """
    try:
        monitoring_service = get_model_monitoring_service()
        summary = monitoring_service.get_performance_summary(days=days, db=db)
        
        return summary
        
    except Exception as e:
        logger.error(f"Error getting performance summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting performance summary: {str(e)}"
        )


@router.post("/performance/calculate-daily")
async def calculate_daily_metrics(
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Calculate and store daily performance metrics
    
    Args:
        target_date: Date to calculate metrics for (default: yesterday)
        
    Returns:
        Calculated daily metrics
    """
    try:
        monitoring_service = get_model_monitoring_service()
        metrics = await monitoring_service.calculate_daily_metrics(target_date)
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error calculating daily metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating daily metrics: {str(e)}"
        )


@router.post("/retrain/manual")
async def trigger_manual_retrain(
    request: ManualRetrainRequest = ManualRetrainRequest(),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Manually trigger model retraining
    
    Args:
        request: Retraining configuration
        
    Returns:
        Retraining results and deployment decision
    """
    try:
        logger.info(f"Manual retraining triggered. Reason: {request.reason}")
        
        result = await model_retrainer.auto_retrain_model(
            trigger_type='manual',
            trigger_details={
                'reason': request.reason,
                'force_deploy': request.force_deploy,
                'triggered_at': datetime.utcnow().isoformat()
            },
            performance_threshold=request.performance_threshold
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in manual retraining: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in manual retraining: {str(e)}"
        )


@router.get("/retrain/status")
async def get_retrain_status(
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Get the current retraining schedule and last execution status
    
    Returns:
        Retraining schedule information and history
    """
    try:
        # Get scheduler info
        from ..main import scheduler
        
        jobs = []
        for job in scheduler.get_jobs():
            if 'retrain' in job.id:
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                })
        
        # TODO: Get last retrain info from database when tables are created
        last_retrain = {
            'status': 'No retraining history available',
            'message': 'Model retraining log table not yet implemented'
        }
        
        return {
            'scheduled_jobs': jobs,
            'last_retrain': last_retrain,
            'current_time': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting retrain status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting retrain status: {str(e)}"
        )


@router.get("/alerts/recent")
async def get_recent_alerts(
    days: int = Query(7, ge=1, le=30, description="Number of days to check"),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Get recent model performance alerts
    
    Args:
        days: Number of days to check for alerts (1-30)
        
    Returns:
        List of recent alerts and their details
    """
    try:
        monitoring_service = get_model_monitoring_service()
        
        # Calculate metrics for recent days to check for alerts
        alerts_summary = []
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        current_date = start_date
        while current_date <= end_date:
            try:
                metrics = await monitoring_service.calculate_daily_metrics(current_date)
                if metrics.get('has_alerts'):
                    alerts_summary.append({
                        'date': current_date.isoformat(),
                        'alerts': metrics.get('alerts', []),
                        'daily_mape': metrics.get('daily_mape', 0)
                    })
            except:
                # Skip if no data for that date
                pass
            
            current_date += timedelta(days=1)
        
        # Get current health status
        health = monitoring_service.check_model_health(db)
        
        return {
            'period_days': days,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'current_health': health.get('overall_status'),
            'daily_alerts': alerts_summary,
            'total_alert_days': len(alerts_summary)
        }
        
    except Exception as e:
        logger.error(f"Error getting recent alerts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting recent alerts: {str(e)}"
        )


@router.get("/comparison/models")
async def get_model_comparison(
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Get comparison between current and previous model versions
    
    Returns:
        Comparison metrics between model versions
    """
    try:
        # TODO: Implement when model versioning table is created
        return {
            'status': 'not_implemented',
            'message': 'Model versioning comparison will be available after database migration',
            'current_model': {
                'version': 'v_20250630_current',
                'test_mape': 4.92,
                'features': 61,
                'training_samples': 7491
            }
        }
        
    except Exception as e:
        logger.error(f"Error comparing models: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error comparing models: {str(e)}"
        )
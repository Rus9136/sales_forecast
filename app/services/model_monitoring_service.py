"""
Model Monitoring Service

This service continuously monitors model performance and triggers
alerts when degradation is detected.
"""

import json
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc, text
from typing import Optional, Dict, List, Tuple, Any
import logging
import numpy as np

from ..db import get_db
from ..models.branch import Department, SalesSummary, ForecastAccuracyLog, Forecast
from ..agents.sales_forecaster_agent import get_forecaster_agent
from .error_analysis_service import ErrorAnalysisService

logger = logging.getLogger(__name__)


class ModelMonitoringService:
    """Service for continuous model performance monitoring"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Alert thresholds
        self.mape_warning_threshold = 10.0
        self.mape_critical_threshold = 15.0
        self.degradation_threshold = 20.0  # 20% increase in error
    
    async def calculate_daily_metrics(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Calculate daily performance metrics for the model
        
        Args:
            target_date: Date to calculate metrics for (default: yesterday)
            
        Returns:
            Dict with daily metrics and any alerts
        """
        db: Session = next(get_db())
        
        try:
            # Default to yesterday if no date specified
            if not target_date:
                target_date = date.today() - timedelta(days=1)
            
            self.logger.info(f"Calculating daily metrics for {target_date}")
            
            # 1. Get all forecasts and actuals for the date using raw SQL to handle UUID casting
            forecasts_actuals = db.execute(text("""
                SELECT 
                    f.branch_id,
                    f.predicted_amount,
                    s.total_sales as actual_amount,
                    d.name as branch_name
                FROM forecasts f
                JOIN sales_summary s ON CAST(f.branch_id AS UUID) = s.department_id 
                    AND f.forecast_date = s.date
                JOIN departments d ON CAST(f.branch_id AS UUID) = d.id
                WHERE f.forecast_date = :target_date
            """), {"target_date": target_date}).fetchall()
            
            if not forecasts_actuals:
                self.logger.warning(f"No forecast/actual pairs found for {target_date}")
                return {
                    "date": target_date.isoformat(),
                    "status": "no_data",
                    "message": "No predictions found for this date"
                }
            
            # 2. Calculate metrics
            errors = []
            mapes = []
            branch_errors = {}
            
            for fa in forecasts_actuals:
                if fa.actual_amount > 0:
                    error = fa.predicted_amount - fa.actual_amount
                    mape = (abs(error) / fa.actual_amount) * 100
                    
                    errors.append(error)
                    mapes.append(mape)
                    
                    branch_errors[str(fa.branch_id)] = {
                        "name": fa.branch_name,
                        "mape": mape,
                        "error": error,
                        "predicted": fa.predicted_amount,
                        "actual": fa.actual_amount
                    }
                    
                    # Update accuracy log
                    self._update_accuracy_log(
                        db, fa.branch_id, target_date, 
                        fa.predicted_amount, fa.actual_amount,
                        abs(error), mape
                    )
            
            # 3. Calculate aggregated metrics
            daily_metrics = {
                "date": target_date.isoformat(),
                "daily_mape": np.mean(mapes) if mapes else 0.0,
                "daily_mae": np.mean(np.abs(errors)) if errors else 0.0,
                "daily_rmse": np.sqrt(np.mean(np.square(errors))) if errors else 0.0,
                "daily_predictions_count": len(mapes),
                "prediction_bias": np.mean(errors) if errors else 0.0,  # >0 means over-predicting
                "mape_std": np.std(mapes) if mapes else 0.0
            }
            
            # 4. Find best and worst performing branches
            if branch_errors:
                sorted_branches = sorted(branch_errors.items(), key=lambda x: x[1]['mape'])
                best_branch = sorted_branches[0]
                worst_branch = sorted_branches[-1]
                
                daily_metrics.update({
                    "best_branch_id": best_branch[0],
                    "best_branch_name": best_branch[1]['name'],
                    "best_branch_mape": best_branch[1]['mape'],
                    "worst_branch_id": worst_branch[0],
                    "worst_branch_name": worst_branch[1]['name'],
                    "worst_branch_mape": worst_branch[1]['mape']
                })
            
            # 5. Calculate trend (compare to last 7 days)
            trend_metrics = self._calculate_trend_metrics(db, target_date, daily_metrics['daily_mape'])
            daily_metrics.update(trend_metrics)
            
            # 6. Check for alerts
            alerts = self._check_for_alerts(daily_metrics, branch_errors)
            daily_metrics['alerts'] = alerts
            daily_metrics['has_alerts'] = len(alerts) > 0
            
            # 7. Get model info
            forecaster = get_forecaster_agent()
            model_info = forecaster.get_model_info()
            daily_metrics['model_version'] = model_info.get('training_date', 'unknown')
            
            # 8. Save metrics (would save to model_performance_metrics table)
            self._save_daily_metrics(db, daily_metrics)
            
            self.logger.info(f"Daily metrics calculated: MAPE={daily_metrics['daily_mape']:.2f}%, "
                           f"Predictions={daily_metrics['daily_predictions_count']}")
            
            return daily_metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating daily metrics: {str(e)}", exc_info=True)
            return {
                "date": target_date.isoformat() if target_date else "unknown",
                "status": "error",
                "message": str(e)
            }
        
        finally:
            db.close()
    
    def get_performance_summary(
        self, 
        days: int = 30,
        db: Session = None
    ) -> Dict[str, Any]:
        """Get performance summary for the last N days"""
        if not db:
            db = next(get_db())
            close_db = True
        else:
            close_db = False
        
        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=days)
            
            # Get accuracy logs
            accuracy_data = db.query(
                func.date(ForecastAccuracyLog.forecast_date).label('date'),
                func.avg(ForecastAccuracyLog.mape).label('avg_mape'),
                func.count(ForecastAccuracyLog.id).label('count'),
                func.stddev(ForecastAccuracyLog.mape).label('mape_std')
            ).filter(
                and_(
                    ForecastAccuracyLog.forecast_date >= start_date,
                    ForecastAccuracyLog.forecast_date <= end_date,
                    ForecastAccuracyLog.mape.isnot(None)
                )
            ).group_by(
                func.date(ForecastAccuracyLog.forecast_date)
            ).order_by(
                func.date(ForecastAccuracyLog.forecast_date)
            ).all()
            
            # Convert to time series
            time_series = []
            overall_mapes = []
            
            for row in accuracy_data:
                time_series.append({
                    "date": row.date.isoformat(),
                    "mape": round(row.avg_mape, 2),
                    "predictions": row.count,
                    "mape_std": round(row.mape_std, 2) if row.mape_std else 0
                })
                overall_mapes.append(row.avg_mape)
            
            # Calculate summary statistics
            if overall_mapes:
                summary = {
                    "period_days": days,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "avg_mape": round(np.mean(overall_mapes), 2),
                    "min_mape": round(np.min(overall_mapes), 2),
                    "max_mape": round(np.max(overall_mapes), 2),
                    "mape_trend": self._calculate_linear_trend(overall_mapes),
                    "days_above_warning": sum(1 for m in overall_mapes if m > self.mape_warning_threshold),
                    "days_above_critical": sum(1 for m in overall_mapes if m > self.mape_critical_threshold),
                    "time_series": time_series
                }
            else:
                summary = {
                    "period_days": days,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "status": "no_data",
                    "message": "No performance data available for this period"
                }
            
            # Add current model info
            forecaster = get_forecaster_agent()
            model_info = forecaster.get_model_info()
            summary['current_model'] = {
                "version": model_info.get('training_date', 'unknown'),
                "status": model_info.get('status', 'unknown'),
                "features": model_info.get('n_features', 0)
            }
            
            return summary
            
        finally:
            if close_db:
                db.close()
    
    def check_model_health(self, db: Session = None) -> Dict[str, Any]:
        """
        Comprehensive model health check
        
        Returns:
            Dict with health status and any issues found
        """
        if not db:
            db = next(get_db())
            close_db = True
        else:
            close_db = False
        
        try:
            health_checks = []
            overall_status = "healthy"
            
            # 1. Check recent performance
            recent_performance = self.get_performance_summary(days=7, db=db)
            if recent_performance.get('avg_mape', 0) > self.mape_critical_threshold:
                health_checks.append({
                    "check": "recent_performance",
                    "status": "critical",
                    "message": f"Recent MAPE ({recent_performance['avg_mape']}%) exceeds critical threshold"
                })
                overall_status = "critical"
            elif recent_performance.get('avg_mape', 0) > self.mape_warning_threshold:
                health_checks.append({
                    "check": "recent_performance",
                    "status": "warning",
                    "message": f"Recent MAPE ({recent_performance['avg_mape']}%) exceeds warning threshold"
                })
                if overall_status == "healthy":
                    overall_status = "warning"
            else:
                health_checks.append({
                    "check": "recent_performance",
                    "status": "healthy",
                    "message": f"Recent MAPE ({recent_performance.get('avg_mape', 0)}%) is acceptable"
                })
            
            # 2. Check performance trend
            if recent_performance.get('mape_trend', 0) > 0.5:  # Increasing by >0.5% per day
                health_checks.append({
                    "check": "performance_trend",
                    "status": "warning",
                    "message": "Model performance is degrading over time"
                })
                if overall_status == "healthy":
                    overall_status = "warning"
            else:
                health_checks.append({
                    "check": "performance_trend",
                    "status": "healthy",
                    "message": "Model performance is stable"
                })
            
            # 3. Check model age
            forecaster = get_forecaster_agent()
            model_info = forecaster.get_model_info()
            model_age = self._calculate_model_age(model_info)
            
            if model_age > 60:  # Older than 60 days
                health_checks.append({
                    "check": "model_age",
                    "status": "warning",
                    "message": f"Model is {model_age} days old, consider retraining"
                })
                if overall_status == "healthy":
                    overall_status = "warning"
            else:
                health_checks.append({
                    "check": "model_age",
                    "status": "healthy",
                    "message": f"Model age ({model_age} days) is acceptable"
                })
            
            # 4. Check problematic branches
            error_service = ErrorAnalysisService(db)
            problematic_branches = error_service.identify_problematic_branches(
                from_date=date.today() - timedelta(days=7),
                to_date=date.today(),
                mape_threshold=20.0
            )
            
            if len(problematic_branches) > 5:
                health_checks.append({
                    "check": "problematic_branches",
                    "status": "warning",
                    "message": f"{len(problematic_branches)} branches have MAPE > 20%"
                })
                if overall_status == "healthy":
                    overall_status = "warning"
            else:
                health_checks.append({
                    "check": "problematic_branches",
                    "status": "healthy",
                    "message": f"Only {len(problematic_branches)} problematic branches"
                })
            
            # 5. Check data freshness
            latest_sales = db.query(func.max(SalesSummary.date)).scalar()
            if latest_sales:
                days_behind = (date.today() - latest_sales).days
                if days_behind > 2:
                    health_checks.append({
                        "check": "data_freshness",
                        "status": "warning",
                        "message": f"Sales data is {days_behind} days behind"
                    })
                    if overall_status == "healthy":
                        overall_status = "warning"
                else:
                    health_checks.append({
                        "check": "data_freshness",
                        "status": "healthy",
                        "message": "Sales data is up to date"
                    })
            
            return {
                "overall_status": overall_status,
                "check_time": datetime.utcnow().isoformat(),
                "health_checks": health_checks,
                "summary": {
                    "recent_mape": recent_performance.get('avg_mape', 0),
                    "model_age_days": model_age,
                    "problematic_branches_count": len(problematic_branches)
                }
            }
            
        finally:
            if close_db:
                db.close()
    
    def _update_accuracy_log(
        self, 
        db: Session, 
        branch_id: str, 
        forecast_date: date,
        predicted: float, 
        actual: float, 
        mae: float, 
        mape: float
    ):
        """Update or create accuracy log entry"""
        try:
            # Check if entry exists
            existing = db.query(ForecastAccuracyLog).filter(
                and_(
                    ForecastAccuracyLog.branch_id == branch_id,
                    ForecastAccuracyLog.forecast_date == forecast_date
                )
            ).first()
            
            if existing:
                # Update existing
                existing.actual_amount = actual
                existing.mae = mae
                existing.mape = mape
            else:
                # Create new
                new_log = ForecastAccuracyLog(
                    branch_id=branch_id,
                    forecast_date=forecast_date,
                    predicted_amount=predicted,
                    actual_amount=actual,
                    mae=mae,
                    mape=mape
                )
                db.add(new_log)
            
            db.commit()
            
        except Exception as e:
            self.logger.error(f"Error updating accuracy log: {e}")
            db.rollback()
    
    def _calculate_trend_metrics(
        self, 
        db: Session, 
        target_date: date, 
        current_mape: float
    ) -> Dict[str, float]:
        """Calculate trend metrics compared to previous period"""
        # Get last 7 days average
        week_ago = target_date - timedelta(days=7)
        
        prev_week_avg = db.query(
            func.avg(ForecastAccuracyLog.mape)
        ).filter(
            and_(
                ForecastAccuracyLog.forecast_date >= week_ago,
                ForecastAccuracyLog.forecast_date < target_date,
                ForecastAccuracyLog.mape.isnot(None)
            )
        ).scalar()
        
        if prev_week_avg:
            mape_trend = current_mape - prev_week_avg
            trend_percent = (mape_trend / prev_week_avg * 100) if prev_week_avg > 0 else 0
        else:
            mape_trend = 0
            trend_percent = 0
        
        return {
            "mape_trend": mape_trend,
            "trend_percent": trend_percent,
            "prev_week_avg_mape": prev_week_avg or 0
        }
    
    def _check_for_alerts(
        self, 
        daily_metrics: Dict, 
        branch_errors: Dict
    ) -> List[Dict[str, Any]]:
        """Check for various alert conditions"""
        alerts = []
        
        # 1. Overall MAPE alerts
        daily_mape = daily_metrics.get('daily_mape', 0)
        if daily_mape > self.mape_critical_threshold:
            alerts.append({
                "type": "critical",
                "category": "overall_performance",
                "message": f"Critical: Daily MAPE ({daily_mape:.1f}%) exceeds threshold",
                "value": daily_mape
            })
        elif daily_mape > self.mape_warning_threshold:
            alerts.append({
                "type": "warning",
                "category": "overall_performance",
                "message": f"Warning: Daily MAPE ({daily_mape:.1f}%) is high",
                "value": daily_mape
            })
        
        # 2. Degradation alerts
        trend_percent = daily_metrics.get('trend_percent', 0)
        if trend_percent > self.degradation_threshold:
            alerts.append({
                "type": "warning",
                "category": "degradation",
                "message": f"Model degrading: {trend_percent:.1f}% worse than last week",
                "value": trend_percent
            })
        
        # 3. Branch-specific alerts
        critical_branches = [
            (bid, info) for bid, info in branch_errors.items() 
            if info['mape'] > 30.0  # 30% MAPE threshold for branches
        ]
        
        if len(critical_branches) > 3:
            alerts.append({
                "type": "warning",
                "category": "branch_performance",
                "message": f"{len(critical_branches)} branches have MAPE > 30%",
                "branches": [b[1]['name'] for b in critical_branches[:5]]  # Top 5
            })
        
        # 4. Bias alert
        bias = daily_metrics.get('prediction_bias', 0)
        if abs(bias) > 10000:  # Significant systematic bias
            direction = "over-predicting" if bias > 0 else "under-predicting"
            alerts.append({
                "type": "info",
                "category": "prediction_bias",
                "message": f"Model is systematically {direction} by {abs(bias):.0f} on average",
                "value": bias
            })
        
        return alerts
    
    def _calculate_linear_trend(self, values: List[float]) -> float:
        """Calculate linear trend (slope) of values"""
        if len(values) < 2:
            return 0.0
        
        x = np.arange(len(values))
        y = np.array(values)
        
        # Simple linear regression
        n = len(values)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x)**2)
        
        return float(slope)
    
    def _calculate_model_age(self, model_info: Dict) -> int:
        """Calculate model age in days"""
        try:
            if 'training_date' in model_info:
                training_date_str = model_info['training_date']
                if isinstance(training_date_str, str):
                    # Parse various date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                        try:
                            training_date = datetime.strptime(training_date_str.split('.')[0], fmt)
                            return (datetime.utcnow() - training_date).days
                        except:
                            continue
        except:
            pass
        
        return 0
    
    def _save_daily_metrics(self, db: Session, metrics: Dict):
        """Save daily metrics to database"""
        # This would save to model_performance_metrics table when created
        # For now, just log
        self.logger.info(f"Daily metrics: MAPE={metrics.get('daily_mape', 0):.2f}%, "
                        f"Predictions={metrics.get('daily_predictions_count', 0)}, "
                        f"Alerts={len(metrics.get('alerts', []))}")


def get_model_monitoring_service() -> ModelMonitoringService:
    """Factory function to get ModelMonitoringService instance"""
    return ModelMonitoringService()
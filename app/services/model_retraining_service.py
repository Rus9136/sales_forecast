"""
Model Retraining Service

This service handles automatic model retraining with versioning,
performance comparison, and deployment decisions.
"""

import asyncio
import os
import json
import pickle
import shutil
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import Optional, Dict, List, Tuple, Any
import logging
import traceback
import uuid
from pathlib import Path

from ..db import get_db
from ..models.branch import Department, SalesSummary, ForecastAccuracyLog, ModelVersion, ModelRetrainingLog
from ..agents.sales_forecaster_agent import get_forecaster_agent, SalesForecasterAgent
from .training_service import TrainingDataService
from .error_analysis_service import ErrorAnalysisService

logger = logging.getLogger(__name__)


class ModelRetrainingService:
    """Service for automatic model retraining with versioning"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.models_dir = Path("models")
        self.models_dir.mkdir(exist_ok=True)
        self.archive_dir = self.models_dir / "archive"
        self.archive_dir.mkdir(exist_ok=True)
    
    async def auto_retrain_model(
        self,
        trigger_type: str = 'scheduled',
        trigger_details: Optional[Dict] = None,
        performance_threshold: float = 10.0  # MAPE threshold for deployment
    ) -> Dict[str, Any]:
        """
        Automatically retrain model and decide whether to deploy
        
        Args:
            trigger_type: Type of trigger ('scheduled', 'manual', 'performance_degradation')
            trigger_details: Additional details about the trigger
            performance_threshold: Maximum acceptable MAPE improvement threshold
            
        Returns:
            Dict with retraining results and deployment decision
        """
        db: Session = next(get_db())
        retrain_start = datetime.utcnow()
        
        try:
            self.logger.info(f"Starting automatic model retraining. Trigger: {trigger_type}")
            
            # 1. Get current model performance
            current_performance = await self._get_current_model_performance(db)
            current_version = current_performance.get('version_id', 'unknown')
            current_mape = current_performance.get('recent_mape', float('inf'))
            
            self.logger.info(f"Current model version: {current_version}, Recent MAPE: {current_mape:.2f}%")
            
            # 2. Check if retraining is needed
            if not self._should_retrain(current_performance, trigger_type):
                self.logger.info("Retraining skipped - performance is acceptable")
                return {
                    "status": "skipped",
                    "message": "Model performance is within acceptable range",
                    "current_version": current_version,
                    "current_mape": current_mape
                }
            
            # 3. Prepare training data
            training_service = TrainingDataService(db)
            training_data = training_service.prepare_training_data(
                days=365,  # Use last year of data
                handle_outliers=True,
                outlier_method='winsorize'
            )
            
            if training_data.empty or len(training_data) < 1000:
                raise ValueError(f"Insufficient training data: {len(training_data)} samples")
            
            # 4. Split data
            train_df, val_df, test_df = training_service.split_train_validation_test(training_data)
            
            # 5. Train new model
            self.logger.info(f"Training new model with {len(training_data)} samples")
            new_forecaster = SalesForecasterAgent()
            model, metrics = new_forecaster.train_model(train_df, val_df, test_df)
            
            # 6. Generate version ID
            new_version_id = self._generate_version_id()
            
            # 7. Save new model temporarily
            temp_model_path = self.models_dir / f"temp_{new_version_id}.pkl"
            new_forecaster._save_model(metrics=metrics)
            
            # Copy to temp path for deployment decision
            import shutil
            self.logger.info(f"Source model path: {new_forecaster.model_path}")
            self.logger.info(f"Target temp path: {temp_model_path}")
            if os.path.exists(new_forecaster.model_path):
                shutil.copy2(new_forecaster.model_path, str(temp_model_path))
                self.logger.info(f"Model copied to temp path successfully")
            else:
                self.logger.error(f"Source model path does not exist: {new_forecaster.model_path}")
                raise FileNotFoundError(f"Source model not found: {new_forecaster.model_path}")
            
            # 8. Calculate feature importance
            feature_importance = new_forecaster.get_feature_importance()
            top_features = dict(list(feature_importance.items())[:10])
            
            # 9. Log model version
            model_version_data = {
                "version_id": new_version_id,
                "model_type": "LGBMRegressor",
                "training_date": retrain_start,
                "training_end_date": datetime.utcnow(),
                "n_features": len(train_df.columns) - 1,  # Exclude target
                "n_samples": len(training_data),
                "training_days": 365,
                "outlier_method": "winsorize",
                "hyperparameters": new_forecaster.model.get_params() if hasattr(new_forecaster.model, 'get_params') else {},
                "train_mape": metrics.get('train_mape'),
                "validation_mape": metrics.get('validation_mape'),
                "test_mape": metrics.get('test_mape'),
                "train_r2": metrics.get('train_r2'),
                "validation_r2": metrics.get('validation_r2'),
                "test_r2": metrics.get('test_r2'),
                "top_features": top_features,
                "feature_names": list(train_df.columns[:-1]),
                "model_path": str(temp_model_path),
                "model_size_mb": os.path.getsize(temp_model_path) / (1024 * 1024) if os.path.exists(temp_model_path) else 0.0,
                "status": "trained",
                "created_by": trigger_type
            }
            
            # 10. Decide whether to deploy
            new_test_mape = metrics.get('test_mape', float('inf'))
            deployment_decision = self._make_deployment_decision(
                current_mape, new_test_mape, performance_threshold
            )
            
            # 11. Log retraining attempt
            retrain_log = {
                "retrain_date": retrain_start,
                "trigger_type": trigger_type,
                "trigger_details": trigger_details or {},
                "previous_version_id": current_version,
                "previous_mape": current_mape,
                "new_version_id": new_version_id,
                "new_mape": new_test_mape,
                "mape_improvement": current_mape - new_test_mape,
                "decision": deployment_decision['decision'],
                "decision_reason": deployment_decision['reason'],
                "execution_time_seconds": int((datetime.utcnow() - retrain_start).total_seconds()),
                "status": "completed"
            }
            
            # 12. Deploy if approved
            if deployment_decision['decision'] == 'deployed':
                self._deploy_model(new_version_id, temp_model_path)
                model_version_data['is_active'] = True
                model_version_data['status'] = 'deployed'
                model_version_data['deployment_date'] = datetime.utcnow()
                
                # Archive old model
                self._archive_current_model(current_version)
                
                self.logger.info(f"✅ New model deployed! Version: {new_version_id}, MAPE: {new_test_mape:.2f}%")
            else:
                # Move to archive if rejected
                archive_path = self.archive_dir / f"rejected_{new_version_id}.pkl"
                shutil.move(str(temp_model_path), str(archive_path))
                model_version_data['status'] = 'rejected'
                model_version_data['model_path'] = str(archive_path)
                
                self.logger.warning(f"⚠️ New model rejected. Reason: {deployment_decision['reason']}")
            
            # 13. Save metadata to database (would need model_versions table)
            self._save_model_metadata(db, model_version_data)
            self._save_retrain_log(db, retrain_log)
            
            # 14. Return results
            result = {
                "status": "success",
                "new_version_id": new_version_id,
                "deployment_decision": deployment_decision['decision'],
                "decision_reason": deployment_decision['reason'],
                "metrics": {
                    "previous_mape": round(current_mape, 2),
                    "new_mape": round(new_test_mape, 2),
                    "improvement": round(current_mape - new_test_mape, 2),
                    "improvement_percent": round(((current_mape - new_test_mape) / current_mape * 100), 2) if current_mape > 0 else 0
                },
                "training_details": {
                    "samples": len(training_data),
                    "features": len(train_df.columns) - 1,
                    "execution_time": int((datetime.utcnow() - retrain_start).total_seconds())
                }
            }
            
            return result
            
        except Exception as e:
            error_msg = f"Error in automatic model retraining: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            
            # Log failed attempt
            self._save_retrain_log(db, {
                "retrain_date": retrain_start,
                "trigger_type": trigger_type,
                "trigger_details": trigger_details or {},
                "status": "failed",
                "error_message": str(e),
                "execution_time_seconds": int((datetime.utcnow() - retrain_start).total_seconds())
            })
            
            return {
                "status": "error",
                "message": error_msg,
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        
        finally:
            db.close()
    
    async def _get_current_model_performance(self, db: Session) -> Dict[str, Any]:
        """Get current model performance metrics"""
        # Get recent predictions accuracy (last 7 days)
        seven_days_ago = date.today() - timedelta(days=7)
        
        accuracy_logs = db.query(
            func.avg(ForecastAccuracyLog.mape).label('avg_mape'),
            func.count(ForecastAccuracyLog.id).label('prediction_count'),
            func.stddev(ForecastAccuracyLog.mape).label('mape_std')
        ).filter(
            ForecastAccuracyLog.forecast_date >= seven_days_ago,
            ForecastAccuracyLog.mape.isnot(None)
        ).first()
        
        # Get current model info
        forecaster = get_forecaster_agent()
        model_info = forecaster.get_model_info()
        
        return {
            "version_id": model_info.get('training_date', 'unknown'),
            "recent_mape": accuracy_logs.avg_mape or 0.0,
            "prediction_count": accuracy_logs.prediction_count or 0,
            "mape_std": accuracy_logs.mape_std or 0.0,
            "model_age_days": self._calculate_model_age(model_info),
            "model_info": model_info
        }
    
    def _should_retrain(self, current_performance: Dict, trigger_type: str) -> bool:
        """Decide if model should be retrained"""
        # Always retrain for manual triggers
        if trigger_type == 'manual':
            return True
        
        # Check performance degradation
        if trigger_type == 'performance_degradation':
            return current_performance.get('recent_mape', 0) > 15.0  # 15% MAPE threshold
        
        # For scheduled retraining, check multiple conditions
        if trigger_type == 'scheduled':
            # Retrain if model is older than 30 days
            if current_performance.get('model_age_days', 0) > 30:
                return True
            
            # Retrain if recent MAPE is above 10%
            if current_performance.get('recent_mape', 0) > 10.0:
                return True
            
            # Retrain if we have enough new data (at least 1000 predictions)
            if current_performance.get('prediction_count', 0) > 1000:
                return True
        
        return False
    
    def _generate_version_id(self) -> str:
        """Generate unique version ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"v_{timestamp}_{short_uuid}"
    
    def _make_deployment_decision(
        self, 
        current_mape: float, 
        new_mape: float, 
        threshold: float
    ) -> Dict[str, str]:
        """Decide whether to deploy new model"""
        improvement = current_mape - new_mape
        improvement_percent = (improvement / current_mape * 100) if current_mape > 0 else 0
        
        # Deploy if new model is better
        if new_mape < current_mape:
            if improvement_percent > 5:  # Significant improvement (>5%)
                return {
                    "decision": "deployed",
                    "reason": f"Significant improvement: {improvement_percent:.1f}% better"
                }
            elif improvement_percent > 1:  # Minor improvement (1-5%)
                return {
                    "decision": "deployed",
                    "reason": f"Minor improvement: {improvement_percent:.1f}% better"
                }
            else:  # Negligible improvement (<1%)
                return {
                    "decision": "rejected",
                    "reason": f"Negligible improvement: only {improvement_percent:.1f}% better"
                }
        else:
            # Reject if new model is worse
            deterioration = abs(improvement_percent)
            return {
                "decision": "rejected",
                "reason": f"Performance degradation: {deterioration:.1f}% worse"
            }
    
    def _deploy_model(self, version_id: str, model_path: Path):
        """Deploy new model by replacing the current one"""
        production_path = self.models_dir / "lgbm_model.pkl"
        
        # Backup current model
        if production_path.exists():
            backup_path = self.models_dir / f"backup_lgbm_model_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pkl"
            shutil.copy2(production_path, backup_path)
        
        # Deploy new model
        shutil.copy2(model_path, production_path)
        
        # Remove temporary file
        if model_path.exists() and "temp_" in str(model_path):
            os.remove(model_path)
    
    def _archive_current_model(self, version_id: str):
        """Archive the current model"""
        production_path = self.models_dir / "lgbm_model.pkl"
        if production_path.exists() and version_id != 'unknown':
            archive_path = self.archive_dir / f"archived_{version_id}_{datetime.utcnow().strftime('%Y%m%d')}.pkl"
            shutil.copy2(production_path, archive_path)
    
    def _calculate_model_age(self, model_info: Dict) -> int:
        """Calculate model age in days"""
        try:
            if 'training_date' in model_info:
                # Parse training date from various formats
                training_date_str = model_info['training_date']
                if isinstance(training_date_str, str):
                    # Try to parse ISO format
                    training_date = datetime.fromisoformat(training_date_str.replace('Z', '+00:00'))
                    return (datetime.utcnow() - training_date).days
        except:
            pass
        
        # Default to 0 if can't determine
        return 0
    
    def _save_model_metadata(self, db: Session, metadata: Dict):
        """Save model metadata to database"""
        try:
            model_version = ModelVersion(
                version_id=metadata['version_id'],
                model_type=metadata['model_type'],
                is_active=metadata.get('is_active', False),
                training_date=metadata['training_date'],
                training_end_date=metadata.get('training_end_date'),
                deployment_date=metadata.get('deployment_date'),
                n_features=metadata['n_features'],
                n_samples=metadata['n_samples'],
                training_days=metadata['training_days'],
                outlier_method=metadata.get('outlier_method'),
                train_mape=metadata.get('train_mape'),
                validation_mape=metadata.get('validation_mape'),
                test_mape=metadata.get('test_mape'),
                train_r2=metadata.get('train_r2'),
                validation_r2=metadata.get('validation_r2'),
                test_r2=metadata.get('test_r2'),
                hyperparameters=json.dumps(metadata.get('hyperparameters')) if metadata.get('hyperparameters') else None,
                top_features=json.dumps(metadata.get('top_features')) if metadata.get('top_features') else None,
                feature_names=json.dumps(metadata.get('feature_names')) if metadata.get('feature_names') else None,
                model_path=metadata['model_path'],
                model_size_mb=metadata.get('model_size_mb'),
                status=metadata['status'],
                created_by=metadata['created_by']
            )
            
            db.add(model_version)
            db.commit()
            self.logger.info(f"✅ Model metadata saved to database: {metadata['version_id']}")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving model metadata: {e}")
            db.rollback()
    
    def _save_retrain_log(self, db: Session, log_data: Dict):
        """Save retraining log to database"""
        try:
            retrain_log = ModelRetrainingLog(
                retrain_date=log_data['retrain_date'],
                trigger_type=log_data['trigger_type'],
                trigger_details=json.dumps(log_data.get('trigger_details')) if log_data.get('trigger_details') else None,
                previous_version_id=log_data.get('previous_version_id'),
                previous_mape=log_data.get('previous_mape'),
                new_version_id=log_data['new_version_id'],
                new_mape=log_data['new_mape'],
                mape_improvement=log_data.get('mape_improvement'),
                decision=log_data.get('decision', 'unknown'),
                decision_reason=log_data.get('decision_reason'),
                execution_time_seconds=log_data.get('execution_time_seconds'),
                status=log_data['status'],
                error_message=log_data.get('error_message')
            )
            
            db.add(retrain_log)
            db.commit()
            self.logger.info(f"✅ Retraining log saved to database: {log_data['new_version_id']}")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving retraining log: {e}")
            db.rollback()


# Global instance for scheduler
model_retrainer = ModelRetrainingService()


def run_auto_retrain():
    """
    Wrapper function for scheduler to run async auto_retrain_model
    This function will be called by APScheduler
    """
    logger.info("Scheduler triggered: Starting automatic model retraining")
    
    try:
        # Handle event loop similar to sales loader
        try:
            existing_loop = asyncio.get_running_loop()
            logger.warning("Event loop already running, creating new thread for retraining")
            
            import threading
            import concurrent.futures
            
            def retrain_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        model_retrainer.auto_retrain_model(trigger_type='scheduled')
                    )
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(retrain_in_thread)
                result = future.result(timeout=1800)  # 30 minute timeout
                
        except RuntimeError:
            # No event loop running
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    model_retrainer.auto_retrain_model(trigger_type='scheduled')
                )
            finally:
                loop.close()
        
        logger.info(f"Automatic retraining completed: {result.get('status')}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to run automatic retraining: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Scheduler execution failed: {str(e)}"
        }
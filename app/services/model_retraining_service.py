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

import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import Optional, Dict, List, Tuple, Any
import logging
import traceback
import uuid
from pathlib import Path

from ..config import settings
from ..db import get_db
from ..models.branch import Department, SalesSummary, ForecastAccuracyLog, ModelVersion, ModelRetrainingLog
from ..agents.sales_forecaster_agent import (
    get_forecaster_agent,
    reload_forecaster_agent,
    SalesForecasterAgent,
)
from .training_service import TrainingDataService
from .error_analysis_service import ErrorAnalysisService

logger = logging.getLogger(__name__)


def _clean_numpy(obj):
    """Рекурсивно привести numpy-типы к нативным Python.

    Аудит P0-4: psycopg2 не умеет адаптировать np.float64 — INSERT в
    model_versions/model_retraining_log падал с InvalidSchemaName
    (schema "np" does not exist), и весь аудит-трейл переобучений молча
    терялся с момента перехода на numpy 2.x.
    """
    if isinstance(obj, dict):
        return {k: _clean_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_numpy(v) for v in obj]
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


class ModelRetrainingService:
    """Service for automatic model retraining with versioning"""
    
    def __init__(self, models_dir: str = "models"):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.models_dir = Path(models_dir)
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
            
            # 3. Prepare training data — единая политика выбросов (P1-2):
            # flag-only, без winsorize. Клиппинг таргета делал test-метрики
            # несравнимыми с ручным /retrain и портил обучение на реальных
            # пиках (праздники/зарплата). Решение о деплое — на честном hold-out.
            training_service = TrainingDataService(db)
            training_data = training_service.prepare_training_data(
                days=365,  # Use last year of data
                handle_outliers=False,
            )
            
            if training_data.empty or len(training_data) < 1000:
                raise ValueError(f"Insufficient training data: {len(training_data)} samples")
            
            # 4. Кандидат для РЕШЕНИЯ обучается на данных БЕЗ hold-out окна
            # (Фаза 1.2, P0-3): решение принимается сравнением с прод-моделью
            # на общем hold-out, которого decision-кандидат не видел вообще.
            # Прод-модель могла видеть начало hold-out (обучалась неделю+
            # назад) — смещение В ПОЛЬЗУ прода, т.е. консервативно.
            # КРИТИЧНО (аудит P0-1a): оба кандидата сохраняются во ВРЕМЕННЫЕ
            # пути — прод-файл не перезаписывается до deployment decision.
            new_version_id = self._generate_version_id()
            temp_model_path = self.models_dir / f"temp_{new_version_id}.pkl"
            decision_model_path = self.models_dir / f"temp_decision_{new_version_id}.pkl"

            holdout_days = settings.RETRAIN_HOLDOUT_DAYS
            holdout_start = pd.Timestamp(date.today() - timedelta(days=holdout_days - 1))
            decision_data = training_data[pd.to_datetime(training_data['date']) < holdout_start]
            if len(decision_data) < 1000:
                raise ValueError(
                    f"Insufficient decision-training data outside hold-out: "
                    f"{len(decision_data)} samples"
                )

            self.logger.info(
                f"Training decision-candidate on {len(decision_data)} samples "
                f"(hold-out {holdout_days}d excluded)"
            )
            d_train, d_val, d_test = training_service.split_train_validation_test(decision_data)
            decision_forecaster = SalesForecasterAgent(model_path=str(decision_model_path))
            _, decision_metrics = decision_forecaster.train_model(d_train, d_val, d_test)

            # 5. Like-for-like решение о деплое на общем hold-out (Фаза 1.2)
            deployment_decision = self._make_holdout_deployment_decision(
                db, str(decision_model_path)
            )

            # 6. Финальный кандидат на ПОЛНОМ окне — только при решении deploy
            # (задеплоенная модель должна видеть свежайшие hold-out дни;
            # обучение стоит ~1с, поэтому две тренировки допустимы)
            metrics = decision_metrics
            new_forecaster = decision_forecaster
            if deployment_decision['decision'] == 'deployed':
                self.logger.info(f"Training final candidate on full {len(training_data)} samples")
                train_df, val_df, test_df = training_service.split_train_validation_test(training_data)
                new_forecaster = SalesForecasterAgent(model_path=str(temp_model_path))
                _, metrics = new_forecaster.train_model(train_df, val_df, test_df)
                if not temp_model_path.exists():
                    raise FileNotFoundError(f"Candidate model not saved: {temp_model_path}")
            
            # 8. Calculate feature importance
            feature_importance = new_forecaster.get_feature_importance()
            top_features = dict(list(feature_importance.items())[:10])
            
            # 9. Log model version
            model_version_data = {
                "version_id": new_version_id,
                "model_type": "LGBMRegressor",
                "training_date": retrain_start,
                "training_end_date": datetime.utcnow(),
                "n_features": len(new_forecaster.feature_columns or []),
                "n_samples": len(training_data),
                "training_days": 365,
                "outlier_method": "flag",
                "hyperparameters": new_forecaster.model.get_params() if hasattr(new_forecaster.model, 'get_params') else {},
                # Ключи метрик агента: val_* / test_* (аудит P0-4 — раньше
                # искались несуществующие 'validation_mape'/'train_mape')
                "train_mape": metrics.get('train_mape'),
                "validation_mape": metrics.get('val_mape'),
                "test_mape": metrics.get('test_mape'),
                "train_r2": metrics.get('train_r2'),
                "validation_r2": metrics.get('val_r2'),
                "test_r2": metrics.get('test_r2'),
                "top_features": top_features,
                # Реальные фичи модели, а не сырые колонки датафрейма
                "feature_names": list(new_forecaster.feature_columns or []),
                "model_path": str(temp_model_path),
                "model_size_mb": os.path.getsize(temp_model_path) / (1024 * 1024) if os.path.exists(temp_model_path) else 0.0,
                "status": "trained",
                "created_by": trigger_type
            }
            
            new_test_mape = metrics.get('test_mape', float('inf'))

            # 11. Log retraining attempt.
            # С Фазы 1.2 previous_mape/new_mape — hold-out WAPE прода и
            # кандидата (сопоставимые числа); fallback на старую семантику
            # только если hold-out сравнение не состоялось (first baseline).
            holdout_cmp = deployment_decision.get('holdout')
            retrain_log = {
                "retrain_date": retrain_start,
                "trigger_type": trigger_type,
                "trigger_details": trigger_details or {},
                "previous_version_id": current_version,
                "previous_mape": (holdout_cmp['a']['wape'] if holdout_cmp else current_mape),
                "new_version_id": new_version_id,
                "new_mape": (holdout_cmp['b']['wape'] if holdout_cmp else new_test_mape),
                "mape_improvement": (
                    holdout_cmp['a']['wape'] - holdout_cmp['b']['wape']
                    if holdout_cmp else current_mape - new_test_mape
                ),
                "decision": deployment_decision['decision'],
                "decision_reason": deployment_decision['reason'],
                "execution_time_seconds": int((datetime.utcnow() - retrain_start).total_seconds()),
                "status": "completed"
            }
            
            # 12. Deploy if approved
            if deployment_decision['decision'] == 'deployed':
                # Archive old model BEFORE replacing it
                self._archive_current_model(current_version)

                self._deploy_model(new_version_id, temp_model_path)
                model_version_data['is_active'] = True
                model_version_data['status'] = 'deployed'
                model_version_data['deployment_date'] = datetime.utcnow()
                model_version_data['model_path'] = str(self.models_dir / "lgbm_model.pkl")

                # Hot-reload serving-синглтона (аудит P0-1c): иначе API работает
                # на старой in-memory модели до рестарта контейнера
                reload_forecaster_agent()

                # Decision-кандидат больше не нужен
                if decision_model_path.exists():
                    os.remove(decision_model_path)

                self.logger.info(f"✅ New model deployed! Version: {new_version_id}, MAPE: {new_test_mape:.2f}%")
            else:
                # Move to archive if rejected (в архив уходит decision-кандидат —
                # финальный при reject не обучается)
                archive_path = self.archive_dir / f"rejected_{new_version_id}.pkl"
                shutil.move(str(decision_model_path), str(archive_path))
                model_version_data['status'] = 'rejected'
                model_version_data['model_path'] = str(archive_path)

                self.logger.warning(f"⚠️ New model rejected. Reason: {deployment_decision['reason']}")
            
            # 13. Save metadata to database (would need model_versions table)
            self._save_model_metadata(db, model_version_data)
            self._save_retrain_log(db, retrain_log)
            
            # 14. Return results (с Фазы 1.2 сопоставимые числа — hold-out WAPE)
            if holdout_cmp:
                result_metrics = {
                    "holdout_days": settings.RETRAIN_HOLDOUT_DAYS,
                    "production_wape": holdout_cmp['a']['wape'],
                    "candidate_wape": holdout_cmp['b']['wape'],
                    "production_median_ape": holdout_cmp['a']['median_ape'],
                    "candidate_median_ape": holdout_cmp['b']['median_ape'],
                }
            else:
                result_metrics = {
                    "previous_mape": round(current_mape, 2),
                    "new_mape": round(new_test_mape, 2),
                }
            result = {
                "status": "success",
                "new_version_id": new_version_id,
                "deployment_decision": deployment_decision['decision'],
                "decision_reason": deployment_decision['reason'],
                "metrics": result_metrics,
                "training_details": {
                    "samples": len(training_data),
                    "features": len(new_forecaster.feature_columns or []),
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
            # Аудит P0-3/P0-4: ключа 'training_date' в model_info никогда не
            # было — version_id был вечно 'unknown', а model_age всегда 0
            "version_id": model_info.get('trained_at', 'unknown'),
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
    
    def _make_holdout_deployment_decision(
        self,
        db: Session,
        candidate_path: str,
    ) -> Dict[str, Any]:
        """Like-for-like решение о деплое (Фаза 1.2, аудит P0-3).

        Прод-модель и кандидат прогоняются по ОДНОМУ hold-out (последние
        RETRAIN_HOLDOUT_DAYS дней, все точки, фичи из TrainingDataService).
        Критерий деплоя: кандидат лучше по WAPE И не хуже прода по MedianAPE
        более чем на RETRAIN_MEDAPE_TOLERANCE_PCT %.

        Раньше сравнивались несопоставимые числа: прод-MAPE за 7 дней по
        3-4 точкам (после smoothing) против offline test-MAPE кандидата —
        2026-07-05 это дало ложный reject («153.8% worse») модели, которая
        на честном hold-out была ЛУЧШЕ прода.

        Любой сбой сравнения → rejected (прод-модель остаётся, safe default).
        """
        from .model_comparison import compare_on_holdout

        production_path = self.models_dir / "lgbm_model.pkl"
        if not production_path.exists():
            return {
                "decision": "deployed",
                "reason": "No production model found — deploying first baseline",
            }

        try:
            cmp = compare_on_holdout(
                db, str(production_path), candidate_path,
                holdout_days=settings.RETRAIN_HOLDOUT_DAYS,
            )
        except Exception as e:
            self.logger.error(f"Hold-out comparison failed: {e}", exc_info=True)
            return {
                "decision": "rejected",
                "reason": f"Hold-out comparison failed ({e}); keeping production model",
            }

        prod_m, cand_m = cmp["a"], cmp["b"]
        h = cmp["holdout"]
        tol = settings.RETRAIN_MEDAPE_TOLERANCE_PCT
        detail = (
            f"hold-out {h['from']}..{h['to']} ({h['rows']} rows): "
            f"candidate WAPE {cand_m['wape']:.2f}% / MedAPE {cand_m['median_ape']:.2f}% "
            f"vs production WAPE {prod_m['wape']:.2f}% / MedAPE {prod_m['median_ape']:.2f}%"
        )

        if cand_m["wape"] > 50.0:
            return {
                "decision": "rejected",
                "reason": f"Sanity check failed: candidate hold-out WAPE {cand_m['wape']:.1f}% > 50% ({detail})",
                "holdout": cmp,
            }

        wape_better = cand_m["wape"] < prod_m["wape"]
        medape_ok = cand_m["median_ape"] <= prod_m["median_ape"] * (1 + tol / 100.0)

        if wape_better and medape_ok:
            return {
                "decision": "deployed",
                "reason": f"Candidate better on WAPE, MedAPE within {tol:.0f}% tolerance ({detail})",
                "holdout": cmp,
            }
        if not wape_better:
            reason = f"Candidate not better on WAPE ({detail})"
        else:
            reason = f"Candidate MedAPE worse than {tol:.0f}% tolerance ({detail})"
        return {"decision": "rejected", "reason": reason, "holdout": cmp}

    def _make_deployment_decision(
        self,
        current_mape: float,
        new_mape: float,
        threshold: float,
        absolute_max_mape: float = 50.0,
    ) -> Dict[str, str]:
        """LEGACY (до Фазы 1.2): сравнение прод-MAPE с offline test-MAPE.

        В основном контуре заменён на _make_holdout_deployment_decision —
        сравнивал несопоставимые метрики (аудит P0-3). Сохранён как
        sanity-хелпер для тестов и ручных сценариев без БД.

        Rules:
        1. Reject if new model fails sanity check (MAPE > absolute_max_mape).
        2. If current_mape is missing/zero (no monitoring data yet), deploy
           unconditionally — first honest baseline.
        3. Otherwise compare relative improvement.
        """
        if new_mape is None or new_mape <= 0:
            return {
                "decision": "rejected",
                "reason": f"Invalid new_mape: {new_mape}",
            }

        if new_mape > absolute_max_mape:
            return {
                "decision": "rejected",
                "reason": (
                    f"Sanity check failed: new MAPE {new_mape:.1f}% > "
                    f"{absolute_max_mape}%"
                ),
            }

        if current_mape is None or current_mape <= 0:
            return {
                "decision": "deployed",
                "reason": (
                    f"No baseline MAPE available; deploying new model "
                    f"({new_mape:.1f}%) as first honest baseline"
                ),
            }

        improvement = current_mape - new_mape
        improvement_percent = improvement / current_mape * 100

        if new_mape < current_mape:
            if improvement_percent > 5:
                return {
                    "decision": "deployed",
                    "reason": f"Significant improvement: {improvement_percent:.1f}% better",
                }
            if improvement_percent > 1:
                return {
                    "decision": "deployed",
                    "reason": f"Minor improvement: {improvement_percent:.1f}% better",
                }
            return {
                "decision": "rejected",
                "reason": f"Negligible improvement: only {improvement_percent:.1f}% better",
            }

        deterioration = abs(improvement_percent)
        return {
            "decision": "rejected",
            "reason": f"Performance degradation: {deterioration:.1f}% worse",
        }
    
    def _deploy_model(self, version_id: str, model_path: Path):
        """Deploy new model by atomically replacing the current one.

        Аудит P0-1b: shutil.copy2 поверх прод-файла не атомарен — параллельный
        читатель (рестарт контейнера, новый процесс) мог получить наполовину
        записанный .pkl. Пишем во временный файл рядом и os.replace() — на
        POSIX это атомарная операция в пределах одной ФС.
        """
        production_path = self.models_dir / "lgbm_model.pkl"

        # Backup current model
        if production_path.exists():
            backup_path = self.models_dir / f"backup_lgbm_model_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pkl"
            shutil.copy2(production_path, backup_path)

        # Deploy new model atomically
        staging_path = production_path.with_name(production_path.name + ".staging")
        shutil.copy2(model_path, staging_path)
        os.replace(staging_path, production_path)

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
        """Calculate model age in days (по trained_at из метаданных .pkl)."""
        try:
            trained_at = model_info.get('trained_at')
            if isinstance(trained_at, str) and trained_at != 'unknown':
                training_date = datetime.fromisoformat(trained_at.replace('Z', '+00:00'))
                return (datetime.utcnow() - training_date).days
        except Exception as e:
            self.logger.warning(f"Cannot parse model trained_at: {e}")

        # Default to 0 if can't determine
        return 0
    
    def _save_model_metadata(self, db: Session, metadata: Dict):
        """Save model metadata to database"""
        metadata = _clean_numpy(metadata)
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
                created_by=metadata['created_by'],
                revenue_basis=settings.REVENUE_BASIS,  # 'price'|'paid' — база выручки модели
            )
            
            db.add(model_version)
            db.commit()
            self.logger.info(f"✅ Model metadata saved to database: {metadata['version_id']}")
            
        except Exception as e:
            # Не тихий rollback: потеря аудит-трейла — критичное событие
            # (P0-4: так молча терялись ВСЕ записи с эпохи numpy 2.x)
            self.logger.critical(
                f"❌ AUDIT TRAIL LOST — model_versions INSERT failed for "
                f"{metadata.get('version_id')}: {e}", exc_info=True
            )
            db.rollback()
            from .alerting import send_telegram_alert
            send_telegram_alert(
                f"🔴 Sales Forecast: AUDIT TRAIL LOST — model_versions INSERT "
                f"failed for {metadata.get('version_id')}: {e}"
            )
    
    def _save_retrain_log(self, db: Session, log_data: Dict):
        """Save retraining log to database"""
        log_data = _clean_numpy(log_data)
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
            # См. комментарий в _save_model_metadata — аудит-трейл терять нельзя
            self.logger.critical(
                f"❌ AUDIT TRAIL LOST — model_retraining_log INSERT failed for "
                f"{log_data.get('new_version_id')}: {e}", exc_info=True
            )
            db.rollback()
            from .alerting import send_telegram_alert
            send_telegram_alert(
                f"🔴 Sales Forecast: AUDIT TRAIL LOST — model_retraining_log INSERT "
                f"failed for {log_data.get('new_version_id')}: {e}"
            )


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
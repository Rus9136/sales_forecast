"""SKU-level LightGBM forecaster — predicts daily quantity per (department, product).

Architecture mirrors SalesForecasterAgent: singleton pattern, log1p target
transform, pickle persistence, train/predict/forecast API.
"""

import logging
import os
import threading
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..services.sku_training_service import SkuTrainingDataService
from ..services.forecast_metrics import wape as _wape, median_ape as _median_ape

logger = logging.getLogger(__name__)

MODEL_PATH = "models/sku_lgbm_model.pkl"


class SkuForecasterAgent:
    """Train and predict SKU-level daily quantities with LightGBM."""

    def __init__(self, model_path: str = MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.feature_columns: Optional[list] = None
        self._target_transform = "identity"
        self._training_metrics: Optional[dict] = None
        self._encoding_maps: dict = {}
        self._load_model()

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train_model(
        self,
        train_df: Optional[pd.DataFrame] = None,
        val_df: Optional[pd.DataFrame] = None,
        test_df: Optional[pd.DataFrame] = None,
        db: Optional[Session] = None,
        days: Optional[int] = None,
        active_window_days: int = 30,
        save_model: bool = True,
    ) -> Tuple[Any, Dict[str, Any]]:
        logger.info("Starting SKU model training …")

        if train_df is None or val_df is None or test_df is None:
            if db is None:
                raise ValueError("Provide pre-split DataFrames or a db session")

            svc = SkuTrainingDataService(db)
            df = svc.prepare_training_data(days=days, active_window_days=active_window_days)
            if df.empty:
                raise ValueError("No SKU training data available")

            train_df, val_df, test_df = svc.split_train_validation_test(df)
            self.feature_columns = svc.get_feature_columns()
            target_col = svc.get_target_column()
            # Encodings из train-датасета уезжают в .pkl и переиспользуются
            # инференсом (аудит P0-5d)
            self._encoding_maps = svc.encoding_maps
        else:
            # Pre-split путь (retrain-цикл): encoding_maps выставляет вызывающая
            # сторона (agent._encoding_maps = svc.encoding_maps) ДО train_model
            self.feature_columns = SkuTrainingDataService.get_feature_columns()
            target_col = SkuTrainingDataService.get_target_column()

        self._target_transform = "log1p"

        available_features = [c for c in self.feature_columns if c in train_df.columns]
        missing = set(self.feature_columns) - set(available_features)
        if missing:
            logger.warning(f"Missing features (will be 0): {missing}")
            for c in missing:
                for split_df in (train_df, val_df, test_df):
                    split_df[c] = 0
            available_features = self.feature_columns

        # float32: LightGBM работает с ним нативно, а память датасета
        # сокращается вдвое (аудит P0-2a — воскресный OOM всего API)
        X_train = train_df[available_features].astype(np.float32)
        y_train = train_df[target_col].astype(float)
        X_val = val_df[available_features].astype(np.float32)
        y_val = val_df[target_col].astype(float)
        X_test = test_df[available_features].astype(np.float32)
        y_test = test_df[target_col].astype(float)

        y_train_t = np.log1p(y_train)
        y_val_t = np.log1p(y_val)

        n_unique_skus = train_df['product_id'].nunique() if 'product_id' in train_df.columns else 0
        n_unique_depts = train_df['department_id'].nunique() if 'department_id' in train_df.columns else 0
        logger.info(
            f"Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}, "
            f"SKUs={n_unique_skus}, Depts={n_unique_depts}, Features={len(available_features)}"
        )

        self.model = lgb.LGBMRegressor(
            n_estimators=600,
            learning_rate=0.03,
            max_depth=7,
            num_leaves=63,
            min_child_samples=20,
            colsample_bytree=0.8,
            subsample=0.8,
            random_state=42,
            n_jobs=-1,
            verbosity=-1,
        )
        self.model.fit(
            X_train, y_train_t,
            eval_set=[(X_val, y_val_t)],
            eval_metric='mae',
            callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
        )

        y_val_pred = np.maximum(np.expm1(self.model.predict(X_val)), 0.0)
        y_test_pred = np.maximum(np.expm1(self.model.predict(X_test)), 0.0)

        metrics = {
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'test_samples': len(X_test),
            'n_features': len(available_features),
            'n_unique_skus': n_unique_skus,
            'n_unique_departments': n_unique_depts,
            'val_mae': float(mean_absolute_error(y_val, y_val_pred)),
            'val_mape': float(self._mape(y_val, y_val_pred)),
            'val_wape': _wape(y_val, y_val_pred),
            'val_median_ape': _median_ape(y_val, y_val_pred),
            'val_r2': float(r2_score(y_val, y_val_pred)),
            'val_rmse': float(np.sqrt(mean_squared_error(y_val, y_val_pred))),
            'test_mae': float(mean_absolute_error(y_test, y_test_pred)),
            'test_mape': float(self._mape(y_test, y_test_pred)),
            'test_wape': _wape(y_test, y_test_pred),
            'test_median_ape': _median_ape(y_test, y_test_pred),
            'test_r2': float(r2_score(y_test, y_test_pred)),
            'test_rmse': float(np.sqrt(mean_squared_error(y_test, y_test_pred))),
        }
        self._training_metrics = metrics
        logger.info(
            f"SKU model trained — test WAPE={metrics['test_wape']:.2f}%, "
            f"test MAPE={metrics['test_mape']:.2f}%, "
            f"test MAE={metrics['test_mae']:.2f}, test R²={metrics['test_r2']:.4f}"
        )

        if save_model:
            self._save_model(metrics)

        return self.model, metrics

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("SKU model not loaded — train or load first")
        raw = self.model.predict(X)
        if self._target_transform == "log1p":
            raw = np.expm1(raw)
        return np.maximum(raw, 0.0).round(1)

    def forecast_department_skus(
        self,
        department_id: str,
        forecast_date: date,
        db: Session,
        top_n: int = 50,
        save_to_db: bool = False,
        order_by: str = "qty",
    ) -> List[dict]:
        """Batch-predict qty for all active SKUs at a department for one date.

        С Фазы 2.1 признаки строит ТОТ ЖЕ feature-builder, что и обучение
        (аудит P0-5): календарная сетка с нулями за INFERENCE_WINDOW_DAYS,
        rolling строго внутри групп, реальные метаданные и стабильные
        encodings из .pkl. Паритет закреплён тестом test_sku_feature_parity.
        """
        if self.model is None:
            raise RuntimeError("SKU model not loaded")

        from ..services.sku_feature_builder import (
            INFERENCE_WINDOW_DAYS,
            build_features,
            build_inference_grid,
        )
        from ..services.sku_training_service import SkuTrainingDataService

        # Активные SKU точки за 30 дней до прогнозной даты
        active_rows = db.execute(text("""
            SELECT DISTINCT sds.product_id
            FROM sku_daily_sales sds
            JOIN product p ON p.id = sds.product_id
            WHERE sds.department_id = :dept_id
              AND sds.sale_date >= :cutoff
              AND sds.sale_date < :target
              AND p.is_deleted = false
        """), {
            "dept_id": department_id,
            "cutoff": forecast_date - timedelta(days=30),
            "target": forecast_date,
        }).fetchall()
        if not active_rows:
            return []

        active_pairs = pd.DataFrame({
            "department_id": str(department_id),
            "product_id": [r[0] for r in active_rows],
        })

        # История qty/sum подразделения за окно билдера (без метаданных)
        value_rows = db.execute(text("""
            SELECT sds.department_id, sds.product_id, sds.sale_date AS date,
                   sds.total_qty, sds.total_sum
            FROM sku_daily_sales sds
            WHERE sds.department_id = :dept_id
              AND sds.sale_date >= :start
              AND sds.sale_date < :target
        """), {
            "dept_id": department_id,
            "start": forecast_date - timedelta(days=INFERENCE_WINDOW_DAYS),
            "target": forecast_date,
        }).fetchall()
        if not value_rows:
            return []

        raw_values = pd.DataFrame(value_rows, columns=[
            "department_id", "product_id", "date", "total_qty", "total_sum",
        ])
        raw_values["department_id"] = raw_values["department_id"].astype(str)
        raw_values["total_qty"] = raw_values["total_qty"].astype("float32")
        raw_values["total_sum"] = raw_values["total_sum"].astype("float32")

        # Метаданные — теми же загрузчиками, что и train
        svc = SkuTrainingDataService(db)
        product_meta = svc._load_product_meta()
        dept_meta = svc._load_dept_meta()

        grid = build_inference_grid(raw_values, active_pairs, forecast_date)
        feats, _ = build_features(
            grid, product_meta, dept_meta,
            encoding_maps=self._encoding_maps or None,
        )

        target_rows = feats[feats["date"] == pd.Timestamp(forecast_date)].copy()
        if target_rows.empty:
            return []

        missing = [c for c in self.feature_columns if c not in target_rows.columns]
        for c in missing:
            target_rows[c] = 0
        if missing:
            logger.warning(f"SKU inference: missing features filled with 0: {missing}")

        X = (
            target_rows[self.feature_columns]
            .astype(np.float32)
            .fillna(0)
            .replace([np.inf, -np.inf], 0)
        )
        preds = self.predict(X)

        meta_idx = product_meta.drop_duplicates("product_id").set_index("product_id")
        results = []
        for (_, row), raw_qty in zip(target_rows.iterrows(), preds):
            pid = row["product_id"]
            qty = 0.0 if (np.isnan(raw_qty) or np.isinf(raw_qty)) else round(float(raw_qty), 1)
            m = meta_idx.loc[pid] if pid in meta_idx.index else None
            price_val = None
            if m is not None and pd.notna(m["default_sale_price"]):
                try:
                    price_val = float(m["default_sale_price"])
                except (TypeError, ValueError):
                    price_val = None
            results.append({
                "product_id": int(pid),
                "product_name": m["product_name"] if m is not None else None,
                "product_type": m["product_type"] if m is not None else None,
                "group_name": m["group_name"] if m is not None else None,
                "category_name": m["category_name"] if m is not None else None,
                "predicted_qty": qty,
                "avg_price": round(price_val, 2) if price_val else None,
                "estimated_revenue": round(qty * price_val, 2) if price_val and qty else None,
            })

        # order_by='revenue' — топ по прогнозному обороту (Фаза 1.4: ежедневная
        # джоба сохраняет топ-50 SKU по обороту); 'qty' — legacy для UI
        if order_by == "revenue":
            results.sort(key=lambda x: (x.get('estimated_revenue') or 0.0), reverse=True)
        else:
            results.sort(key=lambda x: x['predicted_qty'], reverse=True)
        if top_n:
            results = results[:top_n]

        if save_to_db:
            self._save_forecasts(results, department_id, forecast_date, db)

        return results

    # Persistence
    # ------------------------------------------------------------------

    def _save_model(self, metrics: dict):
        os.makedirs(os.path.dirname(self.model_path) or '.', exist_ok=True)
        payload = {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'version': '1.0',
            'trained_at': pd.Timestamp.now().isoformat(),
            'training_metrics': metrics,
            'target_transform': self._target_transform,
            'encoding_maps': self._encoding_maps,
        }
        joblib.dump(payload, self.model_path)
        logger.info(f"SKU model saved to {self.model_path}")

    def _load_model(self):
        if not os.path.exists(self.model_path):
            logger.info(f"No SKU model at {self.model_path}")
            return
        try:
            payload = joblib.load(self.model_path)
            self.model = payload['model']
            self.feature_columns = payload.get('feature_columns')
            self._trained_at = payload.get('trained_at', 'unknown')
            self._target_transform = payload.get('target_transform', 'identity')
            self._training_metrics = payload.get('training_metrics')
            self._encoding_maps = payload.get('encoding_maps', {})
            logger.info(f"SKU model loaded from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load SKU model: {e}")

    def _save_forecasts(self, results, department_id, forecast_date, db):
        version = self._training_metrics.get('trained_at', 'unknown') if self._training_metrics else 'unknown'
        for item in results:
            db.execute(text("""
                INSERT INTO sku_forecasts (department_id, product_id, forecast_date, predicted_qty, model_version)
                VALUES (:dept, :pid, :fd, :qty, :ver)
                ON CONFLICT (department_id, product_id, forecast_date)
                DO UPDATE SET predicted_qty = :qty, model_version = :ver, created_at = NOW()
            """), {
                'dept': department_id,
                'pid': item['product_id'],
                'fd': forecast_date,
                'qty': item['predicted_qty'],
                'ver': version,
            })
        db.commit()

    def get_model_info(self) -> dict:
        if self.model is None:
            return {'status': 'not_trained', 'model_path': self.model_path}
        return {
            'status': 'ready',
            'model_path': self.model_path,
            'n_features': len(self.feature_columns) if self.feature_columns else 0,
            'training_metrics': self._training_metrics,
            'trained_at': getattr(self, '_trained_at', None) or (self._training_metrics or {}).get('trained_at'),
            'target_transform': self._target_transform,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mape(y_true, y_pred) -> float:
        mask = y_true > 0
        if mask.sum() == 0:
            return 0.0
        return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_sku_forecaster_instance: Optional[SkuForecasterAgent] = None
_sku_forecaster_lock = threading.Lock()


def get_sku_forecaster_agent() -> SkuForecasterAgent:
    """Thread-safe singleton (double-checked lock)."""
    global _sku_forecaster_instance
    if _sku_forecaster_instance is None:
        with _sku_forecaster_lock:
            if _sku_forecaster_instance is None:
                _sku_forecaster_instance = SkuForecasterAgent()
    return _sku_forecaster_instance


def reload_sku_forecaster_agent() -> SkuForecasterAgent:
    """Перечитать SKU-модель с диска и атомарно подменить синглтон.

    Вызывается после деплоя новой модели retrain-контуром (Фаза 2.3):
    обучение идёт в отдельном процессе/агенте и НЕ мутирует serving-синглтон
    (раньше train_model подменял self.model на неотфитченный регрессор прямо
    во время обучения — инференс в это окно падал).
    """
    global _sku_forecaster_instance
    new_agent = SkuForecasterAgent()
    with _sku_forecaster_lock:
        _sku_forecaster_instance = new_agent
    logger.info(
        f"SKU forecaster singleton reloaded "
        f"(trained_at={(new_agent._training_metrics or {}).get('trained_at', 'unknown')})"
    )
    return new_agent


def reset_sku_forecaster_agent():
    """Reset singleton — для тестов."""
    global _sku_forecaster_instance
    _sku_forecaster_instance = None

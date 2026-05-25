"""SKU-level LightGBM forecaster — predicts daily quantity per (department, product).

Architecture mirrors SalesForecasterAgent: singleton pattern, log1p target
transform, pickle persistence, train/predict/forecast API.
"""

import logging
import os
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
        else:
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

        X_train = train_df[available_features].astype(float)
        y_train = train_df[target_col].astype(float)
        X_val = val_df[available_features].astype(float)
        y_val = val_df[target_col].astype(float)
        X_test = test_df[available_features].astype(float)
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
            'val_r2': float(r2_score(y_val, y_val_pred)),
            'val_rmse': float(np.sqrt(mean_squared_error(y_val, y_val_pred))),
            'test_mae': float(mean_absolute_error(y_test, y_test_pred)),
            'test_mape': float(self._mape(y_test, y_test_pred)),
            'test_r2': float(r2_score(y_test, y_test_pred)),
            'test_rmse': float(np.sqrt(mean_squared_error(y_test, y_test_pred))),
        }
        self._training_metrics = metrics
        logger.info(
            f"SKU model trained — test MAPE={metrics['test_mape']:.2f}%, "
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
    ) -> List[dict]:
        """Batch-predict qty for all active SKUs at a department for one date."""
        if self.model is None:
            raise RuntimeError("SKU model not loaded")

        active_skus = db.execute(text("""
            SELECT DISTINCT sds.product_id, p.name, p.type,
                   ng.name AS group_name, nc.name AS category_name,
                   p.default_sale_price
            FROM sku_daily_sales sds
            JOIN product p ON p.id = sds.product_id
            LEFT JOIN nomenclature_group ng ON ng.id = p.group_id
            LEFT JOIN nomenclature_category nc ON nc.id = p.category_id
            WHERE sds.department_id = :dept_id
              AND sds.sale_date >= :cutoff
              AND p.is_deleted = false
        """), {
            "dept_id": department_id,
            "cutoff": forecast_date - timedelta(days=30),
        }).fetchall()

        if not active_skus:
            return []

        history = db.execute(text("""
            SELECT sds.product_id, sds.sale_date, sds.total_qty, sds.total_sum,
                   p.type AS product_type, p.default_sale_price, p.weight_kg,
                   p.is_included_in_menu, p.group_id, p.category_id,
                   ng.name AS group_name, nc.name AS category_name,
                   d.name AS department_name, d.code AS department_code,
                   d.type AS department_type, d.segment_type, d.parent_id,
                   d.brand, d.location_type, d.tourist_traffic_dependent,
                   d.is_24_7, d.opening_hour, d.closing_hour,
                   d.seasonality_intensity, d.city, d.opened_date,
                   d.season_start_month, d.season_end_month
            FROM sku_daily_sales sds
            JOIN product p ON p.id = sds.product_id
            LEFT JOIN nomenclature_group ng ON ng.id = p.group_id
            LEFT JOIN nomenclature_category nc ON nc.id = p.category_id
            JOIN departments d ON d.id = sds.department_id
            WHERE sds.department_id = :dept_id
              AND sds.sale_date >= :start
              AND sds.sale_date <= :end
              AND p.is_deleted = false
            ORDER BY sds.product_id, sds.sale_date
        """), {
            "dept_id": department_id,
            "start": forecast_date - timedelta(days=45),
            "end": forecast_date - timedelta(days=1),
        }).fetchall()

        if not history:
            return []

        results = self._batch_predict_from_history(
            history, active_skus, forecast_date, department_id, db,
        )

        results.sort(key=lambda x: x['predicted_qty'], reverse=True)
        if top_n:
            results = results[:top_n]

        if save_to_db:
            self._save_forecasts(results, department_id, forecast_date, db)

        return results

    def _batch_predict_from_history(
        self, history_rows, active_skus, forecast_date, department_id, db,
    ) -> List[dict]:
        """Build feature matrix for all active SKUs and predict in one call."""
        from ..services.training_service import TrainingDataService

        hist_cols = [
            'product_id', 'sale_date', 'total_qty', 'total_sum',
            'product_type', 'default_sale_price', 'weight_kg',
            'is_included_in_menu', 'group_id', 'category_id',
            'group_name', 'category_name', 'department_name', 'department_code',
            'department_type', 'segment_type', 'parent_id', 'brand',
            'location_type', 'tourist_traffic_dependent', 'is_24_7',
            'opening_hour', 'closing_hour', 'seasonality_intensity', 'city',
            'opened_date', 'season_start_month', 'season_end_month',
        ]
        hist_df = pd.DataFrame(history_rows, columns=hist_cols)
        hist_df['total_qty'] = hist_df['total_qty'].astype(float)
        hist_df['total_sum'] = hist_df['total_sum'].astype(float)

        dept_svc = TrainingDataService(db)

        sku_map = {
            row[0]: {
                'product_name': row[1], 'product_type': row[2],
                'group_name': row[3], 'category_name': row[4],
                'default_sale_price': float(row[5]) if row[5] else None,
            }
            for row in active_skus
        }

        feature_rows = []
        for pid, info in sku_map.items():
            sku_hist = hist_df[hist_df['product_id'] == pid].sort_values('sale_date')
            features = self._build_sku_features(
                forecast_date, sku_hist, hist_df, dept_svc, pid, info,
            )
            features['_product_id'] = pid
            features['_product_name'] = info['product_name']
            features['_product_type'] = info['product_type']
            features['_group_name'] = info['group_name']
            features['_category_name'] = info['category_name']
            features['_default_sale_price'] = info['default_sale_price']
            feature_rows.append(features)

        if not feature_rows:
            return []

        X = pd.DataFrame(feature_rows)
        meta_cols = [c for c in X.columns if c.startswith('_')]
        feature_cols = [c for c in self.feature_columns if c in X.columns]
        missing = set(self.feature_columns) - set(feature_cols)
        for c in missing:
            X[c] = 0
        feature_cols = self.feature_columns

        X_pred = X[feature_cols].astype(float).fillna(0).replace([np.inf, -np.inf], 0)
        preds = self.predict(X_pred)

        results = []
        for i, row in X.iterrows():
            raw_qty = float(preds[i]) if i < len(preds) else 0.0
            qty = 0.0 if (np.isnan(raw_qty) or np.isinf(raw_qty)) else round(raw_qty, 1)
            price = row.get('_default_sale_price')
            try:
                price_val = float(price) if price is not None and not np.isnan(float(price)) else None
            except (TypeError, ValueError):
                price_val = None
            results.append({
                'product_id': int(row['_product_id']),
                'product_name': row['_product_name'],
                'product_type': row['_product_type'],
                'group_name': row['_group_name'],
                'category_name': row['_category_name'],
                'predicted_qty': qty,
                'avg_price': round(price_val, 2) if price_val else None,
                'estimated_revenue': round(qty * price_val, 2) if price_val and qty else None,
            })
        return results

    def _build_sku_features(
        self, forecast_date, sku_hist, all_hist, dept_svc, product_id, product_info,
    ) -> dict:
        """Build a single feature row for one SKU at forecast_date."""
        f = {}
        fd = pd.Timestamp(forecast_date)

        python_dow = fd.dayofweek
        dow = (python_dow + 1) % 7
        f['day_of_week'] = dow
        f['month'] = fd.month
        f['day_of_month'] = fd.day
        f['year'] = fd.year
        f['is_weekend'] = int(dow in (0, 6))
        f['is_friday'] = int(dow == 5)
        f['is_monday'] = int(dow == 1)
        f['is_saturday'] = int(dow == 6)
        f['is_sunday'] = int(dow == 0)
        f['weekend_multiplier'] = 1.2 if dow in (0, 6) else 1.0
        f['quarter'] = fd.quarter
        f['is_quarter_start'] = int(fd.is_quarter_start)
        f['is_quarter_end'] = int(fd.is_quarter_end)
        f['week_of_year'] = fd.isocalendar()[1]
        f['is_month_start'] = int(fd.is_month_start)
        f['is_month_end'] = int(fd.is_month_end)

        season = dept_svc._get_season(fd.month)
        f['is_winter'] = int(season == 'winter')
        f['is_spring'] = int(season == 'spring')
        f['is_summer'] = int(season == 'summer')
        f['is_autumn'] = int(season == 'autumn')

        f['is_holiday'] = int(dept_svc._is_kazakhstan_holiday(fd))
        f['is_pre_holiday'] = int(dept_svc._is_pre_holiday(fd))
        f['is_post_holiday'] = int(dept_svc._is_post_holiday(fd))

        ny = pd.Timestamp(f"{fd.year}-01-01")
        f['days_from_new_year'] = (fd - ny).days
        f['days_to_new_year'] = (pd.Timestamp(f"{fd.year + 1}-01-01") - fd).days

        first_row = sku_hist.iloc[0] if len(sku_hist) > 0 else all_hist.iloc[0] if len(all_hist) > 0 else None
        if first_row is not None:
            dept_type = first_row.get('department_type', '')
            f['is_department'] = int(dept_type == 'DEPARTMENT')
            f['is_organization'] = int(dept_type == 'ORGANIZATION')

            seg = str(first_row.get('segment_type', '')).lower()
            for s in ['coffeehouse', 'restaurant', 'confectionery', 'food_court',
                       'store', 'fast_food', 'bakery', 'cafe', 'bar']:
                f[f'is_{s}'] = int(seg == s)

            f['has_parent'] = int(bool(first_row.get('parent_id')))
            name = str(first_row.get('department_name', ''))
            f['dept_name_length'] = len(name)
            f['has_plaza_in_name'] = int('plaza' in name.lower() or 'PLAZA' in name)
            f['has_center_in_name'] = int(any(x in name for x in ['Center', 'CENTER', 'Центр']))
            f['has_mall_in_name'] = int(any(x in name for x in ['Mall', 'MALL', 'ТРЦ', 'ТРК']))
            f['is_almaty'] = int(any(x in name for x in ['Алматы', 'Almaty']))
            f['is_astana'] = int(any(x in name for x in ['Астана', 'Astana', 'Нур-Султан']))
            f['is_shymkent'] = int(any(x in name for x in ['Шымкент', 'Shymkent']))

            brand = str(first_row.get('brand', '')).lower()
            for b in ['tary', 'sandyq', 'madlen', 'shopan']:
                f[f'is_brand_{b}'] = int(brand == b)

            loc = str(first_row.get('location_type', '')).lower()
            for lt in ['city_center', 'mall', 'business_district',
                        'resort_mountain', 'resort_lake', 'visit_center', 'other']:
                f[f'is_loc_{lt}'] = int(loc == lt)

            f['is_tourist_dependent'] = int(bool(first_row.get('tourist_traffic_dependent')))
            f['is_24_7'] = int(bool(first_row.get('is_24_7')))

            o = first_row.get('opening_hour')
            c = first_row.get('closing_hour')
            if f['is_24_7']:
                f['working_hours_count'] = 24
            elif o is not None and c is not None:
                o, c = int(o), int(c)
                f['working_hours_count'] = (c - o) if c > o else (24 - o + c)
            else:
                f['working_hours_count'] = 12

            opened = first_row.get('opened_date')
            if opened:
                delta = (forecast_date - opened).days if hasattr(opened, 'year') else -1
                f['days_since_opening'] = min(max(delta, -1), 1825)
                f['is_new_department'] = int(0 <= delta < 90)
            else:
                f['days_since_opening'] = -1
                f['is_new_department'] = 0

            si = str(first_row.get('seasonality_intensity', 'none')).lower()
            f['seasonality_score'] = {'none': 0, 'low': 1, 'medium': 2, 'high': 3}.get(si, 0)

            ss = first_row.get('season_start_month')
            se = first_row.get('season_end_month')
            if ss and se:
                ss, se = int(ss), int(se)
                m = fd.month
                if ss <= se:
                    f['is_in_season'] = int(ss <= m <= se)
                else:
                    f['is_in_season'] = int(m >= ss or m <= se)
            else:
                f['is_in_season'] = 1

        ptype = product_info.get('product_type', '')
        f['product_type_dish'] = int(ptype == 'DISH')
        f['product_type_goods'] = int(ptype == 'GOODS')
        f['sku_default_price'] = float(product_info.get('default_sale_price') or 0)
        f['sku_weight_kg'] = 0
        f['sku_is_in_menu'] = 1
        f['sku_group_encoded'] = 0
        f['sku_category_encoded'] = 0
        f['sku_group_depth'] = 1

        qtys = sku_hist['total_qty'].values if len(sku_hist) > 0 else np.array([0.0])
        f['sku_lag_1d_qty'] = float(qtys[-1]) if len(qtys) >= 1 else 0
        f['sku_lag_7d_qty'] = float(qtys[-7]) if len(qtys) >= 7 else 0
        f['sku_lag_14d_qty'] = float(qtys[-14]) if len(qtys) >= 14 else 0

        for w, name in [(3, '3d'), (7, '7d'), (14, '14d'), (30, '30d')]:
            window = qtys[-w:] if len(qtys) >= w else qtys
            f[f'sku_rolling_{name}_avg_qty'] = float(np.mean(window)) if len(window) > 0 else 0

        window_7 = qtys[-7:] if len(qtys) >= 7 else qtys
        f['sku_rolling_7d_std_qty'] = float(np.std(window_7)) if len(window_7) > 1 else 0

        if len(qtys) >= 7:
            target_dow = fd.dayofweek
            indices = [i for i in range(len(qtys)) if i % 7 == len(qtys) % 7]
            same_dow = qtys[indices[-4:]] if indices else qtys[-4:]
            f['sku_same_weekday_avg_qty'] = float(np.mean(same_dow))
        else:
            f['sku_same_weekday_avg_qty'] = float(np.mean(qtys))

        nonzero = np.where(qtys > 0)[0]
        f['sku_days_since_last_sale'] = float(len(qtys) - nonzero[-1]) if len(nonzero) > 0 else 30

        all_qty_sum = all_hist['total_qty'].sum()
        f['dept_total_qty_7d'] = float(all_hist.tail(7)['total_qty'].sum())
        sku_sum_7d = float(sku_hist.tail(7)['total_sum'].sum()) if len(sku_hist) > 0 else 0
        dept_sum_7d = float(all_hist.tail(7)['total_sum'].sum()) if len(all_hist) > 0 else 0
        f['sku_revenue_share_7d'] = sku_sum_7d / dept_sum_7d if dept_sum_7d > 0 else 0
        f['sku_rank_in_dept'] = 50

        return f

    # ------------------------------------------------------------------
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
            'trained_at': (self._training_metrics or {}).get('trained_at'),
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


def get_sku_forecaster_agent() -> SkuForecasterAgent:
    global _sku_forecaster_instance
    if _sku_forecaster_instance is None:
        _sku_forecaster_instance = SkuForecasterAgent()
    return _sku_forecaster_instance

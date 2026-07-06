"""Аудит-трейл переобучения переживает numpy-типы (ML_AUDIT_REPORT.md P0-4, Фаза 0.3).

Инцидент-прототип: с перехода на numpy 2.x каждый INSERT в model_versions /
model_retraining_log падал с `InvalidSchemaName: schema "np" does not exist`
(psycopg2 не адаптирует np.float64) и молча откатывался — в таблицах остались
только 2 строки от 2025-06-30.
"""

from datetime import datetime

import numpy as np
import pytest

from app.models.branch import ModelRetrainingLog, ModelVersion
from app.services.model_retraining_service import ModelRetrainingService, _clean_numpy


@pytest.fixture()
def svc(tmp_path):
    return ModelRetrainingService(models_dir=str(tmp_path / "models"))


def test_clean_numpy_recursive():
    dirty = {
        "mape": np.float64(48.81),
        "n": np.int64(11916),
        "flag": np.bool_(True),
        "nested": {"r2": np.float32(0.93), "items": [np.float64(1.5), 2]},
    }
    clean = _clean_numpy(dirty)
    assert type(clean["mape"]) is float
    assert type(clean["n"]) is int
    assert type(clean["flag"]) is bool
    assert type(clean["nested"]["r2"]) is float
    assert type(clean["nested"]["items"][0]) is float


def test_model_version_insert_survives_np_float64(db_session, svc):
    """Ровно тот payload, что валился в проде 2026-07-05 (np.float64 в метриках)."""
    svc._save_model_metadata(db_session, {
        "version_id": "v_test_np_metadata",
        "model_type": "LGBMRegressor",
        "training_date": datetime(2026, 7, 5, 3, 0, 0),
        "training_end_date": datetime(2026, 7, 5, 3, 0, 5),
        "n_features": np.int64(83),
        "n_samples": np.int64(11916),
        "training_days": 365,
        "outlier_method": "winsorize",
        "hyperparameters": {"learning_rate": np.float64(0.05)},
        "train_mape": None,
        "validation_mape": np.float64(28.39),
        "test_mape": np.float64(48.81139140353805),
        "train_r2": None,
        "validation_r2": np.float64(0.894),
        "test_r2": np.float64(0.9355453278753688),
        "top_features": {"lag_14d_sales": np.int64(230)},
        "feature_names": ["day_of_week", "month"],
        "model_path": "models/temp_v_test.pkl",
        "model_size_mb": np.float64(0.308),
        "status": "rejected",
        "created_by": "test",
    })

    row = db_session.query(ModelVersion).filter_by(version_id="v_test_np_metadata").one()
    assert row.test_mape == pytest.approx(48.811, abs=0.01)
    assert row.validation_mape == pytest.approx(28.39, abs=0.01), (
        "validation_mape должен браться из val_mape-метрик агента (P0-4)"
    )


def test_retrain_log_insert_survives_np_float64(db_session, svc):
    svc._save_retrain_log(db_session, {
        "retrain_date": datetime(2026, 7, 5, 3, 0, 0),
        "trigger_type": "scheduled",
        "trigger_details": None,
        "previous_version_id": "unknown",
        "previous_mape": np.float64(19.230592469176358),
        "new_version_id": "v_test_np_log",
        "new_mape": np.float64(48.81139140353805),
        "mape_improvement": np.float64(-29.580798934361695),
        "decision": "rejected",
        "decision_reason": "Performance degradation: 153.8% worse",
        "execution_time_seconds": 5,
        "status": "completed",
    })

    row = db_session.query(ModelRetrainingLog).filter_by(new_version_id="v_test_np_log").one()
    assert row.decision == "rejected"
    assert row.new_mape == pytest.approx(48.811, abs=0.01)


def test_model_age_parsed_from_trained_at(svc):
    """P0-3: раньше искался несуществующий ключ 'training_date' → возраст всегда 0
    и условие «retrain if older than 30 days» было мёртвым."""
    age = svc._calculate_model_age({"trained_at": "2026-06-01T03:00:00"})
    assert age >= 30

    assert svc._calculate_model_age({"trained_at": "unknown"}) == 0
    assert svc._calculate_model_age({}) == 0

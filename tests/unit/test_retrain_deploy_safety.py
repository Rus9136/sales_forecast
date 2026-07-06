"""Deploy-safety тесты контура переобучения (ML_AUDIT_REPORT.md P0-1, Фаза 0.2d).

Инцидент-прототип: 2026-07-05 отклонённый кандидат (test MAPE 48.8%) оказался
в проде, потому что train_model(save_model=True) писал в models/lgbm_model.pkl
ДО deployment decision, а рестарт контейнера подхватил файл с диска.

Зафиксированный контракт:
1. Обучение кандидата пишет ТОЛЬКО в temp-путь — прод-файл байт-в-байт неизменен.
2. Заведомо плохой кандидат (шум в таргете) отклоняется; прод-файл и
   serving-синглтон не меняются.
3. _deploy_model заменяет прод атомарно (os.replace): бэкап старого, temp
   удалён, .staging не остаётся.
4. reload_forecaster_agent атомарно подменяет синглтон новым объектом.
"""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.agents.sales_forecaster_agent import (
    SalesForecasterAgent,
    get_forecaster_agent,
    reload_forecaster_agent,
    reset_forecaster_agent,
)
from app.services.model_retraining_service import ModelRetrainingService
from app.services.training_service import TrainingDataService

PROD_MARKER = b"PROD-MODEL-BYTES-DO-NOT-TOUCH"


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _synthetic_frames(noise_target: bool, n: int = 420, seed: int = 42):
    """Синтетический датасет с полным списком фичей.

    noise_target=False — таргет выводим из фичи (модель обучаема, низкий MAPE);
    noise_target=True  — таргет независим от фичей («плохой кандидат»).
    """
    feats = TrainingDataService.get_feature_columns()
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(0.0, index=np.arange(n), columns=feats)
    df["day_of_week"] = rng.integers(0, 7, n).astype(float)
    df["month"] = rng.integers(1, 13, n).astype(float)
    df["is_weekend"] = (df["day_of_week"].isin([0, 6])).astype(float)
    df["rolling_7d_avg_sales"] = rng.uniform(5e4, 1.5e5, n)
    df["lag_1d_sales"] = df["rolling_7d_avg_sales"] * rng.uniform(0.9, 1.1, n)

    if noise_target:
        df["total_sales"] = rng.uniform(5e4, 1.5e5, n)
    else:
        df["total_sales"] = df["rolling_7d_avg_sales"] * (
            1.0 + 0.15 * df["is_weekend"]
        ) * rng.uniform(0.99, 1.01, n)

    train = df.iloc[: int(n * 0.7)].copy()
    val = df.iloc[int(n * 0.7): int(n * 0.85)].copy()
    test = df.iloc[int(n * 0.85):].copy()
    return train, val, test


@pytest.fixture()
def models_dir(tmp_path: Path) -> Path:
    d = tmp_path / "models"
    d.mkdir()
    (d / "lgbm_model.pkl").write_bytes(PROD_MARKER)
    return d


@pytest.fixture(autouse=True)
def _isolate_singleton():
    """Каждый тест стартует и завершается с чистым синглтоном."""
    reset_forecaster_agent()
    yield
    reset_forecaster_agent()


def test_candidate_training_writes_only_temp_path(models_dir: Path):
    """P0-1a: кандидат сохраняется в свой temp-путь, прод-файл не тронут."""
    prod = models_dir / "lgbm_model.pkl"
    prod_md5_before = _md5(prod)

    temp_path = models_dir / "temp_v_test_good.pkl"
    agent = SalesForecasterAgent(model_path=str(temp_path))
    train, val, test = _synthetic_frames(noise_target=False)
    _, metrics = agent.train_model(train, val, test)

    assert temp_path.exists(), "кандидат должен быть сохранён в temp-путь"
    assert _md5(prod) == prod_md5_before, "прод-файл изменён во время обучения кандидата"
    assert metrics["test_mape"] < 10, "обучаемый синтетический таргет должен даваться легко"


def test_bad_candidate_rejected_prod_and_singleton_intact(models_dir: Path, monkeypatch):
    """P0-1d: retrain с шумовым таргетом → reject, прод и in-memory модель без изменений."""
    # Синглтон собирается в пустом CWD — детерминированное состояние "без модели"
    monkeypatch.chdir(models_dir.parent)
    serving_agent_before = get_forecaster_agent()

    prod = models_dir / "lgbm_model.pkl"
    prod_md5_before = _md5(prod)

    svc = ModelRetrainingService(models_dir=str(models_dir))
    temp_path = models_dir / "temp_v_test_bad.pkl"
    candidate = SalesForecasterAgent(model_path=str(temp_path))
    train, val, test = _synthetic_frames(noise_target=True, seed=7)
    _, metrics = candidate.train_model(train, val, test)

    decision = svc._make_deployment_decision(
        current_mape=5.0, new_mape=metrics["test_mape"], threshold=10.0
    )

    assert decision["decision"] == "rejected"
    assert _md5(prod) == prod_md5_before, "reject не должен оставлять следов в прод-файле"
    assert get_forecaster_agent() is serving_agent_before, (
        "без деплоя serving-синглтон не должен подменяться"
    )


def test_deploy_model_atomic_replace_backup_and_cleanup(models_dir: Path):
    """P0-1b: деплой заменяет прод атомарно, бэкапит старый, чистит temp/staging."""
    prod = models_dir / "lgbm_model.pkl"
    candidate_bytes = b"CANDIDATE-MODEL-BYTES"
    temp_path = models_dir / "temp_v_deploy.pkl"
    temp_path.write_bytes(candidate_bytes)

    svc = ModelRetrainingService(models_dir=str(models_dir))
    svc._deploy_model("v_deploy", temp_path)

    assert prod.read_bytes() == candidate_bytes, "прод должен содержать кандидата"
    backups = list(models_dir.glob("backup_lgbm_model_*.pkl"))
    assert len(backups) == 1 and backups[0].read_bytes() == PROD_MARKER, (
        "старый прод должен быть забэкаплен до замены"
    )
    assert not temp_path.exists(), "temp-файл кандидата должен быть удалён"
    assert not list(models_dir.glob("*.staging")), "staging-файл не должен оставаться"


def test_reload_swaps_singleton_atomically(tmp_path: Path, monkeypatch):
    """P0-1c: reload_forecaster_agent подменяет синглтон новым объектом."""
    monkeypatch.chdir(tmp_path)  # нет model-файлов — лёгкие агенты
    first = get_forecaster_agent()
    reloaded = reload_forecaster_agent()

    assert reloaded is not first
    assert get_forecaster_agent() is reloaded

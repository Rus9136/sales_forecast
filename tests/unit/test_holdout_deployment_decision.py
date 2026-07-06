"""Like-for-like deployment decision (ML_AUDIT_REPORT.md P0-3, Фаза 1.2).

Контракт _make_holdout_deployment_decision:
- деплой ⇔ кандидат лучше прода по WAPE И MedAPE в пределах толеранса;
- sanity: hold-out WAPE кандидата > 50% → reject;
- нет прод-файла → deploy first baseline;
- сбой сравнения → reject (safe default, прод остаётся).
"""

from pathlib import Path

import pytest

import app.services.model_comparison as model_comparison
from app.services.model_retraining_service import ModelRetrainingService


def _fake_cmp(prod_wape, prod_medape, cand_wape, cand_medape):
    return {
        "a": {"wape": prod_wape, "median_ape": prod_medape, "mape": 0.0,
              "model_path": "prod", "trained_at": "x", "n_rows": 1000, "n_departments": 41,
              "missing_features_filled_0": []},
        "b": {"wape": cand_wape, "median_ape": cand_medape, "mape": 0.0,
              "model_path": "cand", "trained_at": "y", "n_rows": 1000, "n_departments": 41,
              "missing_features_filled_0": []},
        "winner": "cand" if cand_wape <= prod_wape else "prod",
        "holdout": {"days": 28, "from": "2026-06-09", "to": "2026-07-06", "rows": 1094},
    }


@pytest.fixture()
def svc(tmp_path: Path) -> ModelRetrainingService:
    service = ModelRetrainingService(models_dir=str(tmp_path / "models"))
    (service.models_dir / "lgbm_model.pkl").write_bytes(b"PROD")
    return service


def _patch_cmp(monkeypatch, cmp_result=None, error=None):
    def fake(db, a, b, holdout_days=28):
        if error:
            raise error
        return cmp_result
    monkeypatch.setattr(model_comparison, "compare_on_holdout", fake)


def test_better_wape_within_tolerance_deploys(svc, monkeypatch):
    _patch_cmp(monkeypatch, _fake_cmp(19.0, 16.0, 18.0, 16.5))  # MedAPE +3% < 10% tol
    d = svc._make_holdout_deployment_decision(db=None, candidate_path="cand.pkl")
    assert d["decision"] == "deployed"
    assert d["holdout"]["b"]["wape"] == 18.0


def test_worse_wape_rejected(svc, monkeypatch):
    _patch_cmp(monkeypatch, _fake_cmp(19.0, 16.0, 19.5, 15.0))
    d = svc._make_holdout_deployment_decision(db=None, candidate_path="cand.pkl")
    assert d["decision"] == "rejected"
    assert "not better on WAPE" in d["reason"]


def test_medape_beyond_tolerance_rejected(svc, monkeypatch):
    # WAPE лучше, но MedAPE хуже более чем на 10% (16 → 18 = +12.5%)
    _patch_cmp(monkeypatch, _fake_cmp(19.0, 16.0, 18.0, 18.0))
    d = svc._make_holdout_deployment_decision(db=None, candidate_path="cand.pkl")
    assert d["decision"] == "rejected"
    assert "MedAPE" in d["reason"]


def test_sanity_wape_above_50_rejected(svc, monkeypatch):
    _patch_cmp(monkeypatch, _fake_cmp(60.0, 30.0, 55.0, 25.0))  # «лучше» прода, но мусор
    d = svc._make_holdout_deployment_decision(db=None, candidate_path="cand.pkl")
    assert d["decision"] == "rejected"
    assert "Sanity" in d["reason"]


def test_no_production_model_deploys_first_baseline(tmp_path, monkeypatch):
    svc = ModelRetrainingService(models_dir=str(tmp_path / "models"))  # без прод-файла
    d = svc._make_holdout_deployment_decision(db=None, candidate_path="cand.pkl")
    assert d["decision"] == "deployed"
    assert "first baseline" in d["reason"]


def test_comparison_failure_is_safe_reject(svc, monkeypatch):
    _patch_cmp(monkeypatch, error=ValueError("No sales data available to build hold-out"))
    d = svc._make_holdout_deployment_decision(db=None, candidate_path="cand.pkl")
    assert d["decision"] == "rejected"
    assert "keeping production model" in d["reason"]

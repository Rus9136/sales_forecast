"""Guardrail решения о деплое SKU-модели (Фаза 2.3, зеркало 1.2).

compare_sku_on_holdout: деплой ⇔ кандидат лучше по WAPE И MedAPE в пределах
толеранса; sanity WAPE>max → reject. Оценка агентов замокана — проверяем
только логику решения.
"""

import pytest

import app.services.sku_model_comparison as cmp_mod


def _patch_eval(monkeypatch, prod_metrics, cand_metrics):
    calls = {"n": 0}

    def fake_load(db, holdout_days=21, history_days=75):
        return ("grid", "pm", "dm", "holdout_start")

    def fake_eval(agent, grid, pm, dm, holdout_start):
        calls["n"] += 1
        return prod_metrics if calls["n"] == 1 else cand_metrics

    monkeypatch.setattr(cmp_mod, "load_holdout_world", fake_load)
    monkeypatch.setattr(cmp_mod, "evaluate_agent", fake_eval)


def _m(wape, medape, nonzero_wape=50.0):
    return {"n_rows": 1000, "wape": wape, "median_ape": medape,
            "nonzero_wape": nonzero_wape, "zero_day_mean_pred": 0.3,
            "trained_at": "x"}


def test_candidate_better_deploys(monkeypatch):
    _patch_eval(monkeypatch, _m(70.0, 60.0), _m(68.0, 61.0))  # MedAPE +1.6% < 10%
    d = cmp_mod.compare_sku_on_holdout(db=None, production_agent=1, candidate_agent=2)
    assert d["decision"] == "deployed"


def test_candidate_worse_wape_rejected(monkeypatch):
    _patch_eval(monkeypatch, _m(70.0, 60.0), _m(71.0, 55.0))
    d = cmp_mod.compare_sku_on_holdout(db=None, production_agent=1, candidate_agent=2)
    assert d["decision"] == "rejected" and "not better on WAPE" in d["reason"]


def test_medape_beyond_tolerance_rejected(monkeypatch):
    # WAPE лучше, но MedAPE хуже на >10% (60 → 67 = +11.7%)
    _patch_eval(monkeypatch, _m(70.0, 60.0), _m(68.0, 67.0))
    d = cmp_mod.compare_sku_on_holdout(db=None, production_agent=1, candidate_agent=2)
    assert d["decision"] == "rejected" and "MedAPE beyond tolerance" in d["reason"]


def test_sanity_wape_above_max_rejected(monkeypatch):
    _patch_eval(monkeypatch, _m(200.0, 150.0), _m(90.0, 80.0))  # «лучше» прода, но >80% мусор
    d = cmp_mod.compare_sku_on_holdout(db=None, production_agent=1, candidate_agent=2, max_wape=80.0)
    assert d["decision"] == "rejected" and "Sanity" in d["reason"]

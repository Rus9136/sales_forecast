"""Post-processing fixes P1-5 (ML_AUDIT_REPORT.md).

Проверяем:
1. DOW-aware сглаживание не режет легитимный пик выходного (сравнение со
   своей нормой дня недели, а не с общим средним).
2. Произвольные множители ×1.1/×1.15 удалены — business rules только
   санитарные floor/ceiling.
3. Anomaly-детект DOW-aware: высокий выходной прогноз не аномален относительно
   выходной нормы.
4. CI через split-conformal, если есть история остатков; иначе fallback.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.forecast_postprocessing_service import ForecastPostprocessingService


def _svc():
    return ForecastPostprocessingService.__new__(ForecastPostprocessingService)


def _weekly_history(weeks=8, weekday_high=400_000, weekend_high=900_000, end=date(2026, 7, 4)):
    """История с сильной недельностью: выходные вдвое выше будней."""
    rows = []
    for i in range(weeks * 7):
        d = pd.Timestamp(end) - pd.Timedelta(days=i)
        val = weekend_high if d.dayofweek >= 5 else weekday_high
        rows.append({"date": d, "total_sales": float(val)})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def test_smoothing_dow_aware_keeps_weekend_peak():
    """Прогноз на субботу ~ выходной нормы НЕ должен срезаться до буднего среднего."""
    svc = _svc()
    hist = _weekly_history()
    saturday = date(2026, 7, 11)  # суббота
    assert pd.Timestamp(saturday).dayofweek == 5

    # прогноз близок к выходной норме (900k) — раньше резался к ~7-дневному
    # среднему (~530k) как «+70% скачок». DOW-aware: субботняя норма = 900k.
    out = svc._apply_smoothing(880_000, hist, saturday, max_change_percent=50.0)
    assert out == pytest.approx(880_000, rel=1e-6), "легитимный пик выходного срезан"


def test_smoothing_still_caps_true_jump():
    """Аномальный скачок относительно нормы своего дня всё равно клиппится."""
    svc = _svc()
    hist = _weekly_history()
    saturday = date(2026, 7, 11)
    out = svc._apply_smoothing(3_000_000, hist, saturday, max_change_percent=50.0)
    assert out == pytest.approx(900_000 * 1.5, rel=1e-6)  # +50% от субботней нормы


def test_business_rules_have_no_arbitrary_multipliers(monkeypatch):
    """×1.1 (кофейни-выходные) и ×1.15 (праздники) удалены."""
    svc = _svc()
    hist = _weekly_history()
    # значение внутри floor/ceiling → правила не должны его менять
    val = 500_000
    saturday = date(2026, 7, 11)

    # near-holiday дата (перед Наурызом) не должна давать ×1.15
    pre_nauryz = date(2027, 3, 20)
    hist2 = _weekly_history(end=date(2027, 3, 13))
    out_holiday = svc._apply_business_rules(val, hist2, pre_nauryz, "b1")
    assert out_holiday == pytest.approx(val), "остался праздничный множитель"

    # выходной: без обращения к БД за segment_type (Rule 3 удалён)
    out_weekend = svc._apply_business_rules(val, hist, saturday, "b1")
    assert out_weekend == pytest.approx(val), "остался weekend-множитель"


def test_anomaly_dow_aware_weekend_not_flagged():
    """Высокий, но нормальный для выходного прогноз — не аномалия."""
    svc = _svc()
    hist = _weekly_history()
    saturday = date(2026, 7, 11)
    res = svc._detect_forecast_anomalies(900_000, hist, saturday, z_threshold=3.0)
    assert res["basis"] == "same_weekday"
    assert res["is_anomaly"] is False


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
    def filter(self, *a, **k):
        return self
    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
    def query(self, *a, **k):
        return _FakeQuery(self._rows)


def test_conformal_ci_from_residuals():
    """CI строится из эмпирических относительных остатков."""
    svc = _svc()
    # остатки: факт систематически ~ прогноз ± до 20%
    rows = []
    for i in range(40):
        pred = 500_000.0
        rel = -0.2 + 0.4 * (i / 39)  # от -20% до +20%
        rows.append((pred, pred * (1 + rel)))
    svc.db = _FakeDB(rows)

    ci = svc._calculate_confidence_interval(600_000, pd.DataFrame({"date": [], "total_sales": []}), "b1")
    assert ci["method"] == "split_conformal"
    assert ci["n_residuals"] == 40
    assert ci["lower_bound"] < 600_000 < ci["upper_bound"]


def test_conformal_falls_back_when_insufficient():
    svc = _svc()
    svc.db = _FakeDB([(500_000.0, 510_000.0)] * 3)  # <10 остатков
    hist = _weekly_history()
    ci = svc._calculate_confidence_interval(600_000, hist, "b1")
    assert ci["method"] in ("historical_volatility_fallback", "default_range")

"""Единый календарь РК (ML_AUDIT_REPORT.md P1-3, P2-7, Фаза 3.1).

Раньше is_holiday считался тремя расходящимися реализациями (train ≠ inference
≠ postprocessing), а Курбан-айт заканчивался 2026 годом. Тест фиксирует один
источник истины и то, что все три места вызова делегируют в него.
"""

from datetime import date

import pandas as pd
import pytest

from app.services import kz_calendar


def test_fixed_holidays():
    assert kz_calendar.is_holiday(date(2027, 1, 1))    # Новый год
    assert kz_calendar.is_holiday(date(2027, 3, 22))   # Наурыз
    assert kz_calendar.is_holiday(date(2027, 12, 16))  # Независимость
    assert not kz_calendar.is_holiday(date(2027, 2, 10))  # обычный день


def test_kurban_ait_extends_past_2026():
    """Ключевой баг: старый календарь заканчивал Курбан-айт 2026 годом."""
    assert kz_calendar.is_holiday(date(2027, 5, 16))
    assert kz_calendar.is_holiday(date(2028, 5, 5))
    assert kz_calendar.is_holiday(date(2030, 4, 13))


def test_pre_post_holiday():
    assert kz_calendar.is_pre_holiday(date(2026, 12, 31))   # перед Новым годом
    assert kz_calendar.is_post_holiday(date(2027, 1, 3))    # после 1-2 января


def test_ramadan_window():
    assert kz_calendar.is_ramadan(date(2026, 3, 1))     # внутри окна 2026
    assert not kz_calendar.is_ramadan(date(2026, 5, 1))  # вне


def test_payday_window():
    assert kz_calendar.is_payday_window(date(2026, 7, 1))   # начало месяца
    assert kz_calendar.is_payday_window(date(2026, 7, 25))  # аванс
    assert not kz_calendar.is_payday_window(date(2026, 7, 15))


def test_accepts_timestamp_and_date():
    assert kz_calendar.is_holiday(pd.Timestamp("2027-03-22")) == kz_calendar.is_holiday(date(2027, 3, 22))


def test_all_three_call_sites_agree():
    """training_service, agent, postprocessing — один результат на одну дату."""
    from app.agents.sales_forecaster_agent import SalesForecasterAgent
    from app.services.forecast_postprocessing_service import ForecastPostprocessingService
    from app.services.training_service import TrainingDataService

    ts = TrainingDataService(None)
    agent = SalesForecasterAgent.__new__(SalesForecasterAgent)  # без загрузки модели
    pp = ForecastPostprocessingService.__new__(ForecastPostprocessingService)

    for d in [date(2027, 5, 16), date(2027, 3, 22), date(2028, 5, 5), date(2027, 2, 10)]:
        expected = kz_calendar.is_holiday(d)
        assert bool(ts._is_kazakhstan_holiday(pd.Timestamp(d))) == expected
        assert bool(agent._is_kazakhstan_holiday(pd.Timestamp(d))) == expected
        assert bool(pp._is_kazakhstan_holiday(d)) == expected

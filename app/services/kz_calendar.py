"""Единый календарь Казахстана для ML-фичей (ML_AUDIT_REPORT.md P1-3, P2-7).

Раньше `is_holiday` считался ТРЕМЯ расходящимися реализациями:
- training_service (Наурыз 21-23, Незав. 16-17, Курбан-айт 2022-2026);
- sales_forecaster_agent (Наурыз 21-24, Незав. 16-18, БЕЗ Курбан-айта);
- forecast_postprocessing (третий вариант).
→ фича `is_holiday` при инференсе не совпадала с обучением (тихая деградация),
а Курбан-айт молча заканчивался 2026 годом.

Здесь ОДИН источник истины. Плюс сигналы, которых не было (P2-7):
Рамадан (сдвигает выручку общепита на месяц) и зарплатные окна.

Самодостаточный модуль (без пакета `holidays`) — полный контроль над
лунными датами; обновляются по мере официального объявления.
"""

from datetime import date, timedelta
from functools import lru_cache
from typing import Union

import pandas as pd

DateLike = Union[date, "pd.Timestamp"]

# --- Фиксированные госпраздники РК (актуальный набор после реформы 2022) ---
# First President Day (1 дек) убран в 2022 — не включаем. Наурыз официально
# 21-23 марта; Независимость 16-17 декабря.
FIXED_HOLIDAYS = frozenset({
    (1, 1), (1, 2),   # Новый год
    (1, 7),           # Православное Рождество (выходной в РК)
    (3, 8),           # Международный женский день
    (3, 21), (3, 22), (3, 23),  # Наурыз
    (5, 1),           # Праздник единства народа
    (5, 7),           # День защитника Отечества
    (5, 9),           # День Победы
    (7, 6),           # День столицы
    (8, 30),          # День Конституции
    (12, 16), (12, 17),  # День независимости
})

# Курбан-айт (Eid al-Adha, 1-й день) — лунный, объявляется ежегодно.
# Значения после 2026 — астрономическая оценка, уточнять при объявлении.
KURBAN_AIT = {
    2022: date(2022, 7, 9),
    2023: date(2023, 6, 28),
    2024: date(2024, 6, 16),
    2025: date(2025, 6, 6),
    2026: date(2026, 5, 27),
    2027: date(2027, 5, 16),
    2028: date(2028, 5, 5),
    2029: date(2029, 4, 24),
    2030: date(2030, 4, 13),
}

# Рамадан (начало..конец, включительно) — оценка, уточнять при объявлении.
RAMADAN = {
    2024: (date(2024, 3, 11), date(2024, 4, 9)),
    2025: (date(2025, 3, 1), date(2025, 3, 30)),
    2026: (date(2026, 2, 18), date(2026, 3, 19)),
    2027: (date(2027, 2, 8), date(2027, 3, 9)),
    2028: (date(2028, 1, 28), date(2028, 2, 26)),
    2029: (date(2029, 1, 16), date(2029, 2, 14)),
    2030: (date(2030, 1, 6), date(2030, 2, 4)),
}

# Зарплатные окна: аванс (25-е) и получка/начало месяца (1-5) — всплеск трат.
PAYDAY_DAYS = frozenset({1, 2, 3, 4, 5, 10, 25})


def _to_date(d: DateLike) -> date:
    if isinstance(d, date) and not hasattr(d, "to_pydatetime"):
        return d
    return pd.Timestamp(d).date()


def is_holiday(d: DateLike) -> bool:
    """Государственный праздник РК (фиксированный или Курбан-айт)."""
    dd = _to_date(d)
    if (dd.month, dd.day) in FIXED_HOLIDAYS:
        return True
    return KURBAN_AIT.get(dd.year) == dd


def is_pre_holiday(d: DateLike) -> bool:
    """День перед праздником (предпраздничный всплеск)."""
    return is_holiday(_to_date(d) + timedelta(days=1))


def is_post_holiday(d: DateLike) -> bool:
    """День после праздника."""
    return is_holiday(_to_date(d) - timedelta(days=1))


def is_ramadan(d: DateLike) -> bool:
    """Идёт ли месяц Рамадан (меняет паттерн общепита)."""
    dd = _to_date(d)
    window = RAMADAN.get(dd.year)
    if not window:
        return False
    return window[0] <= dd <= window[1]


def is_payday_window(d: DateLike) -> bool:
    """Зарплатное окно (аванс/получка) — повышенные траты."""
    return _to_date(d).day in PAYDAY_DAYS


@lru_cache(maxsize=4096)
def _holiday_cached(y: int, m: int, day: int) -> bool:
    return is_holiday(date(y, m, day))

"""Tests for app.bonus.calculator.kpi_engine."""

from decimal import Decimal

import pytest

from app.bonus.calculator.kpi_engine import overall_kpi, score_kpi


class TestScoreKpi:
    # TC-50: higher_is_better
    def test_higher_is_better_at_target(self):
        assert score_kpi(100, 100, "higher_is_better") == Decimal("100.00")

    def test_higher_is_better_above_target_capped(self):
        assert score_kpi(120, 100, "higher_is_better", cap_at_100=True) == Decimal("100.00")

    def test_higher_is_better_above_target_uncapped(self):
        assert score_kpi(120, 100, "higher_is_better", cap_at_100=False) == Decimal("120.00")

    def test_higher_is_better_below_target(self):
        assert score_kpi(80, 100, "higher_is_better") == Decimal("80.00")

    def test_higher_is_better_zero_fact(self):
        assert score_kpi(0, 100, "higher_is_better") == Decimal("0.00")

    # TC-51: lower_is_better (negative reviews share)
    def test_lower_is_better_below_target_capped(self):
        # fact 3% < target 5% — exceeds plan, cap to 100%
        assert score_kpi(3, 5, "lower_is_better") == Decimal("100.00")

    def test_lower_is_better_at_target(self):
        assert score_kpi(5, 5, "lower_is_better") == Decimal("100.00")

    def test_lower_is_better_above_target(self):
        # fact 10% > target 5% — fell short
        assert score_kpi(10, 5, "lower_is_better") == Decimal("50.00")

    def test_lower_is_better_zero_fact(self):
        assert score_kpi(0, 5, "lower_is_better") == Decimal("100")

    # TC-52: binary (rating 1..5)
    def test_binary_at_target(self):
        assert score_kpi(5, 5, "binary") == Decimal("100.00")

    def test_binary_below(self):
        assert score_kpi(4, 5, "binary") == Decimal("80.00")

    def test_binary_low(self):
        assert score_kpi(3, 5, "binary") == Decimal("60.00")

    # Edge cases
    def test_target_zero(self):
        assert score_kpi(50, 0, "higher_is_better") == Decimal("0")

    def test_unknown_direction(self):
        with pytest.raises(ValueError):
            score_kpi(50, 100, "sideways_is_best")


class TestOverallKpi:
    def test_average(self):
        # KPI: 95, 96, 90, 88, 85 → 90.8
        assert overall_kpi([
            Decimal("95"), Decimal("96"), Decimal("90"),
            Decimal("88"), Decimal("85"),
        ]) == Decimal("90.80")

    def test_empty(self):
        assert overall_kpi([]) == Decimal(0)

    def test_single_value(self):
        assert overall_kpi([Decimal("75")]) == Decimal("75.00")

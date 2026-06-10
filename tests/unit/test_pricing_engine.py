"""Unit tests for the pricing engine pure logic.

Covers: rule checks (B4), candidate grid + GP math + planning elasticity (B3),
reliability grades (B2) and realized-elasticity math (feedback loop).
No DB — services are instantiated with db=None where only pure methods are used.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.elasticity_estimation_service import _assign_grade
from app.services.price_optimizer_service import (
    PriceOptimizerService,
    select_planning_elasticity,
)
from app.services.pricing_feedback_service import compute_realized_elasticity
from app.services.pricing_rules_service import PricingRulesService

pytestmark = pytest.mark.unit


@pytest.fixture()
def rules_svc() -> PricingRulesService:
    return PricingRulesService(db=None)


@pytest.fixture()
def optimizer() -> PriceOptimizerService:
    return PriceOptimizerService(db=None)


DEFAULT_RULES = {
    "min_margin": {"value": 0.60},
    "max_step": {"value": 0.05},
    "min_frequency": {"days": 14},
    "no_decrease_anchor": {"enabled": True},
    "rounding": {"step": 50, "flagship_step": 100},
    "no_psychological": {"enabled": True, "endings": [9, 99]},
}


class TestCheckRecommendation:
    def test_valid_increase_passes(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            current_price=1000, candidate_price=1050, cogs=300,
            menu_role="margin_driver", last_change_date=None, rules=DEFAULT_RULES,
        )
        assert ok and violations == []

    def test_min_margin_blocks(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            1000, 1000 - 50, cogs=450, menu_role="margin_driver",
            last_change_date=None, rules=DEFAULT_RULES,
        )
        assert not ok
        assert any(v.startswith("min_margin") for v in violations)

    def test_min_margin_skipped_without_cogs(self, rules_svc):
        ok, _ = rules_svc.check_recommendation(
            1000, 1050, cogs=None, menu_role="margin_driver",
            last_change_date=None, rules=DEFAULT_RULES,
        )
        assert ok  # правило молча неприменимо — фильтрация SKU без COGS выше

    def test_max_step_blocks(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            1000, 1100, cogs=300, menu_role="margin_driver",
            last_change_date=None, rules=DEFAULT_RULES,
        )
        assert not ok
        assert any(v.startswith("max_step") for v in violations)

    def test_min_frequency_blocks_recent_change(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            1000, 1050, cogs=300, menu_role="margin_driver",
            last_change_date=date.today() - timedelta(days=5), rules=DEFAULT_RULES,
        )
        assert not ok
        assert any(v.startswith("min_frequency") for v in violations)

    def test_min_frequency_allows_old_change(self, rules_svc):
        ok, _ = rules_svc.check_recommendation(
            1000, 1050, cogs=300, menu_role="margin_driver",
            last_change_date=date.today() - timedelta(days=30), rules=DEFAULT_RULES,
        )
        assert ok

    def test_anchor_decrease_blocked(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            1000, 950, cogs=200, menu_role="premium_anchor",
            last_change_date=None, rules=DEFAULT_RULES,
        )
        assert not ok
        assert any(v.startswith("no_decrease_anchor") for v in violations)

    def test_rounding_flagship_100(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            1000, 1050, cogs=200, menu_role="premium_anchor",
            last_change_date=None, rules=DEFAULT_RULES,
        )
        assert not ok
        assert any(v.startswith("rounding") for v in violations)

    def test_stop_list_blocks_any_change(self, rules_svc):
        rules = {**DEFAULT_RULES, "stop_list": {"enabled": True}}
        ok, violations = rules_svc.check_recommendation(
            1000, 1050, cogs=200, menu_role="margin_driver",
            last_change_date=None, rules=rules,
        )
        assert not ok
        assert any(v.startswith("stop_list") for v in violations)

    def test_missing_value_key_does_not_raise(self, rules_svc):
        # params без 'value' — дефолт работает и сообщение не падает KeyError
        rules = {"min_margin": {}, "max_step": {}}
        ok, violations = rules_svc.check_recommendation(
            1000, 1050, cogs=900, menu_role="margin_driver",
            last_change_date=None, rules=rules,
        )
        assert not ok
        assert any("min_margin" in v for v in violations)


class TestEnumerateCandidates:
    def test_grid_within_corridor_and_rounded(self, optimizer):
        candidates = optimizer._enumerate_candidates(1000.0, DEFAULT_RULES, "margin_driver")
        assert 1000.0 in candidates
        grid = [c for c in candidates if c != 1000.0]
        assert all(c % 50 == 0 for c in grid)
        assert min(grid) >= 950.0 and max(grid) <= 1050.0

    def test_flagship_uses_100_step(self, optimizer):
        candidates = optimizer._enumerate_candidates(5000.0, DEFAULT_RULES, "premium_anchor")
        grid = [c for c in candidates if c != 5000.0]
        assert all(c % 100 == 0 for c in grid)
        assert min(grid) >= 4750.0 and max(grid) <= 5250.0


class TestGpMath:
    def test_qty_follows_constant_elasticity(self, optimizer):
        gp, qty = optimizer._compute_gp_and_qty(
            price=1050, current_price=1000, cogs=400, q_base=100, elasticity=-0.5,
        )
        assert qty == pytest.approx(100 * 1.05 ** -0.5, rel=1e-9)
        assert gp == pytest.approx((1050 - 400) * qty, rel=1e-9)

    def test_unchanged_price_keeps_base_qty(self, optimizer):
        gp, qty = optimizer._compute_gp_and_qty(1000, 1000, 400, 100, -0.5)
        assert qty == 100
        assert gp == 600 * 100

    def test_inelastic_increase_raises_gp(self, optimizer):
        gp_base, _ = optimizer._compute_gp_and_qty(1000, 1000, 400, 100, -0.3)
        gp_up, _ = optimizer._compute_gp_and_qty(1050, 1000, 400, 100, -0.3)
        assert gp_up > gp_base

    def test_highly_elastic_increase_lowers_gp(self, optimizer):
        gp_base, _ = optimizer._compute_gp_and_qty(1000, 1000, 400, 100, -3.0)
        gp_up, _ = optimizer._compute_gp_and_qty(1050, 1000, 400, 100, -3.0)
        assert gp_up < gp_base


class TestPlanningElasticity:
    def test_grade_a_b_use_mean(self):
        assert select_planning_elasticity(-0.4, -0.9, "A") == -0.4
        assert select_planning_elasticity(-0.4, -0.9, "B") == -0.4

    def test_grade_c_d_use_conservative_ci(self):
        assert select_planning_elasticity(-0.2, -0.8, "C") == -0.8
        assert select_planning_elasticity(-0.2, -0.8, "D") == -0.8

    def test_missing_ci_falls_back_hard(self):
        assert select_planning_elasticity(-0.5, None, "D") == -1.0
        # уже консервативнее fallback — не ослабляем
        assert select_planning_elasticity(-1.5, None, "D") == -1.5


class TestAssignGrade:
    def test_grades(self):
        assert _assign_grade(5, 90) == "A"
        assert _assign_grade(5, 89) == "B"  # дней мало для A, хватает для B
        assert _assign_grade(4, 60) == "B"
        assert _assign_grade(3, 10) == "C"
        assert _assign_grade(2, 400) == "D"
        assert _assign_grade(0, 0) == "D"


class TestRealizedElasticity:
    def test_control_adjustment(self):
        # своя qty -10%, контроль -5% → скорректированное ≈ -5.26%
        adj, eps = compute_realized_elasticity(-0.10, -0.05, 1000, 1050)
        assert adj == pytest.approx(0.9 / 0.95 - 1, abs=1e-4)
        assert eps is not None and eps < 0

    def test_no_control_uses_raw_change(self):
        adj, eps = compute_realized_elasticity(-0.049, None, 1000, 1050)
        assert adj == pytest.approx(-0.049, abs=1e-4)
        # ln(0.951)/ln(1.05) ≈ -1.03
        assert eps == pytest.approx(-1.03, abs=0.01)

    def test_same_price_returns_none_eps(self):
        adj, eps = compute_realized_elasticity(-0.1, None, 1000, 1000)
        assert eps is None

    def test_full_drop_returns_none_eps(self):
        adj, eps = compute_realized_elasticity(-1.0, None, 1000, 1050)
        assert eps is None

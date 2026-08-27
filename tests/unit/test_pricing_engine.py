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


class TestWithinEstimator:
    """Within-преобразование должно убирать межпозиционные различия уровней цен."""

    @staticmethod
    def _make_df(rows):
        import pandas as pd
        return pd.DataFrame(rows, columns=[
            "product_id", "department_id", "log_qty", "log_price",
            "month", "week_index", "cat_log_qty",
        ])

    def test_pooled_cross_sectional_bias_removed(self):
        import numpy as np
        from app.services.elasticity_estimation_service import (
            _build_design_matrix, _run_ols,
        )
        # Два SKU с РАЗНЫМИ уровнями цен и спроса, но БЕЗ временной вариации цены.
        # Дорогой продаётся меньше → pooled-OLS найдёт ложную ε, within — нет сигнала.
        rows = []
        for w in range(12):
            rows.append((1, "d1", np.log(100 + w % 3), np.log(1000), 1 + w % 3, w, 0.0))
            rows.append((2, "d1", np.log(10 + w % 3), np.log(5000), 1 + w % 3, w, 0.0))
        df = self._make_df(rows)

        X, y, cols, extra_dof = _build_design_matrix(df, within=True)
        assert extra_dof == 1  # 2 пары → 1 поглощённое среднее
        beta, se, _, _, _ = _run_ols(X, y, extra_dof)
        eps = beta[cols.index("log_price")]
        # после демининга log_price внутри пары константен → нет идентификации, ε≈0
        assert abs(eps) < 1e-6

    def test_within_recovers_true_elasticity(self):
        import numpy as np
        from app.services.elasticity_estimation_service import (
            _build_design_matrix, _run_ols,
        )
        # Истинная ε = -0.8; у пар разные базовые уровни (FE), цена меняется во времени
        true_eps = -0.8
        rng_prices = [1000, 1000, 1050, 1050, 1100, 1100, 1000, 1050, 1100, 1000, 1050, 1100]
        rows = []
        for pid, base_q in ((1, 100.0), (2, 30.0)):
            for w, p in enumerate(rng_prices):
                q = base_q * (p / 1000.0) ** true_eps
                rows.append((pid, "d1", np.log(q), np.log(p), 1 + w % 3, w, 0.0))
        df = self._make_df(rows)

        X, y, cols, extra_dof = _build_design_matrix(df, within=True)
        beta, se, _, _, _ = _run_ols(X, y, extra_dof)
        eps = beta[cols.index("log_price")]
        assert eps == pytest.approx(true_eps, abs=0.05)


class TestJobRegistry:
    def test_submit_and_get(self):
        import time
        from app.services.pricing_jobs import JobRegistry

        reg = JobRegistry()
        job_id = reg.submit("test", lambda: {"status": "ok", "value": 42})
        for _ in range(50):
            job = reg.get(job_id)
            if job["status"] != "running":
                break
            time.sleep(0.05)
        assert job["status"] == "done"
        assert job["result"]["value"] == 42

    def test_failure_recorded(self):
        import time
        from app.services.pricing_jobs import JobRegistry

        def boom():
            raise RuntimeError("nope")

        reg = JobRegistry()
        job_id = reg.submit("fail", boom)
        for _ in range(50):
            job = reg.get(job_id)
            if job["status"] != "running":
                break
            time.sleep(0.05)
        assert job["status"] == "error"
        assert "nope" in job["result"]["message"]

    def test_unknown_job(self):
        from app.services.pricing_jobs import JobRegistry
        assert JobRegistry().get("missing") is None


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


class TestFailSafeDefaults:
    """Ревью 2026-07-03: отсутствие строки правила в БД не должно отключать
    защитные проверки — применяются FAILSAFE_DEFAULTS (fail-safe, не fail-open)."""

    def test_min_margin_enforced_without_rule(self, rules_svc):
        # маржа 20% при дефолте 60% — блок даже с пустым набором правил
        ok, violations = rules_svc.check_recommendation(
            current_price=1000, candidate_price=1000, cogs=800,
            menu_role="margin_driver", last_change_date=None, rules={},
        )
        assert not ok
        assert any(v.startswith("min_margin") for v in violations)

    def test_max_step_enforced_without_rule(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            current_price=1000, candidate_price=1200, cogs=100,
            menu_role="margin_driver", last_change_date=None, rules={},
        )
        assert not ok
        assert any(v.startswith("max_step") for v in violations)

    def test_rounding_enforced_without_rule(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            current_price=1000, candidate_price=1030, cogs=100,
            menu_role="margin_driver", last_change_date=None, rules={},
        )
        assert not ok
        assert any(v.startswith("rounding") for v in violations)

    def test_min_frequency_enforced_without_rule(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            current_price=1000, candidate_price=1050, cogs=100,
            menu_role="margin_driver",
            last_change_date=date.today() - timedelta(days=3), rules={},
        )
        assert not ok
        assert any(v.startswith("min_frequency") for v in violations)

    def test_valid_candidate_passes_with_empty_rules(self, rules_svc):
        ok, violations = rules_svc.check_recommendation(
            current_price=1000, candidate_price=1050, cogs=100,
            menu_role="margin_driver", last_change_date=None, rules={},
        )
        assert ok, violations


class TestPlanningElasticityGlobalLevel:
    """Global prior (≈ -0.1) не должен уходить в планирование data-poor SKU."""

    def test_global_level_uses_hard_fallback(self):
        # ci_lower от global prior почти равен mean — планируем не мягче -1.0
        assert select_planning_elasticity(-0.106, -0.11, "D", "global") == -1.0

    def test_global_level_keeps_more_elastic_ci(self):
        assert select_planning_elasticity(-0.5, -1.8, "D", "global") == -1.8

    def test_group_level_still_uses_ci(self):
        assert select_planning_elasticity(-0.2, -0.8, "C", "group") == -0.8

    def test_grade_ab_unaffected_by_level(self):
        assert select_planning_elasticity(-0.4, -0.9, "A", "global") == -0.4


class TestCumulativeCap:
    """Храповик: цена не выше +15% к цене 90 дней назад."""

    def _sku(self, price_90d):
        return {
            "product_id": 1,
            "product_name": "Test",
            "current_price": 1000.0,
            "avg_daily_qty": 100.0,
            "cogs": 200.0,
            "elasticity": -0.3,
            "elasticity_mean": -0.3,
            "elasticity_grade": "A",
            "menu_role": "margin_driver",
            "last_change_date": None,
            "segment_type": None,
            "estimation_level": "sku",
            "price_90d": price_90d,
            "department_id": "00000000-0000-0000-0000-000000000001",
        }

    def _patch_rules(self, optimizer, monkeypatch):
        monkeypatch.setattr(
            optimizer.rules_service, "get_effective_rules",
            lambda *a, **k: dict(DEFAULT_RULES),
        )

    def test_cap_blocks_price_above_cumulative_ceiling(self, optimizer, monkeypatch):
        self._patch_rules(optimizer, monkeypatch)
        # 90 дней назад цена была 900 → потолок 1035; неэластичный SKU
        # без потолка ушёл бы на верх коридора (1050)
        rec = optimizer._optimize_single(
            self._sku(price_90d=900.0), "batch", 0.0, date.today(),
        )
        if rec is not None:
            assert rec["recommended_price"] <= 900.0 * 1.15
            assert "cumulative_cap" in (rec["constraints_applied"] or [])

    def test_no_cap_without_history(self, optimizer, monkeypatch):
        self._patch_rules(optimizer, monkeypatch)
        rec = optimizer._optimize_single(
            self._sku(price_90d=None), "batch", 0.0, date.today(),
        )
        assert rec is not None
        assert rec["recommended_price"] == 1050.0  # верх коридора ±5%


class TestDirectionalPlanningElasticity:
    """Двусторонний пессимизм: вниз — неэластичный край, иначе широкий CI
    для C/D делает снижение цены ложно привлекательным."""

    def test_down_uses_inelastic_edge_for_cd(self):
        from app.services.price_optimizer_service import select_planning_elasticity_down
        assert select_planning_elasticity_down(-1.5, -0.2, "D", "group") == -0.2
        assert select_planning_elasticity_down(-1.5, -0.2, "C", "group") == -0.2

    def test_down_grade_ab_uses_mean(self):
        from app.services.price_optimizer_service import select_planning_elasticity_down
        assert select_planning_elasticity_down(-0.7, -0.2, "A") == -0.7

    def test_down_without_ci_falls_back_near_zero(self):
        from app.services.price_optimizer_service import select_planning_elasticity_down
        assert select_planning_elasticity_down(-1.5, None, "D") == -0.1

    def test_optimizer_does_not_recommend_speculative_decrease(self, optimizer, monkeypatch):
        """Grade D с широким CI: снижение цены не должно выигрывать за счёт
        сверхэластичного края — вниз планируем по неэластичному краю."""
        monkeypatch.setattr(
            optimizer.rules_service, "get_effective_rules",
            lambda *a, **k: {k2: v for k2, v in DEFAULT_RULES.items() if k2 != "no_decrease_anchor"},
        )
        sku = {
            "product_id": 1, "product_name": "T", "current_price": 1000.0,
            "avg_daily_qty": 100.0, "cogs": 200.0,
            "elasticity": -3.0,        # вверх: сверхконсервативно
            "elasticity_down": -0.2,   # вниз: почти нет отклика
            "elasticity_mean": -0.4, "elasticity_grade": "D",
            "menu_role": "margin_driver", "last_change_date": None,
            "segment_type": None, "estimation_level": "group",
            "price_90d": None,
            "department_id": "00000000-0000-0000-0000-000000000001",
        }
        rec = optimizer._optimize_single(sku, "batch", 0.0, date.today())
        # при ε_down=-0.2 снижение цены режет GP → рекомендации быть не должно
        # (повышение заблокировано ε_up=-3.0)
        assert rec is None


class TestRollbackRuleRelaxation:
    """Откат возвращает цену, которая уже стояла в каталоге.

    Правила, описывающие выбор НОВОЙ цены (округление, шаг, защита якорей),
    к нему неприменимы: на пилоте они запрещали вернуться туда, откуда система
    сама же увела цену — исходные цены 430/810/1010/1360/1990/2890 ₸ не кратны
    шагу 50. Финансовый пол min_margin при этом остаётся.
    """

    def test_rounding_blocks_optimizer_but_not_rollback(self, rules_svc):
        # 1400 → 1360: возврат к прежней цене, не кратной 50
        ok_opt, viol = rules_svc.check_recommendation(
            1400.0, 1360.0, 331.86, "traffic_driver", None, DEFAULT_RULES)
        assert not ok_opt
        assert any(v.startswith("rounding") for v in viol)

        ok_rb, viol_rb = rules_svc.check_recommendation(
            1400.0, 1360.0, 331.86, "traffic_driver", None, DEFAULT_RULES,
            rec_type="rollback")
        assert ok_rb, viol_rb

    def test_max_step_relaxed_for_rollback(self, rules_svc):
        # 3090 → 2890 это −6.5%: шаг больше 5% только потому, что цену
        # применили вручную с окончанием «90»
        ok_opt, viol = rules_svc.check_recommendation(
            3090.0, 2890.0, 870.87, "traffic_driver", None, DEFAULT_RULES)
        assert not ok_opt
        assert any(v.startswith("max_step") for v in viol)

        ok_rb, _ = rules_svc.check_recommendation(
            3090.0, 2890.0, 870.87, "traffic_driver", None, DEFAULT_RULES,
            rec_type="rollback")
        assert ok_rb

    def test_anchor_and_frequency_relaxed_for_rollback(self, rules_svc):
        yesterday = date.today() - timedelta(days=1)
        ok_opt, viol = rules_svc.check_recommendation(
            3100.0, 3000.0, 800.0, "premium_anchor", yesterday, DEFAULT_RULES)
        assert not ok_opt
        assert any(v.startswith("no_decrease_anchor") for v in viol)
        assert any(v.startswith("min_frequency") for v in viol)

        ok_rb, _ = rules_svc.check_recommendation(
            3100.0, 3000.0, 800.0, "premium_anchor", yesterday, DEFAULT_RULES,
            rec_type="rollback")
        assert ok_rb

    def test_min_margin_is_never_relaxed(self, rules_svc):
        """Финансовый пол — не политика выбора цены: снимать его нельзя."""
        ok, viol = rules_svc.check_recommendation(
            450.0, 400.0, 163.15, "traffic_driver", None, DEFAULT_RULES,
            rec_type="rollback")
        assert not ok
        assert any(v.startswith("min_margin") for v in viol)

    def test_optimizer_unaffected_by_default(self, rules_svc):
        """rec_type по умолчанию не меняет поведение существующих вызовов."""
        a = rules_svc.check_recommendation(
            1000.0, 1050.0, 300.0, "traffic_driver", None, DEFAULT_RULES)
        b = rules_svc.check_recommendation(
            1000.0, 1050.0, 300.0, "traffic_driver", None, DEFAULT_RULES,
            rec_type="optimizer")
        assert a == b


class TestStopListDirection:
    """params.block задаёт направление блокировки.

    Позиции с доказанным убытком от повышения должны быть закрыты для подъёма
    и открыты для возврата — иначе стоп-лист блокирует собственное лечение.
    """

    def test_default_blocks_any_change(self, rules_svc):
        rules = {**DEFAULT_RULES, "stop_list": {"reason": "x"}}
        for candidate in (1050.0, 950.0):
            ok, viol = rules_svc.check_recommendation(
                1000.0, candidate, 300.0, "traffic_driver", None, rules,
                rec_type="rollback")
            assert not ok
            assert any(v.startswith("stop_list") for v in viol)

    def test_block_increase_allows_rollback(self, rules_svc):
        rules = {**DEFAULT_RULES, "stop_list": {"block": "increase"}}
        ok_up, viol = rules_svc.check_recommendation(
            1000.0, 1050.0, 300.0, "traffic_driver", None, rules)
        assert not ok_up
        assert any(v.startswith("stop_list") for v in viol)

        ok_down, _ = rules_svc.check_recommendation(
            1000.0, 950.0, 300.0, "traffic_driver", None, rules,
            rec_type="rollback")
        assert ok_down

    def test_block_decrease_allows_increase(self, rules_svc):
        rules = {**DEFAULT_RULES, "stop_list": {"block": "decrease"}}
        ok_up, _ = rules_svc.check_recommendation(
            1000.0, 1050.0, 300.0, "traffic_driver", None, rules)
        assert ok_up
        ok_down, _ = rules_svc.check_recommendation(
            1000.0, 950.0, 300.0, "traffic_driver", None, rules,
            rec_type="rollback")
        assert not ok_down

    def test_unchanged_price_never_violates(self, rules_svc):
        rules = {**DEFAULT_RULES, "stop_list": {"block": "any"}}
        _, viol = rules_svc.check_recommendation(
            1000.0, 1000.0, 300.0, "traffic_driver", None, rules)
        assert not any(v.startswith("stop_list") for v in viol)

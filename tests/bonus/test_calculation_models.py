"""Tests for the 5 calculation models — using exact numbers from docs/10-testing.md."""

from decimal import Decimal
from datetime import date

import pytest

from app.bonus.calculator import get_model
from app.bonus.calculator.context import CalculationContext, KpiFact, ShiftStats
from app.bonus.utils.period import PeriodKey


PERIOD_2026_04 = PeriodKey(2026, 4)


def _ctx(**overrides) -> CalculationContext:
    base = dict(
        period=PERIOD_2026_04,
        department_id="dept-1",
        department_name="Test Dept",
        shifts=ShiftStats(worked=Decimal("22"), norm=Decimal("22")),
    )
    base.update(overrides)
    return CalculationContext(**base)


def _kpi(code, percent, direction="higher_is_better", fact=None, target=None):
    return KpiFact(code=code, fact=fact, target=target, percent=Decimal(str(percent)),
                   direction=direction)


# ---------------------------------------------------------------------------
# flat_by_kpi — Управляющий
# ---------------------------------------------------------------------------
GRADES_FLAT = [
    {"from": 70, "to": 79, "value": 80000},
    {"from": 80, "to": 84, "value": 100000},
    {"from": 85, "to": 89, "value": 130000},
    {"from": 90, "to": 97, "value": 150000},
    {"from": 98, "to": 100, "value": 170000},
]

CONFIG_FLAT = {
    "model": "flat_by_kpi",
    "kpis": [
        {"code": "staffing", "source": "hr_staffing_percent",
         "direction": "higher_is_better", "target": 100},
        {"code": "negative_reviews", "source": "crm_negative_reviews_share",
         "direction": "lower_is_better", "target": 5},
        {"code": "audit", "source": "manual_audit",
         "direction": "higher_is_better", "target": 100},
        {"code": "apc_growth", "source": "iiko_apc_growth",
         "direction": "higher_is_better", "target": 5},
        {"code": "profitability", "source": "manual_profitability",
         "direction": "higher_is_better", "target_metric": "monthly_plan_profitability"},
    ],
    "grades": GRADES_FLAT,
    "below_threshold_bonus": 0,
    "apply_shifts_proration": False,
}


class TestFlatByKpi:
    def setup_method(self):
        self.model = get_model("flat_by_kpi")
        self.model.validate_config(CONFIG_FLAT)

    def test_TC01_perfect_100_percent(self):
        ctx = _ctx(kpi_values={
            "staffing": _kpi("staffing", 100),
            "negative_reviews": _kpi("negative_reviews", 100, "lower_is_better"),
            "audit": _kpi("audit", 100),
            "apc_growth": _kpi("apc_growth", 100),
            "profitability": _kpi("profitability", 100),
        })
        result = self.model.calculate(CONFIG_FLAT, ctx)
        assert result.final_bonus == Decimal("170000")
        assert result.applied_grade_from == Decimal("98")

    def test_TC02_average_90_8(self):
        # 95+96+90+88+85 = 454/5 = 90.8 → ceil 91 → grade 90-97 → 150000
        ctx = _ctx(kpi_values={
            "staffing": _kpi("staffing", 95),
            "negative_reviews": _kpi("negative_reviews", 96, "lower_is_better"),
            "audit": _kpi("audit", 90),
            "apc_growth": _kpi("apc_growth", 88),
            "profitability": _kpi("profitability", 85),
        })
        result = self.model.calculate(CONFIG_FLAT, ctx)
        assert result.overall_kpi_percent == Decimal("90.80")
        assert result.final_bonus == Decimal("150000")

    def test_TC03_below_threshold(self):
        # 60+65+70+80+50 = 325/5 = 65 → below 70%
        ctx = _ctx(kpi_values={
            "staffing": _kpi("staffing", 60),
            "negative_reviews": _kpi("negative_reviews", 65, "lower_is_better"),
            "audit": _kpi("audit", 70),
            "apc_growth": _kpi("apc_growth", 80),
            "profitability": _kpi("profitability", 50),
        })
        result = self.model.calculate(CONFIG_FLAT, ctx)
        assert result.final_bonus == Decimal("0")
        assert result.is_zero_reason == "kpi_below_min_grade"

    def test_TC04_boundary_79_5_ceil_to_80(self):
        # 78+80+79+80+80 = 397/5 = 79.4 — let's pick 79.5
        ctx = _ctx(kpi_values={
            "staffing": _kpi("staffing", "79.5"),
            "negative_reviews": _kpi("negative_reviews", "79.5", "lower_is_better"),
            "audit": _kpi("audit", "79.5"),
            "apc_growth": _kpi("apc_growth", "79.5"),
            "profitability": _kpi("profitability", "79.5"),
        })
        result = self.model.calculate(CONFIG_FLAT, ctx)
        assert result.final_bonus == Decimal("100000")

    def test_TC05_exact_grade_boundary_90(self):
        ctx = _ctx(kpi_values={
            "staffing": _kpi("staffing", 90),
            "negative_reviews": _kpi("negative_reviews", 90, "lower_is_better"),
            "audit": _kpi("audit", 90),
            "apc_growth": _kpi("apc_growth", 90),
            "profitability": _kpi("profitability", 90),
        })
        result = self.model.calculate(CONFIG_FLAT, ctx)
        assert result.final_bonus == Decimal("150000")


# ---------------------------------------------------------------------------
# revenue_direct — Кассир / Старший бариста
# ---------------------------------------------------------------------------
class TestRevenueDirect:
    def setup_method(self):
        self.model = get_model("revenue_direct")

    def test_TC10_cashier_no_proration(self):
        config = {
            "model": "revenue_direct",
            "revenue_source": "iiko_revenue_without_discount",
            "rate": "0.0007",
            "apply_shifts_proration": False,
        }
        self.model.validate_config(config)
        ctx = _ctx(revenue_values={"iiko_revenue_without_discount": Decimal("25000000")})
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("17500")

    def test_TC11_cashier_with_proration(self):
        config = {
            "model": "revenue_direct",
            "revenue_source": "iiko_revenue_without_discount",
            "rate": "0.0007",
            "apply_shifts_proration": True,
            "shifts_proration_formula": "ratio",
        }
        ctx = _ctx(
            revenue_values={"iiko_revenue_without_discount": Decimal("25000000")},
            shifts=ShiftStats(worked=Decimal("11"), norm=Decimal("22")),
        )
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("8750")

    def test_TC12_senior_barista_norm_then_actual(self):
        config = {
            "model": "revenue_direct",
            "revenue_source": "iiko_revenue_with_discount",
            "rate": "0.0033",
            "apply_shifts_proration": True,
            "shifts_proration_formula": "norm_then_actual",
        }
        ctx = _ctx(
            revenue_values={"iiko_revenue_with_discount": Decimal("25000000")},
            shifts=ShiftStats(worked=Decimal("20"), norm=Decimal("22")),
        )
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("75000")

    def test_TC13_tary_kainar_senior_barista_full_month(self):
        config = {
            "model": "revenue_direct",
            "revenue_source": "iiko_revenue_with_discount",
            "rate": "0.007",
            "apply_shifts_proration": True,
            "shifts_proration_formula": "norm_then_actual",
        }
        ctx = _ctx(
            revenue_values={"iiko_revenue_with_discount": Decimal("25000000")},
            shifts=ShiftStats(worked=Decimal("22"), norm=Decimal("22")),
        )
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("175000")


# ---------------------------------------------------------------------------
# combined_products — Бариста
# ---------------------------------------------------------------------------
class TestCombinedProducts:
    def setup_method(self):
        self.model = get_model("combined_products")

    def test_TC20_tary_kainar_50000(self):
        config = {
            "model": "combined_products",
            "components": [
                {"code": "ready_products", "name": "Готовая продукция",
                 "source": "iiko_personal_ready_products_with_discount", "rate": "0.001"},
                {"code": "prepared_products", "name": "Приготовленная продукция",
                 "source": "iiko_personal_prepared_products_with_discount", "rate": "0.016"},
            ],
            "apply_shifts_proration": False,
            "require_no_violations": True,
        }
        self.model.validate_config(config)
        ctx = _ctx(revenue_values={
            "iiko_personal_ready_products_with_discount": Decimal("2000000"),
            "iiko_personal_prepared_products_with_discount": Decimal("3000000"),
        })
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("50000")

    def test_TC21_sandyq_kainar_41000(self):
        config = {
            "model": "combined_products",
            "components": [
                {"code": "ready_products", "name": "Готовая",
                 "source": "iiko_personal_ready_products_with_discount", "rate": "0.001"},
                {"code": "prepared_products", "name": "Приготовленная",
                 "source": "iiko_personal_prepared_products_with_discount", "rate": "0.013"},
            ],
        }
        ctx = _ctx(revenue_values={
            "iiko_personal_ready_products_with_discount": Decimal("2000000"),
            "iiko_personal_prepared_products_with_discount": Decimal("3000000"),
        })
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("41000")

    def test_TC22_senior_astana_37000(self):
        config = {
            "model": "combined_products",
            "components": [
                {"code": "r", "name": "Готовая",
                 "source": "iiko_personal_ready_products_with_discount", "rate": "0.001"},
                {"code": "p", "name": "Приготовленная",
                 "source": "iiko_personal_prepared_products_with_discount", "rate": "0.007"},
            ],
        }
        ctx = _ctx(revenue_values={
            "iiko_personal_ready_products_with_discount": Decimal("2000000"),
            "iiko_personal_prepared_products_with_discount": Decimal("5000000"),
        })
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("37000")

    def test_TC23_middle_astana_18000(self):
        config = {
            "model": "combined_products",
            "components": [
                {"code": "r", "name": "Готовая",
                 "source": "iiko_personal_ready_products_with_discount", "rate": "0.0015"},
                {"code": "p", "name": "Приготовленная",
                 "source": "iiko_personal_prepared_products_with_discount", "rate": "0.003"},
            ],
        }
        ctx = _ctx(revenue_values={
            "iiko_personal_ready_products_with_discount": Decimal("2000000"),
            "iiko_personal_prepared_products_with_discount": Decimal("5000000"),
        })
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("18000")


# ---------------------------------------------------------------------------
# revenue_percent_by_kpi — Менеджер, Официант
# ---------------------------------------------------------------------------
GRADES_RATE = [
    {"from": 70, "to": 79, "rate": "0.03"},
    {"from": 80, "to": 84, "rate": "0.035"},
    {"from": 85, "to": 89, "rate": "0.04"},
    {"from": 90, "to": 97, "rate": "0.042"},
    {"from": 98, "to": 100, "rate": "0.045"},
]


class TestRevenuePercentByKpi:
    def setup_method(self):
        self.model = get_model("revenue_percent_by_kpi")

    def test_TC30_perfect_waiter(self):
        config = {
            "model": "revenue_percent_by_kpi",
            "kpis": [
                {"code": "sales_plan", "source": "iiko_sales_plan_personal",
                 "direction": "higher_is_better", "target_metric": "monthly_plan_sales"},
                {"code": "individual_negative_reviews", "source": "crm_individual_negative_reviews",
                 "direction": "lower_is_better", "target": 3},
                {"code": "margin_share", "source": "iiko_margin_share",
                 "direction": "higher_is_better", "target": 40},
            ],
            "revenue_source": "iiko_personal_revenue_with_discount",
            "grades": GRADES_RATE,
            "apply_shifts_proration": False,
        }
        self.model.validate_config(config)
        ctx = _ctx(
            kpi_values={
                "sales_plan": _kpi("sales_plan", 100),
                "individual_negative_reviews": _kpi("individual_negative_reviews", 100, "lower_is_better"),
                "margin_share": _kpi("margin_share", 100),
            },
            revenue_values={"iiko_personal_revenue_with_discount": Decimal("2500000")},
        )
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("112500")

    def test_TC31_85pct(self):
        config = {
            "model": "revenue_percent_by_kpi",
            "kpis": [{"code": "k1", "source": "x", "direction": "higher_is_better", "target": 100}],
            "revenue_source": "rev",
            "grades": GRADES_RATE,
        }
        ctx = _ctx(
            kpi_values={"k1": _kpi("k1", 85)},
            revenue_values={"rev": Decimal("2000000")},
        )
        result = self.model.calculate(config, ctx)
        # 85% → grade 85-89% → rate 0.04 → 2_000_000 × 0.04 = 80_000
        assert result.final_bonus == Decimal("80000")

    def test_TC32_below_threshold(self):
        config = {
            "model": "revenue_percent_by_kpi",
            "kpis": [{"code": "k1", "source": "x", "direction": "higher_is_better", "target": 100}],
            "revenue_source": "rev",
            "grades": GRADES_RATE,
        }
        ctx = _ctx(
            kpi_values={"k1": _kpi("k1", 65)},
            revenue_values={"rev": Decimal("2000000")},
        )
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("0")
        assert result.is_zero_reason == "kpi_below_min_grade"

    def test_TC36_manager_with_proration(self):
        # KPI 100% → rate 0.002, revenue 50M, worked 11/22 → 50_000
        config = {
            "model": "revenue_percent_by_kpi",
            "kpis": [{"code": "k1", "source": "x", "direction": "higher_is_better", "target": 100}],
            "revenue_source": "rev",
            "grades": [
                {"from": 70, "to": 79, "rate": "0.0005"},
                {"from": 80, "to": 84, "rate": "0.001"},
                {"from": 85, "to": 89, "rate": "0.0013"},
                {"from": 90, "to": 97, "rate": "0.0015"},
                {"from": 98, "to": 100, "rate": "0.002"},
            ],
            "apply_shifts_proration": True,
        }
        ctx = _ctx(
            kpi_values={"k1": _kpi("k1", 100)},
            revenue_values={"rev": Decimal("50000000")},
            shifts=ShiftStats(worked=Decimal("11"), norm=Decimal("22")),
        )
        result = self.model.calculate(config, ctx)
        assert result.final_bonus == Decimal("50000")


# ---------------------------------------------------------------------------
# team_revenue_by_kpi — KITCHEN
# ---------------------------------------------------------------------------
class TestTeamRevenueByKpi:
    def setup_method(self):
        self.model = get_model("team_revenue_by_kpi")
        self.config = {
            "model": "team_revenue_by_kpi",
            "kpis": [
                {"code": "sales_plan", "source": "iiko_sales_plan_location",
                 "direction": "higher_is_better", "target_metric": "monthly_plan_sales"},
                {"code": "kitchen_audit", "source": "manual_kitchen_audit",
                 "direction": "higher_is_better", "target": 100},
                {"code": "kitchen_negative_reviews", "source": "crm_kitchen_reviews",
                 "direction": "lower_is_better", "target": 3},
            ],
            "revenue_source": "iiko_revenue_with_discount",
            "grades": GRADES_RATE,
            "below_threshold_bonus_zero": True,
            "distribution_formula": "revenue * slot_weight * shifts_ratio",
            "apply_shifts_proration": True,
            "exclude_probation_period": True,
        }

    def test_TC40_chef_full_month(self):
        self.model.validate_config(self.config)
        ctx = _ctx(
            kpi_values={
                "sales_plan": _kpi("sales_plan", 100),
                "kitchen_audit": _kpi("kitchen_audit", 100),
                "kitchen_negative_reviews": _kpi("kitchen_negative_reviews", 100, "lower_is_better"),
            },
            revenue_values={"iiko_revenue_with_discount": Decimal("50000000")},
            team_position_slot="chef",
            team_position_weight=Decimal("0.0013"),
            shifts=ShiftStats(worked=Decimal("22"), norm=Decimal("22")),
        )
        result = self.model.calculate(self.config, ctx)
        assert result.final_bonus == Decimal("65000")

    def test_TC41_sous_chef_partial_shifts(self):
        ctx = _ctx(
            kpi_values={
                "sales_plan": _kpi("sales_plan", 100),
                "kitchen_audit": _kpi("kitchen_audit", 100),
                "kitchen_negative_reviews": _kpi("kitchen_negative_reviews", 100, "lower_is_better"),
            },
            revenue_values={"iiko_revenue_with_discount": Decimal("50000000")},
            team_position_slot="sous_chef_1",
            team_position_weight=Decimal("0.0009"),
            shifts=ShiftStats(worked=Decimal("11"), norm=Decimal("22")),
        )
        result = self.model.calculate(self.config, ctx)
        assert result.final_bonus == Decimal("22500")

    def test_TC42_below_threshold_zero(self):
        ctx = _ctx(
            kpi_values={
                "sales_plan": _kpi("sales_plan", 65),
                "kitchen_audit": _kpi("kitchen_audit", 65),
                "kitchen_negative_reviews": _kpi("kitchen_negative_reviews", 65, "lower_is_better"),
            },
            revenue_values={"iiko_revenue_with_discount": Decimal("50000000")},
            team_position_slot="chef",
            team_position_weight=Decimal("0.0013"),
        )
        result = self.model.calculate(self.config, ctx)
        assert result.final_bonus == Decimal("0")
        assert result.is_zero_reason == "team_kpi_below_min_grade"

    def test_TC43_probation_excluded(self):
        ctx = _ctx(
            kpi_values={
                "sales_plan": _kpi("sales_plan", 100),
                "kitchen_audit": _kpi("kitchen_audit", 100),
                "kitchen_negative_reviews": _kpi("kitchen_negative_reviews", 100, "lower_is_better"),
            },
            revenue_values={"iiko_revenue_with_discount": Decimal("50000000")},
            team_position_slot="chef",
            team_position_weight=Decimal("0.0013"),
            employment_type="probation",
            probation_until=date(2026, 4, 30),
        )
        result = self.model.calculate(self.config, ctx)
        assert result.final_bonus == Decimal("0")
        assert result.is_zero_reason == "probation_period"


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------
def test_registry_has_all_5_models():
    from app.bonus.calculator import CALCULATION_MODELS
    expected = {
        "flat_by_kpi",
        "revenue_percent_by_kpi",
        "revenue_direct",
        "combined_products",
        "team_revenue_by_kpi",
    }
    assert set(CALCULATION_MODELS.keys()) == expected


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        get_model("nonexistent")

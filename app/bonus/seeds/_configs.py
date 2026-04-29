"""Reusable scheme configs taken from bonus_docs/07-config-examples.md.

Functions return dicts ready to feed into upsert_scheme(). All numbers are
strings to preserve Decimal precision.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Управляющий — общий грейд для всех локаций (числа из 07-config-examples)
# ---------------------------------------------------------------------------
def manager_director_config() -> dict:
    return {
        "model": "flat_by_kpi",
        "kpis": [
            {"code": "staffing", "source": "hr_staffing_percent",
             "direction": "higher_is_better", "target": "100"},
            {"code": "negative_reviews", "source": "crm_negative_reviews_share",
             "direction": "lower_is_better", "target": "5"},
            {"code": "audit", "source": "manual_audit",
             "direction": "higher_is_better", "target": "100"},
            {"code": "apc_growth", "source": "iiko_apc_growth",
             "direction": "higher_is_better", "target": "5"},
            {"code": "profitability", "source": "manual_profitability",
             "direction": "higher_is_better",
             "target_metric": "monthly_plan_profitability"},
        ],
        "grades": [
            {"from": 70, "to": 79, "value": "80000"},
            {"from": 80, "to": 84, "value": "100000"},
            {"from": 85, "to": 89, "value": "130000"},
            {"from": 90, "to": 97, "value": "150000"},
            {"from": 98, "to": 100, "value": "170000"},
        ],
        "below_threshold_bonus": "0",
        "apply_shifts_proration": False,
    }


# ---------------------------------------------------------------------------
# Менеджер (Администратор-кассир)
# ---------------------------------------------------------------------------
def manager_admin_config() -> dict:
    return {
        "model": "revenue_percent_by_kpi",
        "kpis": [
            {"code": "restaurant_rating", "source": "crm_restaurant_rating",
             "direction": "binary", "target": "5"},
            {"code": "sales_plan", "source": "iiko_sales_plan_location",
             "direction": "higher_is_better",
             "target_metric": "monthly_plan_sales"},
            {"code": "negative_reviews", "source": "crm_negative_reviews_share",
             "direction": "lower_is_better", "target": "5"},
            {"code": "audit_quality", "source": "manual_audit",
             "direction": "higher_is_better", "target": "80"},
        ],
        "revenue_source": "iiko_revenue_with_discount",
        "grades": [
            {"from": 70, "to": 79, "rate": "0.0005"},
            {"from": 80, "to": 84, "rate": "0.001"},
            {"from": 85, "to": 89, "rate": "0.0013"},
            {"from": 90, "to": 97, "rate": "0.0015"},
            {"from": 98, "to": 100, "rate": "0.002"},
        ],
        "apply_shifts_proration": True,
    }


# ---------------------------------------------------------------------------
# Кассир — варьируется по локациям. Передаём rate.
# ---------------------------------------------------------------------------
def cashier_config(rate: str) -> dict:
    return {
        "model": "revenue_direct",
        "revenue_source": "iiko_revenue_dish_sum",   # «без скидки»
        "rate": rate,
        "apply_shifts_proration": True,
        "shifts_proration_formula": "ratio",
    }


# ---------------------------------------------------------------------------
# Старший бариста — varies by location
# ---------------------------------------------------------------------------
def senior_barista_config(rate: str) -> dict:
    return {
        "model": "revenue_direct",
        "revenue_source": "iiko_revenue_with_discount",
        "rate": rate,
        "apply_shifts_proration": True,
        "shifts_proration_formula": "norm_then_actual",
    }


# ---------------------------------------------------------------------------
# Бариста — combined products
# ---------------------------------------------------------------------------
def barista_config(ready_rate: str, prepared_rate: str) -> dict:
    return {
        "model": "combined_products",
        "components": [
            {"code": "ready_products", "name": "Готовая продукция",
             "source": "iiko_personal_ready_products_with_discount",
             "rate": ready_rate},
            {"code": "prepared_products", "name": "Приготовленная продукция",
             "source": "iiko_personal_prepared_products_with_discount",
             "rate": prepared_rate},
        ],
        "apply_shifts_proration": False,
        "require_no_violations": True,
    }


# ---------------------------------------------------------------------------
# Официант — общий
# ---------------------------------------------------------------------------
def waiter_config() -> dict:
    return {
        "model": "revenue_percent_by_kpi",
        "kpis": [
            {"code": "sales_plan", "source": "iiko_sales_plan_personal",
             "direction": "higher_is_better",
             "target_metric": "monthly_plan_sales"},
            {"code": "individual_negative_reviews",
             "source": "crm_individual_negative_reviews",
             "direction": "lower_is_better", "target": "3"},
            {"code": "margin_share", "source": "iiko_margin_share",
             "direction": "higher_is_better", "target": "40"},
        ],
        "revenue_source": "iiko_personal_revenue_with_discount",
        "grades": [
            {"from": 70, "to": 79, "rate": "0.03"},
            {"from": 80, "to": 84, "rate": "0.035"},
            {"from": 85, "to": 89, "rate": "0.04"},
            {"from": 90, "to": 97, "rate": "0.042"},
            {"from": 98, "to": 100, "rate": "0.045"},
        ],
        "apply_shifts_proration": True,
    }


# ---------------------------------------------------------------------------
# KITCHEN — team_revenue_by_kpi
# ---------------------------------------------------------------------------
def kitchen_config() -> dict:
    return {
        "model": "team_revenue_by_kpi",
        "kpis": [
            {"code": "sales_plan", "source": "iiko_sales_plan_location",
             "direction": "higher_is_better",
             "target_metric": "monthly_plan_sales"},
            {"code": "kitchen_audit", "source": "manual_kitchen_audit",
             "direction": "higher_is_better", "target": "100"},
            {"code": "kitchen_negative_reviews", "source": "crm_kitchen_reviews",
             "direction": "lower_is_better", "target": "3"},
        ],
        "revenue_source": "iiko_revenue_with_discount",
        "grades": [
            {"from": 70, "to": 79, "rate": "0.03"},
            {"from": 80, "to": 84, "rate": "0.035"},
            {"from": 85, "to": 89, "rate": "0.04"},
            {"from": 90, "to": 97, "rate": "0.042"},
            {"from": 98, "to": 100, "rate": "0.045"},
        ],
        "below_threshold_bonus_zero": True,
        "distribution_formula": "revenue * slot_weight * shifts_ratio",
        "apply_shifts_proration": True,
        "exclude_probation_period": True,
        "exclude_violators": False,
    }


# ---------------------------------------------------------------------------
# KITCHEN slots — 21 позиция (одинаковая структура для всех KITCHEN-команд)
# ---------------------------------------------------------------------------
KITCHEN_SLOTS: list[dict] = [
    {"slot": "chef",                "name": "Шеф-повар",                 "weight": "0.0013", "position_code": "chef"},
    {"slot": "sous_chef_1",         "name": "Су-шеф 1",                  "weight": "0.0009", "position_code": "sous_chef"},
    {"slot": "sous_chef_2",         "name": "Су-шеф 2",                  "weight": "0.0006", "position_code": "sous_chef"},
    {"slot": "senior_shift_cook_1", "name": "Повар старшей смены 1",     "weight": "0.0008", "position_code": "senior_shift_cook"},
    {"slot": "senior_shift_cook_2", "name": "Повар старшей смены 2",     "weight": "0.0008", "position_code": "senior_shift_cook"},
    {"slot": "hot_cook_1",          "name": "Повар горячего цеха 1",     "weight": "0.0007", "position_code": "hot_cook"},
    {"slot": "hot_cook_2",          "name": "Повар горячего цеха 2",     "weight": "0.0004", "position_code": "hot_cook"},
    {"slot": "cold_cook_1",         "name": "Повар холодного цеха 1",    "weight": "0.0006", "position_code": "cold_cook"},
    {"slot": "cold_cook_2",         "name": "Повар холодного цеха 2",    "weight": "0.0004", "position_code": "cold_cook"},
    {"slot": "junior_cook_1",       "name": "Младший повар 1",           "weight": "0.0005", "position_code": "junior_cook"},
    {"slot": "junior_cook_2",       "name": "Младший повар 2",           "weight": "0.0003", "position_code": "junior_cook"},
    {"slot": "senior_meat_prep",    "name": "Старший заготовщик мяса",   "weight": "0.0008", "position_code": "senior_meat_prep"},
    {"slot": "junior_meat_prep",    "name": "Младший заготовщик мяса",   "weight": "0.0005", "position_code": "junior_meat_prep"},
    {"slot": "staff_cook_1",        "name": "Стафф-повар 1",             "weight": "0.0005", "position_code": "staff_cook"},
    {"slot": "staff_cook_2",        "name": "Стафф-повар 2",             "weight": "0.0005", "position_code": "staff_cook"},
    {"slot": "pastry_chef",         "name": "Шеф-кондитер",              "weight": "0.0007", "position_code": "pastry_chef"},
    {"slot": "senior_pastry",       "name": "Старший кондитер",          "weight": "0.0006", "position_code": "senior_pastry"},
    {"slot": "pastry_1",            "name": "Кондитер 1",                "weight": "0.0006", "position_code": "pastry"},
    {"slot": "pastry_2",            "name": "Кондитер 2",                "weight": "0.0004", "position_code": "pastry"},
    {"slot": "baker_1",             "name": "Пекарь 1",                  "weight": "0.0005", "position_code": "baker"},
    {"slot": "baker_2",             "name": "Пекарь 2",                  "weight": "0.0003", "position_code": "baker"},
]

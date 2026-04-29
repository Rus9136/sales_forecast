"""Master seed runner.

Usage:
    docker exec sales-forecast-app python -m app.bonus.seeds.run_all

Idempotent: re-running upserts existing rows. Doesn't touch existing schemes
that have non-null effective_to (closed versions remain frozen).
"""

from __future__ import annotations

import logging
from datetime import date

# Import all parent models first so SQLAlchemy can resolve cross-package FKs
from ...models import *  # noqa: F401,F403
from ...db import SessionLocal
from ._configs import (
    barista_config,
    cashier_config,
    kitchen_config,
    KITCHEN_SLOTS,
    manager_admin_config,
    manager_director_config,
    senior_barista_config,
    waiter_config,
)
from ._helpers import (
    find_department_by_name,
    upsert_company,
    upsert_kpi_definition,
    upsert_position,
    upsert_scheme,
    upsert_team,
    upsert_team_position,
)

logger = logging.getLogger(__name__)
DEFAULT_EFFECTIVE_FROM = date(2026, 1, 1)


def seed_companies(db):
    upsert_company(db, code="sandyq_kainar",  name="ТОО Sandyq Kainar")
    upsert_company(db, code="sandyq_astana",  name="ТОО Sandyq Astana")
    upsert_company(db, code="sandyq_world",   name="ТОО Sandyq World (Алматы)")
    upsert_company(db, code="tary_holding",   name="ТОО Tary Holding")


def seed_positions(db):
    # Service / Management
    upsert_position(db, code="director",       name="Управляющий",       category="management",
                    iiko_role_code="MN0", iiko_role_name="Управляющий")
    upsert_position(db, code="admin_manager",  name="Менеджер (Админ)",  category="management",
                    iiko_role_code="MN1", iiko_role_name="Администратор")
    upsert_position(db, code="cashier",        name="Кассир",            category="cashier",
                    iiko_role_code="CS1", iiko_role_name="Кассир")
    upsert_position(db, code="cashier_ff",     name="Кассир фаст-фуда",  category="cashier",
                    iiko_role_code="FFC", iiko_role_name="Кассир фаст-фуда")
    upsert_position(db, code="waiter",         name="Официант",          category="service",
                    iiko_role_code="WR1", iiko_role_name="Официант")
    upsert_position(db, code="senior_barista", name="Старший бариста",   category="bar",
                    iiko_role_code="Ст.барист", iiko_role_name="Старший барист")
    upsert_position(db, code="barista",        name="Бариста",           category="bar",
                    iiko_role_code="Барист", iiko_role_name="Барист")
    upsert_position(db, code="bartender",      name="Бармен",            category="bar",
                    iiko_role_code="BR1", iiko_role_name="Бармен")

    # KITCHEN positions (used as labels in team slots)
    upsert_position(db, code="chef",                name="Шеф-повар",         category="kitchen",
                    iiko_role_code="шеф-повар", iiko_role_name="шеф-повар")
    upsert_position(db, code="sous_chef",           name="Су-шеф",            category="kitchen",
                    iiko_role_code="су-шеф", iiko_role_name="су-шеф")
    upsert_position(db, code="senior_shift_cook",   name="Повар старшей смены", category="kitchen",
                    iiko_role_code="CO1", iiko_role_name="Повар")
    upsert_position(db, code="hot_cook",            name="Повар горячего цеха", category="kitchen",
                    iiko_role_code="CO1", iiko_role_name="Повар")
    upsert_position(db, code="cold_cook",           name="Повар холодного цеха", category="kitchen",
                    iiko_role_code="CO1", iiko_role_name="Повар")
    upsert_position(db, code="junior_cook",         name="Младший повар",     category="kitchen",
                    iiko_role_code="CO1", iiko_role_name="Повар")
    upsert_position(db, code="senior_meat_prep",    name="Старший заготовщик мяса", category="kitchen")
    upsert_position(db, code="junior_meat_prep",    name="Младший заготовщик мяса", category="kitchen")
    upsert_position(db, code="staff_cook",          name="Стафф-повар",       category="kitchen")
    upsert_position(db, code="pastry_chef",         name="Шеф-кондитер",      category="kitchen",
                    iiko_role_code="кондитер", iiko_role_name="Кондитер")
    upsert_position(db, code="senior_pastry",       name="Старший кондитер",  category="kitchen",
                    iiko_role_code="Ст.кондитер", iiko_role_name="Старший кондитер")
    upsert_position(db, code="pastry",              name="Кондитер",          category="kitchen",
                    iiko_role_code="кондитер", iiko_role_name="Кондитер")
    upsert_position(db, code="baker",               name="Пекарь",            category="kitchen",
                    iiko_role_code="пекарь", iiko_role_name="пекарь")


def seed_kpi_definitions(db):
    upsert_kpi_definition(db, code="hr_staffing_percent", name="% укомплектованности штата",
                          data_source_code="hr_staffing_percent", direction="higher_is_better",
                          default_target=100)
    upsert_kpi_definition(db, code="crm_negative_reviews_share", name="% негативных отзывов (точка)",
                          data_source_code="crm_negative_reviews_share", direction="lower_is_better",
                          default_target=5)
    upsert_kpi_definition(db, code="crm_individual_negative_reviews",
                          name="Личные негативные отзывы (%)",
                          data_source_code="crm_individual_negative_reviews",
                          direction="lower_is_better", default_target=3)
    upsert_kpi_definition(db, code="crm_kitchen_reviews", name="Негативные отзывы на кухню (%)",
                          data_source_code="crm_kitchen_reviews", direction="lower_is_better",
                          default_target=3)
    upsert_kpi_definition(db, code="crm_restaurant_rating", name="Рейтинг ресторана",
                          data_source_code="crm_restaurant_rating", direction="binary",
                          default_target=5)
    upsert_kpi_definition(db, code="manual_audit", name="Аудит / стандарты (%)",
                          data_source_code="manual_audit", direction="higher_is_better",
                          default_target=100)
    upsert_kpi_definition(db, code="manual_kitchen_audit", name="Аудит кухни (%)",
                          data_source_code="manual_kitchen_audit", direction="higher_is_better",
                          default_target=100)
    upsert_kpi_definition(db, code="manual_profitability", name="Рентабельность (%)",
                          data_source_code="manual_profitability", direction="higher_is_better",
                          target_metric="monthly_plan_profitability")
    upsert_kpi_definition(db, code="iiko_apc_growth", name="Рост среднего чека (%)",
                          data_source_code="iiko_apc_growth", direction="higher_is_better",
                          default_target=5)
    upsert_kpi_definition(db, code="iiko_margin_share", name="Доля маржинальных позиций (%)",
                          data_source_code="iiko_margin_share", direction="higher_is_better",
                          default_target=40)
    upsert_kpi_definition(db, code="iiko_sales_plan_personal", name="Личный план продаж (%)",
                          data_source_code="iiko_sales_plan_personal", direction="higher_is_better",
                          target_metric="monthly_plan_sales")
    upsert_kpi_definition(db, code="iiko_sales_plan_location", name="План продаж точки (%)",
                          data_source_code="iiko_sales_plan_location", direction="higher_is_better",
                          target_metric="monthly_plan_sales")


# ---------------------------------------------------------------------------
# Per-location scheme bundles
# ---------------------------------------------------------------------------
def _seed_basic_position_schemes(db, dept_id, *, cashier_rate=None,
                                 senior_barista_rate=None,
                                 barista_rates=None,
                                 with_director=True, with_admin_manager=True,
                                 with_waiter=True):
    positions = {p.code: p.id for p in db.query(__import___position_class()).all()}

    if with_director:
        upsert_scheme(db,
            department_id=dept_id, position_id=positions["director"], team_id=None,
            calculation_model="flat_by_kpi", config=manager_director_config(),
            effective_from=DEFAULT_EFFECTIVE_FROM, notes="seed",
        )
    if with_admin_manager:
        upsert_scheme(db,
            department_id=dept_id, position_id=positions["admin_manager"], team_id=None,
            calculation_model="revenue_percent_by_kpi", config=manager_admin_config(),
            effective_from=DEFAULT_EFFECTIVE_FROM, notes="seed",
        )
    if cashier_rate is not None:
        upsert_scheme(db,
            department_id=dept_id, position_id=positions["cashier"], team_id=None,
            calculation_model="revenue_direct", config=cashier_config(cashier_rate),
            effective_from=DEFAULT_EFFECTIVE_FROM, notes="seed",
        )
    if senior_barista_rate is not None:
        upsert_scheme(db,
            department_id=dept_id, position_id=positions["senior_barista"], team_id=None,
            calculation_model="revenue_direct", config=senior_barista_config(senior_barista_rate),
            effective_from=DEFAULT_EFFECTIVE_FROM, notes="seed",
        )
    if barista_rates is not None:
        ready_rate, prepared_rate = barista_rates
        upsert_scheme(db,
            department_id=dept_id, position_id=positions["barista"], team_id=None,
            calculation_model="combined_products",
            config=barista_config(ready_rate, prepared_rate),
            effective_from=DEFAULT_EFFECTIVE_FROM, notes="seed",
        )
    if with_waiter:
        upsert_scheme(db,
            department_id=dept_id, position_id=positions["waiter"], team_id=None,
            calculation_model="revenue_percent_by_kpi", config=waiter_config(),
            effective_from=DEFAULT_EFFECTIVE_FROM, notes="seed",
        )


def __import___position_class():
    from ..models.position import BonusPosition
    return BonusPosition


def _seed_kitchen(db, dept_id):
    positions = {p.code: p.id for p in db.query(__import___position_class()).all()}
    team = upsert_team(db, department_id=dept_id, code="kitchen", name="Кухня")
    for i, slot in enumerate(KITCHEN_SLOTS):
        pos_id = positions.get(slot["position_code"])
        if pos_id is None:
            logger.warning("Skipping KITCHEN slot %s: position %s not found",
                           slot["slot"], slot["position_code"])
            continue
        upsert_team_position(db,
            team_id=team.id, position_id=pos_id, slot=slot["slot"],
            display_name=slot["name"], distribution_weight=slot["weight"],
            sort_order=i, effective_from=DEFAULT_EFFECTIVE_FROM,
        )
    upsert_scheme(db,
        department_id=dept_id, position_id=None, team_id=team.id,
        calculation_model="team_revenue_by_kpi", config=kitchen_config(),
        effective_from=DEFAULT_EFFECTIVE_FROM, notes="seed",
    )


def seed_locations(db):
    """Build schemes for every recognised location.

    Locations not present in the departments table are skipped with a
    warning — they can be added later without re-seeding.
    """
    # (department lookup_name, cashier_rate, senior_barista_rate, barista_rates, has_kitchen)
    LOCATIONS = [
        # Sandyq Astana — full set + KITCHEN. Barista middle/senior schemes
        # need separate position codes; for MVP we use a single 'barista' rate.
        ("Sandyq Astana", "0.0007", "0.0033", ("0.0015", "0.003"), True),
        # Sandyq Almaty (БД: «Sandyq  Алматы» с двойным пробелом)
        ("Sandyq  Алматы", "0.0007", "0.0033", ("0.0015", "0.003"), True),
        # Sandyq Turkestan
        ("Sandyq Turkestan", "0.001", "0.005", ("0.001", "0.013"), False),
        # Tary Astana / Almaty / Ayusai / etc — без кассира, без KITCHEN кроме Tary Ayusai
        ("Tary Astana", None, "0.007", ("0.001", "0.016"), False),
        ("Tary Almaty", None, "0.007", ("0.001", "0.016"), False),
        ("Tary Ayusai", None, "0.007", ("0.001", "0.016"), True),
        ("Tary Europe City", None, "0.007", ("0.001", "0.016"), False),
        ("Tary Burabay", None, "0.007", ("0.001", "0.016"), False),
        ("Tary Kolsay", None, "0.007", ("0.001", "0.016"), False),
        ("Tary Charyn", None, "0.007", ("0.001", "0.016"), False),
    ]

    seeded = 0
    skipped = []
    for name, cashier_rate, senior_rate, barista_rates, has_kitchen in LOCATIONS:
        dept_id = find_department_by_name(db, name)
        if dept_id is None:
            skipped.append(name)
            logger.warning("Department '%s' not found in DB — skipping", name)
            continue
        _seed_basic_position_schemes(db, str(dept_id),
                                     cashier_rate=cashier_rate,
                                     senior_barista_rate=senior_rate,
                                     barista_rates=barista_rates)
        if has_kitchen:
            _seed_kitchen(db, str(dept_id))
        seeded += 1
        logger.info("Seeded schemes for %s (kitchen=%s)", name, has_kitchen)

    return seeded, skipped


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    db = SessionLocal()
    try:
        seed_companies(db)
        seed_positions(db)
        seed_kpi_definitions(db)
        db.commit()
        logger.info("Catalogues seeded (companies, positions, KPIs)")

        seeded, skipped = seed_locations(db)
        db.commit()
        logger.info("Schemes seeded for %d locations; skipped: %s", seeded, skipped)
    finally:
        db.close()


if __name__ == "__main__":
    main()

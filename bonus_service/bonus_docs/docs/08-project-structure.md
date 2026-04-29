# 08. Структура проекта

```
bonus_service/
│
├── README.md
├── CLAUDE.md                       # Инструкции для Claude Code
├── pyproject.toml                  # Зависимости (uv/poetry)
├── uv.lock                          # Lockfile
├── .env.example
├── .gitignore
├── .python-version                 # 3.12
│
├── docker-compose.yml              # PostgreSQL + Redis для dev
├── Dockerfile                      # Production image
│
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                   # Миграции
│
├── docs/                           # Эта документация
│   ├── 00-context.md
│   ├── 01-architecture.md
│   ├── 02-calculation-models.md
│   ├── 03-data-model.md
│   ├── 04-domain-rules.md
│   ├── 05-data-sources.md
│   ├── 06-api-spec.md
│   ├── 07-config-examples.md
│   ├── 08-project-structure.md
│   ├── 09-implementation-plan.md
│   └── 10-testing.md
│
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, startup/shutdown
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Settings (Pydantic BaseSettings)
│   │   ├── db.py                   # async engine, session factory
│   │   ├── logging.py              # structlog setup
│   │   ├── exceptions.py           # Custom exceptions
│   │   ├── security.py             # JWT, password hashing
│   │   └── deps.py                 # FastAPI dependencies (get_db, get_current_user)
│   │
│   ├── models/                     # SQLAlchemy 2.0 models
│   │   ├── __init__.py
│   │   ├── base.py                 # Base, common columns (created_at, updated_at)
│   │   ├── company.py
│   │   ├── location.py
│   │   ├── position.py
│   │   ├── team.py                 # Team + TeamPosition
│   │   ├── employee.py             # Employee + EmployeeAssignment
│   │   ├── scheme.py               # BonusScheme
│   │   ├── kpi.py                  # KpiDefinition + ManualKpiInput
│   │   ├── monthly_plan.py
│   │   ├── calculation.py          # BonusCalculation + CalculationPenalty
│   │   ├── audit.py                # AuditLog
│   │   └── enums.py                # Все Enum'ы (CalculationStatus, EmploymentType, etc.)
│   │
│   ├── schemas/                    # Pydantic schemas (request/response)
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseSchema (camelCase, ConfigDict)
│   │   ├── company.py
│   │   ├── location.py
│   │   ├── team.py
│   │   ├── employee.py
│   │   ├── scheme.py
│   │   ├── calculation.py
│   │   ├── breakdown.py            # BonusBreakdown структура
│   │   └── calc_configs/           # Pydantic schemas для config каждой модели
│   │       ├── __init__.py
│   │       ├── flat_by_kpi.py
│   │       ├── revenue_percent_by_kpi.py
│   │       ├── revenue_direct.py
│   │       ├── combined_products.py
│   │       └── team_revenue_by_kpi.py
│   │
│   ├── repositories/               # Data access layer
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseRepository (CRUD)
│   │   ├── scheme_repo.py
│   │   ├── employee_repo.py
│   │   ├── calculation_repo.py
│   │   ├── team_repo.py
│   │   ├── location_repo.py
│   │   └── kpi_repo.py
│   │
│   ├── services/                   # Business logic
│   │   ├── __init__.py
│   │   ├── scheme_service.py       # Создание/версионирование схем
│   │   ├── calculation_service.py  # Запуск расчётов за период
│   │   ├── employee_service.py
│   │   ├── team_service.py
│   │   └── report_service.py
│   │
│   ├── calculator/                 # Calculation engine
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseBonusModel (ABC)
│   │   ├── registry.py             # CALCULATION_MODELS + register_model
│   │   ├── context.py              # CalculationContext
│   │   ├── result.py               # BonusResult, BonusBreakdown
│   │   ├── grading.py              # find_grade, grade scoring
│   │   ├── kpi_engine.py           # score_kpi, overall_kpi
│   │   ├── preloader.py            # CalculationPreloader (тянет данные из источников)
│   │   ├── runner.py               # CalculatorRunner (диспетчер)
│   │   └── models/                 # Реализации моделей
│   │       ├── __init__.py         # импортирует все, чтобы декораторы сработали
│   │       ├── flat_by_kpi.py
│   │       ├── revenue_percent_by_kpi.py
│   │       ├── revenue_direct.py
│   │       ├── combined_products.py
│   │       └── team_revenue_by_kpi.py
│   │
│   ├── data_sources/               # Адаптеры внешних данных
│   │   ├── __init__.py
│   │   ├── base.py                 # DataSource (ABC)
│   │   ├── registry.py             # DataSourceRegistry
│   │   ├── types.py                # ShiftStats, KpiFact и пр.
│   │   ├── iiko/
│   │   │   ├── __init__.py
│   │   │   ├── client.py           # HTTP-клиент iiko (для будущего)
│   │   │   ├── revenue.py          # IikoRevenueWithDiscount, IikoRevenueWithoutDiscount, ...
│   │   │   ├── personal.py         # IikoPersonalRevenue*, IikoPreparedProducts*, ...
│   │   │   └── reports.py          # IikoApc, IikoMarginShare
│   │   ├── tco/
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   └── shifts.py           # TcoShifts
│   │   ├── crm/
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   └── reviews.py          # CrmNegativeReviews, CrmRestaurantRating, ...
│   │   ├── hr/
│   │   │   ├── __init__.py
│   │   │   └── staffing.py         # HrStaffingPercent
│   │   ├── manual.py               # ManualKpiSource (берёт из manual_kpi_input)
│   │   ├── monthly_plans.py        # MonthlyPlanSales, MonthlyPlanProfitability
│   │   └── mock/                   # Моки для MVP
│   │       ├── __init__.py         # register_mock_sources()
│   │       ├── fixtures.py         # тестовые данные
│   │       ├── iiko_mocks.py
│   │       ├── tco_mocks.py
│   │       ├── crm_mocks.py
│   │       └── hr_mocks.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py           # главный роутер v1
│   │       ├── auth.py             # /auth/login, /auth/refresh
│   │       ├── companies.py        # /companies
│   │       ├── locations.py        # /locations
│   │       ├── teams.py            # /teams
│   │       ├── positions.py        # /positions
│   │       ├── schemes.py          # /schemes
│   │       ├── employees.py        # /employees
│   │       ├── kpi_definitions.py  # /kpi-definitions, /manual-kpi
│   │       ├── monthly_plans.py    # /monthly-plans
│   │       ├── calculations.py     # /calculations
│   │       ├── reports.py          # /reports
│   │       └── system.py           # /health, /config
│   │
│   ├── seeds/                      # Заливка данных из документов
│   │   ├── __init__.py
│   │   ├── 01_companies.py
│   │   ├── 02_locations.py
│   │   ├── 03_positions.py
│   │   ├── 04_kpi_definitions.py
│   │   ├── 05_monthly_plans.py
│   │   ├── 06_schemes.py
│   │   ├── 07_kitchen_teams.py
│   │   ├── 08_kitchen_slots.py
│   │   ├── 09_demo_employees.py    # тестовые сотрудники для dev
│   │   └── run_all.py              # python -m app.seeds.run_all
│   │
│   └── utils/
│       ├── __init__.py
│       ├── period.py               # PeriodKey (year, month)
│       ├── decimal_utils.py        # round_to_tenge, percent_to_decimal
│       └── pagination.py
│
└── tests/
    ├── __init__.py
    ├── conftest.py                 # фикстуры (db, client, sample data)
    ├── factories.py                # фабрики (factory_boy)
    ├── unit/
    │   ├── __init__.py
    │   ├── calculator/
    │   │   ├── test_grading.py
    │   │   ├── test_kpi_engine.py
    │   │   └── models/
    │   │       ├── test_flat_by_kpi.py
    │   │       ├── test_revenue_percent_by_kpi.py
    │   │       ├── test_revenue_direct.py
    │   │       ├── test_combined_products.py
    │   │       └── test_team_revenue_by_kpi.py
    │   ├── services/
    │   │   ├── test_scheme_service.py
    │   │   └── test_calculation_service.py
    │   └── data_sources/
    │       └── test_registry.py
    ├── integration/
    │   ├── test_full_calculation_flow.py     # E2E для одной локации
    │   ├── test_kitchen_team_distribution.py # E2E для KITCHEN
    │   ├── test_scheme_versioning.py
    │   └── api/
    │       ├── test_schemes_api.py
    │       ├── test_calculations_api.py
    │       └── test_teams_api.py
    └── fixtures/
        ├── kpi_data.json           # тестовые KPI значения
        ├── revenue_data.json
        └── shifts_data.json
```

## Конвенции импортов

```python
# В каждом файле первой строкой:
from __future__ import annotations

# Группы (в этом порядке):
# 1. stdlib
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

# 2. third-party
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# 3. local
from app.core.deps import get_db
from app.services.calculation_service import CalculationService
```

## Где НЕ должно быть кода

- `models/` — только SQLAlchemy ORM, никакой бизнес-логики
- `schemas/` — только Pydantic, никаких запросов в БД
- `repositories/` — только запросы в БД, никакой бизнес-логики
- `api/` — только парсинг запроса, вызов service, формирование ответа
- `services/` — основная бизнес-логика (использует repositories + calculator)
- `calculator/` — чистая логика расчёта (не знает про БД!)

## Правила импортов между слоями

```
api ──→ services ──→ repositories ──→ models
              ├──→ calculator ──→ data_sources
              └──→ schemas
```

**Запрещено:**
- `models` → импортирует что-то ещё (только base)
- `repositories` → импортирует services (нет!)
- `calculator` → импортирует repositories или models (нет, только своё)
- `api` → импортирует repositories напрямую (только через services)

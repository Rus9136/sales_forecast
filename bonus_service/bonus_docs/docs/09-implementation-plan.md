# 09. План реализации (для Claude Code)

Реализация делится на **этапы (milestones)**. Каждый этап = рабочий, тестируемый, мёрджабельный кусок. Не прыгай вперёд — жди готовности предыдущего.

После каждого этапа: ✅ зелёные тесты, ✅ ruff/mypy чистые, ✅ запись в CHANGELOG (если есть).

---

## Этап 0. Bootstrap проекта

**Цель:** базовая инфраструктура.

### Задачи
- [ ] Создать `pyproject.toml` с зависимостями (см. ниже)
- [ ] Настроить `uv` (`uv sync`)
- [ ] `.python-version` = 3.12
- [ ] `.gitignore` (Python, IDE, .env)
- [ ] `.env.example` со всеми переменными
- [ ] `docker-compose.yml` с PostgreSQL 15 (на порту 5433 чтобы не конфликтовать)
- [ ] `app/main.py` с пустым FastAPI приложением + healthcheck `GET /api/v1/health`
- [ ] `app/core/config.py` (Settings через Pydantic)
- [ ] `app/core/db.py` (async engine + sessionmaker)
- [ ] `app/core/logging.py` (structlog)
- [ ] `alembic init alembic`, настройка `alembic/env.py` для async
- [ ] Запустить `docker compose up -d postgres`, `alembic upgrade head` — должно быть пусто но без ошибок
- [ ] Запустить `uvicorn app.main:app --reload`, проверить `/api/v1/health`

### Зависимости (`pyproject.toml`)
```toml
[project]
name = "bonus-service"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.25",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "structlog>=24.1.0",
    "httpx>=0.26.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "factory-boy>=3.3.0",
    "ruff>=0.2.0",
    "mypy>=1.8.0",
    "types-passlib",
]
```

### Готово, когда
- [ ] `uvicorn` стартует
- [ ] `curl localhost:8000/api/v1/health` → 200 OK
- [ ] `pytest` находит 0 тестов и не падает

---

## Этап 1. Модели БД и миграции

**Цель:** все таблицы из `docs/03-data-model.md` живут в БД.

### Задачи
- [ ] `app/models/base.py` — `Base`, миксин `TimestampMixin` (created_at, updated_at)
- [ ] `app/models/enums.py` — `CalculationStatus`, `EmploymentType`, `KpiDirection`, `CalculationModelCode`
- [ ] Создать модели **в порядке зависимостей**:
  1. `Company`
  2. `Location` (FK: company)
  3. `Position`
  4. `Team` (FK: location), `TeamPosition` (FK: team, position)
  5. `KpiDefinition`
  6. `MonthlyPlan` (FK: location)
  7. `Employee`, `EmployeeAssignment` (FK: employee, location, position, team)
  8. `BonusScheme` (FK: location, position, team)
  9. `BonusCalculation` (FK: employee, location, scheme, team)
  10. `CalculationPenalty` (FK: calculation)
  11. `ManualKpiInput` (FK: location)
  12. `AuditLog`
- [ ] CHECK constraints где нужно (см. data-model.md)
- [ ] Индексы согласно data-model.md
- [ ] `alembic revision --autogenerate -m "initial schema"`
- [ ] Проверить migration sql глазами — нет ли странностей
- [ ] `alembic upgrade head` без ошибок
- [ ] Юнит-тесты на создание/чтение каждой модели

### Готово, когда
- [ ] `alembic upgrade head && alembic downgrade base && alembic upgrade head` работает
- [ ] `pytest tests/unit/test_models.py` зелёный

---

## Этап 2. Pydantic schemas + базовый Repository

**Цель:** слой DTO и базовый CRUD.

### Задачи
- [ ] `app/schemas/base.py` — `BaseSchema(BaseModel)` с общими настройками
- [ ] Schemas для каждой модели (Create, Update, Read варианты)
- [ ] `app/repositories/base.py` — `BaseRepository[Model]` с методами get/list/create/update/delete
- [ ] Конкретные репозитории: `SchemeRepository`, `EmployeeRepository`, и т.д.
- [ ] Метод `SchemeRepository.find_active(location_id, position_id, on_date)` — резолвинг активной версии
- [ ] Тесты на каждый репозиторий (с in-memory SQLite или test PostgreSQL)

### Готово, когда
- [ ] `pytest tests/unit/repositories/` зелёный
- [ ] Покрытие репозиториев >= 80%

---

## Этап 3. KPI Engine + Grading + базовый calculator

**Цель:** чистая логика без БД.

### Задачи
- [ ] `app/calculator/kpi_engine.py`:
  - `score_kpi(fact, target, direction, cap_at_100) -> Decimal`
  - `overall_kpi(results) -> Decimal`
  - Тесты: все направления, граничные случаи (fact=0, target=0)
- [ ] `app/calculator/grading.py`:
  - `find_grade(grades, percent) -> Grade | None`
  - Тесты: внутри грейда, на границе, ниже минимума, выше максимума, дырки между грейдами
- [ ] `app/calculator/result.py`: `BonusResult`, `BonusBreakdown` (dataclasses или Pydantic)
- [ ] `app/calculator/context.py`: `CalculationContext` (dataclass)
- [ ] `app/calculator/base.py`: `BaseBonusModel` (ABC)
- [ ] `app/calculator/registry.py`: `CALCULATION_MODELS`, `register_model`

### Готово, когда
- [ ] `pytest tests/unit/calculator/test_kpi_engine.py` зелёный
- [ ] `pytest tests/unit/calculator/test_grading.py` зелёный
- [ ] Тестовое покрытие модуля calculator >= 95%

---

## Этап 4. Реализация 5 моделей расчёта

**Цель:** все алгоритмы работают на тестовых данных.

Делать **по одной модели** в таком порядке:

### 4.1. `flat_by_kpi`
- [ ] `app/calculator/models/flat_by_kpi.py`
- [ ] `app/schemas/calc_configs/flat_by_kpi.py` — Pydantic config
- [ ] Тесты: примеры из документа (управляющий, 90.8% → 150 000)
- [ ] Тесты: ниже 70% → 0
- [ ] Тесты: на границе 79.5% → 80%-84% грейд (округление)

### 4.2. `revenue_direct`
- [ ] Реализация
- [ ] Тесты: кассир Астана (25 000 000 × 0.0007 = 17 500)
- [ ] Тесты: с proration (старший бариста)

### 4.3. `combined_products`
- [ ] Реализация
- [ ] Тесты: бариста Tary Kainar (2M × 0.001 + 3M × 0.016 = 50 000)
- [ ] Тесты: только один компонент

### 4.4. `revenue_percent_by_kpi`
- [ ] Реализация
- [ ] Тесты: официант (2 500 000 × 0.045 при 100% KPI = 112 500)
- [ ] Тесты: менеджер с proration

### 4.5. `team_revenue_by_kpi`
- [ ] Реализация (учитывая распределение по слотам)
- [ ] Тесты: KITCHEN с 21 слотом
- [ ] Тесты: один сотрудник на 0 смен → его доля 0
- [ ] Тесты: ниже 70% KPI → пул = 0 → все нули

### Готово, когда
- [ ] Все 5 файлов в `app/calculator/models/` есть
- [ ] Все импортируются в `app/calculator/models/__init__.py`
- [ ] `pytest tests/unit/calculator/models/` весь зелёный
- [ ] Покрытие моделей >= 95%

---

## Этап 5. Data Sources + Mock реализации

**Цель:** калькулятор может тянуть данные.

### Задачи
- [ ] `app/data_sources/base.py`: `DataSource` ABC
- [ ] `app/data_sources/registry.py`: `DataSourceRegistry`
- [ ] `app/data_sources/types.py`: `ShiftStats`, `KpiFact`
- [ ] `app/data_sources/mock/` — реализовать **все источники из docs/05-data-sources.md** как моки:
  - возвращают предсказуемые числа (детерминированные по location/period/employee)
  - данные хранятся в `app/data_sources/mock/fixtures.py`
- [ ] `register_mock_sources()` — регистрация всех моков
- [ ] Вызывается в `app/main.py` при старте если `settings.use_mock_data_sources=True`
- [ ] Тесты: каждый мок возвращает ожидаемое значение

### Готово, когда
- [ ] При запуске app в логах: «Registered N data sources»
- [ ] `GET /api/v1/config/data-sources` возвращает список (после реализации этого endpoint позже)

---

## Этап 6. Preloader + Runner

**Цель:** связать всё — калькулятор работает с источниками.

### Задачи
- [ ] `app/calculator/preloader.py`: `CalculationPreloader.preload(scheme, target, period) -> CalculationContext`
- [ ] `app/calculator/runner.py`: `CalculatorRunner.run(scheme, target, period) -> BonusResult`
- [ ] Подбор активной схемы в `runner` (через `SchemeRepository.find_active`)
- [ ] Сохранение результата в БД через `CalculationRepository`
- [ ] Снапшот всех данных в `bonus_calculation.breakdown`
- [ ] Идемпотентность: повторный запуск удаляет предыдущий `draft`
- [ ] Интеграционный тест: полный расчёт для одного сотрудника

### Готово, когда
- [ ] Можно вызвать `runner.run(scheme, employee, period)` и получить `BonusResult` + запись в БД
- [ ] `pytest tests/integration/test_full_calculation_flow.py` зелёный

---

## Этап 7. Services Layer

**Цель:** бизнес-логика поверх repositories + calculator.

### Задачи
- [ ] `app/services/scheme_service.py`:
  - `create_scheme()` с валидацией config через Pydantic схему модели
  - `update_scheme_to_new_version()` (закрывает старую, создаёт новую)
- [ ] `app/services/calculation_service.py`:
  - `run_for_period(location_id, year, month, scope)` — запускает расчёты для всех применимых сотрудников
  - `run_for_team(team_id, year, month)` — для коллективных
  - Формирование сводки (сколько посчитано, ошибок)
- [ ] `app/services/team_service.py`:
  - CRUD команд и слотов с версионированием
- [ ] `app/services/employee_service.py`
- [ ] Тесты на сервисы

### Готово, когда
- [ ] `pytest tests/unit/services/` зелёный

---

## Этап 8. Seeds (заливка данных из документов)

**Цель:** в БД лежат все 10+ локаций со схемами.

### Задачи
- [ ] `app/seeds/01_companies.py` — список юрлиц
- [ ] `app/seeds/02_locations.py` — все локации
- [ ] `app/seeds/03_positions.py` — все должности (включая kitchen-позиции: chef, sous_chef, hot_cook, ...)
- [ ] `app/seeds/04_kpi_definitions.py` — все KPI из документов
- [ ] `app/seeds/05_monthly_plans.py` — план продаж по месяцам для всех локаций (из доков), план рентабельности
- [ ] `app/seeds/06_schemes.py` — схемы для всех (location × position) комбинаций (см. 07-config-examples.md)
- [ ] `app/seeds/07_kitchen_teams.py` — KITCHEN для Sandyq Astana, Sandyq Almaty, Tary Auysai
- [ ] `app/seeds/08_kitchen_slots.py` — 21 слот для каждой KITCHEN команды
- [ ] `app/seeds/09_demo_employees.py` — несколько тестовых сотрудников для каждой локации
- [ ] `app/seeds/run_all.py` — последовательно вызывает все
- [ ] Идемпотентность: повторный запуск не дублирует записи

### Готово, когда
- [ ] `python -m app.seeds.run_all` без ошибок
- [ ] В БД: ~12 локаций, ~50 схем, ~63 слота KITCHEN (3 × 21), ~30 демо-сотрудников
- [ ] Можно зарелодить — данные не дублируются

---

## Этап 9. API endpoints

**Цель:** все эндпоинты из `docs/06-api-spec.md` работают.

Делать **по разделам**:

### 9.1. System & Auth
- [ ] `/health`, `/config/calculation-models`, `/config/data-sources`
- [ ] `/auth/login`, `/auth/refresh`
- [ ] JWT middleware
- [ ] Роли (RBAC)

### 9.2. Справочники (read-only для начала)
- [ ] `/companies`, `/locations`, `/positions`, `/kpi-definitions`

### 9.3. Schemes
- [ ] `GET /schemes`, `GET /schemes/{id}`
- [ ] `POST /schemes` (с валидацией config)
- [ ] `POST /schemes/{id}/validate`

### 9.4. Teams
- [ ] CRUD команд
- [ ] CRUD слотов

### 9.5. Employees
- [ ] CRUD сотрудников и assignments

### 9.6. Manual KPI / Monthly Plans
- [ ] CRUD ручных KPI
- [ ] CRUD планов

### 9.7. Calculations
- [ ] `POST /calculations/run` (асинхронно через background task)
- [ ] `GET /calculations`, `GET /calculations/{id}` с breakdown
- [ ] `POST /calculations/{id}/penalties`
- [ ] `POST /calculations/{id}/approve`, `/reject`
- [ ] `GET /calculations/export?format=xlsx`

### 9.8. Reports
- [ ] `/reports/summary`
- [ ] `/reports/employee/{id}/history`
- [ ] `/reports/scheme-changes`

### Готово, когда
- [ ] Swagger `/docs` показывает все эндпоинты
- [ ] `pytest tests/integration/api/` зелёный
- [ ] Можно через curl/Postman пройти полный сценарий: seed → создать сотрудника → ввести KPI → запустить расчёт → посмотреть результат

---

## Этап 10. Полировка

### Задачи
- [ ] Логирование во всех слоях
- [ ] Обработка ошибок (proper HTTP коды)
- [ ] OpenAPI описания (summary, response_model)
- [ ] CORS (для будущего фронта)
- [ ] Rate limiting (slowapi) — на login и расчёты
- [ ] Health check для БД (`SELECT 1`)
- [ ] Покрытие тестами >= 80%
- [ ] `mypy app/` чисто
- [ ] `ruff check app/ tests/` чисто
- [ ] README с примерами запросов
- [ ] Dockerfile для production

---

## Что НЕ входит в первую версию (delegate to v2)

❌ Реальные интеграции iiko/TCO/CRM (заменяем когда будут готовы)  
❌ Веб-админка (UI) — только API. Можно использовать Swagger или Postman.  
❌ Email/Telegram уведомления о расчётах  
❌ Bulk operations (массовые изменения схем)  
❌ Кэширование Redis  
❌ Многопоточность/Celery для расчётов (пока через FastAPI BackgroundTasks)  
❌ Audit log UI (есть в БД, но без эндпоинта)  

---

## Порядок коммитов

Каждая задача = 1-3 коммита. Конвенциональные сообщения:
```
feat(scheme): add BonusScheme model
feat(scheme): add SchemeRepository.find_active
feat(api): add POST /schemes endpoint
test(scheme): cover scheme versioning logic
fix(calculator): handle zero target in score_kpi
refactor(seeds): split kitchen seeds by location
docs: update implementation plan
```

## Если застрял

1. Перечитай `docs/02-calculation-models.md` (формулы)
2. Перечитай `docs/04-domain-rules.md` (правила)
3. Посмотри `docs/10-testing.md` — там точные ожидаемые числа
4. Спроси у Rus — не угадывай бизнес-правила

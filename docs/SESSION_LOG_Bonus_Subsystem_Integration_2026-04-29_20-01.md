# Session Log: Bonus Subsystem Integration

**Дата**: 2026-04-29, 20:01
**Задача**: Интегрировать `bonus_service` (спроектированный отдельно, на локальной машине) в существующий проект Sales Forecast так, чтобы расчёт бонусов работал на реальных данных `sales_by_waiter` / `employees` / `departments`
**Статус**: Завершено и задеплоено на прод (https://aqniet.site)

---

## Контекст

Заказчик (Sandyq Group, ресторанная сеть) ранее спроектировал отдельный `bonus_service` для расчёта ежемесячных KPI-бонусов сотрудников: 5 моделей расчёта (`flat_by_kpi`, `revenue_percent_by_kpi`, `revenue_direct`, `combined_products`, `team_revenue_by_kpi`), универсальные команды (KITCHEN со слотами и весами), плагинная архитектура источников данных. Документация — в `bonus_service/bonus_docs/` (12 markdown-файлов + .docx KPI 2026 для 10 локаций).

В Sales Forecast уже были:
- `departments` (UUID, iiko-маппинг)
- `employees` (UUID, `main_role_code`/`main_role_name`: `WR1`, `CS1`, `MN0`, `MN1`, `BR1`, …)
- `sales_by_waiter` (5629 строк, апрель 2025 – апрель 2026, `total_sales` = `DishSumInt`, `total_sales_with_discount` = `DishDiscountSumInt`)
- `sales_summary` (дневные точки)

**Цель**: сделать единый проект, где бонусы считаются на реальных данных, без дублирования сущностей.

---

## Архитектурные решения

| Решение | Обоснование |
|---|---|
| Sync SQLAlchemy 2.0 (а не async, как в дизайне) | Текущий проект синхронный, конвертировать рискованно |
| Новый пакет `app/bonus/` внутри проекта | Один проект, одна БД, общий `Base.metadata` |
| Префикс таблиц `bonus_*` | Не путать с системными `position`, `team` именами |
| `departments` = `location` | Не дублируем; добавили `departments.company_id` FK на `bonus_company` |
| Маппинг должностей через `bonus_position.iiko_role_code` → `employees.main_role_code` | Единственный source of truth — iiko |
| Raw SQL миграции (`migrations/007_*.sql`) | Совместимо с существующей конвенцией проекта; Alembic не вводим |
| Реальные data sources, заглушки только где данных нет | `iiko_personal_revenue_*` → `sales_by_waiter`; `tco_shifts` → `COUNT DISTINCT date` |

---

## Что сделано (10 этапов)

### Stage 0. Recon
Прочитал реальные данные в БД:
- 21 локация департаментов (Sandyq Astana/Almaty/Turkestan + 17× Tary + Madlen/Salam Bro/Shopan)
- 905 официантов (`WR1`), 133 кассира (`CS1`), 17 управляющих (`MN0`), 131 администратор (`MN1`), 119 барменов (`BR1`), KITCHEN роли (су-шеф, шеф-повар, повар `CO1`, …)
- `Sandyq Kainar` и `Tary Kainar` отсутствуют в БД (были в KPI-документах) — пропущены seeds с warning

### Stage 1. Migration 007 + SQLAlchemy models
**Файл**: `migrations/007_bonus_core.sql`
**Таблиц**: 12
- `bonus_company`, `bonus_position` (iiko_role_code unique), `bonus_team`, `bonus_team_position` (DECIMAL(8,6) weight, версионирование), `bonus_kpi_definition`, `bonus_monthly_plan`, `bonus_employee_assignment`, `bonus_scheme` (JSONB config + CHECK position XOR team), `bonus_manual_kpi`, `bonus_calculation` (JSONB scheme_config_snapshot/kpi_values/breakdown), `bonus_calculation_penalty`
- `ALTER TABLE departments ADD COLUMN company_id`

**SQLAlchemy модели** в `app/bonus/models/` (11 классов в 8 файлах). Зарегистрированы в общем `app.db.Base` через импорт в `app/models/__init__.py`.

### Stage 2. Calculator engine + 5 моделей
**Структура**: `app/bonus/calculator/`
- `base.py` — `BaseBonusModel` ABC
- `registry.py` — `@register_model` декоратор + `CALCULATION_MODELS` dict
- `kpi_engine.py` — `score_kpi(fact, target, direction)` (higher_is_better / lower_is_better / binary), `overall_kpi(percents)` (среднее)
- `grading.py` — `find_grade(grades, percent)` с `math.ceil` для попадания в диапазоны (89.5 → 90 → грейд 90-97)
- `result.py`, `context.py` — dataclass-структуры
- 5 моделей в `models/`: каждая в своём файле, регистрируется через декоратор

**Pydantic-валидация config** в `schemas/calc_configs/` (с `populate_by_name=True` и `by_alias=True` при сохранении JSONB — иначе `from_` вместо `from`).

### Stage 3. Data sources на реальных данных
**Файл**: `app/bonus/data_sources/`, **источников**: 19
- `iiko/revenue.py` — 6 источников: location и personal × `with_discount`/`dish_sum`/`sales_plan`
  - `IikoPersonalRevenueWithDiscount` → `SUM(sales_by_waiter.total_sales_with_discount)` по `(department_id, employee_id, period)`
  - `IikoLocationRevenueWithDiscount` → `SUM(sales_summary.total_sales)`
- `iiko/products.py` — заглушки (нет разбивки по категориям блюд в БД)
- `tco/shifts.py` — `worked = COUNT DISTINCT date`, `norm` из `bonus_monthly_plan(metric=shifts_norm)` или 22 по умолчанию
- `manual/manual_kpi.py` — 10 источников через одну базу `_ManualKpiBase` (audit, kitchen_audit, profitability, hr_staffing, crm_*, iiko_apc_growth, iiko_margin_share)
- `bootstrap.py` — `register_all_sources()` вызывается в `app/main.py` при старте

### Stage 4. Service + Preloader + Runner
- `repositories/scheme_repository.py` — `find_active_scheme_for_position`/`for_team` (по effective_from/to на дату)
- `services/preloader.py` — `CalculationPreloader.preload()`: тянет KPI, выручку, смены, веса слотов команды
- `services/runner.py` — `CalculatorRunner.run_for_employee()`: idempotent (старые drafts → `superseded`, при наличии approved/paid → новый идёт как `recalculated`)
- `services/scheme_service.py` — `create()` с версионированием (старая закрывается на effective_from-1, новая `version+1`)

**Smoke-тест** на реальных данных:
- Официант UUID `a719fdf2…`, Sandyq Astana, апрель 2026
- Revenue 40,951,119 KZT (со скидкой) ← из `sales_by_waiter`
- KPI 100% → грейд 98-100% → 4.5%
- **Final bonus: 1,842,800 KZT**, breakdown сохранён в JSONB

### Stage 5. Seeds
**Файл**: `app/bonus/seeds/run_all.py`
- 4 юрлица, 21 должность (с `iiko_role_code` маппингом), 12 KPI definitions
- 56 схем расчёта для 10 локаций (Sandyq Astana/Almaty/Turkestan + Tary Astana/Almaty/Ayusai/Europe City/Burabay/Kolsay/Charyn). 2 локации из KPI-доков (`Sandyq Kainar`, `Tary Kainar`) пропущены — нет в БД
- 3 KITCHEN команды × 21 слот = 63 `bonus_team_position` (Sandyq Astana, Sandyq Almaty, Tary Ayusai)
- Идемпотентность через `upsert_*` хелперы в `_helpers.py`

### Stage 6. REST API
**Префикс**: `/api/bonus/*`, авторизация — существующая `get_api_key_or_bypass`
- `dictionary.py` — `/companies`, `/kpi-definitions`, `/config/calculation-models`, `/config/data-sources`
- `positions.py`, `schemes.py` (CRUD + validate + active-by-position), `teams.py`
- `kpi.py` — manual KPI (GET / POST upsert / DELETE)
- `plans.py` — monthly plans (GET / POST upsert)
- `calculations.py` — `/run` (`scope: all|employee:<uuid>|position:<code>`), `/list`, `/{id}` с breakdown, `/penalties`, `/approve`, `/reject`, `/reports/summary`

### Stage 7. APScheduler
Job `monthly_bonus_auto_calc`: 5-го числа в 05:00, считает draft за прошлый месяц для всех с активным `bonus_employee_assignment`. Логика в `app/bonus/services/scheduled_calc.py`.

### Stage 8. Frontend (React SPA)
- 4 новые страницы в `frontend/src/pages/`: `bonus-calculations-page.tsx`, `bonus-schemes-page.tsx`, `bonus-manual-kpi-page.tsx`, `bonus-monthly-plans-page.tsx`
- Хуки в `hooks/use-bonus.ts` (TanStack Query: queries + mutations)
- Типы в `types/bonus.ts`
- Новая секция «БОНУСЫ» в `Sidebar`
- 4 маршрута в `App.tsx`

Использованы существующие компоненты: `DepartmentSelect`, `Card`, `Table`, `Dialog`, `Badge`, `Input`, `Button`, `Select`, `LoadingSpinner`, `ErrorAlert`, `EmptyState`.

### Stage 9. Tests + docs
- **53/53 unit-теста** в `tests/bonus/`:
  - `test_kpi_engine.py` (16 тестов) — все направления, граничные случаи
  - `test_grading.py` (12 тестов) — все диапазоны, дырки, ceil
  - `test_calculation_models.py` (25 тестов) — все 5 моделей, числа из `bonus_service/bonus_docs/10-testing.md` (TC-01..TC-43)
- Обновлён `CLAUDE.md` основного проекта: новый раздел «Bonus Subsystem» (архитектура, таблицы, эндпоинты, команды, правила доработки do/don't)
- `bonus_service/bonus_docs/CLAUDE.md` удалён (актуальные правила перенесены в основной CLAUDE.md, остальное было устаревшим — async/uv/alembic)

---

## End-to-end проверка на реальных данных

**Sandyq Astana, апрель 2026**:
- Создал `bonus_employee_assignment` для 17 сотрудников с `main_role_code='WR1'`
- Через API `POST /api/bonus/monthly-plans` создал план продаж 50М
- Через API `POST /api/bonus/manual-kpi` ввёл `iiko_margin_share=45`
- Через API `POST /api/bonus/calculations/run` (`scope: position:waiter`)
- Получено: 17 расчётов, KPI 100%, ставка 4.5%
- **Общий пул бонусов: 4,117,312 KZT**, средний бонус 242,195 KZT

---

## Деплой

Способ: rebuild Docker образа из `docker-compose.prod.yml` (3-stage build: Node.js + Python + final).

```bash
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app  # ~113s
docker-compose -f docker-compose.prod.yml up -d sales-forecast-app             # ~10s
```

**Прод-проверка** через https://aqniet.site:
- `/health` → 200 OK
- `/api/bonus/config/data-sources` → 19 источников
- `/api/bonus/schemes` → 56 схем
- `/api/bonus/calculations?year=2026&month=4` → 17 активных, итого 4,117,312 KZT
- `/bonus/calculations` (SPA) → отдаётся, `<title>Sales Forecast</title>`
- Логи показывают новую APScheduler-задачу: «Bonus auto-calc 5th-of-month 5:00»

---

## Git

Два коммита, оба запушены на `github.com:Rus9136/sales_forecast.git`:

1. **`908291c feat(bonus): add KPI-based monthly bonus calculation subsystem`**
   - 105 файлов, +9487 строк
   - Включает: `app/bonus/`, миграцию, seeds, tests, frontend, документацию `bonus_service/bonus_docs/`

2. **`3d9bc00 docs(bonus): merge bonus_docs/CLAUDE.md rules into main CLAUDE.md`**
   - Удалён `bonus_service/bonus_docs/CLAUDE.md`, актуальные правила перенесены в основной `CLAUDE.md`

Не вошли в коммиты (преднамеренно):
- `models/*.pkl` — артефакты ML-обучения
- `frontend/tsconfig.tsbuildinfo` — build cache
- 2× PDF в корне (`primery-vyzova-olap-otchet-v2.pdf`, `rabota-s-dannymi-sotrudnikovv.pdf`) — не относятся к задаче

---

## Известные ограничения / TODO

| # | Что | Решение |
|---|---|---|
| 1 | `iiko_personal_ready_products_with_discount` / `_prepared_products` возвращают 0 | Расширить iiko OLAP loader: запросить разбивку по `DishCategory.Name`, заливать в новую таблицу `sales_by_waiter_category` или JSONB-столбец |
| 2 | TCO смены аппроксимируются `COUNT DISTINCT date` из `sales_by_waiter` | Когда появится TCO API — добавить адаптер `TcoShiftsReal`, заменить регистрацию в `bootstrap.py` |
| 3 | `Sandyq Kainar` и `Tary Kainar` нет в `departments` | Если бренд работает — добавить через 1С Exchange sync, потом перезапустить seeds |
| 4 | Авто-привязка сотрудников к `bonus_position` по `main_role_code` | Сейчас `bonus_employee_assignment` создаются вручную. Можно сделать nightly job: для каждого `employee` создать assignment если есть совпадение iiko_role_code и preferred_department_code привязан к локации со схемой |
| 5 | `sales_summary` хранит только `DishSumInt` (без скидки) | Если потребуется revenue со скидкой по локации (для `revenue_percent_by_kpi` менеджера) — расширить `iiko_sales_loader` чтобы тянул и `DishDiscountSumInt`, добавить столбец `total_sales_with_discount` в `sales_summary` |

---

## Архитектурные принципы (зафиксированы в основном CLAUDE.md)

**❌ НЕЛЬЗЯ:**
- Хардкодить ставки/проценты/грейды в Python — всё через БД (`bonus_scheme.config` JSONB) и seeds
- Делать таблицы под конкретное подразделение (`KitchenDistribution`) — использовать `bonus_team` + `bonus_team_position`
- Звать iiko/TCO/CRM напрямую из калькулятора — только через `DataSourceRegistry`
- `float` для денег — только `Decimal`
- Удалять `bonus_scheme` — версионировать через `effective_to`
- Изменять `approved`/`paid` расчёты — перерасчёт даёт новую запись

**✅ ОБЯЗАТЕЛЬНО:**
- Снапшот при расчёте (`scheme_config_snapshot`, `kpi_values`, `breakdown` JSONB)
- Валидация config через Pydantic при сохранении
- `BonusBreakdown` с детализацией шагов
- Proration по сменам где `apply_shifts_proration: true`
- Структурированное логирование

**Decimal precision:**
- Деньги: `DECIMAL(14, 2)`
- Проценты-доли: `DECIMAL(8, 6)` (`0.000700` = 0.07%)
- Грейды: `DECIMAL(5, 2)`
- Веса слотов: `DECIMAL(8, 6)`

---

## Финальные числа

| Метрика | Значение |
|---|---|
| Новых SQL таблиц | 12 (+1 ALTER) |
| SQLAlchemy моделей | 11 |
| Моделей расчёта (плагины) | 5 |
| Источников данных | 19 |
| REST endpoints | 24 |
| Seeds: компании / должности / KPI / схемы / KITCHEN-слоты | 4 / 21 / 12 / 56 / 63 |
| React страниц | 4 |
| Unit-тестов | 53/53 ✅ |
| Файлов в коммите | 105 |
| Строк кода | +9487 |
| Время сборки Docker | ~113s |
| Прод-проверка (Sandyq Astana апр.2026) | 17 расчётов, пул 4,117,312 KZT |

---

## Релевантные файлы

**Backend:**
- `app/bonus/` — пакет (60+ файлов)
- `app/main.py` — подключение router'а и регистрация data sources
- `app/models/__init__.py` — регистрация bonus моделей в Base.metadata
- `migrations/007_bonus_core.sql` — миграция

**Frontend:**
- `frontend/src/pages/bonus-*.tsx` (4 страницы)
- `frontend/src/hooks/use-bonus.ts`
- `frontend/src/types/bonus.ts`
- `frontend/src/App.tsx`, `frontend/src/components/layout/sidebar.tsx`

**Tests:**
- `tests/bonus/test_calculation_models.py` (476 строк, 25 тестов)
- `tests/bonus/test_kpi_engine.py` (73 строки, 16 тестов)
- `tests/bonus/test_grading.py` (72 строки, 12 тестов)

**Docs:**
- `CLAUDE.md` — раздел «Bonus Subsystem»
- `bonus_service/bonus_docs/` — оригинальная спецификация (00-context, 01-architecture, 02-calculation-models, 03-data-model, 04-domain-rules, 05-data-sources, 06-api-spec, 07-config-examples, 08-project-structure, 09-implementation-plan, 10-testing)
- `bonus_service/Документы по расчету/` — оригинальные .docx KPI 2026 (10 файлов от заказчика)

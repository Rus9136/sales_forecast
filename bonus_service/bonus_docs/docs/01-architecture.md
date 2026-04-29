# 01. Архитектура

## Слоистая структура

```
┌────────────────────────────────────────────────────────────┐
│                   API LAYER (FastAPI)                      │
│   /api/v1/schemes  /calculations  /reports  /teams         │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                           │
│   BonusCalculatorService                                   │
│   SchemeService     PeriodCalculationService               │
│   ReportService     EmployeeService                        │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                  CALCULATION ENGINE                        │
│   ┌─────────────────┬──────────────┬──────────────────┐   │
│   │ Calculation     │ KPI Engine   │ Grading          │   │
│   │ Models Registry │ (scoring)    │ (find grade)     │   │
│   │ ─────────────── │              │                  │   │
│   │ flat_by_kpi     │              │                  │   │
│   │ revenue_pct_kpi │              │                  │   │
│   │ revenue_direct  │              │                  │   │
│   │ combined_prods  │              │                  │   │
│   │ team_revenue    │              │                  │   │
│   └─────────────────┴──────────────┴──────────────────┘   │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                  DATA SOURCES LAYER                        │
│   DataSourceRegistry (плагинная архитектура)               │
│   ┌──────┬──────┬─────┬────┬────────┬────────────────┐    │
│   │ iiko │ tco  │ crm │ hr │ manual │ monthly_plans  │    │
│   └──────┴──────┴─────┴────┴────────┴────────────────┘    │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                  REPOSITORY LAYER                          │
│   SchemeRepository   EmployeeRepository                    │
│   CalculationRepository   TeamRepository                   │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                      DATABASE                              │
│                  PostgreSQL 15+                            │
└────────────────────────────────────────────────────────────┘
```

## Ключевые архитектурные решения

### 1. Плагинная архитектура моделей расчёта

```python
# app/calculator/registry.py
CALCULATION_MODELS: dict[str, type[BaseBonusModel]] = {}

def register_model(code: str):
    def decorator(cls: type[BaseBonusModel]):
        CALCULATION_MODELS[code] = cls
        return cls
    return decorator
```

Каждая модель — отдельный класс, регистрируется через декоратор. Добавление новой модели = создание файла + декоратор. Никаких `if/elif` цепочек в коде калькулятора.

### 2. Плагинная архитектура источников данных

```python
# app/data_sources/registry.py
class DataSourceRegistry:
    _sources: dict[str, DataSource] = {}

    @classmethod
    def register(cls, code: str, source: DataSource): ...

    @classmethod
    def get(cls, code: str) -> DataSource: ...
```

Калькулятор не знает про iiko/TCO. Он работает через абстракцию `DataSource`, в config схемы указано имя источника (`"revenue_source": "iiko_revenue_with_discount"`).

Для MVP все источники — моки с предсказуемыми данными.

### 3. Версионирование схем

Схема (`BonusScheme`) имеет `effective_from` и `effective_to`. При расчёте за период берётся та схема, которая действовала в этот период. Изменение ставки = создание новой версии (старая закрывается датой), не UPDATE.

### 4. Снапшоты при расчёте

Каждый `BonusCalculation` сохраняет:
- `scheme_version_id` — какая версия схемы использовалась
- `kpi_values_snapshot` (JSONB) — все значения KPI на момент расчёта
- `data_sources_snapshot` (JSONB) — какие источники, с какими параметрами вызваны
- `breakdown` (JSONB) — пошаговая разбивка формулы

Это нужно для аудита: через 6 месяцев финдиректор должен открыть и увидеть всё.

### 5. Универсальные команды (Team)

KITCHEN — не специальная сущность. Это `team` со слотами (`team_position`). Та же абстракция работает для будущих BAR_TEAM, DELIVERY, и т.д.

```
team(code='kitchen', location='astana')
  ├─ team_position(slot='chef', weight=0.0013)
  ├─ team_position(slot='sous_chef_1', weight=0.0009)
  ├─ team_position(slot='sous_chef_2', weight=0.0006)
  └─ ... (21 слот всего)
```

Сотрудник назначается на конкретный слот через `employee_assignment`.

### 6. Декомпозиция расчёта

```
calculate(employee, period)
  ↓
  1. resolve_scheme(employee, period)        → BonusScheme (правильная версия)
  ↓
  2. fetch_kpi_values(scheme, employee)      → dict[kpi_code, percent]
  ↓
  3. find_grade(scheme, overall_percent)     → coefficient
  ↓
  4. fetch_revenue(scheme, employee)         → Decimal
  ↓
  5. fetch_shifts(employee, period)          → ShiftStats(worked, norm)
  ↓
  6. apply_formula(...)                      → base_bonus
  ↓
  7. apply_penalties(employee, base_bonus)   → final_bonus
  ↓
  8. save_with_breakdown(...)                → BonusCalculation
```

Каждый шаг — отдельный метод, его легко тестировать независимо.

## Зависимости между модулями

```
api → service → calculator → data_sources
        ↓           ↓             ↓
       repo      registry      registry
        ↓
      models
```

**Правило:** модуль может импортировать только модули "ниже" (по стрелкам). API не лезет в repository напрямую — только через service.

## Асинхронность

Всё async через SQLAlchemy 2.0 + asyncpg + FastAPI. Источники данных тоже async (потому что в проде это будут HTTP-запросы).

## Конфигурация

`Settings` через Pydantic + `.env`:
```python
class Settings(BaseSettings):
    database_url: PostgresDsn
    iiko_base_url: str | None = None
    tco_base_url: str | None = None
    use_mock_data_sources: bool = True   # для MVP
    log_level: str = "INFO"
```

## Логирование

Структурированное (JSON) через `structlog`:
```python
log.info("bonus.calculated", 
         employee_id=42, 
         period="2026-04",
         scheme_version=3,
         overall_kpi=87.5,
         grade_rate=0.04,
         revenue=Decimal("2500000"),
         final_bonus=Decimal("100000"))
```

## Безопасность

- Все эндпоинты под JWT (отдельный модуль `app.security`)
- Роли: `admin` (всё), `hr` (расчёты, ввод KPI), `viewer` (только чтение)
- Аудит: каждое изменение схемы = запись в `audit_log` (кто, когда, что было, что стало)

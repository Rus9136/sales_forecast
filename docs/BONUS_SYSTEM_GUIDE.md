# Bonus System — полное руководство

**Дата документа**: 2026-04-29
**Версия системы**: 1.0 (MVP, задеплоен на https://aqniet.site)

Это полное руководство по подсистеме расчёта бонусов в проекте Sales Forecast: бизнес-логика, архитектура, текущее состояние и роадмап до production-ready.

---

## Оглавление

1. [Зачем эта система](#1-зачем-эта-система)
2. [Общая логика](#2-общая-логика)
3. [Целевой бизнес-процесс](#3-целевой-бизнес-процесс)
4. [Модели расчёта (5 шт.)](#4-модели-расчёта-5-шт)
5. [Архитектура](#5-архитектура)
6. [Модель данных](#6-модель-данных)
7. [API](#7-api)
8. [Frontend](#8-frontend)
9. [Источники данных](#9-источники-данных)
10. [Операционный workflow](#10-операционный-workflow)
11. [Что готово сейчас](#11-что-готово-сейчас)
12. [Что нужно дополнить до production](#12-что-нужно-дополнить-до-production)
13. [Расширение системы](#13-расширение-системы)
14. [FAQ](#14-faq)
15. [Troubleshooting и health-checks](#15-troubleshooting-и-health-checks)
16. [Снапшот текущего состояния production-данных](#16-снапшот-текущего-состояния-production-данных)

---

## 1. Зачем эта система

### Заказчик

**Sandyq Group** — ресторанная сеть в Казахстане под двумя брендами:
- **Sandyq** — премиум формат
- **Tary** — массовый формат

10+ локаций, ~1500+ сотрудников.

### Проблема (как было)

1. Управляющий ресторана **вручную считает** показатели по каждому сотруднику в Excel
2. Заполняет служебную записку с расчётами
3. Согласовывает с бухгалтером, финдиректором, гендиректором
4. Бухгалтерия начисляет

**Боли:**
- Ошибки в расчётах (200+ сотрудников × 10 локаций = высокая вероятность опечаток)
- Изменение коэффициентов = переделка инструкций для всех управляющих
- Нет аудита: через полгода невозможно поднять, **почему** именно столько начислили
- Нет прозрачности для сотрудника

### Решение

Автоматизированный сервис, который:
1. **Тянет данные** из iiko (выручка по сотруднику), TCO (смены — будет), CRM (отзывы — будет)
2. **Применяет схему** конкретной локации × должности × периода
3. **Считает** бонус по одной из 5 моделей
4. **Сохраняет** полный снапшот: какая схема, какие KPI значения, какая ставка, какая выручка → итог
5. **Возвращает** breakdown с пошаговой расшифровкой

---

## 2. Общая логика

### Главная идея архитектуры

> Все ставки, проценты, грейды и распределения — **в БД и админке**, а не в коде.

Когда HR меняет процент бариста с 1.3% на 1.5% — это `UPDATE` строки в `bonus_scheme.config`, а не правка Python-кода.

### Подразделения = универсальные команды

KITCHEN — **не специальная сущность**. Это `bonus_team` со слотами (`bonus_team_position`). Та же абстракция работает для будущих BAR_TEAM, DELIVERY, HOUSEKEEPING — просто новая запись в `bonus_team` + наполнение слотами.

### Версионирование

Схема (`bonus_scheme`) имеет `effective_from` и `effective_to`. При расчёте за прошлый период берётся та схема, которая **действовала в этот период**. Изменение ставки = создание новой версии (старая закрывается датой), не UPDATE.

Это критически важно: расчёт за апрель 2026 должен использовать апрельские ставки, даже если в мае их подняли.

### Снапшоты для аудита

Каждый `bonus_calculation` сохраняет:
- `scheme_config_snapshot` (JSONB) — точная копия конфига схемы на момент расчёта
- `kpi_values` (JSONB) — все значения KPI с фактом и таргетом
- `breakdown` (JSONB) — пошаговая разбивка формулы

Это нужно для аудита: через 6 месяцев финдиректор должен открыть и увидеть всё, не лезя в логи.

---

## 3. Целевой бизнес-процесс

### Месячный цикл

| День | Кто | Что |
|---|---|---|
| **1-е** | Авто-sync iiko | Загрузка `sales_by_waiter` за прошлый месяц (cron 02:30) |
| **5-е, 05:00** | Авто-расчёт (cron) | Создание `bonus_calculation` со статусом `draft` для всех с активным `bonus_employee_assignment` |
| **5-7-е** | HR / Управляющий | Заполнение `bonus_manual_kpi`: аудит, отзывы CRM (вручную), укомплектованность |
| **5-7-е** | HR | Re-run расчёта через `POST /api/bonus/calculations/run` после ввода ручных KPI |
| **8-10-е** | Управляющий ресторана | Просмотр расчётов своих сотрудников через `/bonus/calculations`, добавление штрафов через `POST /calculations/{id}/penalties`, статус `review` |
| **11-13-е** | Финдиректор | `POST /calculations/{id}/approve` — статус становится `approved` |
| **14-15-е** | Бухгалтерия | Выгрузка в 1С:ЗУП (TODO: эндпоинт `/calculations/export?format=xlsx`), оформление начисления |
| **16-25-е** | Сотрудник | Получает зарплату с бонусом, может посмотреть свою расшифровку |

### Жизненный цикл расчёта

```
draft → review → approved → paid
              ↓
            rejected
              
draft → superseded (если запустить пересчёт)
        recalculated (если есть already approved/paid)
```

**Важно**: расчёт с `status=approved` или `paid` **не пересчитывается** — он остаётся как есть, новый расчёт сохраняется со статусом `recalculated` (для истории).

---

## 4. Модели расчёта (5 шт.)

Каждая модель — отдельный класс в `app/bonus/calculator/models/`, регистрируется через `@register_model('<code>')` в `CALCULATION_MODELS`.

### 4.1 `flat_by_kpi` — фиксированная сумма по KPI

**Кто**: Управляющий

**Идея**: % выполнения KPI → грейд → **фиксированная сумма** в тенге.

**Формула**:
```
overall_kpi = avg(kpi_values)         # 5 KPI: укомплектованность, отзывы, аудит, рост APC, рентабельность
grade = find_grade(grades, overall)   # если < 70% → бонус = 0
bonus = grade.value                   # 80 000 / 100 000 / 130 000 / 150 000 / 170 000
если apply_shifts_proration:
    bonus = bonus × (worked / norm)
bonus -= penalties
```

**Пример**: Управляющий с KPI 95/96/90/88/85 → avg 90.8% → грейд 90-97% → **150 000 KZT**

### 4.2 `revenue_percent_by_kpi` — % от выручки × KPI-грейд

**Кто**: Менеджер (Администратор), Официант

**Идея**: % KPI → грейд (как процент!) → **выручка × коэффициент**.

**Формула**:
```
overall_kpi = avg(kpi_values)
grade_rate = find_grade(grades, overall)   # 0.03 / 0.035 / 0.04 / 0.042 / 0.045
revenue = fetch(scheme.revenue_source)
bonus = revenue × grade_rate
если apply_shifts_proration:
    bonus = bonus × (worked / norm)
bonus -= penalties
```

**Пример (Официант Sandyq Astana)**:
- Личная выручка со скидкой = 2 500 000 KZT
- KPI: план продаж 100%, отзывы 100%, маржинальность 100% → avg 100%
- Грейд 98-100% → 4.5%
- **Бонус = 2 500 000 × 0.045 = 112 500 KZT**

### 4.3 `revenue_direct` — % от выручки без KPI

**Кто**: Кассир, Старший бариста

**Идея**: Просто **выручка × фиксированный процент**, без KPI и грейда.

**Формула**:
```
revenue = fetch(scheme.revenue_source)
bonus = revenue × scheme.rate
если apply_shifts_proration:
    bonus = bonus × (worked / norm)
    # ИЛИ для shifts_proration_formula='norm_then_actual':
    # bonus = revenue / norm × worked × rate
bonus -= penalties
```

**Пример (Кассир Sandyq Astana)**:
- Выручка точки без скидки = 25 000 000 KZT
- 25 000 000 × 0.0007 = **17 500 KZT**

### 4.4 `combined_products` — сумма по компонентам

**Кто**: Бариста

**Идея**: Несколько компонентов выручки, у каждого свой процент. Сумма = бонус.

**Формула**:
```
total = 0
for component in components:
    revenue = fetch(component.source)
    total += revenue × component.rate
если apply_shifts_proration:
    total = total × (worked / norm)
bonus = total - penalties
```

**Пример (Бариста Tary Kainar)**:
- Готовая продукция: 2 000 000 × 0.001 = 2 000 KZT
- Приготовленная: 3 000 000 × 0.016 = 48 000 KZT
- **Итого: 50 000 KZT**

### 4.5 `team_revenue_by_kpi` — коллективный (KITCHEN)

**Кто**: KITCHEN команды (Sandyq Astana, Sandyq Almaty, Tary Ayusai). В будущем — BAR_TEAM, DELIVERY.

**Идея**: KPI команды → **гейт** (если ниже минимума, всем 0). Распределение через веса слотов команды.

**Формула**:
```
overall_kpi = avg(team_kpi_values)
если overall_kpi < min_grade и below_threshold_bonus_zero:
    return 0  # гейт сработал

revenue = fetch(scheme.revenue_source)              # выручка ВСЕЙ точки
slot_weight = bonus_team_position.distribution_weight  # 0.0013 для chef, 0.0009 для sous_chef_1, …
shifts_ratio = worked / norm

bonus = revenue × slot_weight × shifts_ratio
```

**Веса слотов** (всего 21 слот в KITCHEN):
| slot | display_name | distribution_weight |
|---|---|---|
| chef | Шеф-повар | 0.0013 |
| sous_chef_1 | Су-шеф 1 | 0.0009 |
| sous_chef_2 | Су-шеф 2 | 0.0006 |
| senior_shift_cook_1 | Повар старшей смены 1 | 0.0008 |
| hot_cook_1 | Повар горячего цеха 1 | 0.0007 |
| junior_cook_1 | Младший повар 1 | 0.0005 |
| pastry_chef | Шеф-кондитер | 0.0007 |
| baker_1 | Пекарь 1 | 0.0005 |
| … | (всего 21) | … |

**Пример (Шеф Sandyq Astana, идеальный месяц)**:
- KPI команды: план продаж 100%, аудит кухни 100%, нет негативных отзывов → 100% > 70% (гейт пройден)
- Revenue точки = 50 000 000 KZT
- Шеф: weight=0.0013, worked=22, norm=22 → ratio=1.0
- **Бонус = 50 000 000 × 0.0013 × 1.0 = 65 000 KZT**

**Особые правила**:
- `exclude_probation_period: true` — сотрудники на испытательном сроке исключены из распределения (бонус = 0)
- `exclude_violators: true` — нарушители исключены (через флаг в employee_assignment)

### Сводная таблица

| Модель | Должности | KPI | Выручка | Что грейд возвращает |
|---|---|---|---|---|
| `flat_by_kpi` | Управляющий | да | нет | сумма (тг) |
| `revenue_percent_by_kpi` | Менеджер, Официант | да | да | процент |
| `revenue_direct` | Кассир, Ст. бариста | нет | да | (нет грейда) |
| `combined_products` | Бариста | нет | да (×N) | (нет грейда) |
| `team_revenue_by_kpi` | KITCHEN | да (гейт) | да | используется только как гейт |

---

## 5. Архитектура

### Слоистая структура

```
┌──────────────────────────────────────────────────────────────┐
│                  API LAYER (FastAPI)                         │
│   /api/bonus/* (24 эндпоинта)                                │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                             │
│   SchemeService (versioning + validation)                    │
│   CalculationPreloader (fetch all needed data)               │
│   CalculatorRunner (orchestration + persistence)             │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                  CALCULATION ENGINE                          │
│   ┌────────────────┬──────────────┬──────────────────────┐   │
│   │ Calculation    │ KPI Engine   │ Grading              │   │
│   │ Models         │ (scoring)    │ (find_grade + ceil)  │   │
│   │ Registry       │              │                      │   │
│   │ ─────────────  │              │                      │   │
│   │ flat_by_kpi    │              │                      │   │
│   │ revenue_pct    │              │                      │   │
│   │ revenue_direct │              │                      │   │
│   │ combined_prods │              │                      │   │
│   │ team_revenue   │              │                      │   │
│   └────────────────┴──────────────┴──────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                  DATA SOURCES LAYER                          │
│   DataSourceRegistry (плагинная архитектура, 19 источников)  │
│   ┌──────┬──────┬─────┬────┬────────┬────────────────┐       │
│   │ iiko │ tco  │ crm │ hr │ manual │ monthly_plans  │       │
│   └──────┴──────┴─────┴────┴────────┴────────────────┘       │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                  REPOSITORY LAYER                            │
│   SchemeRepository (find_active_*)                           │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│              DATABASE (PostgreSQL 15)                        │
│   11 bonus_* таблиц + departments.company_id (ALTER)         │
└──────────────────────────────────────────────────────────────┘
```

### Плагинная архитектура моделей расчёта

```python
# app/bonus/calculator/registry.py
CALCULATION_MODELS: dict[str, type[BaseBonusModel]] = {}

def register_model(code: str):
    def decorator(cls):
        cls.code = code
        CALCULATION_MODELS[code] = cls
        return cls
    return decorator

# app/bonus/calculator/models/flat_by_kpi.py
@register_model("flat_by_kpi")
class FlatByKpiModel(BaseBonusModel):
    def calculate(self, config, context) -> BonusResult: ...
```

Добавление новой модели = создание файла + декоратор. Никаких `if/elif` цепочек.

### Плагинная архитектура источников данных

```python
# app/bonus/data_sources/registry.py
class DataSourceRegistry:
    _sources: dict[str, BonusDataSource] = {}

    @classmethod
    def register(cls, source): ...

    @classmethod
    def get(cls, code) -> BonusDataSource: ...
```

Калькулятор не знает про iiko/TCO/CRM. Работает через абстракцию `BonusDataSource`. В config схемы указано имя источника (`"revenue_source": "iiko_personal_revenue_with_discount"`).

---

## 6. Модель данных

### 11 таблиц `bonus_*` + ALTER `departments.company_id`

```
bonus_company ←──── departments (.company_id)
                     │
                     ├──< bonus_scheme >── bonus_position
                     │       │                  │
                     │       └─── (xor) ──┐     │
                     │                    │     │
                     │  bonus_team ──< bonus_team_position
                     │       │                  │
                     │       └─< bonus_employee_assignment ──> employee
                     │                          │
                     ├──< bonus_monthly_plan    │
                     │                          │
                     └──< bonus_manual_kpi      │
                                                │
employee ─────< bonus_calculation ──────────────┘
                     │
                     └─< bonus_calculation_penalty
```

### Описание ключевых таблиц

| Таблица | Назначение | Ключевые поля |
|---|---|---|
| `bonus_company` | Юрлица (ТОО Sandyq Kainar, ТОО Sandyq Astana, …) | `code`, `name`, `bin` |
| `bonus_position` | Должности с маппингом на iiko-роли | `code`, `name`, `category`, `iiko_role_code` |
| `bonus_team` | Подразделения внутри локации (KITCHEN, BAR_TEAM, …) | `department_id`, `code`, `name` |
| `bonus_team_position` | Слоты команды с весами (версионируется) | `team_id`, `position_id`, `slot`, `distribution_weight DECIMAL(8,6)`, `effective_from/to` |
| `bonus_kpi_definition` | Справочник KPI | `code`, `data_source_code`, `direction`, `target_metric` |
| `bonus_monthly_plan` | Помесячные планы продаж/рентабельности/норма смен | `department_id`, `metric`, `year/month`, `target_value` |
| `bonus_employee_assignment` | Назначение сотрудника на должность/слот | `employee_id`, `department_id`, `position_id`, `team_id`, `team_position_slot`, `effective_from/to` |
| `bonus_scheme` | **Главная сущность**: схема расчёта | `department_id`, `position_id` ИЛИ `team_id`, `calculation_model`, `config` JSONB, `effective_from/to`, `version` |
| `bonus_manual_kpi` | Ручной ввод KPI | `department_id`, `kpi_code`, `period_year/month`, `fact_value` |
| `bonus_calculation` | Результат расчёта со снапшотом | `employee_id`, `period_year/month`, `scheme_config_snapshot`, `kpi_values`, `breakdown` JSONB, `final_bonus`, `status` |
| `bonus_calculation_penalty` | Удержания/штрафы | `calculation_id`, `reason_code`, `reason_text`, `penalty_amount` |

### Точность Decimal

| Тип данных | DDL | Пример |
|---|---|---|
| Деньги (тенге) | `DECIMAL(14, 2)` | `170000.00` |
| Проценты-доли | `DECIMAL(8, 6)` | `0.000700` (= 0.07%) |
| Грейды (5..100) | `DECIMAL(5, 2)` | `89.50` |
| Веса слотов команды | `DECIMAL(8, 6)` | `0.001300` (= 0.13%) |

**Никогда не использовать `float`** для денег и процентов.

### Маппинг с существующими таблицами

| bonus_* | Sales Forecast | Связь |
|---|---|---|
| `bonus_employee_assignment.employee_id` | `employees.id` | UUID FK |
| `bonus_employee_assignment.department_id` | `departments.id` | UUID FK |
| `departments.company_id` | `bonus_company.id` | INTEGER FK (новая колонка) |
| `bonus_calculation.employee_id` | `employees.id` | UUID FK |
| `bonus_position.iiko_role_code` | `employees.main_role_code` | Логическая связь (не FK) |

### Версионирование

- **`bonus_scheme`**: при изменении `config` старая запись закрывается на `new.effective_from - 1 day`, создаётся новая с `version + 1`
- **`bonus_team_position`**: то же самое (изменение веса слота = новая строка)
- **`bonus_employee_assignment`**: то же (перевод сотрудника = закрытие старой + создание новой)

Резолвинг активной записи на дату `D`:
```sql
SELECT * FROM bonus_scheme
WHERE department_id = :dept
  AND position_id = :pos
  AND effective_from <= :D
  AND (effective_to IS NULL OR effective_to >= :D)
ORDER BY version DESC
LIMIT 1;
```

---

## 7. API

Все эндпоинты под `/api/bonus/*`. Авторизация — `Authorization: Bearer <API_TOKEN>` (общая с основным проектом).

### Справочники

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/companies` | Список юрлиц |
| GET | `/positions?category=` | Должности (фильтр по категории) |
| GET | `/kpi-definitions` | Справочник KPI |
| GET | `/config/calculation-models` | 5 кодов моделей |
| GET | `/config/data-sources` | 19 кодов источников |

### Схемы

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/schemes?department_id=&position_id=&active_on=` | Список схем |
| GET | `/schemes/{id}` | Детали схемы |
| POST | `/schemes` | Создать (с авто-версионированием прошлой) |
| POST | `/schemes/validate` | Валидация config без сохранения |
| GET | `/schemes/active/by-position?department_id=&position_id=&on_date=` | Активная для пары |

### Команды (KITCHEN)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/teams?department_id=` | Список команд |
| GET | `/teams/{id}` | Команда + список слотов |

### Помесячные планы

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/monthly-plans?department_id=&year=&metric=` | Список планов |
| POST | `/monthly-plans` | Upsert (UNIQUE по dept+metric+year+month) |

### Ручные KPI

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/manual-kpi?department_id=&year=&month=` | Список |
| POST | `/manual-kpi` | Upsert |
| DELETE | `/manual-kpi/{id}` | Удалить |

### Расчёты

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/calculations/run` | Запустить (`scope: all\|employee:<uuid>\|position:<code>`) |
| GET | `/calculations?department_id=&year=&month=&status=&employee_id=` | Список |
| GET | `/calculations/{id}` | Детали + breakdown + penalties |
| POST | `/calculations/{id}/penalties` | Добавить удержание |
| POST | `/calculations/{id}/approve?actor=` | Утвердить |
| POST | `/calculations/{id}/reject?reason=` | Отклонить |
| GET | `/reports/summary?year=&month=` | Сводка по локациям |

### Пример полного цикла через curl

```bash
TOKEN=$(grep '^API_TOKEN' .env | cut -d= -f2-)
DEPT="2086adde-d191-496e-9ff7-eb78173fa8bb"  # Sandyq Astana

# 1. Ввести план продаж
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/bonus/monthly-plans \
  -d "{\"department_id\":\"$DEPT\",\"metric\":\"sales\",\"year\":2026,\"month\":4,\"target_value\":\"50000000\"}"

# 2. Ввести ручной KPI (аудит)
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/bonus/manual-kpi \
  -d "{\"department_id\":\"$DEPT\",\"kpi_code\":\"manual_audit\",\"period_year\":2026,\"period_month\":4,\"fact_value\":\"95\"}"

# 3. Запустить расчёт всех официантов
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/bonus/calculations/run \
  -d "{\"department_id\":\"$DEPT\",\"year\":2026,\"month\":4,\"scope\":\"position:waiter\"}"

# 4. Посмотреть результаты
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8002/api/bonus/calculations?department_id=$DEPT&year=2026&month=4"

# 5. Утвердить расчёт #42
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8002/api/bonus/calculations/42/approve?actor=director@sandyq.kz"
```

---

## 8. Frontend

4 страницы под `/bonus/*` в `frontend/src/pages/`. Стек: React 19 + TanStack Query + shadcn/ui + Recharts.

### `/bonus/calculations` — расчёты бонусов

**Что показывает**: таблица всех расчётов с фильтрами (локация, год, месяц, статус).
- Колонки: ID, локация, сотрудник, период, выручка, KPI %, ставка, итого, статус
- Сумма пула всех расчётов в шапке
- Кнопка «Запустить расчёт» — батч для выбранной локации/периода
- Клик по строке → диалог с деталями: breakdown (JSON шагов), список штрафов, кнопки «Утвердить» / «Отклонить» (для draft/review)

### `/bonus/schemes` — схемы расчёта

**Что показывает**: таблица схем с фильтром по локации.
- Колонки: локация, должность/команда, модель расчёта, версия, период действия
- Клик «Показать» → диалог с JSONB конфигом (просмотр, не редактирование)

> **TODO для production**: визуальный редактор грейдов / ставок / KPI вместо JSONB.

### `/bonus/manual-kpi` — ручной ввод KPI

**Что показывает**: таблица ручных KPI за период.
- Форма: локация, KPI (из dropdown), год/месяц, значение
- Удаление записей
- Используется HR для ввода аудита, отзывов, укомплектованности

### `/bonus/monthly-plans` — помесячные планы

**Что показывает**: таблица планов.
- Форма: локация, метрика (sales / profitability / shifts_norm), год/месяц, значение
- Используется один раз в начале года + правки

### Sidebar

Новый раздел «БОНУСЫ» в `frontend/src/components/layout/sidebar.tsx`:
```
БОНУСЫ
├ Расчёты бонусов     (Calculator icon)
├ Схемы расчёта       (FileText icon)
├ Ручной ввод KPI     (ClipboardList icon)
└ Помесячные планы    (Target icon)
```

---

## 9. Источники данных

### 19 зарегистрированных источников

#### iiko (реальные)

| Код | Что | Откуда |
|---|---|---|
| `iiko_personal_revenue_with_discount` | Личная выручка официанта со скидкой | `SUM(sales_by_waiter.total_sales_with_discount)` |
| `iiko_personal_revenue_dish_sum` | Личная выручка без скидки | `SUM(sales_by_waiter.total_sales)` |
| `iiko_revenue_with_discount` | Выручка точки со скидкой | `SUM(sales_summary.total_sales)` (TODO: со скидкой реально) |
| `iiko_revenue_dish_sum` | Выручка точки без скидки | `SUM(sales_summary.total_sales)` |
| `iiko_sales_plan_personal` | Личные продажи (для KPI плана) | `SUM(sales_by_waiter.total_sales_with_discount)` |
| `iiko_sales_plan_location` | Продажи точки (для KPI плана) | `SUM(sales_summary.total_sales)` ÷ `bonus_monthly_plan(metric=sales)` × 100 |

#### iiko (заглушки — нужны для бариста)

| Код | Что | Статус |
|---|---|---|
| `iiko_personal_ready_products_with_discount` | Готовая продукция (бариста) | **Возвращает 0** — нужна доработка iiko OLAP loader (DishCategory.Name) |
| `iiko_personal_prepared_products_with_discount` | Приготовленная продукция | **Возвращает 0** — то же |

#### TCO (Time Control Office) — заглушка

| Код | Что | Статус |
|---|---|---|
| `tco_shifts` | Смены сотрудника | **Аппроксимация**: `worked = COUNT DISTINCT date FROM sales_by_waiter`, `norm` из `bonus_monthly_plan(metric=shifts_norm)` или 22 |

#### Manual / CRM / HR (через `bonus_manual_kpi`)

| Код | KPI | Direction |
|---|---|---|
| `manual_audit` | Аудит / стандарты | higher_is_better |
| `manual_kitchen_audit` | Аудит кухни | higher_is_better |
| `manual_profitability` | Рентабельность | higher_is_better |
| `hr_staffing_percent` | Укомплектованность штата | higher_is_better |
| `crm_negative_reviews_share` | Негативные отзывы (точка) | lower_is_better |
| `crm_individual_negative_reviews` | Личные негативные отзывы | lower_is_better |
| `crm_kitchen_reviews` | Негативные отзывы кухни | lower_is_better |
| `crm_restaurant_rating` | Рейтинг ресторана (1-5) | binary |
| `iiko_apc_growth` | Рост среднего чека (%) | higher_is_better |
| `iiko_margin_share` | Доля маржинальных позиций (%) | higher_is_better |

> Все CRM/HR/audit пока вводятся через `POST /api/bonus/manual-kpi`. Когда появятся реальные API — заменить адаптеры в `bootstrap.py`.

---

## 10. Операционный workflow

### Однократная настройка (один раз)

```bash
# 1. Применить миграцию
docker exec -i sales-forecast-db psql -U sales_user -d sales_forecast \
  < migrations/007_bonus_core.sql

# 2. Залить seeds (компании, должности, KPI, схемы, KITCHEN)
docker exec sales-forecast-app python -m app.bonus.seeds.run_all

# 3. Создать assignments для сотрудников (TODO: автоматизировать)
# Сейчас вручную через SQL или API. Пример для официантов Sandyq Astana:
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c "
INSERT INTO bonus_employee_assignment(employee_id, department_id, position_id,
    employment_type, effective_from)
SELECT DISTINCT sbw.employee_id, sbw.department_id,
    (SELECT id FROM bonus_position WHERE code='waiter'),
    'permanent', DATE '2026-01-01'
FROM sales_by_waiter sbw JOIN employees e ON e.id=sbw.employee_id
WHERE sbw.department_id='2086adde-d191-496e-9ff7-eb78173fa8bb'
  AND e.main_role_code='WR1' AND sbw.employee_id IS NOT NULL
ON CONFLICT DO NOTHING;
"

# 4. Залить планы продаж на 2026 год
# Через API (пример для одной локации/месяца):
TOKEN=$(grep '^API_TOKEN' .env | cut -d= -f2-)
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://aqniet.site/api/bonus/monthly-plans \
  -d '{"department_id":"<uuid>","metric":"sales","year":2026,"month":4,"target_value":"50000000"}'
```

### Месячный цикл (повторяется каждый месяц)

```
[1-2 числа]  Авто-sync iiko запускается (cron 02:30)
                ↓
[5 число] APScheduler автоматически создаёт draft расчёты (cron 05:00)
                ↓
[5-7 число] HR через UI вводит ручные KPI (аудит, отзывы, укомплектованность)
                ↓
[5-7 число] HR re-run расчётов (старые drafts → superseded, новые → draft)
                ↓
[8-10 число] Управляющий просматривает + добавляет penalties
                ↓
[11-13 число] Финдиректор approve через UI
                ↓
[14-15 число] Бухгалтерия экспортирует в 1С (TODO: эндпоинт)
                ↓
[16-25 число] Сотрудник получает выплату
```

---

## 11. Что готово сейчас

### ✅ Полностью реализовано

**Backend:**
- 11 таблиц `bonus_*` + ALTER `departments.company_id`
- 11 SQLAlchemy моделей с relationship'ами
- Calculator engine с 5 моделями расчёта (плагинная архитектура)
- KPI Engine (3 направления: higher_is_better / lower_is_better / binary, cap@100)
- Grading с ceil-rounding
- 19 data sources (плагинная регистрация)
- SchemeService с версионированием
- CalculationPreloader, CalculatorRunner с idempotency
- 24 REST endpoints под `/api/bonus/*`
- APScheduler job (5-го числа в 05:00, авто-расчёт за прошлый месяц)
- Pydantic-валидация config через `populate_by_name=True` + `by_alias=True`
- JSONB снапшоты (config, kpi_values, breakdown) для аудита

**Frontend:**
- 4 страницы (calculations, schemes, manual-kpi, monthly-plans)
- TanStack Query хуки + типы
- Новая секция «БОНУСЫ» в Sidebar
- Просмотр breakdown расчёта в диалоге

**Seeds:**
- 4 юрлица
- 21 должность с маппингом на iiko-роли
- 12 KPI definitions
- 56 схем расчёта для 10 локаций
- 3 KITCHEN команды × 21 слот = 63 `bonus_team_position`

**Tests:**
- 53/53 unit-теста с конкретными числами из KPI-документов
- Покрытие всех 5 моделей расчёта, KPI engine, grading

**Деплой:**
- Задеплоено на https://aqniet.site
- Docker-образ пересобран (113s build)
- Миграция применена, seeds выполнены

**Документация:**
- `CLAUDE.md` — раздел «Bonus Subsystem» с правилами do/don't
- `bonus_service/bonus_docs/` — оригинальная спецификация (00-context до 10-testing)
- `bonus_service/Документы по расчету/` — оригинальные .docx KPI 2026
- `docs/SESSION_LOG_Bonus_Subsystem_Integration_2026-04-29_20-01.md`
- Этот документ

### ✅ Реальные расчёты на проде

End-to-end проверка (Sandyq Astana, апрель 2026):
- 17 официантов
- Реальные данные из `sales_by_waiter`
- Общий пул бонусов: **4,117,312 KZT**
- Средний бонус: 242,195 KZT
- Все breakdown сохранены в `bonus_calculation.breakdown`

---

## 12. Что нужно дополнить до production

### 🔥 12.0 Минимальный чек-лист перед первым боевым запуском (5 мая 2026)

Авто-расчёт за апрель сработает автоматически 5-го мая в 05:00 (cron `monthly_bonus_auto_calc`). На текущий момент в проде заполнено только Sandyq Astana (см. раздел 16). Чтобы первый боевой запуск дал содержательный результат, минимум:

| # | Что | Где | SQL/API проверка |
|---|---|---|---|
| 1 | Заполнить `bonus_employee_assignment` для всех должностей всех 10 локаций | `/bonus/calculations` (бэкенд UI пока не сделан, заводить через SQL/скрипт) | `SELECT department_id, count(*) FROM bonus_employee_assignment WHERE effective_to IS NULL GROUP BY department_id;` |
| 2 | Завести `bonus_monthly_plan(metric=sales)` для каждой локации × апрель 2026 | `/bonus/monthly-plans` | `SELECT department_id, target_value FROM bonus_monthly_plan WHERE metric='sales' AND year=2026 AND month=4;` |
| 3 | Опционально: `metric=shifts_norm` если норма ≠ 22 | `/bonus/monthly-plans` | `SELECT department_id, target_value FROM bonus_monthly_plan WHERE metric='shifts_norm' AND year=2026 AND month=4;` |
| 4 | Ввести через `/bonus/manual-kpi` за апрель: `manual_audit`, `manual_kitchen_audit`, `manual_profitability`, `hr_staffing_percent` для каждой локации | `/bonus/manual-kpi` | `SELECT department_id, kpi_code FROM bonus_manual_kpi WHERE period_year=2026 AND period_month=4;` |
| 5 | Временно: ввести `crm_*` метрики через `/bonus/manual-kpi` (пока нет CRM-интеграции) | `/bonus/manual-kpi` | те же KPI с кодами `crm_negative_reviews_share`, `crm_kitchen_reviews`, `crm_individual_negative_reviews`, `crm_restaurant_rating` |
| 6 | Прогнать `POST /calculations/run` руками с `scope: all` для каждой локации **до** 5-го числа | `/bonus/calculations` или `curl` | `SELECT department_id, count(*), sum(final_bonus) FROM bonus_calculation WHERE period_year=2026 AND period_month=4 AND status='draft' GROUP BY department_id;` |
| 7 | Глазами проверить разброс сумм: если у кого-то ноль или явно завышено — найти отсутствующий KPI/план | UI таблица или SQL | `SELECT * FROM bonus_calculation WHERE final_bonus = 0 OR final_bonus > 500000 ORDER BY final_bonus DESC LIMIT 20;` |
| 8 | Только после ручной валидации первой локации — дать crontab отработать на остальных 5-го мая | — | смотреть логи: `docker logs sales-forecast-app 2>&1 \| grep "monthly_bonus_auto_calc"` |

**Если что-то из 1-5 не успели — лучше отключить cron за день до запуска, чтобы не создавать сотни мусорных draft-расчётов:**

```bash
# Отключить cron временно
docker exec sales-forecast-app python -c "
from apscheduler.schedulers.background import BackgroundScheduler
# либо закомментировать блок monthly_bonus_auto_calc в app/main.py и пересобрать
"
```

Безопаснее — закомментировать `scheduler.add_job(..., id='monthly_bonus_auto_calc', ...)` в `app/main.py`, пересобрать образ. Раскомментировать после готовности.

### 🔴 Критичное (блокеры выплат)

#### 12.1 Реальные данные по продуктам для бариста

**Проблема**: `iiko_personal_ready_products_with_discount` и `iiko_personal_prepared_products_with_discount` сейчас возвращают 0 → бариста по схеме `combined_products` всегда получают 0.

**Что нужно**:
1. Расширить `app/services/iiko_waiter_sales_loader.py` — добавить группировку по `DishCategory.Name` или `DishCode` в OLAP-запросе
2. Создать новую таблицу `sales_by_waiter_category` (или JSONB-столбец `categories` в `sales_by_waiter`)
3. Заменить заглушки в `app/bonus/data_sources/iiko/products.py` на реальные SQL-запросы
4. Уточнить у заказчика классификацию: какие категории относятся к «готовой» (`ready_products`), какие к «приготовленной» (`prepared_products`)

**Оценка**: 2-3 дня работы

#### 12.2 Реальные смены TCO

**Проблема**: `tco_shifts` сейчас аппроксимирует `worked = COUNT DISTINCT date FROM sales_by_waiter`, и это даёт **некорректные** числа в нескольких сценариях:

| Сценарий | Что считает аппроксимация | Что должно быть | Влияние |
|---|---|---|---|
| Сплит-смена (утро + вечер одного дня) | 1 | 2 | занижение бонуса |
| Смена без продаж (утренняя подготовка, обучение) | 0 | 1 | занижение |
| KITCHEN — повара не пробивают чеки | 0 для всех дней | реальные смены | бонус KITCHEN ≈ 0 |
| Кассиры (`CS1`) — не привязываются к `sales_by_waiter` | 0 | реальные смены | бонус кассиров ≈ 0 |
| Хосты, бар-юниоры без своих чеков | 0 | реальные смены | бонус ≈ 0 |
| Удалённый заказ (день есть, смены не было) | 1 | 0 | завышение |

Особенно опасно для модели `team_revenue_by_kpi` (KITCHEN), где `bonus = revenue × slot_weight × (worked / norm)`: при `worked=0` весь шеф-повар получает 0.

**Что нужно**:
1. Договориться с командой TCO о REST API (endpoint типа `GET /shifts?employee_id=&from=&to=` → список смен)
2. Создать `app/bonus/data_sources/tco/shifts_real.py` с HTTP-клиентом + кешированием
3. Заменить регистрацию в `bootstrap.py` (`TcoShifts` → `TcoShiftsReal`)
4. Для всех ролей **без** `sales_by_waiter` (KITCHEN, кассиры, хосты) — это **обязательно**, заглушка для них фундаментально не работает

**Оценка**: 3-5 дней (зависит от готовности TCO API)

**Промежуточные решения** (если TCO API ещё не готов к 5-му мая):
- Ввести `bonus_monthly_plan(metric='shifts_norm')` для каждой локации/месяца через API
- Для KITCHEN/кассиров временно завести таблицу-проксю `bonus_manual_shifts` или ввести вручную через `bonus_manual_kpi` с кодом `tco_shifts_worked` (придётся создать KPI-definition и адаптер)
- Альтернатива: руками заносить в `bonus_calculation_penalty` корректировку «доплата за отработанные смены X»

#### 12.3 Локации `Sandyq Kainar` и `Tary Kainar`

**Проблема**: KPI-документы заказчика содержат конфиги для этих локаций, но в `departments` их нет. Seeds их пропускает с warning.

**Что нужно**:
1. Уточнить: эти бренды действительно работают? Или это будущие?
2. Если работают — добавить в `departments` через 1C Exchange sync (`POST /api/departments/sync`)
3. Перезапустить seeds: `docker exec sales-forecast-app python -m app.bonus.seeds.run_all`

#### 12.4 Авто-привязка сотрудников к должностям

**Проблема**: `bonus_employee_assignment` создаются вручную через SQL. На проде это не масштабируется.

**Что нужно**:
1. Создать `app/bonus/services/auto_assignment.py`:
   - Для каждого employee с `main_role_code` найти `bonus_position` с тем же `iiko_role_code`
   - Создать assignment если есть совпадение и `preferred_department_code` привязан к локации со схемой
   - Закрывать assignment когда `employee.deleted=true` или сменилась роль
2. Добавить в APScheduler (например, ежедневно в 06:00 после `employees_sync`)
3. UI: страница «Назначения» с возможностью ручной коррекции

**Оценка**: 2-3 дня

### 🟡 Важное (для удобства работы)

#### 12.5 Excel-экспорт расчётов для бухгалтерии

**Что нужно**:
1. Добавить эндпоинт `GET /api/bonus/calculations/export?department_id=&year=&month=&format=xlsx`
2. Использовать `openpyxl` или `pandas.to_excel()` для генерации
3. Колонки: ИИН (если есть), ФИО, должность, период, base_bonus, penalties, final_bonus, статус
4. Кнопка «Экспорт в Excel» на странице `/bonus/calculations`

**Оценка**: 1 день

#### 12.6 Визуальный редактор схем

**Проблема**: сейчас изменение схемы возможно только через `POST /schemes` с JSON-конфигом. Это требует знания формата JSONB.

**Phase 1 — DONE (2026-05-02)** — фундамент для редактора:
- ✅ `BonusDataSource` расширен метаданными (`name`, `description`, `value_type`, `unit`, `category`, `is_stub`); заполнено для всех 19 источников
- ✅ `app/bonus/calculator/metadata.py` — `CALCULATION_MODEL_METADATA` для 5 моделей (флаги `requires_*`, `grade_type`, `options[]` с label/hint)
- ✅ `GET /api/bonus/config/data-sources` и `/calculation-models` отдают объекты вместо массивов кодов
- ✅ Frontend: новый компонент `SchemeConfigView` рендерит config читабельными таблицами (KPI, грейды с локализацией, источники с категориями, опции с подсказками); диалог схемы — Tabs «Параметры / JSON»
- 📄 Подробности: `docs/SESSION_LOG_Bonus_Scheme_UI_Editor_Phase1_2026-05-02_10-27.md`

**Phase 2 — DONE (2026-05-02)** — визуальный редактор:
- ✅ Кнопка «Создать схему» в шапке `/bonus/schemes`
- ✅ Кнопка «Новая версия» в каждой строке таблицы (предзаполняет диалог из существующей схемы)
- ✅ `SchemeEditorDialog` (`frontend/src/components/bonus/scheme-editor-dialog.tsx`) — Dialog с двумя секциями:
  - Контекст: `DepartmentSelect`, дата начала, Select модели, Select должности/команды (auto-switch при `is_team_model`), Textarea заметок
  - Параметры модели — динамические блоки (KPI / Revenue source / Rate / Grades / Components / Options) рендерятся по флагам метаданных модели
- ✅ Подкомпоненты в `frontend/src/components/bonus/editors/`:
  - `KpiEditor` — inline-таблица; при выборе KPI auto-fill source/direction/target из `bonus_kpi_definition`
  - `GradesEditor` — flat (₸) или rate (%, автоконвертация 4.5% → 0.045); валидация непрерывности и пересечения диапазонов
  - `RevenueSourceSelect` — Select с группировкой по category, фильтром по value_type, описание выбранного источника, badge заглушек
  - `ComponentsEditor` — для `combined_products`
  - `OptionsEditor` — диспетчер по type (`bool` → Switch, `enum` → RadioGroup, `money` → NumberInput) с label + hint
- ✅ Live-валидация через `POST /schemes/validate` (кнопка «Проверить») с нормализацией ответа
- ✅ Сохранение через `POST /schemes` (кнопка «Создать схему» / «Сохранить как новую версию»)
- ✅ Новые shadcn-компоненты: `Switch`, `RadioGroup`, `RadioGroupItem`, `SelectLabel`, `SelectSeparator`
- 📄 Подробности: `docs/SESSION_LOG_Bonus_Scheme_UI_Editor_Phase2_*.md`

**Phase 3 — ДОПОЛНИТЕЛЬНО (2-3 дня)**:
- Тестовый расчёт (sandbox) — эндпоинт `POST /schemes/preview-calculation` + UI-форма «При KPI=__%, выручке=__₸ → бонус будет ХХХ»
- Diff против активной версии (особенно важно для грейдов)
- Inline-редактор слотов KITCHEN (`bonus_team_position.distribution_weight`) на странице `/bonus/teams/{id}`
- История версий схемы с timeline и диффами

**Оценка остатка**: 7-10 дней

#### 12.7 CRM интеграция (отзывы, рейтинг)

**Что нужно**:
1. Уточнить у заказчика — что за CRM (Bitrix24? самописная?)
2. Создать `app/bonus/data_sources/crm/` с реальными адаптерами
3. Заменить заглушки `crm_*` в `bootstrap.py`
4. Опционально: cron-job для авто-синхронизации отзывов в `bonus_manual_kpi`

**Оценка**: 5-10 дней (зависит от CRM)

#### 12.8 HR интеграция (укомплектованность)

**Что нужно**:
1. Источник данных — 1С:ЗУП?
2. Либо периодическая синхронизация через 1C Exchange Service
3. Либо ручной ввод через UI (текущий подход)

**Оценка**: 3-5 дней

### 🟢 Желательное (UX и аналитика)

#### 12.9 Дашборд сотрудника

Личный кабинет с историей бонусов: показать сотруднику его breakdown за последние 6 месяцев, как менялся KPI, какие были штрафы.

#### 12.10 Сравнение факт vs прогноз бонусов

Использовать существующий ML-прогноз продаж (Sales Forecast) для предсказания бонуса до закрытия месяца. «По текущей траектории к 30 числу заработаешь ~120 000 KZT».

#### 12.11 Telegram-бот для уведомлений

После approve расчёта отправлять сотруднику в Telegram: «Бонус за апрель 2026: 105 000 KZT».

#### 12.12 Audit log

Сейчас `BonusCalculation` имеет снапшот, но действия пользователей (кто/когда создал/изменил схему, ввёл KPI, утвердил расчёт) логируются только в `calculated_by`/`approved_by`. Можно добавить отдельную таблицу `bonus_audit_log` с детальной историей.

#### 12.13 Расширенные роли и RBAC

Сейчас один `API_TOKEN` даёт всё. Нужны роли:
- `viewer` — только просмотр
- `hr` — ввод KPI, запуск расчётов, штрафы
- `manager_director` — approve расчётов своей локации
- `cfo` — approve всех, экспорт
- `admin` — всё + редактирование схем

Можно использовать существующую `auth.py` с расширением.

#### 12.14 Backups и миграция

- Регулярные бэкапы `bonus_*` таблиц (особенно `bonus_calculation`)
- Скрипт миграции схем при изменении формата `config` JSONB

---

## 13. Расширение системы

### Добавление новой модели расчёта

Допустим, придумали «бонус от чаевых»:

1. Создать `app/bonus/calculator/models/tips_based.py`:
   ```python
   @register_model('tips_based')
   class TipsBasedModel(BaseBonusModel):
       def validate_config(self, config): ...
       def calculate(self, config, context) -> BonusResult: ...
   ```
2. Создать Pydantic-схему `app/bonus/schemas/calc_configs/tips_based.py` и добавить в `CONFIG_VALIDATORS`
3. Добавить мок источника `tips_data` (если нет)
4. Добавить тесты в `tests/bonus/test_calculation_models.py`
5. Добавить миграцию для `bonus_scheme.calculation_model` CHECK constraint
6. Создать схему через UI или API

**Никаких правок в `BonusCalculatorService`, базовых классах, БД или фронте.**

### Добавление нового подразделения (BAR_TEAM, DELIVERY)

```sql
-- 1. Создать команду
INSERT INTO bonus_team(department_id, code, name)
VALUES ('<dept_uuid>', 'bar_team', 'Бар-команда');

-- 2. Добавить позиции (если новые)
INSERT INTO bonus_position(code, name, category, iiko_role_code)
VALUES ('senior_bartender', 'Старший бармен', 'bar', 'BR0'),
       ('junior_bartender', 'Младший бармен', 'bar', 'BR2');

-- 3. Слоты команды
INSERT INTO bonus_team_position(team_id, position_id, slot, distribution_weight, effective_from)
VALUES (..., 'senior_bar_1', 0.0010, '2026-05-01'),
       (..., 'junior_bar_1', 0.0007, '2026-05-01');

-- 4. Схема
INSERT INTO bonus_scheme(department_id, team_id, calculation_model, config, effective_from)
VALUES (..., 'team_revenue_by_kpi', '{...}'::jsonb, '2026-05-01');
```

### Изменение ставки (новая версия схемы)

Через API:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/bonus/schemes \
  -d '{
    "department_id": "<uuid>",
    "position_id": 8,
    "calculation_model": "revenue_percent_by_kpi",
    "config": { ... новые грейды ... },
    "effective_from": "2026-05-01",
    "notes": "Решение совета от 25.04.2026"
  }'
```

Старая схема автоматически закрывается на `2026-04-30`. Новая получает `version+1`. Расчёты за апрель и раньше используют старую (через `find_active_scheme_for_position(on_date)`).

### Новая локация

1. Добавить в `departments` через `POST /api/departments/sync` (1C Exchange)
2. Опционально: связать с юрлицом — `UPDATE departments SET company_id = X WHERE id = ...`
3. Добавить в `app/bonus/seeds/run_all.py` в список `LOCATIONS` нужные ставки
4. Перезапустить seeds: `docker exec sales-forecast-app python -m app.bonus.seeds.run_all`

---

## 14. FAQ

**Q: Как вернуть прошлогодние расчёты?**
A: `GET /api/bonus/calculations?year=2025&month=12&status=paid`. Сами snapshot-данные хранятся в `scheme_config_snapshot` и `breakdown` — даже если схема изменилась, старый расчёт показывает что было.

**Q: Что если KPI отсутствует в `bonus_manual_kpi`?**
A: Считается как 0% (для `higher_is_better`) или 100% (для `lower_is_better` с fact=0). Это занижает overall_kpi и может дать ниже-порогового грейда.

**Q: Что если выручки нет (точка не работала в этом месяце)?**
A: `revenue=0`, бонус = 0 для всех моделей кроме `flat_by_kpi` (там зависит только от KPI).

**Q: Как тестировать новую схему перед деплоем?**
A: `POST /api/bonus/schemes/validate` — валидация без сохранения. Затем создать на тестовой локации с `effective_from` в будущем, запустить `/calculations/run` для одного employee.

**Q: Что если налоги (NET vs GROSS)?**
A: Все суммы в системе — **NET** (на руки). Бухгалтерия в 1С:ЗУП накручивает gross (ИПН 10% + ОПВ 10%). Сервис gross не считает.

**Q: Идемпотентность — что если запустить расчёт дважды?**
A: Старые `draft`/`review` помечаются `superseded`, создаётся новый `draft`. Если есть `approved`/`paid` — они не трогаются, новый расчёт получает статус `recalculated` (для истории).

**Q: Можно ли откатить approved расчёт?**
A: Нет напрямую, можно через `/reject` (статус → `rejected`). Сам бонус остаётся в БД (для аудита).

**Q: Сколько данных за год?**
A: Прикидка на 1500 сотрудников × 12 месяцев = 18,000 `bonus_calculation` в год. С JSONB полями ~1-2 GB. Никаких проблем с производительностью.

**Q: Версионирование — что если HR забыл создать новую версию и старая ушла в прошлое?**
A: Расчёт за прошлый период использует прошлую версию (по `effective_from <= on_date AND effective_to >= on_date`). Если новая версия не создана, последняя продолжает действовать (`effective_to IS NULL`).

**Q: В CLAUDE.md написана команда `docker exec sales-forecast-app python -m pytest tests/bonus/ -v` — почему она не работает?**
A: В production-образе (`Dockerfile`) папка `tests/` не копируется (она исключена из build-контекста), и `pytest` не установлен. Чтобы прогнать тесты на сервере:
```bash
docker cp tests sales-forecast-app:/app/tests
docker exec sales-forecast-app pip install pytest -q
docker exec -w /app sales-forecast-app python -m pytest tests/bonus/ -p no:cacheprovider
```
Для регулярного запуска тестов лучше прогонять локально (`python -m pytest tests/bonus/`) перед `git push` или поднять отдельный CI-пайплайн.

**Q: Можно ли вводить CRM-метрики (отзывы, рейтинг) через `/bonus/manual-kpi` пока нет интеграции?**
A: Технически — да, при условии что `bonus_kpi_definition` для нужного `kpi_code` существует. Сейчас CRM-источники (`crm_negative_reviews_share`, `crm_individual_negative_reviews`, `crm_kitchen_reviews`, `crm_restaurant_rating`) зарегистрированы как DataSource-заглушки, но `bonus_kpi_definition.data_source_code` ссылается на них. Чтобы перейти на ручной ввод — нужно:
1. Либо создать копию KPI-definition с `data_source_code='manual_<name>'` и в схемах ссылаться на копию
2. Либо переключить адаптеры в `bootstrap.py` так, чтобы CRM-источники сначала смотрели в `bonus_manual_kpi` (это правильнее — тогда любой ручной ввод поверх заглушки сработает автоматически, без правок схем)

Второй вариант — буквально 30 строк кода в `app/bonus/data_sources/manual/manual_kpi.py` (унаследовать CRM-классы от `_ManualKpiBase` с теми же `code='crm_*'`).

**Q: Что если в локации работает несколько KITCHEN-команд (две смены поваров)?**
A: Сейчас в `bonus_team` стоит `UNIQUE(department_id, code)`, то есть в одной локации только одна KITCHEN. Если потребуется две — добавить версионирование команды (`effective_from/to` в `bonus_team`) или сделать код составным (`kitchen_morning`, `kitchen_evening`). Текущий MVP это не поддерживает.

---

## 15. Troubleshooting и health-checks

### Симптомы и диагностика

#### Расчёт = 0 для всех сотрудников

**Возможные причины** (в порядке частоты):
1. Нет `bonus_employee_assignment` для сотрудников этой локации/должности
2. Нет активной `bonus_scheme` на дату расчёта (проверить `effective_from <= '2026-04-30' AND (effective_to IS NULL OR effective_to >= '2026-04-30')`)
3. Нет `bonus_monthly_plan(metric=sales)` — если схема использует `iiko_sales_plan_*` KPI
4. Нет `sales_by_waiter` за этот период — проверить что iiko sync прошёл (`SELECT max(period_date) FROM sales_by_waiter`)
5. Все KPI = 0 → overall_kpi ниже минимального грейда → бонус 0 (это валидный сценарий)

**Диагностика**:
```sql
-- 1. Проверить assignment
SELECT * FROM bonus_employee_assignment
WHERE employee_id = '<uuid>' AND effective_to IS NULL;

-- 2. Проверить активную схему
SELECT * FROM bonus_scheme
WHERE department_id = '<uuid>' AND position_id = (SELECT id FROM bonus_position WHERE code='waiter')
  AND effective_from <= '2026-04-30' AND (effective_to IS NULL OR effective_to >= '2026-04-30');

-- 3. Проверить план
SELECT * FROM bonus_monthly_plan
WHERE department_id = '<uuid>' AND year=2026 AND month=4;

-- 4. Проверить выручку
SELECT employee_id, sum(total_sales_with_discount) FROM sales_by_waiter
WHERE department_id = '<uuid>' AND period_date BETWEEN '2026-04-01' AND '2026-04-30'
GROUP BY employee_id;

-- 5. Посмотреть сам breakdown
SELECT id, final_bonus, kpi_values, breakdown FROM bonus_calculation
WHERE employee_id = '<uuid>' AND period_year=2026 AND period_month=4
ORDER BY id DESC LIMIT 1;
```

#### Расчёт неоправданно высокий

**Возможные причины**:
1. `bonus_monthly_plan(metric=sales)` не заведён → KPI плана = 100% по умолчанию, грейд максимальный
2. `tco_shifts` вернул `worked > norm` (сотрудник работал в выходные) → proration > 1.0
3. KPI не введён в `bonus_manual_kpi`, источник вернул 100% (для `lower_is_better` с fact=0)
4. Версия схемы старая, ставки не пересмотрены

**Диагностика**: открыть `breakdown` JSONB конкретного расчёта — там пошагово видно, на чём «накрутилось».

#### Cron 5-го числа не сработал

**Проверить логи**:
```bash
docker logs sales-forecast-app 2>&1 | grep -i "bonus_auto_calc\|monthly_bonus"
```

В норме должна быть запись:
```
"Background scheduler started - ... Bonus auto-calc 5th-of-month 5:00"
```
И при срабатывании:
```
"Monthly bonus auto-calc started for 2026-04"
"Monthly bonus auto-calc finished: 17 calculations created"
```

Если scheduler не стартует — ошибка в `app/main.py` lifespan, проверить весь старт контейнера.

#### Pytest не находит тесты в production-контейнере

См. FAQ выше. Кратко: `tests/` не в образе, нужно `docker cp tests sales-forecast-app:/app/tests` и `pip install pytest`.

#### Schema validation error при создании схемы

`POST /api/bonus/schemes` возвращает 422 — Pydantic-валидация config провалилась. Причины:
- Лишнее поле в config (`extra="forbid"`)
- Поле `from`/`to` в грейдах должно сериализоваться через `populate_by_name=True` — на входе ожидается `from`, не `from_`
- `revenue_source` не зарегистрирован в `DataSourceRegistry` (опечатка в коде источника)

Проверить список валидных источников: `GET /api/bonus/config/data-sources`.

### Smoke-чеки health-системы

Запускать после каждого деплоя:

```bash
TOKEN=$(grep '^API_TOKEN' .env.prod | cut -d= -f2-)

# 1. API живой
curl -fsS https://aqniet.site/health

# 2. Bonus router зарегистрирован
curl -fsS -H "Authorization: Bearer $TOKEN" \
  https://aqniet.site/api/bonus/config/calculation-models | jq 'length'  # должно быть 5

# 3. Все 19 источников зарегистрированы
curl -fsS -H "Authorization: Bearer $TOKEN" \
  https://aqniet.site/api/bonus/config/data-sources | jq 'length'  # должно быть 19

# 4. Схемы существуют
curl -fsS -H "Authorization: Bearer $TOKEN" \
  https://aqniet.site/api/bonus/schemes | jq 'length'  # должно быть 56+

# 5. Scheduler зарегистрировал задачу
docker logs sales-forecast-app 2>&1 | grep -c "Bonus auto-calc"  # должно быть >= 1
```

### SQL-аудит наполненности

Запустить раз в неделю / перед запуском cron:

```sql
-- Локации без assignment
SELECT d.id, d.name FROM departments d
WHERE NOT EXISTS (
  SELECT 1 FROM bonus_employee_assignment a
  WHERE a.department_id = d.id AND a.effective_to IS NULL
)
AND EXISTS (SELECT 1 FROM bonus_scheme s WHERE s.department_id = d.id AND s.effective_to IS NULL);

-- Локации без плана за период
SELECT d.id, d.name FROM departments d
JOIN bonus_scheme s ON s.department_id = d.id AND s.effective_to IS NULL
WHERE NOT EXISTS (
  SELECT 1 FROM bonus_monthly_plan p
  WHERE p.department_id = d.id AND p.metric = 'sales'
    AND p.year = 2026 AND p.month = 4
);

-- KPI без значения за период
SELECT d.name, k.code FROM departments d
CROSS JOIN bonus_kpi_definition k
WHERE k.code IN ('manual_audit','manual_kitchen_audit','manual_profitability','hr_staffing_percent')
  AND NOT EXISTS (
    SELECT 1 FROM bonus_manual_kpi m
    WHERE m.department_id = d.id AND m.kpi_code = k.code
      AND m.period_year = 2026 AND m.period_month = 4
  );

-- Расчёты со странными суммами
SELECT id, employee_id, final_bonus FROM bonus_calculation
WHERE period_year = 2026 AND period_month = 4 AND status = 'draft'
  AND (final_bonus = 0 OR final_bonus > 500000)
ORDER BY final_bonus DESC;
```

---

## 16. Снапшот текущего состояния production-данных

**На дату**: 2026-04-29

### Справочники (заполнены seeds)

| Таблица | Записей | Статус |
|---|---|---|
| `bonus_company` | 4 | ✅ ТОО Sandyq Astana, Sandyq Almaty, Sandyq Turkestan, Tary |
| `bonus_position` | 21 | ✅ с маппингом на iiko-роли |
| `bonus_kpi_definition` | 12 | ✅ |
| `bonus_scheme` | 56 | ✅ для 10 локаций (без `Sandyq Kainar`/`Tary Kainar`) |
| `bonus_team` | 3 | ✅ KITCHEN для Sandyq Astana, Sandyq Almaty, Tary Ayusai |
| `bonus_team_position` | 63 | ✅ 3 команды × 21 слот |

### Эксплуатационные данные (требуют ручного заполнения перед боевым стартом)

| Таблица | Записей | Что есть | Что нужно |
|---|---|---|---|
| `bonus_employee_assignment` | 18 | только официанты Sandyq Astana | для всех 10 локаций × всех должностей × ~1500 сотрудников |
| `bonus_monthly_plan` | 1 | один `sales`-план за апрель 2026 | для всех 10 локаций × минимум 12 месяцев × `sales` (опционально `shifts_norm`, `profitability`) |
| `bonus_manual_kpi` | 0–N (зависит от ввода) | пусто либо тестовые данные | ежемесячно: `manual_audit`, `manual_kitchen_audit`, `manual_profitability`, `hr_staffing_percent`, и временно — `crm_*` для каждой локации |

### Расчёты

| Период | Статус | Кол-во | Сумма пула |
|---|---|---|---|
| 2026-04 | `superseded` | 17 | 0 (старые черновики) |
| 2026-04 | `draft` | 17 | 4 117 312 KZT |

Все 17 расчётов — официанты Sandyq Astana. Других локаций пока нет.

### Известные пробелы по источникам данных

| Источник | Статус | Влияние |
|---|---|---|
| `iiko_personal_ready_products_with_discount` | заглушка → 0 | бариста по `combined_products` получают 0 |
| `iiko_personal_prepared_products_with_discount` | заглушка → 0 | то же |
| `tco_shifts` | аппроксимация через `sales_by_waiter` | KITCHEN/кассиры/хосты считаются с `worked=0` → бонус 0 |
| `crm_*` (4 источника) | заглушка → 0 | KPI отзывов всегда 0% (или 100% для `lower_is_better`) |
| `iiko_revenue_with_discount` (location-level) | использует `sales_summary.total_sales` без скидки | для менеджеров завышение на размер скидок |
| `Sandyq Kainar`, `Tary Kainar` | нет в `departments` | seeds пропускают, бонус не считается |

### Интерпретация для бизнеса

Текущая система **готова считать бонусы только для официантов и кассиров на тех локациях, где iiko-выручка по сотруднику есть в `sales_by_waiter`**. Все остальные роли (KITCHEN, бариста, хосты, частично менеджеры) либо посчитаются в 0, либо некорректно — до интеграций TCO/CRM/iiko-categories.

**До 5 мая 2026** рекомендуется:
- либо отключить cron `monthly_bonus_auto_calc` и считать только Sandyq Astana вручную через UI,
- либо за 3-4 дня закрыть `12.0` чек-лист хотя бы для официантов всех 10 локаций (это даст осмысленный пилот без KITCHEN/бариста).

---

## Релевантные файлы

| Что | Где |
|---|---|
| Backend пакет | `app/bonus/` |
| Миграция | `migrations/007_bonus_core.sql` |
| Frontend страницы | `frontend/src/pages/bonus-*.tsx` |
| Tests | `tests/bonus/` |
| Эта документация | `docs/BONUS_SYSTEM_GUIDE.md` |
| Session log реализации | `docs/SESSION_LOG_Bonus_Subsystem_Integration_2026-04-29_20-01.md` |
| Оригинальная спецификация | `bonus_service/bonus_docs/` (00-context до 10-testing) |
| Исходные .docx от заказчика | `bonus_service/Документы по расчету/` (10 файлов KPI 2026) |
| Краткая справка для разработчика | Раздел «Bonus Subsystem» в `CLAUDE.md` |

# 06. REST API Specification

Все эндпоинты под `/api/v1`. Аутентификация — JWT (Bearer).  
Ответы — JSON с UTF-8.  
Ошибки — стандартный `{detail: "..."}` или Pydantic `{detail: [{loc, msg, type}]}`.

## Локации и должности

### `GET /api/v1/companies`
Список юрлиц.

### `GET /api/v1/locations`
Список локаций. Query: `?company_code=sandyq_kainar&active=true`

### `GET /api/v1/locations/{code}`
Детали локации со списком всех её схем и команд.

### `GET /api/v1/positions`
Справочник должностей.

---

## Команды (подразделения)

### `GET /api/v1/teams?location_code=sandyq_astana`
Список команд локации.

### `POST /api/v1/teams`
Создать команду.
```json
{
  "location_code": "sandyq_astana",
  "code": "kitchen",
  "name": "Кухня",
  "description": "Все сотрудники кухни"
}
```

### `GET /api/v1/teams/{team_id}/positions`
Список слотов команды (на текущую дату).
```json
[
  {"slot": "chef", "display_name": "Шеф-повар", "weight": 0.0013, "position": "chef"},
  {"slot": "sous_chef_1", "display_name": "Су-шеф 1", "weight": 0.0009, "position": "sous_chef"}
]
```

### `POST /api/v1/teams/{team_id}/positions`
Добавить слот.
```json
{
  "slot": "junior_cook_3",
  "display_name": "Младший повар 3",
  "position_code": "junior_cook",
  "weight": 0.0003,
  "effective_from": "2026-05-01"
}
```

### `PATCH /api/v1/teams/{team_id}/positions/{slot}`
Изменить слот = создать новую версию (старая закрывается).
```json
{
  "weight": 0.0005,
  "effective_from": "2026-06-01"
}
```

---

## Схемы расчёта

### `GET /api/v1/schemes`
Query: `?location_code=sandyq_astana&position_code=manager&active_on=2026-04-15`

```json
[
  {
    "id": 12,
    "location_code": "sandyq_astana",
    "position_code": "manager",
    "team_code": null,
    "calculation_model": "revenue_percent_by_kpi",
    "version": 2,
    "effective_from": "2026-03-01",
    "effective_to": null,
    "config": {...}
  }
]
```

### `GET /api/v1/schemes/{id}`
Полные детали схемы + историю версий.

### `POST /api/v1/schemes`
Создать схему.
```json
{
  "location_code": "sandyq_astana",
  "position_code": "manager",
  "calculation_model": "revenue_percent_by_kpi",
  "config": {...},
  "effective_from": "2026-05-01",
  "notes": "Изменили грейды по решению совета"
}
```
**Эффект:** если есть активная схема, она закрывается на `effective_from - 1 день`. Создаётся новая `version + 1`.  
**Валидация:** config валидируется через Pydantic-схему модели.

### `PATCH /api/v1/schemes/{id}`
Изменить notes/effective_to. Сам config менять нельзя — только через POST новой версии.

### `POST /api/v1/schemes/{id}/validate`
Проверить config без сохранения.

---

## Сотрудники и назначения

### `GET /api/v1/employees?location_code=...`
Список сотрудников.

### `POST /api/v1/employees`
Создать сотрудника.

### `POST /api/v1/employees/{id}/assignments`
Назначить на должность (или слот команды).
```json
{
  "location_code": "sandyq_astana",
  "position_code": "sous_chef",
  "team_code": "kitchen",
  "team_position_slot": "sous_chef_1",
  "employment_type": "permanent",
  "base_salary": 250000,
  "effective_from": "2026-04-01"
}
```

---

## KPI Definitions

### `GET /api/v1/kpi-definitions`
Список всех KPI (справочник).

### `POST /api/v1/kpi-definitions`
Создать новый KPI.

### `POST /api/v1/manual-kpi`
Ручной ввод значения KPI за период.
```json
{
  "location_code": "sandyq_astana",
  "kpi_code": "audit",
  "year": 2026,
  "month": 4,
  "fact_value": 87.5,
  "document_ref": "Акт аудита №42 от 02.05.2026"
}
```

### `GET /api/v1/manual-kpi?location_code=...&year=2026&month=4`
Получить введённые KPI за период.

---

## Месячные планы

### `GET /api/v1/monthly-plans?location_code=...&year=2026`
План продаж и рентабельности по месяцам.

### `POST /api/v1/monthly-plans`
Залить план (можно массово — массивом).
```json
[
  {"location_code": "sandyq_astana", "metric": "sales", "year": 2026, "month": 4, "target_value": 50602310},
  {"location_code": "sandyq_astana", "metric": "profitability", "year": 2026, "month": 4, "target_value": 40}
]
```

---

## Расчёты

### `POST /api/v1/calculations/run`
Запустить расчёт за период.
```json
{
  "location_code": "sandyq_astana",
  "year": 2026,
  "month": 4,
  "scope": "all",            // "all" | "position:manager" | "team:kitchen" | "employee:42"
  "force_recalculate": false  // даже если уже есть draft
}
```
**Ответ (асинхронно):**
```json
{
  "job_id": "calc-2026-04-sandyq-astana-abc123",
  "status": "running",
  "started_at": "2026-05-01T10:00:00Z"
}
```

### `GET /api/v1/calculations/jobs/{job_id}`
Статус задачи.

### `GET /api/v1/calculations`
Query: `?location_code=...&year=2026&month=4&status=draft`
```json
[
  {
    "id": 1234,
    "employee_id": 42,
    "employee_name": "Алихан Темиров",
    "position": "Официант",
    "period": "2026-04",
    "status": "draft",
    "final_bonus": 112500,
    "calculated_at": "2026-05-01T10:01:23Z"
  }
]
```

### `GET /api/v1/calculations/{id}`
Полные детали + breakdown.
```json
{
  "id": 1234,
  "employee": {...},
  "scheme_used": {"id": 12, "version": 2, "snapshot": {...}},
  "kpi_values": [
    {"code": "sales_plan", "fact": 2500000, "target": 50602310, "percent": 100, "weight": 1},
    {"code": "individual_negative_reviews", "fact": 0, "target": 3, "percent": 100, "weight": 1},
    {"code": "margin_share", "fact": 45, "target": 40, "percent": 100, "weight": 1}
  ],
  "overall_kpi_percent": 100,
  "applied_grade": {"from": 98, "to": 100, "rate": 0.045},
  "revenue_used": 2500000,
  "shifts": {"worked": 22, "norm": 22, "ratio": 1.0},
  "base_bonus": 112500,
  "penalties": [],
  "final_bonus": 112500,
  "breakdown": {
    "step_1": "kpi_fetched",
    "step_2": "overall_kpi=100%",
    "step_3": "grade=98-100% → rate=4.5%",
    "step_4": "revenue=2,500,000 KZT",
    "step_5": "bonus = 2,500,000 × 0.045 = 112,500 KZT",
    "step_6": "no shift proration applied? false → ratio 1.0",
    "step_7": "no penalties",
    "final": "112,500 KZT"
  }
}
```

### `POST /api/v1/calculations/{id}/penalties`
Добавить удержание.
```json
{
  "reason_code": "discipline",
  "reason_text": "Опоздания 3 раза в апреле",
  "penalty_percent": 20,
  "document_ref": "Служебная записка №15"
}
```

### `POST /api/v1/calculations/{id}/approve`
Перевести в статус `approved` (требует роль `admin` или `finance`).

### `POST /api/v1/calculations/{id}/reject`
```json
{"reason": "Неверные данные по выручке"}
```

### `GET /api/v1/calculations/export?location_code=...&year=2026&month=4&format=xlsx`
Выгрузка в Excel/CSV для бухгалтерии.

---

## Отчёты и аналитика

### `GET /api/v1/reports/summary?year=2026&month=4`
Сводка по всем локациям: сколько сотрудников, общая сумма бонусов, средний бонус.

### `GET /api/v1/reports/employee/{id}/history?from=2025-01&to=2026-04`
История бонусов сотрудника (для дашборда сотрудника).

### `GET /api/v1/reports/scheme-changes?from=2026-01-01`
Все изменения схем за период (аудит).

---

## Системные

### `GET /api/v1/health`
```json
{"status": "ok", "version": "1.0.0", "db": "ok"}
```

### `GET /api/v1/config/calculation-models`
Список зарегистрированных моделей расчёта.

### `GET /api/v1/config/data-sources`
Список зарегистрированных источников данных.

---

## Аутентификация

```
POST /api/v1/auth/login {username, password}
→ {access_token, refresh_token, expires_in}

POST /api/v1/auth/refresh {refresh_token}
→ {access_token, expires_in}
```

Заголовок: `Authorization: Bearer <token>`

## Роли

| Роль | Что может |
|---|---|
| `viewer` | Только GET (просмотр) |
| `hr` | + ручной ввод KPI, запуск расчёта, добавление штрафов |
| `finance` | + approval расчётов, экспорт |
| `admin` | + управление схемами, командами, сотрудниками |
| `superadmin` | + управление пользователями, ролями |

## OpenAPI

FastAPI автоматически генерит:
- `/docs` — Swagger UI
- `/redoc` — ReDoc
- `/openapi.json` — спецификация

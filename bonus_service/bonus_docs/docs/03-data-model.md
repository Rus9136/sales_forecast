# 03. Модель данных

## Полная схема (ER)

```
company ──< location ──< team ──< team_position
              │                       │
              │                       └─< employee_assignment
              │                                │
              ├─< bonus_scheme >── position    │
              │       │                        │
              │       └─< scheme_kpi >── kpi_definition
              │                                │
              └─< monthly_plan                 │
                                               │
employee ──────────────────────────────────────┘
   │
   └─< bonus_calculation >── bonus_scheme (snapshot)
            │
            ├─< calculation_kpi_value
            └─< calculation_penalty
```

## Таблицы

### `company` — Юрлицо

```sql
CREATE TABLE company (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(50) UNIQUE NOT NULL,    -- 'sandyq_kainar'
    name            VARCHAR(200) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `location` — Ресторан/точка

```sql
CREATE TABLE location (
    id                  SERIAL PRIMARY KEY,
    company_id          INTEGER NOT NULL REFERENCES company(id),
    code                VARCHAR(50) UNIQUE NOT NULL,   -- 'sandyq_astana'
    name                VARCHAR(200) NOT NULL,
    iiko_department_id  VARCHAR(100),                  -- маппинг на iiko
    timezone            VARCHAR(50) NOT NULL DEFAULT 'Asia/Almaty',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_location_company ON location(company_id);
```

### `position` — Должность

```sql
CREATE TABLE position (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(50) UNIQUE NOT NULL,    -- 'manager', 'cashier', 'chef'
    name        VARCHAR(200) NOT NULL,          -- 'Менеджер', 'Кассир', 'Шеф-повар'
    category    VARCHAR(50) NOT NULL,           -- 'management', 'service', 'kitchen', 'bar'
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);
```

### `team` — Подразделение/команда

```sql
CREATE TABLE team (
    id              SERIAL PRIMARY KEY,
    location_id     INTEGER NOT NULL REFERENCES location(id),
    code            VARCHAR(50) NOT NULL,           -- 'kitchen', 'bar_team'
    name            VARCHAR(200) NOT NULL,          -- 'Кухня', 'Бар-команда'
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (location_id, code)
);

CREATE INDEX idx_team_location ON team(location_id);
```

### `team_position` — Слоты команды (с весом для распределения)

```sql
CREATE TABLE team_position (
    id                      SERIAL PRIMARY KEY,
    team_id                 INTEGER NOT NULL REFERENCES team(id),
    position_id             INTEGER NOT NULL REFERENCES position(id),
    slot                    VARCHAR(100) NOT NULL,        -- 'chef', 'sous_chef_1', 'sous_chef_2'
    display_name            VARCHAR(200),                 -- 'Су-шеф 1', 'Повар горячего цеха 1'
    distribution_weight     DECIMAL(8, 6) NOT NULL,       -- 0.001300 (=0.13%)
    sort_order              INTEGER NOT NULL DEFAULT 0,
    
    effective_from          DATE NOT NULL,
    effective_to            DATE,                          -- NULL = действует
    
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (team_id, slot, effective_from)
);

CREATE INDEX idx_team_position_team ON team_position(team_id);
CREATE INDEX idx_team_position_active ON team_position(team_id, effective_from, effective_to);
```

### `kpi_definition` — Справочник KPI

```sql
CREATE TABLE kpi_definition (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(80) UNIQUE NOT NULL,
    name                VARCHAR(200) NOT NULL,
    description         TEXT,
    data_source_code    VARCHAR(80) NOT NULL,             -- 'iiko_sales_plan', 'manual_audit'
    direction           VARCHAR(30) NOT NULL,             -- 'higher_is_better' | 'lower_is_better' | 'binary'
    default_target      DECIMAL(12, 4),                   -- если константный
    target_metric       VARCHAR(80),                      -- 'monthly_plan_sales' если зависит от месяца
    cap_at_100_percent  BOOLEAN NOT NULL DEFAULT TRUE,    -- обрезать выполнение по 100%?
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    
    CHECK (direction IN ('higher_is_better', 'lower_is_better', 'binary'))
);
```

### `bonus_scheme` — Схема расчёта бонуса (главная сущность!)

```sql
CREATE TABLE bonus_scheme (
    id                  SERIAL PRIMARY KEY,
    location_id         INTEGER NOT NULL REFERENCES location(id),
    
    -- Целевая сущность: либо должность (индивидуальная схема), либо команда (коллективная)
    position_id         INTEGER REFERENCES position(id),
    team_id             INTEGER REFERENCES team(id),
    
    calculation_model   VARCHAR(50) NOT NULL,    -- 'flat_by_kpi', etc.
    
    config              JSONB NOT NULL,           -- параметры модели
    
    effective_from      DATE NOT NULL,
    effective_to        DATE,                     -- NULL = действует
    version             INTEGER NOT NULL DEFAULT 1,
    
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          VARCHAR(100),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Должна быть указана либо позиция, либо команда (но не обе и не ни одна)
    CHECK (
        (position_id IS NOT NULL AND team_id IS NULL) OR
        (position_id IS NULL AND team_id IS NOT NULL)
    )
);

-- Индексы для поиска активной схемы
CREATE INDEX idx_scheme_position_active ON bonus_scheme(location_id, position_id, effective_from, effective_to);
CREATE INDEX idx_scheme_team_active ON bonus_scheme(location_id, team_id, effective_from, effective_to);

-- Не должно быть пересекающихся периодов для одной (location + position) или (location + team)
-- (реализуется через exclusion constraint или триггер)
```

### `monthly_plan` — Планы по месяцам (продажи, рентабельность)

```sql
CREATE TABLE monthly_plan (
    id              SERIAL PRIMARY KEY,
    location_id     INTEGER NOT NULL REFERENCES location(id),
    metric          VARCHAR(80) NOT NULL,         -- 'sales', 'profitability'
    year            SMALLINT NOT NULL,
    month           SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    target_value    DECIMAL(14, 2) NOT NULL,      -- 61031035.00 (план продаж в тг) или 38.00 (% рентабельности)
    
    UNIQUE (location_id, metric, year, month)
);

CREATE INDEX idx_monthly_plan_lookup ON monthly_plan(location_id, metric, year, month);
```

### `employee` — Сотрудник

```sql
CREATE TABLE employee (
    id                  SERIAL PRIMARY KEY,
    iiko_id             VARCHAR(100),
    tco_id              VARCHAR(100),
    full_name           VARCHAR(200) NOT NULL,
    iin                 VARCHAR(12),                 -- ИИН (Казахстан)
    phone               VARCHAR(20),
    email               VARCHAR(200),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    hired_at            DATE,
    fired_at            DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `employee_assignment` — Назначение сотрудника на позицию/слот

```sql
CREATE TABLE employee_assignment (
    id                  SERIAL PRIMARY KEY,
    employee_id         INTEGER NOT NULL REFERENCES employee(id),
    location_id         INTEGER NOT NULL REFERENCES location(id),
    position_id         INTEGER NOT NULL REFERENCES position(id),
    
    -- Если сотрудник в команде с распределением:
    team_id             INTEGER REFERENCES team(id),
    team_position_slot  VARCHAR(100),                   -- 'sous_chef_1'
    
    employment_type     VARCHAR(30) NOT NULL DEFAULT 'permanent',  -- 'permanent', 'probation', 'trial'
    probation_until     DATE,                           -- последний день испыт. срока (включительно)
    base_salary         DECIMAL(14, 2),                 -- оклад
    
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    
    -- Если есть team_id, должен быть team_position_slot
    CHECK ((team_id IS NULL) = (team_position_slot IS NULL))
);

CREATE INDEX idx_assignment_employee_active ON employee_assignment(employee_id, effective_from, effective_to);
CREATE INDEX idx_assignment_location ON employee_assignment(location_id, effective_from, effective_to);
CREATE INDEX idx_assignment_team ON employee_assignment(team_id, effective_from, effective_to);
```

### `bonus_calculation` — Результат расчёта (с полным снапшотом)

```sql
CREATE TABLE bonus_calculation (
    id                          SERIAL PRIMARY KEY,
    
    -- Кто, где, когда
    employee_id                 INTEGER NOT NULL REFERENCES employee(id),
    location_id                 INTEGER NOT NULL REFERENCES location(id),
    period_year                 SMALLINT NOT NULL,
    period_month                SMALLINT NOT NULL,
    
    -- Какая схема использовалась (снапшот)
    scheme_id                   INTEGER NOT NULL REFERENCES bonus_scheme(id),
    scheme_version              INTEGER NOT NULL,
    scheme_config_snapshot      JSONB NOT NULL,
    
    -- Если коллективный расчёт
    team_id                     INTEGER REFERENCES team(id),
    team_position_slot          VARCHAR(100),
    
    -- KPI значения на момент расчёта (снапшот)
    kpi_values                  JSONB,           -- [{"code": "...", "fact": ..., "target": ..., "percent": ...}]
    overall_kpi_percent         DECIMAL(7, 4),   -- средний % KPI
    
    -- Грейд и применённый коэффициент
    applied_grade_from          DECIMAL(5, 2),
    applied_grade_to            DECIMAL(5, 2),
    applied_coefficient         DECIMAL(14, 6),  -- может быть тенге (170000) или доля (0.045)
    coefficient_type            VARCHAR(20),     -- 'fixed_amount' | 'percent'
    
    -- Выручка и смены
    revenue_used                DECIMAL(14, 2),
    revenue_source_used         VARCHAR(80),
    shifts_worked               DECIMAL(6, 2),   -- может быть дробным (4.5 смены если по часам)
    shifts_norm                 DECIMAL(6, 2),
    shifts_proration_applied    BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Расчёт
    base_bonus                  DECIMAL(14, 2) NOT NULL,
    penalties_amount            DECIMAL(14, 2) NOT NULL DEFAULT 0,
    final_bonus                 DECIMAL(14, 2) NOT NULL,
    
    -- Полная разбивка (для UI и аудита)
    breakdown                   JSONB NOT NULL,
    
    -- Статус
    status                      VARCHAR(30) NOT NULL DEFAULT 'draft',
    -- 'draft' | 'review' | 'approved' | 'paid' | 'rejected' | 'recalculated'
    
    -- Аудит
    calculated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    calculated_by               VARCHAR(100),
    approved_at                 TIMESTAMPTZ,
    approved_by                 VARCHAR(100),
    paid_at                     TIMESTAMPTZ,
    notes                       TEXT,
    
    UNIQUE (employee_id, period_year, period_month, status) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX idx_calc_period ON bonus_calculation(location_id, period_year, period_month);
CREATE INDEX idx_calc_employee ON bonus_calculation(employee_id, period_year, period_month);
CREATE INDEX idx_calc_status ON bonus_calculation(status, period_year, period_month);
```

### `calculation_penalty` — Удержания/штрафы

```sql
CREATE TABLE calculation_penalty (
    id                  SERIAL PRIMARY KEY,
    calculation_id      INTEGER NOT NULL REFERENCES bonus_calculation(id) ON DELETE CASCADE,
    reason_code         VARCHAR(80) NOT NULL,    -- 'discipline', 'data_falsification', 'other'
    reason_text         TEXT NOT NULL,
    penalty_percent     DECIMAL(5, 2),           -- % удержания (0-100)
    penalty_amount      DECIMAL(14, 2) NOT NULL, -- абсолютная сумма
    document_ref        VARCHAR(200),            -- ссылка на служебную записку
    applied_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by          VARCHAR(100)
);

CREATE INDEX idx_penalty_calc ON calculation_penalty(calculation_id);
```

### `manual_kpi_input` — Ручной ввод KPI (аудит, укомплектованность)

```sql
CREATE TABLE manual_kpi_input (
    id                  SERIAL PRIMARY KEY,
    location_id         INTEGER NOT NULL REFERENCES location(id),
    kpi_code            VARCHAR(80) NOT NULL,
    period_year         SMALLINT NOT NULL,
    period_month        SMALLINT NOT NULL,
    fact_value          DECIMAL(14, 4) NOT NULL,
    notes               TEXT,
    document_ref        VARCHAR(200),
    entered_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    entered_by          VARCHAR(100),
    
    UNIQUE (location_id, kpi_code, period_year, period_month)
);
```

### `audit_log` — Аудит изменений

```sql
CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    entity_type     VARCHAR(80) NOT NULL,    -- 'bonus_scheme', 'team_position', etc.
    entity_id       INTEGER NOT NULL,
    action          VARCHAR(20) NOT NULL,    -- 'create', 'update', 'delete', 'recalculate'
    old_values      JSONB,
    new_values      JSONB,
    actor           VARCHAR(100) NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address      INET,
    user_agent      TEXT
);

CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id, occurred_at);
CREATE INDEX idx_audit_actor ON audit_log(actor, occurred_at);
```

## Особенности и инварианты

### Версионирование
- `bonus_scheme` — закрывается `effective_to`, создаётся новая запись с новым `effective_from`
- `team_position` — то же самое (изменение веса слота = новая строка)
- `employee_assignment` — то же (перевод сотрудника = закрытие старой + создание новой)

### Резолвинг активной записи
```sql
-- Активная схема для пары (location, position) на дату D:
SELECT * FROM bonus_scheme
WHERE location_id = :loc 
  AND position_id = :pos
  AND effective_from <= :date
  AND (effective_to IS NULL OR effective_to >= :date);
```

### Запреты
- Нельзя пересечь периоды двух схем для одной комбинации (location, position) или (location, team)
- При расчёте за период всегда использовать ту схему, что была активна **на конец периода** (или на начало — определись и зафиксируй в `domain-rules.md`)

### Soft delete
- Ничего физически не удаляем
- Используем `is_active = false` для справочников
- Используем `effective_to = period_end` для версионируемых

## Маппинг JSON config (по моделям)

См. `docs/02-calculation-models.md` для примеров.

Валидация config — через Pydantic-схемы:
```python
class FlatByKpiConfig(BaseModel):
    kpis: list[KpiConfig]
    grades: list[FlatGrade]
    below_threshold_bonus: Decimal = Decimal(0)
    apply_shifts_proration: bool = False
```

При сохранении схемы (POST/PUT `/schemes`) валидируем config через схему соответствующей модели.

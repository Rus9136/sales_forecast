-- Migration: Bonus subsystem core tables
-- Version: 007
-- Date: 2026-04-29
-- Description: Tables for the bonus calculation engine integrated with existing
--              departments/employees/sales_by_waiter. All tables prefixed with bonus_*.

-- ---------------------------------------------------------------------------
-- 1. bonus_company — Юрлица (привязка к departments через company_id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_company (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(50) UNIQUE NOT NULL,
    name        VARCHAR(200) NOT NULL,
    bin         VARCHAR(20),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES bonus_company(id);

CREATE INDEX IF NOT EXISTS idx_departments_company ON departments(company_id);

-- ---------------------------------------------------------------------------
-- 2. bonus_position — Должности с маппингом на iiko-роли
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_position (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(50) UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    iiko_role_code  VARCHAR(50),
    iiko_role_name  VARCHAR(200),
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (category IN ('management', 'service', 'kitchen', 'bar', 'cashier', 'other'))
);

CREATE INDEX IF NOT EXISTS idx_bonus_position_iiko_role ON bonus_position(iiko_role_code);

-- ---------------------------------------------------------------------------
-- 3. bonus_team — Команды/подразделения внутри локации (KITCHEN и т.п.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_team (
    id              SERIAL PRIMARY KEY,
    department_id   UUID NOT NULL REFERENCES departments(id),
    code            VARCHAR(50) NOT NULL,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (department_id, code)
);

CREATE INDEX IF NOT EXISTS idx_bonus_team_department ON bonus_team(department_id);

-- ---------------------------------------------------------------------------
-- 4. bonus_team_position — Слоты команд (с весом и версионированием)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_team_position (
    id                      SERIAL PRIMARY KEY,
    team_id                 INTEGER NOT NULL REFERENCES bonus_team(id) ON DELETE CASCADE,
    position_id             INTEGER NOT NULL REFERENCES bonus_position(id),
    slot                    VARCHAR(100) NOT NULL,
    display_name            VARCHAR(200),
    distribution_weight     DECIMAL(8, 6) NOT NULL,
    sort_order              INTEGER NOT NULL DEFAULT 0,
    effective_from          DATE NOT NULL,
    effective_to            DATE,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, slot, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_bonus_team_position_team ON bonus_team_position(team_id);
CREATE INDEX IF NOT EXISTS idx_bonus_team_position_active
    ON bonus_team_position(team_id, effective_from, effective_to);

-- ---------------------------------------------------------------------------
-- 5. bonus_kpi_definition — Справочник KPI
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_kpi_definition (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(80) UNIQUE NOT NULL,
    name                VARCHAR(200) NOT NULL,
    description         TEXT,
    data_source_code    VARCHAR(80) NOT NULL,
    direction           VARCHAR(30) NOT NULL,
    default_target      DECIMAL(14, 4),
    target_metric       VARCHAR(80),
    cap_at_100_percent  BOOLEAN NOT NULL DEFAULT TRUE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (direction IN ('higher_is_better', 'lower_is_better', 'binary'))
);

-- ---------------------------------------------------------------------------
-- 6. bonus_monthly_plan — Планы продаж/рентабельности по месяцам
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_monthly_plan (
    id              SERIAL PRIMARY KEY,
    department_id   UUID NOT NULL REFERENCES departments(id),
    metric          VARCHAR(80) NOT NULL,
    year            SMALLINT NOT NULL,
    month           SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    target_value    DECIMAL(14, 2) NOT NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (department_id, metric, year, month)
);

CREATE INDEX IF NOT EXISTS idx_bonus_monthly_plan_lookup
    ON bonus_monthly_plan(department_id, metric, year, month);

-- ---------------------------------------------------------------------------
-- 7. bonus_employee_assignment — Назначение сотрудника на должность/слот
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_employee_assignment (
    id                  SERIAL PRIMARY KEY,
    employee_id         UUID NOT NULL REFERENCES employees(id),
    department_id       UUID NOT NULL REFERENCES departments(id),
    position_id         INTEGER NOT NULL REFERENCES bonus_position(id),
    team_id             INTEGER REFERENCES bonus_team(id),
    team_position_slot  VARCHAR(100),
    employment_type     VARCHAR(30) NOT NULL DEFAULT 'permanent',
    probation_until     DATE,
    base_salary         DECIMAL(14, 2),
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (employment_type IN ('permanent', 'probation', 'trial')),
    CHECK ((team_id IS NULL) = (team_position_slot IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_bonus_assignment_employee_active
    ON bonus_employee_assignment(employee_id, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS idx_bonus_assignment_department
    ON bonus_employee_assignment(department_id, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS idx_bonus_assignment_team
    ON bonus_employee_assignment(team_id, effective_from, effective_to);

-- ---------------------------------------------------------------------------
-- 8. bonus_scheme — Главная сущность: схема расчёта (location × position/team)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_scheme (
    id                  SERIAL PRIMARY KEY,
    department_id       UUID NOT NULL REFERENCES departments(id),
    position_id         INTEGER REFERENCES bonus_position(id),
    team_id             INTEGER REFERENCES bonus_team(id),
    calculation_model   VARCHAR(50) NOT NULL,
    config              JSONB NOT NULL,
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    version             INTEGER NOT NULL DEFAULT 1,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          VARCHAR(100),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (position_id IS NOT NULL AND team_id IS NULL) OR
        (position_id IS NULL AND team_id IS NOT NULL)
    ),
    CHECK (calculation_model IN (
        'flat_by_kpi',
        'revenue_percent_by_kpi',
        'revenue_direct',
        'combined_products',
        'team_revenue_by_kpi'
    ))
);

CREATE INDEX IF NOT EXISTS idx_bonus_scheme_position_active
    ON bonus_scheme(department_id, position_id, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS idx_bonus_scheme_team_active
    ON bonus_scheme(department_id, team_id, effective_from, effective_to);

-- ---------------------------------------------------------------------------
-- 9. bonus_manual_kpi — Ручной ввод KPI (аудит, отзывы, укомплектованность)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_manual_kpi (
    id              SERIAL PRIMARY KEY,
    department_id   UUID NOT NULL REFERENCES departments(id),
    kpi_code        VARCHAR(80) NOT NULL,
    period_year     SMALLINT NOT NULL,
    period_month    SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    fact_value      DECIMAL(14, 4) NOT NULL,
    notes           TEXT,
    document_ref    VARCHAR(200),
    entered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    entered_by      VARCHAR(100),
    UNIQUE (department_id, kpi_code, period_year, period_month)
);

CREATE INDEX IF NOT EXISTS idx_bonus_manual_kpi_lookup
    ON bonus_manual_kpi(department_id, period_year, period_month);

-- ---------------------------------------------------------------------------
-- 10. bonus_calculation — Результат расчёта со снапшотом
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_calculation (
    id                          SERIAL PRIMARY KEY,
    employee_id                 UUID NOT NULL REFERENCES employees(id),
    department_id               UUID NOT NULL REFERENCES departments(id),
    period_year                 SMALLINT NOT NULL,
    period_month                SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),

    scheme_id                   INTEGER NOT NULL REFERENCES bonus_scheme(id),
    scheme_version              INTEGER NOT NULL,
    scheme_config_snapshot      JSONB NOT NULL,

    team_id                     INTEGER REFERENCES bonus_team(id),
    team_position_slot          VARCHAR(100),

    kpi_values                  JSONB,
    overall_kpi_percent         DECIMAL(7, 4),

    applied_grade_from          DECIMAL(5, 2),
    applied_grade_to            DECIMAL(5, 2),
    applied_coefficient         DECIMAL(14, 6),
    coefficient_type            VARCHAR(20),

    revenue_used                DECIMAL(14, 2),
    revenue_source_used         VARCHAR(80),
    shifts_worked               DECIMAL(6, 2),
    shifts_norm                 DECIMAL(6, 2),
    shifts_proration_applied    BOOLEAN NOT NULL DEFAULT FALSE,

    base_bonus                  DECIMAL(14, 2) NOT NULL,
    penalties_amount            DECIMAL(14, 2) NOT NULL DEFAULT 0,
    final_bonus                 DECIMAL(14, 2) NOT NULL,

    breakdown                   JSONB NOT NULL,

    status                      VARCHAR(30) NOT NULL DEFAULT 'draft',

    calculated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    calculated_by               VARCHAR(100),
    approved_at                 TIMESTAMPTZ,
    approved_by                 VARCHAR(100),
    paid_at                     TIMESTAMPTZ,
    notes                       TEXT,

    CHECK (status IN ('draft', 'review', 'approved', 'paid', 'rejected', 'recalculated', 'superseded'))
);

CREATE INDEX IF NOT EXISTS idx_bonus_calc_period
    ON bonus_calculation(department_id, period_year, period_month);
CREATE INDEX IF NOT EXISTS idx_bonus_calc_employee
    ON bonus_calculation(employee_id, period_year, period_month);
CREATE INDEX IF NOT EXISTS idx_bonus_calc_status
    ON bonus_calculation(status, period_year, period_month);

-- Только один активный (draft/review/approved/paid) расчёт на сотрудника-период
CREATE UNIQUE INDEX IF NOT EXISTS uq_bonus_calc_active_per_employee_period
    ON bonus_calculation(employee_id, period_year, period_month)
    WHERE status IN ('draft', 'review', 'approved', 'paid');

-- ---------------------------------------------------------------------------
-- 11. bonus_calculation_penalty — Удержания/штрафы
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_calculation_penalty (
    id                  SERIAL PRIMARY KEY,
    calculation_id      INTEGER NOT NULL REFERENCES bonus_calculation(id) ON DELETE CASCADE,
    reason_code         VARCHAR(80) NOT NULL,
    reason_text         TEXT NOT NULL,
    penalty_percent     DECIMAL(5, 2),
    penalty_amount      DECIMAL(14, 2) NOT NULL,
    document_ref        VARCHAR(200),
    applied_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by          VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_bonus_penalty_calc
    ON bonus_calculation_penalty(calculation_id);

-- ---------------------------------------------------------------------------
-- Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE bonus_company IS 'Юрлица (Sandyq Kainar TOO, Sandyq Astana TOO, ...)';
COMMENT ON TABLE bonus_position IS 'Должности с маппингом на iiko-роли (employees.main_role_code)';
COMMENT ON TABLE bonus_team IS 'Команды внутри локации: KITCHEN, BAR_TEAM и т.п.';
COMMENT ON TABLE bonus_team_position IS 'Слоты команды с весом распределения (версионируется)';
COMMENT ON TABLE bonus_kpi_definition IS 'Справочник KPI с указанием data_source_code и направления';
COMMENT ON TABLE bonus_monthly_plan IS 'Помесячные планы продаж/рентабельности по локациям';
COMMENT ON TABLE bonus_employee_assignment IS 'Назначение сотрудника на должность (или слот команды)';
COMMENT ON TABLE bonus_scheme IS 'Схемы расчёта (department × position/team), версионируются через effective_from/to';
COMMENT ON TABLE bonus_manual_kpi IS 'Ручной ввод KPI (аудит, отзывы CRM, укомплектованность HR)';
COMMENT ON TABLE bonus_calculation IS 'Расчёт бонуса со снапшотом схемы, KPI и breakdown';
COMMENT ON TABLE bonus_calculation_penalty IS 'Удержания/штрафы, прикреплённые к расчёту';

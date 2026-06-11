-- Migration 028: Pricing weekly/monthly LLM reports (C4)
--
-- Хранит сгенерированные LLM сводки по ценообразованию за период.
-- scope='network' (department_id IS NULL) — сводка по сети; иначе по точке.
-- data — снимок собранных метрик (воспроизводимость), kpis — заголовочные
-- показатели, narrative — текст от LLM. Промпты редактируются через
-- ai_prompts (агенты PricingWeeklyReportAgent / PricingMonthlyReportAgent),
-- каждый вызов LLM логируется в ai_prompt_logs.

CREATE TABLE IF NOT EXISTS pricing_report (
    id              BIGSERIAL PRIMARY KEY,
    report_type     TEXT NOT NULL,                       -- 'weekly' | 'monthly'
    scope           TEXT NOT NULL DEFAULT 'network',     -- 'network' | 'department'
    department_id   UUID,                                -- NULL для network
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    data            JSONB NOT NULL,
    kpis            JSONB,
    narrative       TEXT,
    provider        TEXT NOT NULL DEFAULT 'claude',
    model           TEXT,
    status          TEXT NOT NULL DEFAULT 'ok',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pricing_report_type_created
    ON pricing_report (report_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pricing_report_dept
    ON pricing_report (department_id);
CREATE INDEX IF NOT EXISTS idx_pricing_report_period
    ON pricing_report (period_start, period_end);

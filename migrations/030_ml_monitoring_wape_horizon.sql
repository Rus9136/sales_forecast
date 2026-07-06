-- 030_ml_monitoring_wape_horizon.sql
-- ML_AUDIT_REPORT.md Фаза 1 (P0-6, P1-7): стратификация качества прогноза
-- по горизонту + персист дневных агрегатов мониторинга.
--
-- 1) forecasts.horizon_days — на каком горизонте (дней вперёд) был сделан
--    прогноз. Раньше UNIQUE(branch_id, forecast_date) затирал t+7-прогноз
--    более поздним t+1 — деградацию по горизонту нельзя было измерить.
-- 2) forecast_accuracy_log.horizon_days — то же для оценённых пар факт/прогноз.
-- 3) model_performance_metrics — дневные агрегаты (_save_daily_metrics был
--    заглушкой «For now, just log»); horizon_days=0 означает «все горизонты».

BEGIN;

-- 1. forecasts
ALTER TABLE forecasts
    ADD COLUMN IF NOT EXISTS horizon_days INTEGER NOT NULL DEFAULT 1;

DROP INDEX IF EXISTS ix_forecasts_branch_date;
CREATE UNIQUE INDEX IF NOT EXISTS ix_forecasts_branch_date_horizon
    ON forecasts (branch_id, forecast_date, horizon_days);

-- 2. forecast_accuracy_log
ALTER TABLE forecast_accuracy_log
    ADD COLUMN IF NOT EXISTS horizon_days INTEGER NOT NULL DEFAULT 1;

DROP INDEX IF EXISTS ix_accuracy_branch_date;
CREATE UNIQUE INDEX IF NOT EXISTS ix_accuracy_branch_date_horizon
    ON forecast_accuracy_log (branch_id, forecast_date, horizon_days);

-- 3. Дневные агрегаты качества.
-- Внимание: таблица model_performance_metrics из миграции 002 существовала,
-- но в неё НИКОГДА не писали (_save_daily_metrics был заглушкой) — 0 строк
-- на проде на 2026-07-06. Пересоздаём под новую схему (headline WAPE +
-- разрез по горизонту вместо model_version_id-ключа).
DROP TABLE IF EXISTS model_performance_metrics;
CREATE TABLE model_performance_metrics (
    id            SERIAL PRIMARY KEY,
    metric_date   DATE NOT NULL,
    horizon_days  INTEGER NOT NULL DEFAULT 0,  -- 0 = все горизонты вместе
    n_predictions INTEGER NOT NULL,
    wape          DOUBLE PRECISION,
    mape          DOUBLE PRECISION,
    median_ape    DOUBLE PRECISION,
    mae           DOUBLE PRECISION,
    bias_pct      DOUBLE PRECISION,
    alerts        JSONB,
    model_version VARCHAR,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_perf_metrics_date_horizon UNIQUE (metric_date, horizon_days)
);

CREATE INDEX IF NOT EXISTS ix_perf_metrics_date ON model_performance_metrics (metric_date);

COMMIT;

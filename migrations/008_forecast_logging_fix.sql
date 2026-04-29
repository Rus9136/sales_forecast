-- 008: enable forecast logging
--
-- Problem: forecasts table is empty because:
--   1. forecast() agent never writes to it
--   2. FK to legacy branches table doesn't allow modern department_id (UUID)
--   3. No UNIQUE on (branch_id, forecast_date) to support UPSERT
--
-- Fix: drop legacy FK, add UNIQUE for UPSERT semantics.
-- Same for forecast_accuracy_log.

ALTER TABLE forecasts DROP CONSTRAINT IF EXISTS forecasts_branch_id_fkey;

ALTER TABLE forecast_accuracy_log
    DROP CONSTRAINT IF EXISTS forecast_accuracy_log_branch_id_fkey;

CREATE UNIQUE INDEX IF NOT EXISTS ix_forecasts_branch_date
    ON forecasts (branch_id, forecast_date);

CREATE UNIQUE INDEX IF NOT EXISTS ix_accuracy_branch_date
    ON forecast_accuracy_log (branch_id, forecast_date);

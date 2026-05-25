-- Migration: Add iiko_source_domain to departments
-- Version: 013
-- Date: 2026-05-25
-- Description: Track which iiko server (sandy-co-co / madlen-group-so / ...) each
--              department came from. This is the only reliable signal for separating
--              Сандык vs Мадлен ассортименты — `taxpayer_id_number` is empty for 47/91
--              departments and was unreliable for company resolution.
--
-- The column is added as NULLABLE here. Existing 91 rows are populated by the
-- one-shot script `scripts/backfill_iiko_source_domain.py`, which then flips the
-- column to NOT NULL inside the same transaction. After this migration the loader
-- (`app/services/iiko_department_loader.py`) keeps the column filled on every sync.

BEGIN;

ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS iiko_source_domain TEXT;

CREATE INDEX IF NOT EXISTS idx_departments_iiko_source
    ON departments(iiko_source_domain);

COMMIT;

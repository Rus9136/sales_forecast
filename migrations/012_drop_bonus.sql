-- Migration: Drop bonus subsystem
-- Version: 012
-- Date: 2026-05-25
-- Description: Removes the entire bonus calculation subsystem (11 tables + departments.company_id).
--              The subsystem is no longer used. A pg_dump backup was taken before applying this
--              migration; see backups/bonus_dump_*.sql.gz.
--
-- This migration also clears `bonus.*` section keys from `app_role.allowed_sections` so the
-- UI/sidebar does not reference removed sections. The `app_role` rows themselves are kept.
--
-- Order of operations:
--   1. Strip bonus.* section keys from app_role (jsonb array minus elements).
--   2. Drop departments.company_id column + its index (FK to bonus_company).
--   3. DROP TABLE ... CASCADE for all bonus_* tables (CASCADE handles inter-FK order).

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Clean up bonus.* section keys from app_role.allowed_sections
-- ---------------------------------------------------------------------------
-- jsonb_path_query_array + filter to keep only non-bonus keys
UPDATE app_role
SET allowed_sections = COALESCE(
    (
        SELECT jsonb_agg(section)
        FROM jsonb_array_elements_text(allowed_sections) AS section
        WHERE section NOT LIKE 'bonus.%'
    ),
    '[]'::jsonb
)
WHERE allowed_sections::text LIKE '%bonus.%';

-- ---------------------------------------------------------------------------
-- 2. Drop departments.company_id (FK to bonus_company) + its index
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_departments_company;
ALTER TABLE departments DROP COLUMN IF EXISTS company_id;

-- ---------------------------------------------------------------------------
-- 3. Drop all bonus_* tables (CASCADE to satisfy FKs)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS bonus_calculation_penalty CASCADE;
DROP TABLE IF EXISTS bonus_calculation CASCADE;
DROP TABLE IF EXISTS bonus_manual_kpi CASCADE;
DROP TABLE IF EXISTS bonus_scheme CASCADE;
DROP TABLE IF EXISTS bonus_employee_assignment CASCADE;
DROP TABLE IF EXISTS bonus_monthly_plan CASCADE;
DROP TABLE IF EXISTS bonus_kpi_definition CASCADE;
DROP TABLE IF EXISTS bonus_team_position CASCADE;
DROP TABLE IF EXISTS bonus_team CASCADE;
DROP TABLE IF EXISTS bonus_position CASCADE;
DROP TABLE IF EXISTS bonus_company CASCADE;

COMMIT;

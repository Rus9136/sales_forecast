-- Migration: Add main_role_name to employees
-- Version: 006
-- Date: 2026-04-29
-- Description: Stores human-readable role name resolved from /resto/api/employees/roles at sync time.

ALTER TABLE employees ADD COLUMN IF NOT EXISTS main_role_name VARCHAR(255);
CREATE INDEX IF NOT EXISTS idx_employees_main_role_name ON employees(main_role_name);

COMMENT ON COLUMN employees.main_role_name IS 'Resolved role display name from iiko roles catalog (e.g. WR1 -> Официант)';

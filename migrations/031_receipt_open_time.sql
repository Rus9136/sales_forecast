-- Migration 031: add open_time to receipt
-- iiko OLAP exposes OpenTime (full timestamp of order open) parallel to CloseTime.
-- Until now only the accounting day (OpenDate.Typed → open_date) was stored,
-- so the hour/minute a check was opened was lost. Add a nullable column and
-- backfill it on the next receipts re-sync.

ALTER TABLE receipt ADD COLUMN IF NOT EXISTS open_time TIMESTAMP;

-- Optional: index for time-of-day / dwell-time analytics on open_time.
CREATE INDEX IF NOT EXISTS idx_receipt_open_time ON receipt (department_id, open_time);

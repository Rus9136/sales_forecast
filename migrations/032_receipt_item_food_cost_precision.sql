-- Migration 032: widen receipt_item.food_cost_percent precision
-- iiko ProductCostBase.Percent can exceed 1000% for pathological line items
-- (cost far above sale price, or zero sale with non-zero cost). The original
-- NUMERIC(7,4) caps at 999.9999 and raised "numeric field overflow" during
-- receipts sync. Widen to NUMERIC(10,4) to store the raw value as reported.

ALTER TABLE receipt_item ALTER COLUMN food_cost_percent TYPE NUMERIC(10,4);

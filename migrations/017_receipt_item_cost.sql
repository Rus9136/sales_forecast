-- Migration 017: Add cost_price and food_cost_percent to receipt_item
-- Phase 5.2 — cost analytics from iiko OLAP ProductCostBase fields

ALTER TABLE receipt_item ADD COLUMN cost_price NUMERIC(14,2);
ALTER TABLE receipt_item ADD COLUMN food_cost_percent NUMERIC(7,4);

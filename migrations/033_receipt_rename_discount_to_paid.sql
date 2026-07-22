-- 033_receipt_rename_discount_to_paid.sql
-- Rename receipt(.item).discount_sum -> paid_sum.
--
-- Semantics fix: the column stored iiko field `DishDiscountSumInt`, which is the
-- ACTUAL amount to pay (net of discounts, plus service charge) — NOT the discount
-- amount. Empirically `paid_sum` can be both < total_sum (скидка) and > total_sum
-- (сервисный сбор, ~+15%). The real discount is derived as (total_sum - paid_sum).
--
-- `receipt` / `receipt_item` are RANGE-partitioned parents; RENAME COLUMN on the
-- parent cascades to all partitions automatically and is metadata-only (instant).

ALTER TABLE receipt      RENAME COLUMN discount_sum TO paid_sum;
ALTER TABLE receipt_item RENAME COLUMN discount_sum TO paid_sum;

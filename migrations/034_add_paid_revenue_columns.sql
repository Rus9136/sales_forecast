-- 034_add_paid_revenue_columns.sql
-- Пункт B: фактическая выручка (iiko DishDiscountSumInt = сумма к оплате со скидкой/сервисом)
-- на уровне дневных/почасовых продаж — рядом с прайсом (DishSumInt), НЕ замена.
--
-- total_paid / paid_amount — nullable: обратимо (можно дропнуть) и pre-2024-06 история
-- (где нет источника в receipt) остаётся NULL. Инвариант: total_paid == SUM(paid_amount).
--
-- model_versions.revenue_basis — тег базы модели ('price'|'paid'), чтобы мониторинг и любое
-- A/B-сравнение знали, в каких единицах прогнозы модели, и не смешивали базы.

ALTER TABLE sales_summary ADD COLUMN IF NOT EXISTS total_paid  DOUBLE PRECISION;
ALTER TABLE sales_by_hour ADD COLUMN IF NOT EXISTS paid_amount DOUBLE PRECISION;
ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS revenue_basis VARCHAR(20);

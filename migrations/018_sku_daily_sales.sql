-- Phase 5.3: SKU-level daily sales aggregation + forecast storage
-- Depends on: 015_receipts.sql (receipt, receipt_item), 014_nomenclature.sql (product)

-- Pre-aggregated daily sales per (department, product, date).
-- Populated incrementally after each receipts sync from receipt_item.
CREATE TABLE IF NOT EXISTS sku_daily_sales (
    id              BIGSERIAL PRIMARY KEY,
    department_id   UUID NOT NULL REFERENCES departments(id),
    product_id      BIGINT NOT NULL REFERENCES product(id),
    sale_date       DATE NOT NULL,
    total_qty       NUMERIC(14,3) NOT NULL DEFAULT 0,
    total_sum       NUMERIC(16,2) NOT NULL DEFAULT 0,
    receipt_count   INTEGER NOT NULL DEFAULT 0,
    synced_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (department_id, product_id, sale_date)
);

CREATE INDEX IF NOT EXISTS idx_sku_daily_dept_date
    ON sku_daily_sales(department_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_sku_daily_product_date
    ON sku_daily_sales(product_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_sku_daily_date
    ON sku_daily_sales(sale_date);

-- Stores SKU-level forecasts for monitoring and comparison with actuals.
CREATE TABLE IF NOT EXISTS sku_forecasts (
    id              BIGSERIAL PRIMARY KEY,
    department_id   UUID NOT NULL REFERENCES departments(id),
    product_id      BIGINT NOT NULL REFERENCES product(id),
    forecast_date   DATE NOT NULL,
    predicted_qty   NUMERIC(12,3) NOT NULL,
    model_version   TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (department_id, product_id, forecast_date)
);

CREATE INDEX IF NOT EXISTS idx_sku_forecasts_dept_date
    ON sku_forecasts(department_id, forecast_date);

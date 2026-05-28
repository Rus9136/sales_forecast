-- Migration 019: Pricing analytics views (A2)
-- Three analytical tables for elasticity models, menu clustering, and KPI dashboards.
-- Depends on: 018_sku_daily_sales, 014_nomenclature (product), departments

-- 1. SKU price history: one row per price-change event per SKU per department.
CREATE TABLE IF NOT EXISTS sku_price_history (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES product(id),
    department_id   UUID NOT NULL REFERENCES departments(id),
    price           NUMERIC(14,2) NOT NULL,
    prev_price      NUMERIC(14,2),
    change_pct      NUMERIC(10,4),
    first_seen_date DATE NOT NULL,
    last_seen_date  DATE NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, department_id, first_seen_date)
);

CREATE INDEX IF NOT EXISTS idx_sku_price_hist_dept
    ON sku_price_history(department_id, first_seen_date);
CREATE INDEX IF NOT EXISTS idx_sku_price_hist_product
    ON sku_price_history(product_id, department_id);
CREATE INDEX IF NOT EXISTS idx_sku_price_hist_dates
    ON sku_price_history(first_seen_date, last_seen_date);


-- 2. SKU weekly summary: aggregated per SKU x department x ISO week.
CREATE TABLE IF NOT EXISTS sku_weekly_summary (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES product(id),
    department_id   UUID NOT NULL REFERENCES departments(id),
    week_start      DATE NOT NULL,
    total_qty       NUMERIC(14,3) NOT NULL DEFAULT 0,
    total_revenue   NUMERIC(16,2) NOT NULL DEFAULT 0,
    total_cost      NUMERIC(16,2) NOT NULL DEFAULT 0,
    gross_profit    NUMERIC(16,2) NOT NULL DEFAULT 0,
    gp_margin       NUMERIC(7,4),
    avg_price       NUMERIC(14,2),
    avg_daily_qty   NUMERIC(14,3),
    unique_receipts INTEGER NOT NULL DEFAULT 0,
    days_with_sales INTEGER NOT NULL DEFAULT 0,
    qty_cv          NUMERIC(7,4),
    cost_coverage   NUMERIC(7,4),
    synced_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, department_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_sku_weekly_dept_week
    ON sku_weekly_summary(department_id, week_start);
CREATE INDEX IF NOT EXISTS idx_sku_weekly_product_week
    ON sku_weekly_summary(product_id, week_start);
CREATE INDEX IF NOT EXISTS idx_sku_weekly_week
    ON sku_weekly_summary(week_start);


-- 3. Department weekly summary: aggregated per department x ISO week.
CREATE TABLE IF NOT EXISTS department_weekly_summary (
    id              BIGSERIAL PRIMARY KEY,
    department_id   UUID NOT NULL REFERENCES departments(id),
    week_start      DATE NOT NULL,
    total_revenue   NUMERIC(16,2) NOT NULL DEFAULT 0,
    total_cost      NUMERIC(16,2) NOT NULL DEFAULT 0,
    gross_profit    NUMERIC(16,2) NOT NULL DEFAULT 0,
    gp_margin       NUMERIC(7,4),
    total_receipts  INTEGER NOT NULL DEFAULT 0,
    avg_receipt_sum NUMERIC(14,2),
    unique_guests   INTEGER NOT NULL DEFAULT 0,
    cost_coverage   NUMERIC(7,4),
    synced_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (department_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_dept_weekly_dept_week
    ON department_weekly_summary(department_id, week_start);
CREATE INDEX IF NOT EXISTS idx_dept_weekly_week
    ON department_weekly_summary(week_start);

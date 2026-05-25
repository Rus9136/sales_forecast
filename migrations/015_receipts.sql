-- Migration 015: Receipt and receipt_item partitioned tables
-- Phase 3 of Menu & Receipts plan

-- receipt: order header (one row per unique order)
CREATE TABLE receipt (
    id BIGSERIAL,
    department_id UUID NOT NULL REFERENCES departments(id),
    open_date DATE NOT NULL,
    order_num INTEGER NOT NULL,
    close_time TIMESTAMP NOT NULL,
    order_type TEXT,
    table_num TEXT,
    waiter_name TEXT,
    waiter_employee_id UUID REFERENCES employees(id),
    guest_num INTEGER,
    total_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
    discount_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
    return_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
    items_count INTEGER NOT NULL DEFAULT 0,
    synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, open_date),
    UNIQUE (department_id, open_date, order_num)
) PARTITION BY RANGE (open_date);

-- receipt_item: line item within a receipt
CREATE TABLE receipt_item (
    id BIGSERIAL,
    receipt_id BIGINT NOT NULL,
    open_date DATE NOT NULL,
    product_id BIGINT REFERENCES product(id),
    iiko_dish_id UUID,
    dish_name TEXT NOT NULL,
    dish_code TEXT,
    dish_group TEXT,
    dish_category TEXT,
    qty NUMERIC(12,3) NOT NULL,
    price_per_unit NUMERIC(14,2),
    dish_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
    discount_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
    return_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (id, open_date)
) PARTITION BY RANGE (open_date);

-- Indexes (created on parent — propagated to partitions automatically)
CREATE INDEX idx_receipt_dept_date ON receipt (department_id, open_date);
CREATE INDEX idx_receipt_close_time ON receipt (department_id, close_time);
CREATE INDEX idx_receipt_item_receipt ON receipt_item (receipt_id, open_date);
CREATE INDEX idx_receipt_item_product ON receipt_item (product_id, open_date);
CREATE INDEX idx_receipt_item_dish_id ON receipt_item (iiko_dish_id, open_date);

-- Create monthly partitions: 2025-01 through 2027-12
DO $$
DECLARE
    curr DATE := '2025-01-01';
    stop DATE := '2028-01-01';
    next_month DATE;
    pname TEXT;
BEGIN
    WHILE curr < stop LOOP
        next_month := curr + INTERVAL '1 month';
        pname := 'receipt_' || to_char(curr, 'YYYY_MM');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF receipt FOR VALUES FROM (%L) TO (%L)',
            pname, curr, next_month
        );
        pname := 'receipt_item_' || to_char(curr, 'YYYY_MM');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF receipt_item FOR VALUES FROM (%L) TO (%L)',
            pname, curr, next_month
        );
        curr := next_month;
    END LOOP;
END $$;

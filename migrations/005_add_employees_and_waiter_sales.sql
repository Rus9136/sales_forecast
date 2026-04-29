-- Migration: Add Employees + Waiter Sales
-- Version: 005
-- Date: 2026-04-29
-- Description: Adds tables for iiko employees catalog and per-waiter daily sales aggregation.

CREATE TABLE IF NOT EXISTS employees (
    id UUID PRIMARY KEY,
    code VARCHAR(50),
    name VARCHAR(255) NOT NULL,
    login VARCHAR(255),
    first_name VARCHAR(255),
    middle_name VARCHAR(255),
    last_name VARCHAR(255),
    main_role_code VARCHAR(50),
    main_role_id UUID,
    role_codes JSONB,
    department_codes JSONB,
    preferred_department_code VARCHAR(50),
    cell_phone VARCHAR(50),
    email VARCHAR(255),
    hire_date DATE,
    fire_date DATE,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    synced_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employees_code ON employees(code);
CREATE INDEX IF NOT EXISTS idx_employees_name ON employees(name);
CREATE INDEX IF NOT EXISTS idx_employees_main_role_code ON employees(main_role_code);
CREATE INDEX IF NOT EXISTS idx_employees_preferred_department ON employees(preferred_department_code);
CREATE INDEX IF NOT EXISTS idx_employees_deleted ON employees(deleted);

CREATE TABLE IF NOT EXISTS sales_by_waiter (
    department_id UUID NOT NULL REFERENCES departments(id),
    date DATE NOT NULL,
    waiter_name VARCHAR(255) NOT NULL,
    employee_id UUID REFERENCES employees(id),
    total_sales DOUBLE PRECISION NOT NULL,
    total_sales_with_discount DOUBLE PRECISION,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (department_id, date, waiter_name)
);

CREATE INDEX IF NOT EXISTS ix_sales_by_waiter_date ON sales_by_waiter(date);
CREATE INDEX IF NOT EXISTS ix_sales_by_waiter_dept_date ON sales_by_waiter(department_id, date);
CREATE INDEX IF NOT EXISTS ix_sales_by_waiter_employee ON sales_by_waiter(employee_id);

COMMENT ON TABLE employees IS 'iiko employees catalog (synced from /resto/api/employees)';
COMMENT ON TABLE sales_by_waiter IS 'Daily sales aggregated by department and waiter (from iiko OLAP)';
COMMENT ON COLUMN sales_by_waiter.waiter_name IS 'Raw WaiterName from iiko OLAP — natural key';
COMMENT ON COLUMN sales_by_waiter.employee_id IS 'Resolved employee UUID via name lookup; NULL if no match';
COMMENT ON COLUMN sales_by_waiter.total_sales IS 'DishSumInt — net sales';
COMMENT ON COLUMN sales_by_waiter.total_sales_with_discount IS 'DishDiscountSumInt — sales with discounts';

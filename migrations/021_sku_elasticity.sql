-- Migration 021: SKU price elasticity estimates (B2)
-- Depends on: 014 (product), departments, 020 (sku_menu_role)

CREATE TABLE IF NOT EXISTS sku_elasticity (
    id                  BIGSERIAL PRIMARY KEY,
    product_id          BIGINT NOT NULL REFERENCES product(id),
    department_id       UUID NOT NULL REFERENCES departments(id),
    elasticity_mean     NUMERIC(8,4) NOT NULL,
    elasticity_ci_lower NUMERIC(8,4) NOT NULL,
    elasticity_ci_upper NUMERIC(8,4) NOT NULL,
    elasticity_se       NUMERIC(8,4),
    n_price_events      INTEGER NOT NULL DEFAULT 0,
    n_observations      INTEGER NOT NULL DEFAULT 0,
    estimation_level    TEXT NOT NULL,
    reliability_grade   TEXT NOT NULL,
    group_key           TEXT,
    model_r_squared     NUMERIC(6,4),
    model_version       TEXT NOT NULL,
    diagnostics         JSONB,
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, department_id)
);

ALTER TABLE sku_elasticity
    ADD CONSTRAINT chk_elasticity_level CHECK (
        estimation_level IN ('sku', 'group', 'global')
    ),
    ADD CONSTRAINT chk_elasticity_grade CHECK (
        reliability_grade IN ('A', 'B', 'C', 'D')
    );

CREATE INDEX IF NOT EXISTS idx_sku_elasticity_dept
    ON sku_elasticity(department_id);
CREATE INDEX IF NOT EXISTS idx_sku_elasticity_grade
    ON sku_elasticity(reliability_grade);
CREATE INDEX IF NOT EXISTS idx_sku_elasticity_level
    ON sku_elasticity(estimation_level);

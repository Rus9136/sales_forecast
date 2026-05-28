-- Migration 020: SKU menu role clustering (B1)
-- Classifies each (product_id, department_id) into one of 5 business roles.
-- Depends on: 014_nomenclature (product), departments

CREATE TABLE IF NOT EXISTS sku_menu_role (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES product(id),
    department_id   UUID NOT NULL REFERENCES departments(id),
    auto_role       TEXT NOT NULL,
    manual_role     TEXT,
    effective_role  TEXT GENERATED ALWAYS AS (COALESCE(manual_role, auto_role)) STORED,
    features        JSONB,
    cluster_meta    JSONB,
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, department_id)
);

ALTER TABLE sku_menu_role
    ADD CONSTRAINT chk_auto_role CHECK (
        auto_role IN ('premium_anchor', 'margin_driver', 'traffic_driver', 'image_rare', 'tail')
    ),
    ADD CONSTRAINT chk_manual_role CHECK (
        manual_role IS NULL OR
        manual_role IN ('premium_anchor', 'margin_driver', 'traffic_driver', 'image_rare', 'tail')
    );

CREATE INDEX IF NOT EXISTS idx_sku_menu_role_dept
    ON sku_menu_role(department_id);
CREATE INDEX IF NOT EXISTS idx_sku_menu_role_product
    ON sku_menu_role(product_id, department_id);
CREATE INDEX IF NOT EXISTS idx_sku_menu_role_effective
    ON sku_menu_role(effective_role);

-- Migration 023: Price recommendations with approve/reject workflow (B3)

CREATE TABLE IF NOT EXISTS price_recommendation (
    id                    BIGSERIAL PRIMARY KEY,
    product_id            BIGINT NOT NULL REFERENCES product(id),
    department_id         UUID NOT NULL REFERENCES departments(id),
    batch_id              UUID NOT NULL,
    current_price         NUMERIC(14,2) NOT NULL,
    recommended_price     NUMERIC(14,2) NOT NULL,
    delta_pct             NUMERIC(6,2),
    cogs                  NUMERIC(14,2),
    current_qty_forecast  NUMERIC(12,3),
    new_qty_forecast      NUMERIC(12,3),
    current_gp            NUMERIC(14,2),
    expected_gp           NUMERIC(14,2),
    delta_gp              NUMERIC(14,2),
    elasticity_used       NUMERIC(8,4),
    elasticity_grade      TEXT,
    menu_role             TEXT,
    constraints_applied   TEXT[],
    llm_explanation       TEXT,
    status                TEXT NOT NULL DEFAULT 'new',
    created_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    reviewed_by           UUID,
    reviewed_at           TIMESTAMP,
    review_comment        TEXT,
    UNIQUE (batch_id, product_id, department_id)
);

ALTER TABLE price_recommendation
    ADD CONSTRAINT chk_rec_status CHECK (
        status IN ('new', 'approved', 'rejected', 'expired')
    );

CREATE INDEX IF NOT EXISTS idx_price_rec_batch
    ON price_recommendation(batch_id);
CREATE INDEX IF NOT EXISTS idx_price_rec_dept_status
    ON price_recommendation(department_id, status);
CREATE INDEX IF NOT EXISTS idx_price_rec_created
    ON price_recommendation(created_at);
CREATE INDEX IF NOT EXISTS idx_price_rec_product
    ON price_recommendation(product_id, department_id);

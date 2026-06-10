-- Migration 026: Pricing feedback loop + pilot baseline (improvements №1/№3/№5/№6)
--
-- 1. price_recommendation: new terminal status 'applied' + when/at what price
--    the recommendation actually reached the iiko menu (detected by matching
--    a fresh sku_catalog_price interval against the approved recommendation).
--
-- 2. price_recommendation_outcome: 14-day before/after evaluation of every
--    applied recommendation — actual vs expected GP, control-group-adjusted
--    qty change and the realized elasticity (closes roadmap §7.4).
--
-- 3. pricing_baseline_kpi: frozen pre-pilot KPI snapshot per department
--    (roadmap A3) — the reference point for the pilot acceptance metric
--    "ΔGP vs baseline".

-- 1 ------------------------------------------------------------------
ALTER TABLE price_recommendation DROP CONSTRAINT IF EXISTS chk_rec_status;
ALTER TABLE price_recommendation
    ADD CONSTRAINT chk_rec_status CHECK (
        status IN ('new', 'approved', 'rejected', 'expired', 'applied')
    );

ALTER TABLE price_recommendation
    ADD COLUMN IF NOT EXISTS applied_at DATE,
    ADD COLUMN IF NOT EXISTS applied_price NUMERIC(14,2);

CREATE INDEX IF NOT EXISTS idx_price_rec_applied
    ON price_recommendation(status, applied_at);

-- 2 ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_recommendation_outcome (
    id                  BIGSERIAL PRIMARY KEY,
    recommendation_id   BIGINT NOT NULL REFERENCES price_recommendation(id),
    product_id          BIGINT NOT NULL,
    department_id       UUID NOT NULL,
    applied_at          DATE NOT NULL,
    eval_window_days    INTEGER NOT NULL DEFAULT 14,
    baseline_from       DATE NOT NULL,
    baseline_to         DATE NOT NULL,
    eval_from           DATE NOT NULL,
    eval_to             DATE NOT NULL,
    old_price           NUMERIC(14,2),
    new_price           NUMERIC(14,2),
    qty_before          NUMERIC(12,3),
    qty_after           NUMERIC(12,3),
    revenue_before      NUMERIC(14,2),
    revenue_after       NUMERIC(14,2),
    gp_before           NUMERIC(14,2),
    gp_after            NUMERIC(14,2),
    expected_delta_gp   NUMERIC(14,2),
    actual_delta_gp     NUMERIC(14,2),
    qty_change_pct      NUMERIC(8,4),
    control_qty_change_pct NUMERIC(8,4),
    adj_qty_change_pct  NUMERIC(8,4),
    realized_elasticity NUMERIC(8,4),
    n_control_skus      INTEGER,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (recommendation_id)
);

CREATE INDEX IF NOT EXISTS idx_rec_outcome_dept
    ON price_recommendation_outcome(department_id, applied_at);
CREATE INDEX IF NOT EXISTS idx_rec_outcome_product
    ON price_recommendation_outcome(product_id, department_id);

-- 3 ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pricing_baseline_kpi (
    id              BIGSERIAL PRIMARY KEY,
    label           TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'department',  -- department | network
    department_id   UUID REFERENCES departments(id),     -- NULL для scope='network'
    baseline_from   DATE NOT NULL,
    baseline_to     DATE NOT NULL,
    weeks           INTEGER NOT NULL,
    total_revenue   NUMERIC(16,2),
    total_cost      NUMERIC(16,2),
    gross_profit    NUMERIC(16,2),
    gp_margin       NUMERIC(6,4),
    total_receipts  INTEGER,
    avg_receipt_sum NUMERIC(14,2),
    weekly_gp_avg   NUMERIC(16,2),
    weekly_gp_stddev NUMERIC(16,2),
    active_skus     INTEGER,
    cost_coverage   NUMERIC(6,4),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (label, scope, department_id)
);

CREATE INDEX IF NOT EXISTS idx_baseline_label
    ON pricing_baseline_kpi(label);

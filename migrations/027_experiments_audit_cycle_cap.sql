-- Migration 027: price experiments, audit trail, per-cycle change cap,
-- stale catalog intervals (improvements №7/№8/№9/№12)

-- №7: experiment recommendations flow through the same approve→applied→outcome
-- pipeline as optimizer ones, but are generated to MEASURE elasticity (grade
-- C/D SKUs), not to maximize GP.
ALTER TABLE price_recommendation
    ADD COLUMN IF NOT EXISTS rec_type TEXT NOT NULL DEFAULT 'optimizer';
ALTER TABLE price_recommendation DROP CONSTRAINT IF EXISTS chk_rec_type;
ALTER TABLE price_recommendation
    ADD CONSTRAINT chk_rec_type CHECK (rec_type IN ('optimizer', 'experiment'));
CREATE INDEX IF NOT EXISTS idx_price_rec_type
    ON price_recommendation(rec_type, status);

-- №9: append-only audit trail (ТЗ п.9.3)
CREATE TABLE IF NOT EXISTS pricing_audit_log (
    id            BIGSERIAL PRIMARY KEY,
    entity_type   TEXT NOT NULL,   -- recommendation | rule | menu_role | baseline | experiment
    entity_id     TEXT,
    action        TEXT NOT NULL,   -- approve | reject | create | update | delete | override | freeze | generate
    actor         TEXT,            -- reviewer_id / 'api' / 'scheduler'
    department_id UUID,
    details       JSONB,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pricing_audit_entity
    ON pricing_audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_pricing_audit_created
    ON pricing_audit_log(created_at);

-- №8: portfolio cap — не больше N утверждённых изменений на точку за окно
ALTER TABLE pricing_rule DROP CONSTRAINT IF EXISTS chk_rule_type;
ALTER TABLE pricing_rule
    ADD CONSTRAINT chk_rule_type CHECK (
        rule_type IN (
            'min_margin',
            'max_step',
            'min_frequency',
            'no_decrease_anchor',
            'min_competitive_idx',
            'rounding',
            'no_psychological',
            'stop_list',
            'max_changes_per_cycle'
        )
    );
INSERT INTO pricing_rule (rule_type, scope_type, scope_id, params, configured_by_role)
VALUES ('max_changes_per_cycle', 'global', NULL,
        '{"value": 15, "window_days": 14}', 'commercial_director')
ON CONFLICT (rule_type) WHERE scope_type = 'global' AND scope_id IS NULL
DO NOTHING;

-- №12: интервалы, исчезнувшие из снапшота iiko (отозванные приказы)
ALTER TABLE sku_catalog_price
    ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;

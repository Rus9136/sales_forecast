-- Migration 022: Configurable pricing rules (B4)

CREATE TABLE IF NOT EXISTS pricing_rule (
    id                BIGSERIAL PRIMARY KEY,
    rule_type         TEXT NOT NULL,
    scope_type        TEXT NOT NULL,
    scope_id          TEXT,
    params            JSONB NOT NULL,
    is_active         BOOLEAN NOT NULL DEFAULT true,
    configured_by_role TEXT,
    effective_from    DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to      DATE,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP
);

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
            'stop_list'
        )
    ),
    ADD CONSTRAINT chk_scope_type CHECK (
        scope_type IN ('global', 'segment', 'department', 'product')
    ),
    ADD CONSTRAINT uq_pricing_rule_type_scope
        UNIQUE (rule_type, scope_type, scope_id);

CREATE INDEX IF NOT EXISTS idx_pricing_rule_type
    ON pricing_rule(rule_type, is_active);
CREATE INDEX IF NOT EXISTS idx_pricing_rule_scope
    ON pricing_rule(scope_type, scope_id);

-- Seed default global rules
INSERT INTO pricing_rule (rule_type, scope_type, scope_id, params, configured_by_role)
VALUES
    ('min_margin',          'global', NULL, '{"value": 0.60}',                              'financial_director'),
    ('max_step',            'global', NULL, '{"value": 0.05}',                              'commercial_director'),
    ('min_frequency',       'global', NULL, '{"days": 14}',                                 'commercial_director'),
    ('no_decrease_anchor',  'global', NULL, '{"enabled": true}',                            'manager'),
    ('rounding',            'global', NULL, '{"step": 50, "flagship_step": 100}',           'commercial_director'),
    ('no_psychological',    'global', NULL, '{"enabled": true, "endings": [9, 99]}',        'commercial_director')
ON CONFLICT DO NOTHING;

-- Migration 025: Pricing correctness fixes
--
-- 1. One-time cleanup: expire duplicate 'new' recommendations.
--    Daily optimizer batches accumulated up to 17 open 'new' recs per
--    SKU×dept (summary over-counted potential ΔGP ~11x). Keep only the
--    latest 'new' per (product_id, department_id); the optimizer now
--    supersedes all open recs of a department on each generation run.
--
-- 2. Partial unique index for global pricing rules: the existing
--    UNIQUE (rule_type, scope_type, scope_id) does not fire for
--    scope_id IS NULL (NULL <> NULL), so re-running the 022 seed or a
--    duplicate POST could create duplicate global rules with
--    nondeterministic cascade resolution.

UPDATE price_recommendation pr
SET status = 'expired'
WHERE pr.status = 'new'
  AND EXISTS (
      SELECT 1 FROM price_recommendation newer
      WHERE newer.product_id = pr.product_id
        AND newer.department_id = pr.department_id
        AND newer.status = 'new'
        AND (newer.created_at > pr.created_at
             OR (newer.created_at = pr.created_at AND newer.id > pr.id))
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_pricing_rule_global
    ON pricing_rule (rule_type)
    WHERE scope_type = 'global' AND scope_id IS NULL;

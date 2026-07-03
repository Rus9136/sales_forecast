-- Migration 029: pricing hardening (по результатам архитектурного ревью 2026-07-03)
--
-- 1. pricing_audit_log — append-only на уровне СУБД (раньше — только конвенция:
--    любой код под owner-пользователем мог править/чистить журнал).
-- 2. price_recommendation — не больше одной открытой ('new') рекомендации на
--    SKU×dept: supersede жил только в коде оптимизатора, сбой/параллельный
--    запуск снова копил дубли и завышал summary. Перед созданием индекса
--    дубли гасятся (остаётся самая свежая).

-- 1 ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION pricing_audit_log_protect() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'pricing_audit_log is append-only (ТЗ п.9.3)';
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pricing_audit_protect ON pricing_audit_log;
CREATE TRIGGER trg_pricing_audit_protect
    BEFORE UPDATE OR DELETE ON pricing_audit_log
    FOR EACH ROW EXECUTE FUNCTION pricing_audit_log_protect();

-- 2 ------------------------------------------------------------------
WITH dups AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY product_id, department_id
               ORDER BY created_at DESC, id DESC
           ) AS rn
    FROM price_recommendation
    WHERE status = 'new'
)
UPDATE price_recommendation
SET status = 'expired'
WHERE id IN (SELECT id FROM dups WHERE rn > 1);

CREATE UNIQUE INDEX IF NOT EXISTS uq_price_rec_open
    ON price_recommendation (product_id, department_id)
    WHERE status = 'new';

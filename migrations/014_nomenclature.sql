-- Migration: Nomenclature (products + groups + categories)
-- Version: 014
-- Date: 2026-05-25
-- Description: Tables for iiko nomenclature catalog — the foundation for Phase 3
--              (receipts.product_id resolution), Phase 4 (price tracking), and
--              Phase 5 (recipes). See docs/MENU_AND_RECEIPTS_ARCHITECTURE.md.
--
-- Sources (per phase 0 smoke):
--   GET /resto/api/v2/entities/products/group/list      → ~447 groups / Sandy
--   GET /resto/api/v2/entities/products/category/list   → ~40 categories / Sandy
--   GET /resto/api/v2/entities/products/list?includeDeleted=true → ~18k SKU / Sandy
--
-- Key decisions:
--   * BIGSERIAL PK (not iiko UUID) — protects against cross-domain UUID collisions
--     (theoretical but possible if catalogs are imported domain→domain).
--   * Natural unique = (iiko_source_domain, iiko_*_id). Same UUID may legitimately
--     appear under different domains for different physical objects.
--   * Foreign keys (product → group/category, group → group) point at BIGSERIAL ids,
--     not UUIDs, so they're cheap and consistent with PK type.
--   * `iiko_payload` JSONB carries the raw entity from iiko — color, modifiers,
--     frontImageId, allergenGroups, etc. Avoids schema churn when iiko adds fields.
--   * pg_trgm index on product.name for fast prefix/fuzzy search in the UI.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- 1. nomenclature_category — flat dictionary (40 rows per domain). Linked
--    from `product.category_id` and (optionally) from group.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nomenclature_category (
    id                  BIGSERIAL PRIMARY KEY,
    iiko_source_domain  TEXT NOT NULL,
    iiko_category_id    UUID NOT NULL,
    name                TEXT NOT NULL,
    is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,
    synced_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (iiko_source_domain, iiko_category_id)
);
CREATE INDEX IF NOT EXISTS idx_nomenclature_category_source
    ON nomenclature_category(iiko_source_domain);

-- ---------------------------------------------------------------------------
-- 2. nomenclature_group — hierarchical (parent_id → self). `iiko_payload`
--    stores color/modifierSchemaId/visibilityFilter etc.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nomenclature_group (
    id                  BIGSERIAL PRIMARY KEY,
    iiko_source_domain  TEXT NOT NULL,
    iiko_group_id       UUID NOT NULL,
    parent_id           BIGINT REFERENCES nomenclature_group(id),
    name                TEXT NOT NULL,
    num                 TEXT,
    code                TEXT,
    position            INTEGER,
    is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,
    iiko_payload        JSONB,
    synced_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (iiko_source_domain, iiko_group_id)
);
CREATE INDEX IF NOT EXISTS idx_nomenclature_group_source
    ON nomenclature_group(iiko_source_domain);
CREATE INDEX IF NOT EXISTS idx_nomenclature_group_parent
    ON nomenclature_group(parent_id);

-- ---------------------------------------------------------------------------
-- 3. product — main catalog (~18k Sandy / smaller Madlen). `type` is the
--    iiko-side enum: DISH | GOODS | MODIFIER | PREPARED | SERVICE.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product (
    id                      BIGSERIAL PRIMARY KEY,
    iiko_source_domain      TEXT NOT NULL,
    iiko_product_id         UUID NOT NULL,
    num                     TEXT,
    code                    TEXT,
    name                    TEXT NOT NULL,
    description             TEXT,
    type                    TEXT NOT NULL,
    group_id                BIGINT REFERENCES nomenclature_group(id),
    category_id             BIGINT REFERENCES nomenclature_category(id),
    measure_unit_id         UUID,
    default_sale_price      NUMERIC(14, 2),
    estimated_purchase_price NUMERIC(14, 2),
    weight_kg               NUMERIC(10, 4),
    cold_loss_percent       NUMERIC(7, 4),
    hot_loss_percent        NUMERIC(7, 4),
    tax_category_id         UUID,
    accounting_category_id  UUID,
    is_deleted              BOOLEAN NOT NULL DEFAULT FALSE,
    is_included_in_menu     BOOLEAN NOT NULL DEFAULT TRUE,
    iiko_payload            JSONB,
    synced_at               TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (iiko_source_domain, iiko_product_id)
);
CREATE INDEX IF NOT EXISTS idx_product_source ON product(iiko_source_domain);
CREATE INDEX IF NOT EXISTS idx_product_group  ON product(group_id);
CREATE INDEX IF NOT EXISTS idx_product_category ON product(category_id);
CREATE INDEX IF NOT EXISTS idx_product_type   ON product(type);
CREATE INDEX IF NOT EXISTS idx_product_name_trgm
    ON product USING gin (name gin_trgm_ops);

COMMENT ON TABLE nomenclature_category IS
    'iiko categories (Горячие блюда, Холодные блюда, etc.) — flat dictionary';
COMMENT ON TABLE nomenclature_group IS
    'iiko hierarchical groups (Бар, Кухня, …). parent_id points to another row in the same table';
COMMENT ON TABLE product IS
    'iiko nomenclature: DISH/GOODS/MODIFIER/PREPARED/SERVICE. Source-of-truth for receipt_item.product_id resolution';

COMMIT;

-- Migration 016: Recipe and recipe_ingredient tables
-- Phase 5.1 of Menu & Receipts plan

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE recipe (
    id BIGSERIAL PRIMARY KEY,
    iiko_source_domain TEXT NOT NULL,
    iiko_assembly_chart_id UUID NOT NULL,
    product_id BIGINT NOT NULL REFERENCES product(id),
    date_from DATE NOT NULL,
    date_to DATE,
    assembled_amount NUMERIC(12,4) NOT NULL DEFAULT 1,
    description TEXT,
    technology_description TEXT,
    iiko_payload JSONB,
    synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (iiko_source_domain, iiko_assembly_chart_id)
);

CREATE INDEX idx_recipe_product ON recipe(product_id);
CREATE INDEX idx_recipe_domain ON recipe(iiko_source_domain);
CREATE INDEX idx_recipe_date_range ON recipe(product_id, date_from);

CREATE TABLE recipe_ingredient (
    id BIGSERIAL PRIMARY KEY,
    recipe_id BIGINT NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
    iiko_item_id UUID,
    ingredient_product_id BIGINT REFERENCES product(id),
    iiko_ingredient_product_id UUID,
    sort_weight NUMERIC(8,2) DEFAULT 0,
    amount_in NUMERIC(14,6) NOT NULL,
    amount_middle NUMERIC(14,6),
    amount_out NUMERIC(14,6),
    synced_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recipe_ingredient_recipe ON recipe_ingredient(recipe_id);
CREATE INDEX idx_recipe_ingredient_product ON recipe_ingredient(ingredient_product_id);

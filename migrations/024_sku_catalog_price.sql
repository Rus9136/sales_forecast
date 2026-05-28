-- Migration 024: Real menu prices from iiko orders (приказы)
-- Source: GET /resto/api/v2/price (NOT /reports/priceList which 404s).
-- Clean catalog prices with validity intervals [date_from, date_to] + document_id.
-- Replaces derived avg_price (revenue/qty) which was contaminated by mix/modifiers.

CREATE TABLE IF NOT EXISTS sku_catalog_price (
    id                BIGSERIAL PRIMARY KEY,
    department_id     UUID NOT NULL REFERENCES departments(id),
    iiko_product_id   UUID NOT NULL,
    product_id        BIGINT REFERENCES product(id),
    product_size_id   UUID,
    price             NUMERIC(14,2) NOT NULL,
    date_from         DATE NOT NULL,
    date_to           DATE NOT NULL,
    price_type        TEXT NOT NULL DEFAULT 'BASE',
    document_id       UUID,
    included          BOOLEAN,
    is_dish_of_day    BOOLEAN,
    iiko_source_domain TEXT,
    synced_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_price
    ON sku_catalog_price (
        department_id,
        iiko_product_id,
        COALESCE(product_size_id, '00000000-0000-0000-0000-000000000000'::uuid),
        date_from,
        price_type
    );

CREATE INDEX IF NOT EXISTS idx_catalog_price_product
    ON sku_catalog_price(product_id, department_id);
CREATE INDEX IF NOT EXISTS idx_catalog_price_dates
    ON sku_catalog_price(date_from, date_to);
CREATE INDEX IF NOT EXISTS idx_catalog_price_doc
    ON sku_catalog_price(document_id);

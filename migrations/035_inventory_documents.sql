-- Migration 035: складской контур iiko — списания и приходные накладные
--
-- Источники (разведка 2026-07-29, оба домена):
--   склады      GET  /resto/api/corporation/stores            (XML, parentId = departments.id)
--   счета       GET  /resto/api/v2/entities/list?rootType=Account   (JSON, причина списания)
--   поставщики  GET  /resto/api/suppliers                     (XML, обёртка <employees>)
--   ед.изм.     GET  /resto/api/v2/entities/list?rootType=MeasureUnit
--   списания    GET  /resto/api/v2/documents/writeoff?dateFrom=&dateTo=   (JSON)
--   приход      GET  /resto/api/documents/export/incomingInvoice?from=&to= (XML)
--
-- Ключевые семантические решения (см. комментарии к колонкам):
--   * writeoff_item.cost — себестоимость ВСЕЙ строки, не за единицу (как receipt_item.cost_price)
--   * у списания склад на уровне ДОКУМЕНТА, у накладной — на уровне ПОЗИЦИИ
--   * department_id денормализован на позиции, чтобы не джойнить store в каждом отчёте

-- ---------------------------------------------------------------- справочники

CREATE TABLE IF NOT EXISTS store (
    id                 UUID PRIMARY KEY,              -- iiko store id
    department_id      UUID REFERENCES departments(id),
    code               TEXT,
    name               TEXT NOT NULL,
    iiko_source_domain TEXT NOT NULL,
    is_deleted         BOOLEAN NOT NULL DEFAULT FALSE,
    synced_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_store_department ON store(department_id);

COMMENT ON TABLE  store IS 'Склады iiko. У одной точки обычно несколько: Бар / Кухня / Магазин / Хоз.товары.';
COMMENT ON COLUMN store.department_id IS 'iiko stores.parentId — совпадает с departments.id';

CREATE TABLE IF NOT EXISTS iiko_account (
    id                 UUID PRIMARY KEY,
    code               TEXT,
    name               TEXT NOT NULL,
    account_type       TEXT,
    parent_id          UUID,
    iiko_source_domain TEXT NOT NULL,
    is_deleted         BOOLEAN NOT NULL DEFAULT FALSE,
    synced_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE iiko_account IS
    'План счетов iiko. Для актов списания account_id — это ПРИЧИНА списания '
    '("Истек срок хранения", "Порча продуктов(сырья)", "Маркетинг", ...).';

CREATE TABLE IF NOT EXISTS supplier (
    id                 UUID PRIMARY KEY,
    code               TEXT,
    name               TEXT NOT NULL,
    taxpayer_id_number TEXT,
    iiko_source_domain TEXT NOT NULL,
    is_deleted         BOOLEAN NOT NULL DEFAULT FALSE,
    synced_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_supplier_name ON supplier(name);

CREATE TABLE IF NOT EXISTS measure_unit (
    id                 UUID PRIMARY KEY,
    code               TEXT,
    name               TEXT NOT NULL,
    iiko_source_domain TEXT NOT NULL,
    synced_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------- акты списания

CREATE TABLE IF NOT EXISTS writeoff_document (
    id                 UUID PRIMARY KEY,              -- iiko document id
    department_id      UUID REFERENCES departments(id),
    store_id           UUID,
    account_id         UUID,
    document_number    TEXT,
    date_incoming      TIMESTAMP NOT NULL,
    doc_date           DATE NOT NULL,
    status             TEXT NOT NULL,                 -- PROCESSED | DELETED | NEW
    conception_id      UUID,
    comment            TEXT,
    items_count        INTEGER NOT NULL DEFAULT 0,
    total_cost         NUMERIC(16,4) NOT NULL DEFAULT 0,
    iiko_source_domain TEXT NOT NULL,
    synced_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_writeoff_doc_dept_date ON writeoff_document(department_id, doc_date);
CREATE INDEX IF NOT EXISTS idx_writeoff_doc_store ON writeoff_document(store_id, doc_date);
CREATE INDEX IF NOT EXISTS idx_writeoff_doc_account ON writeoff_document(account_id);

COMMENT ON COLUMN writeoff_document.store_id IS 'Склад — у акта списания он на уровне документа, не позиции';
COMMENT ON COLUMN writeoff_document.account_id IS 'Причина списания, FK на iiko_account (без constraint: счёт может приехать позже)';
COMMENT ON COLUMN writeoff_document.status IS 'Отчёты обязаны фильтровать status = PROCESSED';

CREATE TABLE IF NOT EXISTS writeoff_item (
    id              BIGSERIAL PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES writeoff_document(id) ON DELETE CASCADE,
    department_id   UUID,
    store_id        UUID,
    doc_date        DATE NOT NULL,
    num             INTEGER,
    iiko_product_id UUID NOT NULL,
    product_id      BIGINT REFERENCES product(id),
    product_size_id UUID,
    amount          NUMERIC(16,6) NOT NULL,
    amount_factor   NUMERIC(16,6),
    measure_unit_id UUID,
    container_id    UUID,
    cost            NUMERIC(16,4)
);
CREATE INDEX IF NOT EXISTS idx_writeoff_item_doc ON writeoff_item(document_id);
CREATE INDEX IF NOT EXISTS idx_writeoff_item_product ON writeoff_item(product_id, doc_date);
CREATE INDEX IF NOT EXISTS idx_writeoff_item_dept_date ON writeoff_item(department_id, doc_date);

COMMENT ON COLUMN writeoff_item.cost IS
    'Себестоимость ВСЕЙ строки (за все amount), НЕ за единицу. '
    'Суммировать как SUM(cost); умножать на amount — ошибка. Та же семантика, что receipt_item.cost_price.';

-- ------------------------------------------------------- приходные накладные

CREATE TABLE IF NOT EXISTS incoming_invoice (
    id                         UUID PRIMARY KEY,
    supplier_id                UUID,
    default_store_id           UUID,
    document_number            TEXT,
    incoming_document_number   TEXT,
    incoming_date              DATE,
    date_incoming              TIMESTAMP,
    doc_date                   DATE NOT NULL,
    status                     TEXT NOT NULL,          -- PROCESSED | DELETED | NEW
    conception_id              UUID,
    comment                    TEXT,
    linked_outgoing_invoice_id UUID,
    items_count                INTEGER NOT NULL DEFAULT 0,
    total_sum                  NUMERIC(16,4) NOT NULL DEFAULT 0,
    iiko_source_domain         TEXT NOT NULL,
    synced_at                  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_invoice_date ON incoming_invoice(doc_date);
CREATE INDEX IF NOT EXISTS idx_invoice_supplier ON incoming_invoice(supplier_id, doc_date);

COMMENT ON COLUMN incoming_invoice.linked_outgoing_invoice_id IS
    'Связанная расходная накладная отправителя — признак внутрисетевой поставки';
COMMENT ON TABLE incoming_invoice IS
    'Накладная может лежать на склады разных подразделений, поэтому department_id — на позиции, не в шапке.';

CREATE TABLE IF NOT EXISTS incoming_invoice_item (
    id                    BIGSERIAL PRIMARY KEY,
    invoice_id            UUID NOT NULL REFERENCES incoming_invoice(id) ON DELETE CASCADE,
    department_id         UUID,
    store_id              UUID,
    doc_date              DATE NOT NULL,
    num                   INTEGER,
    iiko_product_id       UUID,
    product_id            BIGINT REFERENCES product(id),
    product_article       TEXT,
    amount                NUMERIC(16,6),
    actual_amount         NUMERIC(16,6),
    price                 NUMERIC(16,4),
    price_without_vat     NUMERIC(16,4),
    line_sum              NUMERIC(16,4),
    vat_percent           NUMERIC(9,4),
    vat_sum               NUMERIC(16,4),
    discount_sum          NUMERIC(16,4),
    amount_unit_id        UUID,
    is_additional_expense BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_invoice_item_inv ON incoming_invoice_item(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_item_product ON incoming_invoice_item(product_id, doc_date);
CREATE INDEX IF NOT EXISTS idx_invoice_item_dept_date ON incoming_invoice_item(department_id, doc_date);

COMMENT ON COLUMN incoming_invoice_item.price IS 'Цена за единицу';
COMMENT ON COLUMN incoming_invoice_item.line_sum IS 'Сумма строки (iiko <sum>), переименована — sum зарезервировано';
COMMENT ON COLUMN incoming_invoice_item.is_additional_expense IS
    'Доп.расходы (доставка и пр.) — исключать при расчёте закупленного количества';

-- ------------------------------------------------------------------ журнал

CREATE TABLE IF NOT EXISTS inventory_sync_log (
    id            BIGSERIAL PRIMARY KEY,
    sync_type     TEXT NOT NULL,          -- writeoff | invoice | reference
    department_id UUID,
    from_date     DATE,
    to_date       DATE,
    documents     INTEGER NOT NULL DEFAULT 0,
    items         INTEGER NOT NULL DEFAULT 0,
    unresolved    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL,          -- success | error
    error_message TEXT,
    duration_sec  NUMERIC(10,2),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inventory_sync_log_created ON inventory_sync_log(created_at DESC);

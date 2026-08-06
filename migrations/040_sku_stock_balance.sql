-- Остатки по складам на конец учётного дня.
--
-- Зачем. Оценка эффекта цены сравнивает наши продажи с теми же блюдами в других
-- точках. Если товара не было на складе, продажи упали не из-за цены, и такой
-- день оценку портит. Определять дефицит по времени последнего чека оказалось
-- ненадёжно: 29.07.2026 продажи пирожного оборвались в 12:43, а на складе к
-- концу дня лежало 14 штук.
--
-- Особенности источника (/resto/api/v2/reports/balance/stores?timestamp=):
--   * отдаёт СРЕЗ на момент времени, истории нет — поэтому снимок раз в день;
--   * нулевые позиции в ответ НЕ включаются: нет строки = нулевой остаток;
--   * отрицательные остатки встречаются массово (≈15% строк) — это документы
--     задним числом, а не физическое отсутствие товара;
--   * фильтры store/product работают на сервере (в отличие от writeoff и
--     incomingInvoice, где storeId молча игнорируется).

CREATE TABLE IF NOT EXISTS sku_stock_balance (
    balance_date  date          NOT NULL,
    store_id      uuid          NOT NULL REFERENCES store(id),
    product_id    bigint        NOT NULL REFERENCES product(id),
    department_id uuid          REFERENCES departments(id),
    amount        numeric(16,3) NOT NULL,
    cost_sum      numeric(16,2),
    synced_at     timestamp     NOT NULL DEFAULT now(),
    PRIMARY KEY (balance_date, store_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_balance_product_dept
    ON sku_stock_balance (product_id, department_id, balance_date);
CREATE INDEX IF NOT EXISTS idx_stock_balance_dept_date
    ON sku_stock_balance (department_id, balance_date);

COMMENT ON TABLE sku_stock_balance IS
    'Остаток товара на складе на конец учётного дня (снимок iiko balance/stores)';
COMMENT ON COLUMN sku_stock_balance.amount IS
    'Остаток в единицах учёта. Отрицательный = расхождение документов, не отсутствие';

-- Сколько дней окна выброшено из-за отсутствия товара. NULL = проверка не
-- проводилась (нет снимков остатков за этот период).
ALTER TABLE price_recommendation_outcome
    ADD COLUMN IF NOT EXISTS days_no_stock_before integer,
    ADD COLUMN IF NOT EXISTS days_no_stock_after  integer;

COMMENT ON COLUMN price_recommendation_outcome.days_no_stock_before IS
    'Дней в базовом окне без товара (нулевой остаток и ноль продаж) — исключены из расчёта';
COMMENT ON COLUMN price_recommendation_outcome.days_no_stock_after IS
    'Дней в окне замера без товара — исключены из расчёта';

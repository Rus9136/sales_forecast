-- 039: приказы об изменении меню в iiko (автовыгрузка утверждённых цен).
--
-- До этой миграции путь «утверждено → цена в кассе» был ручным: менеджер
-- выгружал XLSX и вбивал цены в бэк-офис iiko. Отсюда две болезни:
--   1. цена доезжала через часы-дни или не доезжала совсем;
--   2. applied_at детектился «когда заметили в каталоге», а не «когда решили» —
--      окна before/after в замере эффекта плыли на несколько дней.
--
-- Теперь утверждённые рекомендации точки собираются в приказ
-- (POST /resto/api/v2/documents/menuChange) — тот же документ, что заводят
-- руками. Один приказ = одна точка × одна дата вступления в силу: так ведут
-- приказы в бэк-офисе и так же считается эффект пачки решений
-- (price_outcome_batch по department_id × applied_at).
--
-- Статусную машину price_recommendation НЕ трогаем: «отправлено в iiko» —
-- не статус рекомендации, а связь с приказом. applied по-прежнему ставит
-- detect_applied по факту каталога — это проверка «цена реально встала»,
-- а не «мы думаем, что отправили».

BEGIN;

CREATE TABLE IF NOT EXISTS price_change_order (
    id                   BIGSERIAL PRIMARY KEY,
    department_id        UUID NOT NULL REFERENCES departments(id),
    iiko_source_domain   TEXT NOT NULL,
    effective_date       DATE NOT NULL,           -- dateIncoming приказа
    -- draft: собран, но в iiko не ушёл
    -- sending: POST отправлен, ответ не получен (возможен документ-сирота)
    -- sent: документ создан, id получен
    -- failed: iiko отказал
    -- cancelled: отменён (DELETED в iiko либо обратным приказом)
    status               TEXT NOT NULL DEFAULT 'draft',
    iiko_status          TEXT,                    -- NEW | PROCESSED | DELETED (как в iiko)
    iiko_document_id     UUID,
    iiko_document_number TEXT,
    n_items              INTEGER NOT NULL DEFAULT 0,
    request_payload      JSONB NOT NULL,
    response_payload     JSONB,
    error_message        TEXT,
    -- обратный приказ, которым откатили этот (когда DELETE уже невозможен)
    reverses_order_id    BIGINT REFERENCES price_change_order(id),
    created_by           UUID,                    -- app_user.id
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    sent_at              TIMESTAMP,
    cancelled_at         TIMESTAMP,
    CONSTRAINT ck_price_order_status
        CHECK (status IN ('draft', 'sending', 'sent', 'failed', 'cancelled'))
);

-- Один живой приказ на точку и дату: повторный клик по кнопке не плодит
-- документы в iiko. failed/cancelled из-под уникальности выходят — после
-- неудачи можно собрать приказ заново на ту же дату.
CREATE UNIQUE INDEX IF NOT EXISTS uq_price_order_open
    ON price_change_order (department_id, effective_date)
    WHERE status IN ('draft', 'sending', 'sent');

CREATE INDEX IF NOT EXISTS idx_price_order_dept_date
    ON price_change_order (department_id, effective_date DESC);
CREATE INDEX IF NOT EXISTS idx_price_order_doc
    ON price_change_order (iiko_document_id) WHERE iiko_document_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS price_change_order_item (
    id                BIGSERIAL PRIMARY KEY,
    order_id          BIGINT NOT NULL REFERENCES price_change_order(id) ON DELETE CASCADE,
    recommendation_id BIGINT REFERENCES price_recommendation(id),
    product_id        BIGINT NOT NULL,
    iiko_product_id   UUID NOT NULL,
    -- old_price нужен для отката обратным приказом: восстанавливаем ровно ту
    -- цену, которая была базисом решения, а не «что сейчас в каталоге»
    old_price         NUMERIC(14, 2) NOT NULL,
    new_price         NUMERIC(14, 2) NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Одну рекомендацию нельзя отправить дважды. NULL допускается: позиции
-- обратного приказа рекомендацией не порождены.
CREATE UNIQUE INDEX IF NOT EXISTS uq_price_order_item_rec
    ON price_change_order_item (recommendation_id)
    WHERE recommendation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_price_order_item_order
    ON price_change_order_item (order_id);

ALTER TABLE price_recommendation
    ADD COLUMN IF NOT EXISTS order_id BIGINT REFERENCES price_change_order(id),
    ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_price_rec_order
    ON price_recommendation (order_id) WHERE order_id IS NOT NULL;

COMMIT;

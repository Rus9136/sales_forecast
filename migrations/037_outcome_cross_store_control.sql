-- 037: контроль «тот же товар в других точках» + честный интервал.
--
-- Разбор пилота 21.07.2026 показал, что прежняя контрольная группа («соседние
-- блюда той же категории в той же точке») непригодна принципиально:
--
--   1. Соседнее блюдо — конкурент. Подняли цену торта А — часть спроса ушла на
--      Б. Значит Б задет нашим решением и не может изображать «что было бы,
--      если бы мы ничего не делали». Контроль обязан быть НЕ затронут.
--   2. Хвост ассортимента кондитерской крутится: из 34 «контрольных» тортов 21
--      во втором окне не продался ни разу, 7 появились только там. Их «падение
--      на 11%» — ротация выпечки, а не спрос.
--   3. 111 штук за две недели на 34 позиции: собственный шум контроля больше
--      измеряемого эффекта.
--
-- Цена ошибки: старый контроль давал +261 531 ₸ там, где корректный расчёт
-- даёт −41 113 ₸ при интервале −365 000 … +190 000 ₸.
--
-- Новый контроль — тот же SKU в других точках той же концепции (iiko-домен),
-- где цену не меняли. Сравнение трёхслойное: позиция у нас ÷ тот же товар по
-- сети ÷ наша точка целиком по сети.
--
-- Концепции считаются раздельно: Madlen (кофейни с тортами) и Sandyq
-- (рестораны с блюдами) живут в разных доменах, и динамика одной не годится
-- в опору для другой. Колонка concept позволяет резать эффект по концепциям.
--
-- Интервал считается перетасовкой дней (bootstrap): формулы Пуассона врут,
-- потому что в продажах сидят выходные, зарплатные дни и погода.

ALTER TABLE price_recommendation_outcome
    ADD COLUMN IF NOT EXISTS control_method        TEXT,
    ADD COLUMN IF NOT EXISTS measurable            BOOLEAN,
    ADD COLUMN IF NOT EXISTS not_measurable_reason TEXT,
    ADD COLUMN IF NOT EXISTS n_control_stores      INTEGER,
    ADD COLUMN IF NOT EXISTS control_qty_before    NUMERIC(14, 3),
    ADD COLUMN IF NOT EXISTS control_qty_after     NUMERIC(14, 3),
    ADD COLUMN IF NOT EXISTS control_trend         NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS store_trend_adj       NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS effect_ci_low         NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS effect_ci_high        NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS p_negative            NUMERIC(5, 4),
    ADD COLUMN IF NOT EXISTS concept               TEXT;

COMMENT ON COLUMN price_recommendation_outcome.control_method IS
    'cross_store — тот же товар в других точках; none — контроль не собран';
COMMENT ON COLUMN price_recommendation_outcome.measurable IS
    'Прошли ли ворота качества. false = эффект не оценивался; NULL в incremental_delta_gp — это отсутствие оценки, а не ноль';
COMMENT ON COLUMN price_recommendation_outcome.control_trend IS
    'Тренд того же товара по другим точкам концепции (в расчёте на точко-день)';
COMMENT ON COLUMN price_recommendation_outcome.store_trend_adj IS
    'Поправка на тренд самой точки против сети — чтобы слабый месяц точки не записался в минус решению о цене';
COMMENT ON COLUMN price_recommendation_outcome.effect_ci_low IS
    'Нижняя граница 90% интервала эффекта (перетасовка дней)';
COMMENT ON COLUMN price_recommendation_outcome.p_negative IS
    'Доля перетасовок, где эффект вышел отрицательным';
COMMENT ON COLUMN price_recommendation_outcome.concept IS
    'iiko-домен точки: разделяет Madlen (кофейни) и Sandyq (рестораны) для раздельного замера';
COMMENT ON COLUMN price_recommendation_outcome.n_control_skus IS
    'Устарело с миграции 037: теперь дублирует n_control_stores (контроль считается по точкам, не по соседним SKU)';

-- Пачка решений = один приказ по точке. Отдельный штучный торт неизмерим почти
-- всегда (1–2 шт/день), а пачка — измерима. Интервал по пачке нельзя получить
-- сложением интервалов позиций: дни у них общие, ошибки скоррелированы, поэтому
-- перетасовка гоняется совместно по всем позициям приказа.
CREATE TABLE IF NOT EXISTS price_outcome_batch (
    id                BIGSERIAL PRIMARY KEY,
    department_id     UUID NOT NULL REFERENCES departments(id),
    applied_at        DATE NOT NULL,
    concept           TEXT,
    eval_window_days  INTEGER NOT NULL,
    n_positions       INTEGER NOT NULL,
    n_measurable      INTEGER NOT NULL,
    gp_before         NUMERIC(14, 2),
    gp_after          NUMERIC(14, 2),
    actual_delta_gp   NUMERIC(14, 2),
    expected_delta_gp NUMERIC(14, 2),
    effect_gp         NUMERIC(14, 2),
    effect_ci_low     NUMERIC(14, 2),
    effect_ci_high    NUMERIC(14, 2),
    p_negative        NUMERIC(5, 4),
    created_at        TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_price_outcome_batch UNIQUE (department_id, applied_at, eval_window_days)
);

CREATE INDEX IF NOT EXISTS idx_price_outcome_batch_concept
    ON price_outcome_batch (concept, applied_at DESC);

COMMENT ON TABLE price_outcome_batch IS
    'Эффект приказа целиком (точка × дата применения) с совместным интервалом — главная цифра пилота';

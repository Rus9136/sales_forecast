-- Откат подтверждённо убыточного ценового решения + хранение интервала эффекта.
--
-- ЗАЧЕМ ИНТЕРВАЛ В ТАБЛИЦЕ.
-- Оценщик (pricing_effect.PriceEffectEstimator.estimate) уже считает интервал
-- и P(минус) для каждой позиции, но на строку outcome они не пишутся — их
-- заново пересчитывает отчёт «Эффект решений». В результате единственным
-- «признаком значимости», доступным интерфейсу и триггерам, остаётся
-- significance_z, а он считается через ПУАССОНОВСКУЮ ошибку SE = √Σ(1/n)
-- (миграция 036, до перехода на контроль по другим точкам) и исходит из того,
-- что продажи — ровный поток. Bootstrap-интервал систематически шире, и они
-- расходятся в обе стороны:
--   * мин. вода Бонаква, Аэропорт: z = 3.64 «значимо», интервал
--     [-29 322 … +128 863] накрывает ноль;
--   * комбо «Крафт бургер», Kainar: z = 1.95 «не значимо», интервал
--     [+17 948 … +245 966] плюс подтверждает.
-- Строить на z триггер отката нельзя — поэтому интервал переезжает в таблицу.
--
-- ЗАЧЕМ ОТКАТ.
-- Сегодня движок физически не может предложить снижение цены:
--   * в generate_experiments строка `if target <= current_price:
--     target = current_price + step` переворачивает любое снижение в повышение;
--   * возврат к прежней цене отсекается правилом rounding — исходные цены
--     (430, 810, 1010, 1360, 1990, 2890 ₸) не кратны шагу 50;
--   * при |ε| < 1 прибыль монотонно растёт по цене, внутреннего оптимума нет,
--     и grid search обязан выбрать верхний край коридора (92.6% рекомендаций).
-- rec_type='rollback' — отдельный тип решения с целью «прежняя цена»:
-- нулевой бизнес-риск (цена уже работала) и A→B→A для замера, то есть третий
-- ценовой режим и второй DiD в обратную сторону.

BEGIN;

-- 1. Интервал эффекта на строке результата ------------------------------------
ALTER TABLE price_recommendation_outcome
    ADD COLUMN IF NOT EXISTS effect_ci_low  numeric(14, 2),
    ADD COLUMN IF NOT EXISTS effect_ci_high numeric(14, 2),
    ADD COLUMN IF NOT EXISTS p_negative     numeric(5, 4);

COMMENT ON COLUMN price_recommendation_outcome.effect_ci_low IS
    'Нижняя граница эффекта, bootstrap перетасовкой дней, 90%. Вердикт — по интервалу, не по significance_z';
COMMENT ON COLUMN price_recommendation_outcome.effect_ci_high IS
    'Верхняя граница эффекта. effect_ci_high < 0 = минус доказан для позиции';
COMMENT ON COLUMN price_recommendation_outcome.p_negative IS
    'Доля bootstrap-прогонов с отрицательным эффектом';
COMMENT ON COLUMN price_recommendation_outcome.significance_z IS
    'УСТАРЕЛО: пуассоновская z-оценка (SE = sqrt(sum(1/n))), не учитывает выходные/погоду. '
    'Оставлено для совместимости; для вердикта использовать effect_ci_low/high';

-- позиции с доказанным минусом — рабочая выборка триггера отката
CREATE INDEX IF NOT EXISTS idx_outcome_proven_negative
    ON price_recommendation_outcome (department_id, product_id)
    WHERE effect_ci_high < 0;

-- 2. Тип решения «откат» ------------------------------------------------------
ALTER TABLE price_recommendation DROP CONSTRAINT IF EXISTS chk_rec_type;
ALTER TABLE price_recommendation ADD CONSTRAINT chk_rec_type
    CHECK (rec_type IN ('optimizer', 'experiment', 'rollback'));

ALTER TABLE price_recommendation
    ADD COLUMN IF NOT EXISTS reverses_recommendation_id bigint
        REFERENCES price_recommendation(id);

COMMENT ON COLUMN price_recommendation.reverses_recommendation_id IS
    'Какое решение откатывает эта строка. recommended_price = current_price исходного решения';

-- один незакрытый откат на исходное решение: без этого повторный прогон
-- generate_rollbacks плодил бы дубли (uq_price_rec_open ловит только status='new')
CREATE UNIQUE INDEX IF NOT EXISTS uq_rollback_open
    ON price_recommendation (reverses_recommendation_id)
    WHERE reverses_recommendation_id IS NOT NULL
      AND status IN ('new', 'approved', 'applied');

CREATE INDEX IF NOT EXISTS idx_rec_rollback_cooldown
    ON price_recommendation (department_id, product_id, applied_at)
    WHERE rec_type = 'rollback' AND status = 'applied';

COMMIT;

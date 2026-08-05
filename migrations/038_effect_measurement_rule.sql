-- 038: окно замера эффекта — настройка вместо константы в коде.
--
-- Было: EVAL_WINDOW_DAYS = 14 в pricing_feedback_service.py, причём база
-- бралась той же длины симметрично назад. Поменять 14 на 30 «в лоб» нельзя:
-- база уехала бы до 21 июня и захватила волну переоценок 26.06–04.07 (цены на
-- пилотные позиции тогда правили в 16–25 точках). Контрольные точки
-- исключаются при изменении цены внутри периода — контроль обнулился бы:
-- проверено, 0 контрольных точек по всем 18 позициям пилота.
--
-- Поэтому длина базы и длина окна замера разделены. База остаётся на «тихом»
-- участке, окно замера удлиняется вперёд — контроль при этом сохраняется
-- полностью (13 точек в среднем и при 30, и при 56 днях).
--
-- Что именно даёт удлинение (замерено на пилоте):
--   * окно замера 7→14 дней: точность на день не изменилась (±21,6к → ±19,1к),
--     точечная оценка гуляла — растёт и сумма, и её ошибка пропорционально;
--   * база 7→14 дней на одном наборе позиций: интервал сузился на 19%
--     (±197к → ±160к) при устойчивой оценке.
-- Точность даёт база, а не длина замера: контрфакт привязан к среднесуточной
-- базе, и её шум умножается на каждый день окна.
--
-- Scope только global: разные окна по точкам сделали бы результаты
-- несравнимыми между собой.

ALTER TABLE pricing_rule DROP CONSTRAINT IF EXISTS chk_rule_type;
ALTER TABLE pricing_rule ADD CONSTRAINT chk_rule_type CHECK (
    rule_type = ANY (ARRAY[
        'min_margin', 'max_step', 'min_frequency', 'no_decrease_anchor',
        'min_competitive_idx', 'rounding', 'no_psychological', 'stop_list',
        'max_changes_per_cycle', 'effect_measurement'
    ])
);

INSERT INTO pricing_rule (rule_type, scope_type, scope_id, params, configured_by_role)
VALUES ('effect_measurement', 'global', NULL,
        '{"eval_days": 14, "baseline_days": 14}'::jsonb, 'pricing_analyst')
ON CONFLICT (rule_type, scope_type, scope_id) DO NOTHING;

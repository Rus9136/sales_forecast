-- 036: честная оценка эффекта applied-рекомендаций.
--
-- Причина: пилот 2026-07-21 на «Мадлен 18 мкр» показал +172к ₸ ΔGP за две
-- недели при ожидании +83к. Разбор нашёл две систематические ошибки:
--
--   1. Точка не работала 12 июля — базовое окно содержало 13 рабочих дней
--      против 14 в оценочном. Любое сравнение «после/до» завышалось на ~7.7%.
--   2. actual_delta_gp = gp_after - gp_before считался БЕЗ поправки на
--      контрольную группу, хотя сама контрольная группа для этого уже
--      собиралась (control_qty_change_pct). Фон категории (-4% по тортам,
--      -14% по пирожным) в деньги не попадал.
--
-- Что меняет миграция:
--   * days_before / days_after — фактические рабочие дни точки в каждом окне;
--   * counterfactual_qty — сколько бы продали за оценочное окно по старой цене
--     (база × динамика контрольной группы), в пересчёте на рабочие дни;
--   * incremental_delta_gp — эффект решения о цене = GP факт − GP контрфакта;
--   * significance_z — z-оценка разности разностей (Пуассон/дельта-метод).
--     |z| < 2 означает, что эффект неотличим от шума и на нём нельзя строить
--     выводы — критично для штучных тортов с продажами 0.2–2 шт/день.
--
-- Семантика существующих колонок:
--   * qty_change_pct / control_qty_change_pct теперь считаются по СРЕДНЕСУТОЧНОЙ
--     скорости продаж, а не по сырым суммам окон (иначе разное число рабочих
--     дней искажает каждую в отдельности);
--   * adj_qty_change_pct и realized_elasticity не меняются численно — дневные
--     множители сокращаются в отношении отношений;
--   * actual_delta_gp теперь приведён к равному числу дней:
--     gp_after − gp_before × (days_after / days_before). Это по-прежнему «что
--     произошло в кассе», без вычета фона;
--   * gp_before / gp_after остаются сырыми суммами своих окон.

ALTER TABLE price_recommendation_outcome
    ADD COLUMN IF NOT EXISTS days_before          INTEGER,
    ADD COLUMN IF NOT EXISTS days_after           INTEGER,
    ADD COLUMN IF NOT EXISTS counterfactual_qty   NUMERIC(12, 3),
    ADD COLUMN IF NOT EXISTS incremental_delta_gp NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS significance_z       NUMERIC(8, 4);

COMMENT ON COLUMN price_recommendation_outcome.days_before IS
    'Рабочих дней точки в базовом окне (дни с продажами по подразделению)';
COMMENT ON COLUMN price_recommendation_outcome.days_after IS
    'Рабочих дней точки в оценочном окне';
COMMENT ON COLUMN price_recommendation_outcome.counterfactual_qty IS
    'Штук за оценочное окно, если бы цену не меняли (база × фон контрольной группы)';
COMMENT ON COLUMN price_recommendation_outcome.incremental_delta_gp IS
    'Эффект решения о цене: GP факта − GP контрфакта. Основная метрика пилота';
COMMENT ON COLUMN price_recommendation_outcome.significance_z IS
    'z-оценка разности разностей; |z| < 2 — эффект неотличим от шума';
COMMENT ON COLUMN price_recommendation_outcome.actual_delta_gp IS
    'Изменение GP по кассе, приведённое к равному числу рабочих дней. Фон категории НЕ вычтен — для эффекта решения см. incremental_delta_gp';

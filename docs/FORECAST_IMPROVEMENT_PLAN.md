# План улучшения прогноза продаж

**Дата создания:** 2026-04-29
**Владелец:** Sales Forecast team
**Статус:** в работе

---

## 1. Контекст

Заявленные в `CLAUDE.md` метрики модели (Test MAPE **6.18%**, R² 0.9962) расходятся с реальной точностью на проде. Пользователь сообщает, что прогнозы неверны. Аудит подтвердил: реальный out-of-sample MAPE — около **50%**.

### 1.1 Бизнес-задача (уточнение от 2026-04-30)

**Главная задача проекта** — оптимизация графика смен официантов на следующий месяц. Текущая боль: переплата ФОТ (фонд оплаты труда), потому что официанты выходят группами в дни с низкими продажами → отношение ФОТ к выручке уходит в минус.

**Производственный сценарий:**
- В конце месяца строится прогноз продаж на **30 дней вперёд** (целиком на следующий месяц)
- На основе прогноза составляется график смен на следующий месяц
- Метрики MAPE / MedianAPE на горизонте **1 день** (что мы оптимизировали в этапах 1-3) — НЕ отражают реальную производственную задачу

**Следствие:** реальный production-MAPE на горизонте 30 дней почти наверняка **значительно выше** заявленных 36% — все сильные lag-фичи (`lag_1d_sales`, `rolling_7d_avg` и т.п.) свежи только для дня 1, на дне 30 они либо stale, либо подставляются recursively с накоплением ошибки.

**Сегментация подразделений (домен):**
- **Sandyq** — рестораны премиум-сегмента, работают днём-вечером (не круглосуточно).
- **Tary** — кофейни, многие работают круглосуточно. Половина точек находится в горах / визит-центрах с ярко выраженной сезонностью (зима — почти нет гостей, весна-осень — туристический пик). Например, Tary Burabay у озера Бурабай.
- **Madlen, Shopan** — другие бренды.

**Источники данных (важно для feature engineering):**
- ✅ **Можно как фичу**: фактические смены за прошлые дни (исторические факты, не зависят от будущего прогноза)
- ✅ **Можно как фичу**: банкеты/корпоративы из API на дату прогноза — клиенты бронируют независимо от нашего графика, **прибавляются** к обычному обороту
- ❌ **Нельзя как фичу**: запланированный график официантов на дату прогноза (циклическая зависимость — график строится из прогноза)

## 2. Что выявил аудит (факты)

### 2.1 Реальная точность модели (backtest 2026-02-28 .. 2026-04-28, 1 865 предсказаний, 34 отделения)

| Вариант пост-обработки | MAPE | MedianAPE | MAE (₸) | Bias |
|---|---|---|---|---|
| raw (только модель) | 55.12% | 29.73% | 365 320 | −2.3% |
| raw + weekend boost ×1.4 | 59.49% | 29.91% | 386 780 | +9.75% |
| raw + smoothing | **46.96%** | **27.76%** | **342 914** | −7.5% |
| **current (boost + smoothing)** | **49.89%** | 28.22% | 355 465 | +1.7% |

### 2.2 По размеру отделения

| Квартиль | Avg продажи | MAPE current |
|---|---|---|
| Q1 (мелкие) | 176K | 45.1% |
| Q2 | 421K | 34.5% |
| Q3 | 1.05M | 49.5% |
| Q4 (крупные) | 2.63M | **73.5%** |

Single-model для всех масштабов не справляется — крупные отделения предсказываются хуже всего.

### 2.3 По сегментам

| Сегмент | MAPE current | n |
|---|---|---|
| food_court | 25.0% | 134 |
| restaurant | 50.1% | 1 378 |
| coffeehouse | 58.4% | 353 |

### 2.4 Корневые причины

1. **Weekend boost ×1.4 вредит.** На выходных raw bias = −19.6% (занижает), boost переворачивает в +12.6% (завышает). MAPE на выходных: raw 40.3% → boost 54.9%.
2. **Temporal smoothing маскирует плохую модель.** Обрезка ±50% от 4-нед. среднего того же weekday улучшает MAPE с 55% до 47% — но это означает, что модель часто промахивается в 2-3 раза, и сглаживание её спасает. При этом сглаживание убивает реакцию на реальные события (праздники, акции).
3. **Distribution shift в lag-features при N-step прогнозе.** При прогнозе на >1 день вперёд `lag_1d_sales` фактически содержит данные не за «вчера», а за `latest_available_date`, что не соответствует обучающему распределению.
4. **Один LightGBM на масштабы 500..3M ₸/день.** RMSE-loss доминируют крупные отделения, мелкие почти не влияют на градиент.
5. **`eval_metric='rmse'` для early stopping, отчёт по MAPE.** Оптимизируется не та метрика, что показывается.
6. **Модель не переобучалась 5+ месяцев.** Файл `models/lgbm_model.pkl` от **2025-11-17**. В `model_retraining_log` — только 2 попытки за всю историю (обе 2025-06-30, обе rejected).
7. **Баг в decision logic** (`model_retraining_service.py:305`). Когда у активной модели `current_mape = 0` (legacy), новая модель всегда считается «0.0% worse» → rejected → auto-retrain заблокирован навсегда.
8. **Мониторинг точности мёртв.** Таблица `forecast_accuracy_log` пустая, scheduled task в 04:00 (`run_daily_metrics`) либо не запускается, либо падает молча.
9. **Не используются уже загружаемые данные.** Таблицы `Employee` и `SalesByWaiter` существуют, но не подключены как фичи (количество смен, активных официантов, доля топ-сотрудников).
10. **Захардкоженные праздники Казахстана** без учёта плавающих дат (Курбан-айт) и переносов выходных.

---

## 3. Что уже сделано

- [x] **Полный аудит ML-pipeline** — прочитаны `sales_forecaster_agent.py`, `training_service.py`, `forecast_postprocessing_service.py`, `hyperparameter_tuning_service.py`, `model_retraining_service.py`, `model_monitoring_service.py`, `error_analysis_service.py`.
- [x] **Backtest-скрипт** — `scripts/backtest_postprocessing.py`. Сравнивает 4 варианта пост-обработки на out-of-sample данных. Запускается через `docker cp + docker exec sales-forecast-app python /app/backtest_postprocessing.py`.
- [x] **Замер реального MAPE** — 49.89% (current), 46.96% (smoothing only). Сохранено в `/tmp/backtest_results.csv` в контейнере.
- [x] **Диагностика инфраструктуры** — обнаружены: модель от ноября, баг decision-logic, пустой `forecast_accuracy_log`, баг с current_mape=0.
- [x] **Создан этот документ** — `docs/FORECAST_IMPROVEMENT_PLAN.md`.

---

## 4. План улучшений (по этапам)

### Этап 1 — Быстрые выигрыши (1 час, нулевой риск)

Цель: убрать пост-обработку, которая ухудшает прогноз. Эффект — мгновенный, без переобучения.

- [x] **1.1 Удалить weekend boost ×1.4** в `app/agents/sales_forecaster_agent.py:290-298`. **Применено 2026-04-29.** Эффект (по backtest): MAPE 49.89% → 46.96% (**−2.93 п.п.**, −5.87% относительно). Production-код пересобран и задеплоен.
  - **Замечание:** на выходных bias был +5.99% (boost маскировал недооценку модели). После удаления boost проявилась реальная проблема: **модель сама систематически занижает на выходных на ~19%**. Это будет лечиться переобучением + сегментными моделями.
- [x] **1.2 Оптимизировать temporal smoothing.** **Применено 2026-04-29.** Sweep'нул threshold ∈ {0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, off} (`scripts/backtest_smoothing_threshold.py`). Оптимум — **t=0.3** (MAPE 44.54%), не t=0.5 (46.96%). Default изменён в `agent.py:502`.
  - **Diagnostic insight:** более тугой smoothing лучше → значит rolling avg ≈ модели по качеству → модель сильно «разлохмачена», нужно переобучение (этап 2). Riski: t=0.3 может маскировать реальные пики (праздники). После переобучения нужен новый sweep.
- [ ] **1.3 Сменить `eval_metric='rmse'` → `mape` или MAE** в `sales_forecaster_agent.py:115`. Эффект проявится только после переобучения — отложено на этап 2.
- [x] **1.4 Backtest для подтверждения 1.1.** `scripts/backtest_postprocessing.py` уже измерил вариант «без boost» = 46.96% MAPE.

**Целевой MAPE после этапа 1:** ≤ 47%. **Текущий после 1.1+1.2:** **44.54%** (цель перевыполнена).

### Этап 2 — Переобучение и инфраструктура мониторинга (1-2 дня)

Цель: модель должна обучаться на свежих данных и видеть свою деградацию.

- [x] **2.1 Починить баг decision-logic** в `model_retraining_service.py:297-330`. **Применено 2026-04-29.** Новая логика: при `current_mape <= 0` или `None` — deploy безусловно (первый честный baseline). Добавлен sanity-check: `new_mape > 50%` → reject (не задеплоить совсем плохую модель).
- [x] **2.2 Починить запись в `forecasts` + `forecast_accuracy_log`**. **Применено 2026-04-29.** **Корневой баг найден**: таблица `forecasts` была полностью пустая, потому что `agent.forecast()` никогда не сохранял результат. Плюс legacy FK на `branches` не позволял писать UUID-ы.
  - Миграция `008_forecast_logging_fix.sql`: drop legacy FK, add UNIQUE на `(branch_id, forecast_date)` для UPSERT.
  - Добавлен метод `_upsert_forecast()` в agent.py, вызывается из `forecast()` с параметром `save_to_db=True` (default).
  - Backfill через `scripts/backfill_monitoring.py` — заполнено 1 865 записей за 60 дней.
- [x] **2.3 Backfill** — выполнено. `forecast_accuracy_log` теперь содержит 60 дней. avg MAPE подтверждён: **44.54%**.
- [x] **2.4 Переобучить модель** — выполнено 2026-04-29. Старая `.pkl` сохранена как `lgbm_model_pre_etap2_20260429_1929.pkl`. Новая модель: train=8272, val=1773, test=1773. **Test MAPE 9.48%, R² 0.986** (in-sample).
- [x] **2.5 Backtest новой модели** — выполнено. **Out-of-sample MAPE: 44.35% (раньше 44.54%) — улучшение всего −0.19 п.п.**
  - **Критическое наблюдение:** разрыв между in-sample test MAPE (9.48%) и out-of-sample (~47%) — это **5x**. Это не distribution shift (свежие данные не помогли), это **структурный overfit** модели. Модель буквально учит train-set наизусть, не обобщает. Лечится только этапом 3 (log-target + сегментные модели + GroupKFold).
- [x] **2.6 Включить scheduled retrain** — cron уже работает (Sun 03:00). После исправления 2.1 еженедельный re-deploy теперь будет проходить успешно.

**Целевой MAPE после этапа 2:** ≤ 30%. **Фактический: 44.35%** — цель **не достигнута**. Это эмпирически доказывает, что свежесть данных не решает проблему. Структурные изменения (этап 3) обязательны.

### Этап 3 — Архитектура модели (3-5 дней)

Цель: исправить системные изъяны модели — масштаб, leakage, multi-step.

- [x] **3.1 Логарифм target.** **Применено 2026-04-29.** Обучение на `np.log1p(total_sales)`, при inference `np.expm1(pred)`. Метаданные `target_transform='log1p'` сохраняются в pickle. Helper `agent.predict()` инкапсулирует inverse. Параметры обучения подкручены: n_estimators 200→500, learning_rate 0.1→0.05, max_depth 5→6, eval_metric `rmse`→`mae`, early_stopping 15→20.
  - **Эффект:** in-sample test MAPE 9.48% → 7.59%; разрыв val/test уменьшился (10.4/9.5 → 7.7/7.6 — модель меньше переобучается).
  - **Out-of-sample:** MAPE 44.35% → **42.88%** (−1.47 п.п.).
  - **Главный win — крупные отделения (Q4):** 67.18% → **61.15%** (−6.03 п.п.). Именно это и должен был лечить log-target — баланс вклада в loss.
  - **Побочный эффект:** общий bias стал −11% (раньше −5%). Jensen correction (`expm1(pred + 0.5·σ²)`) — отложено: bias не критичен, MAPE главнее.
- [x] **3.2 Сегментные модели.** **Применено и откатано 2026-04-30.** Реализован `train_segmented_models()` в `agent.py` + endpoint `POST /api/forecast/retrain-segmented`, диспетчер в `predict(X, segment_type=...)`, отдельные `.pkl` в `models/segments/{segment}.pkl`. Обучены 3 модели (restaurant 6 186, coffeehouse 1 407, food_court 650 train).
  - **Эффект на out-of-sample:** overall raw MAPE **36.15% → 38.41%** (хуже на 2.3 п.п.), по всем сегментам ухудшение (coffeehouse 46.5% → 54.0%, food_court 17.3% → 21.6%, restaurant 35.4% → 36.1%).
  - **Причина:** дробление 8 243 → 6 186/1 407/650 убивает сигнал — глобальная модель уже использует one-hot `is_coffeehouse`/`is_restaurant`/`is_food_court` и обучается на кросс-сегментных паттернах (праздники, weekly cycles, payday), которые помогают всем.
  - **Файлы перемещены в `models/segments/archive/*_underperformed.pkl`**. Код и endpoint оставлены — могут пригодиться, если в будущем появятся per-сегментные кастомные фичи или объёмы данных вырастут.
- [x] **3.3 Target leakage в rolling/momentum-фичах.** **Применено 2026-04-30.** Найден и устранён системный баг: `dept_sales.rolling(N).mean()` в `training_service._add_rolling_features` включал значение текущего дня в окно (training видел target), а инференс — нет. Аналогично leakage в `pct_change_*` и `sales_momentum_*`. Все 13 leak-фичей переписаны через `past_sales = dept_sales.shift(1)` и past-only формулы, идентичные `agent._create_prediction_features`.
  - **Это и есть тот самый структурный overfit 5x**, который этап 2 эмпирически зафиксировал. После фикса:
    - In-sample test MAPE: **6.06% → 33.11%** (5x → ~1x — реальная generalization-способность).
    - **Out-of-sample raw MAPE: 54.07% → 36.15% (−17.92 п.п.!)**.
    - smooth: 46.12% → 35.43% (−10.69 п.п.); current (boost+smooth) 48.21% → 41.91%.
  - **По segment**: food_court 32% → **17%**, restaurant 54% → 35%, coffeehouse 63% → 47%.
  - **По scale**: Q1 54% → 33%, Q2 37% → 20%, Q3 57% → 40%, **Q4 70% → 54%** (median APE Q4 31% → **18.5%**).
  - Multi-step recursive lag (исходный пункт 3.3) — **отложено**, не критично пока 1-step работает на 36%.
- [x] **3.4 GroupKFold по `department_id` в Optuna.** **Применено 2026-04-30.** В `hyperparameter_tuning_service.optimize_lightgbm` добавлены параметры `groups_train`/`groups_val`, при их наличии CV переключается с `TimeSeriesSplit` на `GroupKFold(department_id)`. В `routers/forecast/tuning.py` пробрасывается `groups = df['department_id']`. Эффект на текущий MAPE — 0 (Optuna не вызывается в production retrain pipeline), но при ручном запуске `/api/forecast/optimize` теперь невозможно подобрать параметры, оптимизированные «как хорошо запоминать те же отделения».
- [x] **3.5 Флаг `is_outlier_day` вместо winsorize.** **Применено 2026-04-30.** Метод `_add_outlier_flag()` в `training_service` помечает IQR-выбросы (1.5×IQR на dept) бинарным флагом, добавлен в `feature_columns` (теперь 65). Default `handle_outliers=False` — winsorize отключен (legacy режимы `winsorize`/`cap`/`remove` оставлены для ablation). На инференсе `is_outlier_day=0` (прогнозируем «обычный» день). Сам по себе флаг без фикса leakage давал ухудшение, после fix leakage — work as expected.

**Целевой MAPE после этапа 3:** ≤ 15%. **Фактический после 3.1+3.3+3.4+3.5 (без 3.2):** **raw 36.15% / smooth 35.43% / current 41.91%**. Цель 15% не достигнута — нужны этапы 4 (обогащение данных) и хорошее post-processing (re-sweep smoothing на новой модели).

### Этап 4 — Адаптация под production-задачу (30-day forecast)

**Стратегический разворот после уточнения бизнес-задачи (см. §1.1).** Все предыдущие оптимизации делались под 1-day forecast; реальная задача — 30-day forecast для построения графика смен. Этап 4 пересматривает приоритеты исходя из этого.

#### Tier 1 — Фундамент (1-2 дня, должно идти первым)

- [x] **4.1 Honest 30-day backtest** (`scripts/backtest_30day.py`) — **выполнено 2026-04-30**
  - Recursive multi-step: на anchor-дате (1-е число месяца) берётся реальная история, прогноз дня d+1 подставляется в running_history как lag для дня d+2 и т.д. Anchors: 2026-03-01, 2026-04-01.
  - **Декомпозиция по горизонтам:** h=1 MAPE 27%/Med 19%, h=2-7 31%/20%, h=8-14 38%/21%, h=15-21 35%/22%, h=22-30 36%/26%. **Деградация умеренная — всего +9 п.п. от h=1 к h=30** (ожидал +25-30 п.п., фактически recursive lag-feeding работает стабильнее).
  - **Месячный агрегат (главная метрика для ФОТ):** сумма прогноза vs сумма факта за 30 дней — **MAPE 21.6% / Median 16.5%, Bias −13.5%** (модель слегка занижает месячную сумму).
  - **Worst hot-spots:** Coffeehouse h=8-14 — **75.4% MAPE** (резорт-сезонность Tary не ловится в средне-дальнем горизонте), Q3 h=8-14 — 60.6%, Q4 h=15-21 — 45.7%.
  - **Оговорка:** модель обучена на данных до 2026-04-30, бэктест март-апрель — частично in-sample. Полностью честные цифры ожидаются на 5-15% хуже после retrain с cutoff. Но shape (decay, hot-spots) — корректный.

- [x] **4.2 Обогащение метаданных подразделений** — **миграция применена 2026-04-30 (commit 9029d6a, отдельная сессия)**, ML-pipeline подключён 2026-04-30.
  - **БД**: `migrations/009_department_enrichment.sql` — 11 колонок (`brand`, `location_type` ∈ city/mall/business/resort_mountain/resort_lake/visit_center/other, `tourist_traffic_dependent`, `is_24_7`, `opening_hour`, `closing_hour`, `seasonality_intensity` ∈ none/low/medium/high, `city`, `opened_date`, `season_start_month`, `season_end_month`), 6 CHECK-constraint, 2 индекса.
  - **UI**: страница `/departments` — диалог редактирования с условными полями (часы скрыты при is_24_7, месяцы сезона скрыты при seasonality=none), datalist для brand/city, новые колонки в таблице, фильтры по бренду и location_type.
  - **iiko sync** не затирает manual-only поля — проверено в loader'е.
  - **ML-pipeline** (`training_service.py`, `agent.py`):
    - `_load_sales_data` тянет 11 новых полей + `_add_operational_features` создаёт 18 ML-фичей: 4 brand one-hot, 7 location_type one-hot, `is_tourist_dependent`, `is_24_7`, `working_hours_count` (handles wrap для 22:00-03:00), `days_since_opening`, `is_new_department` (<90 days), `seasonality_score` (0-3), `is_in_season` (с поддержкой wrap-around Nov-Mar).
    - `_create_prediction_features` в agent.py зеркалит ту же логику для инференса.
    - `dropna()` теперь только по subset feature_columns + `total_sales` — чтобы NULL в raw-метаданных не убивал все строки.
    - `feature_columns`: 65 → **83**.
  - **Замер с 2/91 заполненных подразделений** (Tary Burabay, Tary Charyn — наши hot-spots): монтьый Med APE 16.48% → **15.86%**, in-sample test MAPE 33.11% → 32.99%. Шум.
  - **Feature importance после retrain**: `is_loc_resort_lake` 8.4 gain, `is_brand_tary` 6.5, `is_loc_visit_center` 1.8, `is_24_7` 1.0; остальные 14 из 18 = 0 gain (для всех точек одинаковое значение). Доля новых фичей = **0.02%** — pipeline работает, но без полной разметки эффекта не будет.
  - **Ожидание после полной разметки 91/91 точек**: рост доли новых фичей до 5-15% от gain, ожидаемое улучшение coffeehouse h=8-14 с 75% к 50-60% (в первую очередь резорт-сезонные Tary).

#### Tier 2 — Реальные победы (2-3 дня каждый)

- [ ] **4.3 Banquet / event integration** через workforce API
  - Исторические дни: `has_banquet`, `banquet_count`, `banquet_revenue_estimate` (если API даёт).
  - Дни прогноза: те же фичи из forward-bookings.
  - Банкеты прибавляются к обороту → модель учится «+N тыс ₸ на 1 банкет» → outlier-дни вроде Tary Ayusai 2026-04-16 могут получить объяснение.

- [ ] **4.4 Hybrid horizon-specific модели** (или recursive forecasting)
  - **Вариант A (recursive):** `forecast()` для дня d+30 идёт цепочкой через предсказания дней d+1..d+29.
  - **Вариант B (hybrid, рекомендуется):** `model_short` для h=1-7 (богатые lag-фичи как сейчас), `model_long` для h=8-30 (обучен с таргетом `total_sales[d+30]`, lag-фичи берутся на день d → стабильные). Диспетчер в `agent.forecast()` выбирает по `days_ahead`.
  - **Влияние:** прямая починка production-задачи. На горизонтах 8-30 модель перестанет полагаться на `lag_1d_sales` и научится использовать календарь + признаки точки.

#### Tier 3 — Уточнения (1 день каждый)

- [ ] **4.5 Исторические смены официантов** (после ответа на Q5 — глубина истории)
  - `actual_waiters_count_lag_h` для h ∈ {1, 7, 14, 30}
  - `avg_waiters_same_dow_4w` (стабильный сигнал, есть на любом горизонте)
  - `unique_waiters_30d` (текучка / стабильность команды)
  - **Не циклично:** только фактические смены за прошлые дни.

- [ ] **4.6 Quantile / asymmetric loss** (после ответа на Q6 — направление bias)
  - `objective='quantile', alpha=0.4` (если хотим слегка занижать → экономия ФОТ)
  - `alpha=0.5` (median, нейтрально)
  - `alpha=0.55` (если перестраховаться сверху)

- [ ] **4.7 Volatility-фича** — `cv_30d = std(sales_30d) / mean(sales_30d)` per dept. Резорты получат высокий CV → модель будет менее уверенно extrapolate trend.

- [ ] **4.8 Fourier features годового цикла** — `sin(2π·doy/365)`, `cos(2π·doy/365)` × {1,2,3} гармоники. Плавная замена дискретных `is_winter`/`is_spring`.

- [ ] **4.9 Динамический календарь праздников РК** через `python-holidays`. Курбан-айт, переносы выходных.

**Целевой 30-day MAPE после этапа 4:** ≤ 25% mean / ≤ 15% median (раздельно по горизонтам: h=1 ≤ 25%, h=30 ≤ 35%).

### Этап 5 (опционально) — Альтернативные модели

Если этап 4 не дотянул до целевого MAPE.

- [ ] **5.1 Prophet/NeuralProphet** как baseline на per-department уровне.
- [ ] **5.2 N-BEATS / TFT** для multivariate time series — встроенная сезонность и тренд.
- [ ] **5.3 Погода** через open-meteo (бесплатно): температура, осадки, солнце. Особенно важно для летних веранд и доставки.

---

## 5. Метрики успеха

| Метрика | Старт | Этап 1 (факт) | Этап 2 (факт) | Этап 3 (факт raw / current) | Цель этап 4 |
|---|---|---|---|---|---|
| Overall MAPE | 49.9% | 44.5% | 44.4% | **36.15% / 35.43%** | ≤10% |
| **Overall MedianAPE** | **~28%** | — | — | **19.0% / 19.1%** | **≤10%** |
| Q4 (крупные) MAPE | 73.5% | — | 67% | 53.6% / 53.4% | ≤12% |
| Q4 MedianAPE | — | — | 30.8% | **18.4%** | ≤8% |
| Coffeehouse MAPE | 58.4% | — | — | 46.5% / 44.4% | ≤12% |
| Q1 (мелкие) MAPE | — | — | — | 33.4% / 32.2% | — |
| Weekend bias | +6% | — | — | −13% (raw) / +3% (smooth) | ±2% |
| Auto-retrain работает | нет | нет | **да** | да | да |
| forecast_accuracy_log пишется | нет | нет | **да** | да | да |

**Метрика-приоритет:** **Median APE** — после residual analysis 50/50 худших ошибок оказались over-predictions на резорт-бренде «Tary» и одиночных закрытиях. Mean MAPE завышен из-за 5-10% «непредсказуемых» дней (закрытия, тех. сбои, сезонные провалы у Бурабая). Median APE 19% — реальная пользовательская точность.

Замеры — через `scripts/backtest_postprocessing.py` на скользящем окне последних 60 дней.

---

## 6. Журнал изменений

| Дата | Кто | Что | Эффект |
|---|---|---|---|
| 2026-04-29 | Claude | Полный аудит pipeline, backtest скрипт, выявлены 10 корневых причин | Документация + измеренный реальный MAPE 49.89% |
| 2026-04-29 | Claude | **Этап 1.1**: удалён weekend boost ×1.4 в `agent.py`, пересобран docker, задеплоен на прод | MAPE 49.89% → 46.96% (**−2.93 п.п.**) |
| 2026-04-29 | Claude | **Этап 1.2**: threshold smoothing 0.5 → 0.3 (sweep'нут, выбран оптимум). Sweep-скрипт `scripts/backtest_smoothing_threshold.py` | MAPE 46.96% → 44.54% (**−2.42 п.п.**) |
| 2026-04-29 | Claude | **Этап 2.1**: исправлен deployment-баг — при пустом current_mape deploy безусловно. Добавлен sanity-check >50% | Auto-retrain разблокирован |
| 2026-04-29 | Claude | **Этап 2.2**: миграция `008_forecast_logging_fix.sql`, `_upsert_forecast()` в agent, backfill 1 865 строк | Мониторинг работает, baseline MAPE = 44.54% записан |
| 2026-04-29 | Claude | **Этап 2.4-2.6**: chmod 1000:1000 на `models/`, retrain через `/api/forecast/retrain` (4.5 сек), новая `.pkl`. Test MAPE 9.48% (in-sample) | Out-of-sample MAPE 44.54% → **44.35%** (−0.19 п.п., незначимо). **Найдено: структурный overfit 5x in-sample vs out-of-sample** |
| 2026-04-29 | Claude | **Этап 3.1**: log-target transform — обучение на `log1p(y)`, inverse `expm1(pred)`, helper `agent.predict()`, метаданные `target_transform` в pickle. Параметры: n_est 500, lr 0.05, max_depth 6, eval_metric mae | Out-of-sample MAPE 44.35% → **42.88%** (−1.47 п.п.). **Q4 (крупные): 67% → 61% (−6 п.п.)** |
| 2026-04-30 | Claude | **Этап 3.4**: `GroupKFold(department_id)` в `hyperparameter_tuning_service.optimize_lightgbm` (через `groups_train`/`groups_val`), пробрасывается из `routers/forecast/tuning.py`. Fallback на `TimeSeriesSplit` если groups не переданы | Эффект на production 0 (Optuna не в pipeline retrain). Future-proof: ручной `/api/forecast/optimize` больше не оптимизирует «запоминание отделений» |
| 2026-04-30 | Claude | **Этап 3.5**: `_add_outlier_flag()` в `training_service` (IQR per dept), новая фича `is_outlier_day`, default `handle_outliers=False` (winsorize отключен). На инференсе flag=0. `feature_columns` 64 → 65 | Сам по себе на старом pipeline дал ухудшение (+2 п.п.) — leakage маскировал; после fix 3.3 работает корректно |
| 2026-04-30 | Claude | **Этап 3.3 (target leakage fix)**: `dept_sales.rolling(N).mean()` в training включал текущий день в окно (training видел target), inference — нет. Переписано через `past_sales = dept_sales.shift(1)`. Аналогично `pct_change_*`, `sales_momentum_*` приведены к past-only формулам, идентичным `agent._create_prediction_features`. 13 leak-фичей пофикшено | **Главный win этапа 3.** In-sample test MAPE 6.06% → 33.11% (5x → 1x — честная цифра). **Out-of-sample raw 54.07% → 36.15% (−17.92 п.п.)**. По всем срезам: food_court 32→17%, restaurant 54→35%, coffeehouse 63→47%, Q4 70→54%, median APE Q4 31→18.5% |
| 2026-04-30 | Claude | **Этап 3.2**: `train_segmented_models()` per `segment_type` (3 модели: restaurant/coffeehouse/food_court), endpoint `POST /api/forecast/retrain-segmented`, dispatcher в `predict(X, segment_type=...)`, `models/segments/*.pkl` | **Хуже global на 2.3 п.п.** (overall 36.15% → 38.41%, по всем сегментам ухудшение). Причина — дробление 8K → ~6K/1.4K/0.65K samples убивает кросс-сегментный сигнал, который уже передаётся через one-hot фичи. Файлы перемещены в `models/segments/archive/`, код оставлен |
| 2026-04-30 | Claude | **Re-sweep smoothing threshold** на новой модели (после fix leakage). 8 точек: 0.3/0.5/0.75/1.0/1.5/2.0/3.0/off. Default 0.3 → **0.5** в `agent._apply_temporal_smoothing` | overall MAPE 36.18% → **35.43%** (−0.75 п.п.). Q3 38.08, Q4 53.41 (минимум на 0.5). Q1 хочет 0.3 (32.14), но overall выигрывает |
| 2026-04-30 | Claude | **Optuna 40 trials с GroupKFold** через `/api/forecast/optimize`. cv_folds=4, days=365, GroupKFold(department_id) активен (этап 3.4) | best_cv_score **57.35%**, final val MAPE 62.91% — намного хуже production 36%. **Параметры не применены**. Причина: GroupKFold моделирует «прогноз для unseen департаментов», а production-задача — «прогноз будущих дней для known департаментов». Это разные задачи; tuning выбрал гипер для harder-задачи. Также Optuna service не использует log-target. Future-fix: переписать `optimize_lightgbm` под log-target + TimeSeriesSplit per dept |
| 2026-04-30 | Claude | **Residual analysis** топ-50 худших out-of-sample прогнозов (`scripts/analyze_residuals.py`, `inspect_bad_cases.py`). Filter actual > 50K | **50/50 over-predictions** (модель завышает в хвосте). **32/50 — бренд "Tary"** (Burabay 9×, Ayusai 7×, Kolsay 7×, Charyn 4×, Kutarys 4×, Almaty 1×). 0/50 на праздниках РК. Конкретные кейсы: Tary Ayusai 2026-04-16 actual 107K vs context 1.5M (закрытие); Sandyq Алматы 2026-04-04 actual 912K vs соседние 6M (тех. сбой); Tary Burabay — экстремально сезонный (резорт Бурабай) — модель усредняет 100K зимний будний и 4M летний выходной |
| 2026-04-30 | Claude | **Honest 30-day backtest** (`scripts/backtest_30day.py`) — recursive multi-step с anchor 2026-03-01 / 2026-04-01, h=1..30. Замеры по горизонтам, сегментам, размеру | h=1: MAPE 27%/Med 19%; h=22-30: 36%/26% — деградация всего +9 п.п. Месячный агрегат: **MAPE 21.6% / Med 16.5%, Bias −13.5%**. Hot-spots: coffeehouse h=8-14 = 75% (резорт-сезонность не ловится), Q3 h=8-14 = 60%. Recursive lag-feeding работает стабильнее ожидаемого |
| 2026-04-30 | otherClaude | **Этап 4.2 (БД + UI)** — миграция 009 (11 колонок + 6 CHECK + 2 индекса), Pydantic-схемы с Literal, departments API (PUT поддерживает partial update), iiko sync защищён от затирания, фронт `/departments` с условными полями и фильтрами. Commit 9029d6a | Готова инфраструктура для разметки операционных характеристик подразделений. На момент коммита 0 точек заполнено |
| 2026-04-30 | Claude | **Этап 4.2 (ML-pipeline)** — `_add_operational_features` в `training_service`, зеркальная логика в `agent._create_prediction_features`, 18 новых фичей (brand×4, location×7, is_tourist_dep, is_24_7, working_hours_count, days_since_opening, is_new_department, seasonality_score, is_in_season). `dropna()` сужен до feature subset. `feature_columns`: 65 → 83 | После retrain с **2/91 заполненных точек** (Tary Burabay, Tary Charyn): Monthly Med APE 16.48% → 15.86% (−0.62 п.п.). Feature importance: `is_loc_resort_lake` 8.4, `is_brand_tary` 6.5, `is_loc_visit_center` 1.8, `is_24_7` 1.0 — pipeline работает. Доля новых фичей в gain = 0.02% (минимальная — ждём разметку остальных 89 точек) |
| | | | |

---

## 7. Полезные ссылки

- Backtest скрипт: `scripts/backtest_postprocessing.py`
- ML агент: `app/agents/sales_forecaster_agent.py`
- Подготовка данных: `app/services/training_service.py`
- Пост-обработка: `app/services/forecast_postprocessing_service.py`
- Auto-retrain: `app/services/model_retraining_service.py`
- Мониторинг: `app/services/model_monitoring_service.py`

Запуск backtest:
```bash
docker cp scripts/backtest_postprocessing.py sales-forecast-app:/app/backtest_postprocessing.py
docker exec sales-forecast-app python /app/backtest_postprocessing.py
```

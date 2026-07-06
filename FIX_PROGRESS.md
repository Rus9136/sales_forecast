# Прогресс исправлений ML-подсистемы (по ML_AUDIT_REPORT.md)

**Начато:** 2026-07-06
**Правила:** работа по фазам, после каждой — проверки и подтверждение владельца; ценовой движок не трогаем; per-segment модели не обучаем; инвариант «строго прошлое» в rolling-фичах сохраняется.

---

## Фаза 0 — Остановить кровотечение ✅ (ожидает подтверждения)

### 0.1 Like-for-like сравнение моделей — `f7c1ca3`

`scripts/compare_models_holdout.py`: обе модели по одному hold-out (последние 28 дней, все точки, фичи из `TrainingDataService`, `is_outlier_day=0` — паритет с продом). `compare_on_holdout()` переиспользуется в Фазе 1.2 как deployment decision.

**Результат прогона (hold-out 2026-06-09..2026-07-06, 1094 строки, 41 точка):**

| Модель | trained_at | WAPE | MedianAPE | MAPE |
|---|---|---|---|---|
| `models/lgbm_model.pkl` (кандидат 05.07, «rejected») | 2026-07-05 | **18.89%** | **15.76%** | 42.35% |
| `backup_lgbm_model_20260621_030006.pkl` | 2026-06-21 | 19.38% | 16.23% | 43.06% |

**⚠ Отклонение от рекомендации отчёта:** аудит предлагал откат на бэкап 21.06 (по offline test MAPE 44.4% vs 48.8%). Честное like-for-like сравнение показало обратное — «отклонённый» кандидат 05.07 немного ЛУЧШЕ. Его reject был артефактом сравнения несопоставимых метрик (P0-3). **Откат не выполнялся, прод-файл (md5 `56890031...`) оставлен и верифицирован как лучший из доступных.**

### 0.2 Контур деплоя (P0-1) — `d2aef37`

- Кандидат обучается в `temp_<version>.pkl` (агент с `model_path=temp`) — прод-файл не перезаписывается до deployment decision.
- `_deploy_model`: `.staging` + `os.replace()` (атомарно), бэкап старого до замены, архив старого ДО деплоя.
- `reload_forecaster_agent()`: после деплоя serving-синглтон атомарно подменяется (агент собирается полностью до подмены); `get_forecaster_agent` — double-checked lock.
- Побочно: pre-split ветка `train_model` больше не создаёт утекающий `next(get_db())`.
- Тесты: `tests/unit/test_retrain_deploy_safety.py` (4 шт.), включая сценарий 0.2d — шумовой кандидат → `rejected`, прод-файл байт-в-байт неизменен, синглтон — тот же объект.

### 0.3 Аудит-трейл (P0-4) — `5bb999e`

- `_clean_numpy()` перед INSERT в `model_versions`/`model_retraining_log` (np.float64 ронял psycopg2 → записи молча терялись с эпохи numpy 2.x).
- Маппинг метрик `validation_mape ← val_mape`, `validation_r2 ← val_r2`; `feature_names`/`n_features` — из `feature_columns` модели.
- `get_model_info()` отдаёт `trained_at`; `version_id`/`model_age` из него → ожило условие «retrain if older than 30 days».
- Потеря аудит-трейла → CRITICAL-лог (алерт в Telegram — Фаза 1.5).
- Тесты: `tests/integration/test_retrain_audit_trail.py` (4 шт., payload инцидента 2026-07-05).

### 0.4 SKU-retrain отключён (P0-2, минимум) — `1eecaa7`

Job `weekly_sku_model_retrain` (вс 03:45) закомментирован в `app/main.py` с комментарием-ссылкой на P0-2 (OOM: uvicorn RSS 3.3GB / хост 3.8GB, kern.log 2026-07-05). Ручной `POST /api/forecast/sku/retrain` остаётся. Полное решение — Фаза 2.2 (вынос в отдельный процесс + downcast).

### Деплой и проверки Фазы 0

Образ пересобран, контейнер перезапущен 2026-07-06 18:19 UTC, `/health` OK (локально и через https://aqniet.space).

| Проверка | Результат |
|---|---|
| `ls -la models/` + md5 прод-файла | `lgbm_model.pkl` = победитель 0.1 (md5 `56890031c93aebbcd3116dedbfe3b9b3`), в памяти он же (загружен при рестарте) |
| Тест 0.2d (плохой кандидат) | ✅ `8 passed` (4 deploy-safety + 4 audit-trail) |
| Регрессия: полный unit-набор | ✅ `181 passed, 13 skipped` (skip'ы — исторические) |
| INSERT с np.float64 → SELECT | ✅ строка `v_phase0_check` в `model_versions` (тест-БД, реальный commit): validation_mape 28.39, test_mape 48.81 |
| Scheduler | лог старта: `SKU retrain DISABLED (audit P0-2)`; job закомментирован (`app/main.py:96-115`) |

**Как гонять тесты** (pytest не в прод-образе, ставится ad-hoc):
```bash
docker exec -i -u root sales-forecast-app pip install -q pytest pytest-asyncio pytest-mock freezegun respx
docker cp tests sales-forecast-app:/tmp/tests
docker exec -w /app -e PYTHONPATH=/app sales-forecast-app python -m pytest /tmp/tests -q -p no:cacheprovider
```

**Заметка на Фазу 1.2:** ближайшее воскресенье (12.07, 03:00) retrain пройдёт по НОВОМУ контуру: прод-файл в безопасности при любом решении, но decision всё ещё сравнивает несопоставимые метрики (P0-3) — это чинится в 1.2. До этого reject'ы не страшны (прод не трогается), а deploy пройдёт только при формальном «улучшении» против прод-MAPE.

---

## Фаза 1 — Честное измерение ✅ (ожидает подтверждения)

### 1.1 WAPE/MedianAPE + horizon_days — `2127df5`

- `app/services/forecast_metrics.py` — единый модуль (wape/mape/median_ape/bias_pct/regression_report) для агентов, deployment decision, мониторинга, backtest'ов.
- `train_model` обеих моделей отдаёт `val/test_wape`, `val/test_median_ape`; headline в логах — WAPE.
- Миграция `030_ml_monitoring_wape_horizon.sql` (применена к prod и test БД): `forecasts.horizon_days` + `forecast_accuracy_log.horizon_days` (UNIQUE-ключи расширены — t+1 и t+7 на одну дату больше не затирают друг друга), `model_performance_metrics` пересоздана (старая из 002 всегда была пустой — заглушка в неё не писала).
- **⚠ Отклонение от плана миграции:** `model_performance_metrics` уже существовала (миграция 002) со старой схемой и 0 строк — пересоздана DROP+CREATE, задокументировано в 030.

### 1.2 Like-for-like deployment decision — `b3e30b1`

- `app/services/model_comparison.py` (из скрипта 0.1); скрипт стал тонким CLI.
- `auto_retrain_model`: decision-кандидат обучается **без** hold-out окна (28д) → сравнение с прод-моделью на общем hold-out → финальное обучение на полном окне только при deploy. Прод-модель могла видеть начало hold-out — смещение в пользу прода (консервативно).
- Критерий: кандидат лучше по WAPE И MedAPE в пределах `RETRAIN_MEDAPE_TOLERANCE_PCT` (10%, конфиг). Sanity WAPE>50% → reject. Сбой сравнения → reject (safe default). `previous_mape/new_mape` в retrain_log — теперь hold-out WAPE обеих моделей.
- **Заметка:** ручной `POST /api/forecast/retrain` по-прежнему «train & deploy сразу» (операторский override, минует decision) — кандидат на ужесточение в Фазе 3.

### 1.3+1.4 Ежедневный batch-прогноз — `e34533b`

`app/services/scheduled_forecast_job.py`, scheduler 06:00: t+1 и t+7 для всех активных точек (продажи за 14д) → `forecasts`; SKU t+1 топ-50 по прогнозному обороту → `sku_forecasts`. Идемпотентна (UPSERT).

### 1.5 Telegram-алерты + персист метрик — `de49dbc`

- `app/services/alerting.py` (env `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`); critical-алерты мониторинга и потеря аудит-трейла retrain шлют в Telegram.
- Мониторинг: headline WAPE (warning 25% / critical 35%), MedianAPE, bias_pct, разрез `per_horizon`; `_save_daily_metrics` реализован (UPSERT в `model_performance_metrics`, horizon 0 = общий агрегат); `_update_accuracy_log` с горизонтом; фикс `training_date`→`trained_at` (возраст модели был всегда 0).

### 1.6 Rolling-origin backtest — `2b52c13`

`scripts/backtest_30day.py`: `--anchors`/автоподбор 4 месячных окон, WAPE, таблица ROLLING-ORIGIN BASELINE + агрегат mean±std.

### 📌 БАЗОВАЯ ЛИНИЯ (прод-модель trained_at=2026-07-05, recursive 30-day, 4 окна)

| Anchor | n | WAPE | MedianAPE | Monthly WAPE |
|---|---|---|---|---|
| 2026-03-01 | 923 | 29.94% | 22.40% | 20.93% |
| 2026-04-01 | 929 | 25.18% | 20.16% | 15.54% |
| 2026-05-01 | 937 | 24.97% | 19.14% | 15.07% |
| 2026-06-01 | 1220 | 23.39% | 21.39% | 15.36% |
| **AGGREGATE** | | **25.87% ± 2.83** | **20.77% ± 1.42** | **16.73% ± 2.81** |

Все улучшения Фаз 2-3 меряются против этой линии тем же протоколом (`docker exec ... python /tmp/backtest_30day.py`). Оговорка: окна частично in-sample для прод-модели; протокол честен для сравнения моделей, обученных на одну дату.

### Проверки Фазы 1

| Проверка | Результат |
|---|---|
| Джоба 1.3 вручную → покрытие | ✅ `forecasts` за сегодня: **41 dept**, 82 строки (t+1 + t+7); сводка джобы: 0 ошибок |
| `sku_forecasts` непуста | ✅ **2009 строк**, 41 подразделение (было 0 строк с момента создания таблицы) |
| Мониторинг + персист | ✅ ручной прогон за 2026-07-05: WAPE 39.5% (3 старые точки) → **critical-алерт сгенерирован**, 2 строки записаны в `model_performance_metrics` (horizon 0 и 1) |
| Telegram | ⚠ **токены не добавлены в `.env.prod`** — код готов и покрыт тестами (4 unit), отправка вернёт warning «not configured». Нужны `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (+ перезапуск контейнера), после чего живой тест |
| Тесты | ✅ **284 passed, 18 skipped** (полный набор в контейнере, включая 10 новых) |
| Backtest 3+ окна | ✅ 4 окна, база зафиксирована выше |

## Фаза 2 — SKU-модель (не начата, ждёт подтверждения Фазы 1)

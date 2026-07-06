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

## Фаза 1 — Честное измерение (не начата, ждёт подтверждения Фазы 0)

## Фаза 2 — SKU-модель (не начата)

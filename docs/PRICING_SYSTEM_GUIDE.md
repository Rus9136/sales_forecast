# Pricing System Guide — единая карта подсистемы ценообразования

**Аудитория:** ИИ-агент / разработчик, впервые входящий в код. Этот файл — точка входа:
что делает система, из чего состоит, где лежит, какая семантика зашита и что нельзя ломать.

**Статус:** пилот (заказчик Sandyq Group). Актуально на 2026-07-03, после hardening-коммита
`f813a8f` (закрытие ~60 находок архитектурного ревью) и миграции 029.

Связанные документы:
- [`API_DOCUMENTATION_PRICING.md`](../API_DOCUMENTATION_PRICING.md) — параметры всех эндпоинтов
- [`docs/PRICING_SYSTEM_ROADMAP.md`](PRICING_SYSTEM_ROADMAP.md) — история/замысел (частично устарел, см. §10)
- `CLAUDE.md` — общая карта проекта

---

## 1. Что делает система (в одном абзаце)

По истории чеков iiko (24 мес., ~9.5 млн позиций) система: агрегирует витрины продаж →
классифицирует блюда по 5 ролям меню (KMeans) → оценивает ценовую эластичность спроса
(3-уровневый OLS с shrinkage) → ежедневно генерирует рекомендации цен, максимизирующие
валовую прибыль (grid search с бизнес-правилами) → менеджер утверждает их в UI →
система детектирует фактическое применение цены по каталогу iiko → через 14 дней
считает фактический эффект против контрольной группы → LLM пишет объяснения и
weekly/monthly отчёты. Утверждённые цены уезжают в iiko **приказом** (`menuChange`) по
кнопке в UI; XLSX остаётся запасным путём.

## 2. Поток данных

```
iiko OLAP чеки ──▶ receipt / receipt_item (партиционированы по open_date)
                        │  (02:15 daily + gap check 11:30)
                        ▼
              sku_daily_sales  (агрегат qty/сумма по SKU×точка×день)
                        │
        ┌───────────────┼───────────────────────────────┐
        ▼               ▼                               ▼
sku_price_history  sku_weekly_summary          department_weekly_summary
(derived-история,  (SKU×неделя: qty, GP,       (точка×неделя: KPI дашборда)
 диагностика)       cost_coverage, qty_cv)              (04:30 daily)
                        │
iiko /v2/price ──▶ sku_catalog_price  ◀── АВТОРИТЕТНЫЙ источник цен (приказы)
(03:20 daily)      (интервалы цен, is_stale, product_size_id, price_type)
                        │
        ┌───────────────┼──────────────┐
        ▼               ▼              ▼
  sku_menu_role   sku_elasticity   current_price оптимизатора
  (KMeans, вс     (OLS, вс 03:30)      │
   03:15)               └──────┬───────┘
                               ▼
                    price_recommendation  (оптимизатор 05:00 daily)
                               │  UI approve/reject (или эксперимент C/D)
                               ▼
        price_change_order ──▶ POST /v2/documents/menuChange (кнопка «Отправить в iiko»)
        (+ _item, сверка 03:25)      │
                               ▼
              детекция applied по каталогу (03:20, окно 30 дней;
              приоритет — совпадение document_id нашего приказа)
                               ▼
              price_recommendation_outcome (оценка 05:30, окно 14 дней,
                               │            контрольная группа = категория)
                               ▼
     LLM: объяснения (05:45) + weekly (пн 08:00) / monthly (1-е 08:00) отчёты
                               ▼
              pricing_report, price_recommendation.llm_explanation
```

Сквозной журнал всех мутаций — `pricing_audit_log` (append-only, триггер БД).
База сравнения пилота — `pricing_baseline_kpi` (label `pre-pilot-2026-06`, заморожен).

## 3. Карта файлов

### Backend-сервисы (`app/services/`)
| Файл | Отвечает за |
|---|---|
| `pricing_analytics_service.py` | A2: агрегация `sku_price_history` + weekly-витрин (SQL upsert) |
| `iiko_price_loader.py` | Синк каталожных цен `GET /resto/api/v2/price` → `sku_catalog_price`, stale-маркировка отозванных приказов |
| `menu_clustering_service.py` | B1: KMeans(k=5) → `sku_menu_role` (5 признаков, greedy-маппинг на роли) |
| `elasticity_estimation_service.py` | B2: 3-уровневый OLS (global/group/sku), грейды A–D, τ², upsert `sku_elasticity` |
| `price_optimizer_service.py` | B3: grid search GP, статусная машина review, эксперименты; **ядро** |
| `pricing_rules_service.py` | B4: правила с каскадом scope + fail-safe дефолты |
| `pricing_feedback_service.py` | FB: detect_applied, evaluate_outcomes, freeze_baseline |
| `pricing_explanation_service.py` | C4': LLM-объяснение одной рекомендации (structured JSON) |
| `pricing_report_service.py` | C4: weekly/monthly LLM-отчёты → `pricing_report` |
| `iiko_menu_change_writer.py` | Транспорт к API приказов iiko (create/update/get/list, поиск сироты по маркеру). **POST не ретраится** |
| `price_order_service.py` | Приказы: сборка из approved + ревалидация, отправка, отмена (delete/обратный приказ), сверка |
| `pricing_audit.py` | `log_audit()` — единственная точка записи в аудит |
| `pricing_jobs.py` | In-memory реестр фоновых джобов (`?background=true`) + `log_job_run` → `auto_sync_log` |
| `scheduled_pricing_analytics.py` | Обёртки планировщика: агрегация 04:30, кластеризация вс 03:15 |
| `scheduled_pricing_engine.py` | Обёртки: синк цен 03:20 (+detect_applied), эластичность вс 03:30, оптимизатор 05:00, outcomes 05:30, объяснения 05:45, отчёты |

### Роутеры (`app/routers/`)
- `pricing_engine.py` — `/api/pricing-engine/*`: rules, elasticity, recommendations
  (list/generate/review/batch/export/explain), experiments, outcomes, baseline, audit-log,
  reports, jobs. Хелперы `_require_section` / `_actor_of` — см. §8.
- `pricing_analytics.py` — `/api/pricing-analytics/*`: price-history, sku-weekly,
  department-weekly, aggregate/backfill, menu-roles (+override, +cluster).

### Модели (`app/models/`)
- `pricing_analytics.py`: SkuPriceHistory, SkuCatalogPrice, SkuWeeklySummary,
  DepartmentWeeklySummary, SkuMenuRole, PricingReport
- `pricing_engine.py`: SkuElasticity, PricingRule, PriceRecommendation,
  PriceRecommendationOutcome, PricingBaselineKpi, PricingAuditLog
- `sku_forecast.py`: SkuDailySales (источник объёмов)

ORM синхронизирован с миграциями (UNIQUE-констрейнты, partial-индексы) — держать так,
иначе `create_all` на свежем стенде даст схему, где падают все `ON CONFLICT`.

### Миграции: `019` витрины → `020` роли меню → `021` эластичность → `022` правила →
`023` рекомендации → `024` каталожные цены → `025` фиксы уников → `026` feedback loop +
baseline → `027` эксперименты/аудит/cycle cap/is_stale → `029` append-only триггер +
partial unique на открытые рекомендации → … → `041` откаты + комментарии к
интервалу эффекта.

### Frontend (`frontend/src/`)
- `hooks/use-pricing.ts` — все TanStack-хуки; `types/pricing.ts` — TS-типы
  (статусы: `new|approved|rejected|expired|applied`); `lib/pricing-labels.ts` — лейблы/бейджи.
- `pages/pricing/`: `dashboard` (C1 KPI), `recommendations` (C2 approve/reject/XLSX),
  `position` (C3 карточка SKU: кривая спроса, история, outcomes), `rules` (B4),
  `outcomes` (FB), `elasticity`, `menu-roles`, `audit`, `reports` (C4).

### Тесты
- `tests/unit/test_pricing_engine.py` — чистая логика: правила (включая fail-safe),
  сетка кандидатов, GP-математика, планирующая ε (включая двустороннюю и global-fallback),
  кумулятивный cap, грейды, within-оценщик, realized elasticity, JobRegistry.
- НЕ покрыто интеграционно: SQL статусной машины, detect/evaluate — менять с осторожностью.

## 4. Таблицы БД (ключевые поля и инварианты)

| Таблица | Ключ | Что важно знать |
|---|---|---|
| `sku_catalog_price` | (dept, iiko_product, COALESCE(size), date_from, price_type) UNIQUE | **Авторитетный источник цен.** Интервалы [date_from, date_to). `is_stale=true` = отозванный приказ — всегда фильтровать `NOT is_stale`. «Цена SKU» = цена БАЗОВОЙ серии (price_type='BASE', size IS NULL) через DISTINCT ON — НЕ AVG по размерам |
| `sku_elasticity` | (product, dept) UNIQUE | ε<0 всегда (положительные оценки переопределяются). `estimation_level`: sku/group/global. Строки чужих `model_version` удаляются при переоценке — отсутствие строки = честный fallback −1.0 |
| `sku_menu_role` | (product, dept) UNIQUE | `effective_role` = GENERATED COALESCE(manual, auto). Рекластеризация не трогает manual_role |
| `price_recommendation` | partial UNIQUE (product, dept) WHERE status='new' + partial UNIQUE (reverses_recommendation_id) WHERE status IN new/approved/applied | Статусы см. §6.4. `rec_type`: optimizer/experiment/**rollback**. `elasticity_used` — планирующая ε (консервативная), не mean |
| `price_recommendation_outcome` | recommendation_id UNIQUE | Появляется через 14+ дней после applied. `realized_elasticity` — control-adjusted. **Вердикт — по `effect_ci_low`/`effect_ci_high`** (bootstrap); `significance_z` УСТАРЕЛО (пуассоновская SE, не видит выходных/погоды) и ни на что не влияет |
| `pricing_rule` | (rule_type, scope_type, scope_id) UNIQUE + partial для global | params JSONB. Каскад: product > department > segment > global (первое совпадение по типу) |
| `pricing_baseline_kpi` | (label, scope, dept) UNIQUE NULLS NOT DISTINCT | Перезапись label — только `force=true` (иначе 409) |
| `price_change_order` | partial UNIQUE (dept, effective_date) WHERE status IN draft/sending/sent | Один приказ на точку и дату. `sending` = ответ iiko не получен, документ ищется по маркеру `SF#{id}` в комментарии — **POST не повторять** |
| `price_change_order_item` | partial UNIQUE (recommendation_id) | `old_price` — базис решения, по нему строится обратный приказ при откате |
| `pricing_audit_log` | — | **Append-only на уровне БД** (триггер 029). UPDATE/DELETE кинет исключение |

## 5. Scheduler (что и когда, все в `app/main.py` lifespan)

| Время | Джоб | Файл |
|---|---|---|
| 03:15 вс | Кластеризация ролей меню | scheduled_pricing_analytics |
| 03:20 ежедн. | Синк каталожных цен + detect_applied + экспирация протухших | scheduled_pricing_engine |
| 03:25 ежедн. | Сверка приказов с iiko (провели/удалили руками, зависшие 'sending') | scheduled_pricing_engine |
| 03:30 вс | Переоценка эластичности (lookback **730** — канонический, не менять в одном месте) | scheduled_pricing_engine |
| 04:30 ежедн. | Витрины: price history (окно 8 дней ≥ окна gap check) + weekly | scheduled_pricing_analytics |
| 05:00 ежедн. | Оптимизатор по всем активным точкам (продажи за 30 дней) | scheduled_pricing_engine |
| 05:30 ежедн. | Оценка outcomes (окно 14 дней) | scheduled_pricing_engine |
| 05:45 ежедн. | LLM-объяснения топ-N по ΔGP на точку (`PRICING_EXPLAIN_TOP_N`) | scheduled_pricing_engine |
| 08:00 пн / 1-е | Weekly / monthly LLM-отчёт | scheduled_pricing_engine |

Результаты всех джобов пишутся в `auto_sync_log` (`log_job_run`), видны на странице /sync.

## 6. Ключевая семантика (менять только осознанно!)

### 6.1 Эластичность (B2)
- **Данные:** недельные `sku_weekly_summary` × каталожная цена базовой серии на week_start.
  Log-log OLS: `ln(qty) ~ ln(price) + month dummies + trend + LOO-контроль категории`;
  на global/group уровнях — within-преобразование (FE по паре SKU×dept).
- **Грейды** (`_assign_grade`): по `n_events` = число ценовых РЕЖИМОВ во времени
  (1 + смены цены через LAG по серии размер×тип; A→B→A = 3 режима). НЕ `DISTINCT price`.
  A: ≥5 режимов и ≥90 дней; B: ≥4 и ≥60; C: ≥3; D: остальное.
- **SKU-уровень — только Grade A/B** (+ остаточные dof ≥ 10), с EB-shrinkage к группе
  (τ² по винзоризованным сырым ε).
- **CI для C/D** — предиктивный интервал `ε ± 1.96·sqrt(SE² + τ²)`, НЕ sampling-CI
  (тот при n в тысячи имеет ширину ≈ 0 и не защищает).
- Текущие цифры (2026-07-03): global prior −0.261; A 373 / B 825 / C 3 896 / D 30 040;
  уровни: sku 1 086 / group 31 543 / global 2 505.

### 6.2 Планирующая эластичность оптимизатора (двусторонний пессимизм)
`price_optimizer_service.select_planning_elasticity[_down]`:
- Grade A/B → точечная `mean` (в обе стороны).
- Grade C/D, кандидат ВЫШЕ текущей цены → `ci_lower` (эластичный край: рост цены даёт
  минимум выгоды). `estimation_level='global'` → не мягче **−1.0**; SKU без записи → −1.0.
- Grade C/D, кандидат НИЖЕ текущей цены → `ci_upper` (НЕэластичный край: скидка почти
  не приводит гостей). Без CI → −0.1.
- Зачем: односторонний «консервативный» край делает снижения цены ложно привлекательными —
  пессимизм должен быть в сторону предлагаемого хода. Не «упрощать» до одной ε!

### 6.3 Оптимизатор (B3)
- Grid search по коридору ±`max_step` (деф. 5%) с шагом округления 50₸ (100₸ для
  premium_anchor/image_rare). GP = (P − COGS)·q, q = q_base·(P/P0)^ε, q_base = 30-дневный
  среднедневной qty × 7. SKU без COGS пропускаются (`skipped_no_cogs`).
- Порог: ΔGP ≥ 500₸/нед. **Кумулятивный потолок:** цена ≤ цена_90_дней_назад × 1.15
  (`CUMULATIVE_CAP_PCT`) — защита от храповика +5% каждые 2 недели.
- Генерация сериализована advisory-lock'ом по точке; каждая генерация supersede'ит
  открытые `new` (только optimizer-тип) и **пропускает** SKU с pending `approved` /
  `applied`-без-outcome и SKU в открытых экспериментах. Per-SKU SAVEPOINT.
- LLM-объяснение переносится со старой рекомендации, если цены не изменились.

### 6.4 Статусная машина рекомендаций
```
new ──approve──▶ approved ──каталог показал цену (окно 30д)──▶ applied ──14д──▶ outcome
 │                  │
 │ reject ▶ rejected│ не применено за 30д ──▶ expired
 │ supersede/TTL 30д ▶ expired
```
- Approve: `SELECT ... FOR UPDATE`, ревалидация (TTL 30 дней, актуальность current_price
  по каталогу ±0.01, stop_list, min_frequency), атомарный cycle cap
  (`max_changes_per_cycle`, деф. 15/14 дней на точку) под advisory-lock. Конфликты → HTTP 409
  (`cycle_cap_exceeded|expired|stale_price|min_frequency|stop_list|label_exists`).
- Детекция applied: точное совпадение цены (±0.01) в каталоге, `date_from` в окне
  [reviewed_at, reviewed_at+30д]. Там же экспирируются протухшие approved и new.
- Эксперименты (`rec_type='experiment'`): +2–5% для grade C/D с целью ИЗМЕРИТЬ ε;
  идут тем же циклом; оптимизатор такие SKU не трогает до завершения.
- **Откаты (`rec_type='rollback'`, миграция 041)**: возврат к цене ДО решения там,
  где повышение доказанно навредило. Оптимизатор снижение предложить не может
  структурно (при |ε| < 1 прибыль монотонна по цене → всегда верх коридора; 92.6%
  рекомендаций), а `generate_experiments` переворачивает отрицательный `delta_pct`
  строкой `if target <= current_price: target = current_price + step`.
  Кандидаты: применённое решение с отрицательным эффектом И (`effect_ci_high < 0`
  ИЛИ на товар заведён `stop_list`). Второе условие — потому что на пилоте
  доказанным оказался уровень КАТЕГОРИИ, а не позиции. Цель — `current_price`
  исходной рекомендации; ниже исторической не идём. Для этого типа снимаются
  `ROLLBACK_RELAXED_RULES` (max_step, rounding, no_decrease_anchor,
  no_psychological, min_frequency) — `min_margin` и `stop_list` остаются.
  После applied-отката SKU не возвращается к оптимизатору `ROLLBACK_COOLDOWN_DAYS`=60.

### 6.5 Правила (B4) — fail-safe
`check_recommendation` применяет **зашитые дефолты**, если строки правила нет в БД:
min_margin 60%, max_step 5%, min_frequency 14д, rounding 50/100. Удаление правила через
UI НЕ отключает защиту (fail-safe, не fail-open). Каскад scope: первое совпадение по типу.
`max_changes_per_cycle` валиден только на global/department scope.
`stop_list.params.block` задаёт направление: `any` (деф. — не трогать),
`increase` (не повышать, вернуть можно — для позиций с доказанным убытком от
подъёма), `decrease`.
`rounding.params.tiers` (необяз.) задаёт шаг по цене:
`[{"max_price":1500,"step":10},{"max_price":5000,"step":50},{"step":100}]`.
Единая точка резолва — `resolve_rounding_step()`; раньше логика была
продублирована в `check_recommendation` и `_enumerate_candidates`.
**Правило намеренно НЕ заведено в проде.** Плоский шаг 50 ₸ вырождает коридор
на дешёвых позициях (у товара за 430 ₸ внутри ±5% ровно одно кратное — 450),
но включать tiers до §6.3 нельзя: при |ε| < 1 оптимизатор всегда берёт верх
коридора, поэтому мелкий шаг не даёт настройку, а УВЕЛИЧИВАЕТ подъём
(830 ₸ ушли бы на 870 вместо 850) — ровно на импульсной выпечке, где подъём
доказанно убыточен.

### 6.6 Feedback loop
- `evaluate_outcomes`: before/after 14+14 дней (weekday-сбалансировано), поправка на
  контрольную группу (та же категория+точка, без смен цены за период);
  `ε_realized = ln(1+adj)/ln(P1/P0)`; per-rec SAVEPOINT (одна ошибка не гrobит батч).
- **Петля НЕ замкнута автоматически**: outcome не корректирует ε/правила. Канал обучения —
  еженедельный OLS (применённые цены становятся новыми режимами в каталоге). Это осознанно.
- Baseline: `POST /baseline/freeze` — 409 на существующий label без `force=true`.

### 6.7 LLM-контур
- Движок общий с AI-рекомендациями (`app/services/ai/engines/claude_engine.py`):
  retry 529 (30→600с) и 429 (20→120с), прочие 4xx не ретраятся.
- Числа в промпты подаются JSON-блоком (LLM их не выдумывает); результат объяснения —
  structured JSON в `llm_explanation`; отчёты хранят снапшот данных в `pricing_report.data`.
- Без `ANTHROPIC_API_KEY` отчёт сохраняется со `status='no_llm'` (данные целы).

## 7. API (карта; параметры — в API_DOCUMENTATION_PRICING.md)

`/api/pricing-engine/`: `rules` CRUD+effective · `elasticity` list/summary/{id}/estimate ·
`recommendations` list/summary/generate/review/batch-review/export(XLSX)/explain/explain-batch/
detect-applied · `experiments/generate` · `rollbacks/generate` (`?dry_run=true`) · `outcomes` list/summary/evaluate ·
`baseline` get/freeze · `audit-log` · `reports` list/{id}/generate · `jobs/{id}` ·
`price-orders` list/{id}/preview/create/{id}/cancel/{id}/sync.

`/api/pricing-analytics/`: `price-history` · `sku-weekly` · `department-weekly` ·
`aggregate` / `backfill` · `menu-roles` list/summary/override(PUT)/cluster.

`recommendations/summary?department_id=` возвращает `measurement_forecast` —
прогноз точности будущего замера (`pricing_effect.forecast_batch_precision`).
Откалибровано на 9 приказах: corr(прогноз, факт) = **+0.976** на уровне приказа.
Проверено и отвергнуто: порог отбора позиций по «измеримости» — доказуемость
ОТДЕЛЬНОЙ позиции заранее не предсказуема (оборот p=0.49, ожидаемый ΔGP p=0.64,
ожидание/шум p=0.39; среди доказанных есть торт при 1.4 шт/день, а порог
5 шт/день терял 6 доказанных из 8). Знать заранее можно не «какие позиции
брать», а «удастся ли что-то доказать по приказу целиком».

Тяжёлые POST (`elasticity/estimate`, backfill) поддерживают `?background=true` →
`{job_id}` → `GET /jobs/{id}` (реестр процесс-локальный, теряется при рестарте).

## 8. Авторизация (двухслойная)

1. **Bearer `API_TOKEN`** — обязателен для всего (`get_api_key_or_bypass`). Prod: ключи
   в таблице `api_keys` (SHA256, формат `sf_<key_id 32>_<secret 43>`, **у ключей есть
   `expires_at`** — истечение = 401 «API key expired» у всего SPA).
2. **`X-Session-Token`** (опционально) — на мутирующих pricing-эндпоинтах:
   если заголовок есть → актор аудита = ФИО(телефон) пользователя, `reviewed_by` = его UUID
   (клиентский `reviewer_id` игнорируется), и проверяется секция роли
   (`pricing.recommendations` для review, `pricing.apply` для отправки цен в iiko,
   `pricing.rules` для правил,
   `pricing.outcomes` для baseline, `pricing.analytics|position_detail` для ролей меню) → 403.
   Если заголовка нет (curl/автоматизация) → допускается, актор `'api'`. SPA шлёт оба.

## 9. Операционные команды

```bash
# Ручной прогон джобов (внутри контейнера, как это делает планировщик)
docker exec -i sales-forecast-app python -c "
from app.db import SessionLocal
from app.services.scheduled_pricing_engine import run_price_optimization
print(run_price_optimization())"

# Переоценка эластичности через API (в фоне)
curl -X POST -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/pricing-engine/elasticity/estimate?background=true"

# Миграции применяются вручную:
docker exec -i sales-forecast-db psql -U sales_user -d sales_forecast \
  -v ON_ERROR_STOP=1 < migrations/0XX_*.sql

# Тесты ценового движка
venv/bin/python -m pytest tests/unit/test_pricing_engine.py -q
```

## 10. Осознанно отложенные решения (НЕ «баги»)

| Что | Почему отложено |
|---|---|
| Выручка витрин считается ДО скидок (gross, `DishSumInt`) | Менять только вместе с перезаморозкой baseline — иначе несравнимость KPI пилота |
| Outcome не корректирует ε автоматически | Канал обучения — недельный OLS; авто-shrinkage по outcome — после пилота |
| Кросс-эластичность / каннибализация | Нет данных для матрицы; ΔGP соседних SKU одной категории суммарно завышен — помнить при чтении summary |
| Pydantic-схемы `schemas/pricing_engine.py` не подключены как response_model/body | Контракт держится на ручных TS-типах; при рефакторинге начать отсюда |
| Ролевая проверка для чистых Bearer-клиентов (без сессии) | Совместимость с curl/автоматизацией; действия пишутся как actor='api' |
| Конкурентный анализ (трек D), погода/события | Не блокируют пилот |
| Roadmap §B2 «байесовская иерархия PyMC» | Реализован numpy-OLS + EB shrinkage — достаточно; roadmap в этой части устарел |

## 11. Известные грабли (проверено на этой кодовой базе)

- **`NOW()` прибит к началу транзакции** — для сравнений с `synced_at` только
  `clock_timestamp()` (ловило 130k ложных stale-интервалов).
- **FastAPI `Query(None)` для `?param=` возвращает `''`, не `None`** — пустую строку
  трактовать явно (сброс роли меню).
- **Postgres после ошибки в транзакции** → `InFailedSqlTransaction` у всех последующих
  запросов: в циклах по точкам/rec'ам — SAVEPOINT (`begin_nested`) или `rollback()` в except.
- **`execute_values` НЕ через connection Session'а** — отдельный `engine.raw_connection()`
  (iiko_price_loader), иначе коммит «под ногами» у SQLAlchemy.
- **Партиционированные чеки**: `receipt_item` джойнить с `receipt` по `(id, open_date)`
  и всегда передавать `open_date` для partition pruning.
- **API-ключи истекают** (`api_keys.expires_at`): 401 «API key expired» у всего SPA —
  первым делом смотреть сюда (инцидент 2026-06-30..07-03).
- Реестр фоновых джобов — in-memory: после рестарта контейнера `GET /jobs/{id}` даст 404,
  сам джоб при рестарте обрывается без следа.

## 12. Правила доработки

**НЕЛЬЗЯ:**
- Брать «цену SKU» как AVG по размерам/price_type или из `sku_price_history` — только
  базовая серия `sku_catalog_price` (`NOT is_stale`).
- Планировать C/D по точечной ε или единой ε в обе стороны (см. §6.2).
- Выносить вердикт «значимо» по `significance_z` — только по bootstrap-интервалу
  (`effect_ci_low`/`effect_ci_high`). z считается через пуассоновскую SE = √Σ(1/n)
  и расходится с интервалом в обе стороны: Бонаква z=3.64 при интервале
  [−29 322 … +128 863]; «Крафт бургер» z=1.95 при [+17 948 … +245 966].
- Снимать `min_margin` или `stop_list` для откатов — послабления перечислены
  в `ROLLBACK_RELAXED_RULES` и этими двумя не расширяются.
- Обходить `log_audit()` при мутациях recommendation/rule/menu_role/baseline/experiment.
- UPDATE/DELETE в `pricing_audit_log` (упадёт на триггере — так и задумано).
- Менять lookback эластичности локально (канон 730, грейды зависят от окна).
- Снимать fail-safe дефолты правил или partial unique `uq_price_rec_open`.
- Делать `deletePreviousMenu=true` в приказе или выносить его в параметр API —
  это исключит из меню точки всё, чего нет в документе.
- Ретраить POST `menuChange` (в т.ч. «по таймауту») — повтор создаёт второй приказ
  и цена уезжает дважды. Разбор обрыва — только через сверку по маркеру.
- Отправлять позицию, у которой цена в каталоге разошлась с `current_price` рекомендации,
  есть размеры или небазовая серия — только исключение с причиной.

**ОБЯЗАТЕЛЬНО:**
- Новые мутирующие эндпоинты: `Depends(get_optional_user)` + `_require_section` + актор в аудит.
- Новые статусы/поля рекомендаций: миграция + ORM-модель + `types/pricing.ts` +
  `pricing-labels.ts` + табы/KPI (`recommendations-page`, `dashboard-page`) — синхронно.
- Долгие операции — `?background=true` + JobRegistry (nginx-таймаут 60с).
- После изменения движка: `pytest tests/unit/test_pricing_engine.py` + сервисный smoke
  на одной точке (см. §9) перед деплоем.

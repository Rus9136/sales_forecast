# API: Система интеллектуального ценообразования

Справочник по REST API подсистемы ценообразования Sales Forecast: аналитические витрины,
роли меню, эластичность, ценовые рекомендации и бизнес-правила.

- **Версия:** 1.1 (2026-06-11)
- **Статус:** в проде на `https://aqniet.site`
- **Roadmap / дизайн:** [`docs/PRICING_SYSTEM_ROADMAP.md`](docs/PRICING_SYSTEM_ROADMAP.md)
- **Слой данных:** [`docs/MENU_AND_RECEIPTS_ARCHITECTURE.md`](docs/MENU_AND_RECEIPTS_ARCHITECTURE.md)

Эндпоинты разбиты на два роутера:
- **`/api/pricing-analytics/*`** — витрины (A2) + роли меню (B1)
- **`/api/pricing-engine/*`** — эластичность (B2), рекомендации (B3), правила (B4)

---

## Общее

### Base URL и аутентификация
```
https://aqniet.site
Authorization: Bearer <API_TOKEN>
```
Все эндпоинты требуют общий `API_TOKEN` (тот же, что и остальной API).

### Соглашения
- `department_id` — UUID; даты — `YYYY-MM-DD`; недели (`week_start`) — понедельник (ISO-8601).
- Денежные значения — тенге (₸). Доли/маржа — `[0..1]`.
- Списочные ответы: `{ "items": [...], "total": <int> }` с `limit`/`offset`-пагинацией.
- Таймзона — Asia/Almaty (UTC+5).

### Enum-значения
| Поле | Значения |
|------|----------|
| `effective_role` / `menu_role` / `manual_role` | `traffic_driver`, `margin_driver`, `premium_anchor`, `image_rare`, `tail` |
| `reliability_grade` (эластичность) | `A` (≥5 ценовых событий и ≥90 дн.), `B` (≥4 и ≥60), `C` (≥3), `D` (fallback) |
| `estimation_level` | `sku`, `group`, `global` |
| `status` (рекомендации) | `new`, `approved`, `rejected`, `expired` (вытеснена следующим батчем), `applied` (цена обнаружена в каталоге) |
| `scope_type` (правила) | `global`, `segment`, `department`, `product` |

### Коды ошибок
| Код | Когда |
|-----|-------|
| `400` | Невалидный JSON в `params`, некорректные query-параметры |
| `401`/`403` | Нет/неверный Bearer-токен |
| `404` | Объект не найден (эластичность SKU, правило, рекомендация) |

### Текущее наполнение (2026-06-10)
| Витрина / таблица | Строк |
|---|---|
| `sku_catalog_price` (цены из приказов) | 164,613 |
| `sku_price_history` | 80,843 |
| `sku_weekly_summary` | 612,483 |
| `department_weekly_summary` | 3,052 |
| `sku_menu_role` | 11,495 |
| `sku_elasticity` | 34,021 (A 137 / B 478 / C 6,422 / D 26,984) |
| `price_recommendation` | 41,027 |
| `pricing_rule` | 7 (дефолтные глобальные) |
| `pricing_report` | weekly/monthly LLM-сводки (по запросу + планировщик) |

---

## A. Аналитические витрины — `/api/pricing-analytics`

### A.1 `GET /price-history`
История изменений фактической цены SKU (`sku_price_history`).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `product_id` | int? | Фильтр по товару |
| `department_id` | uuid? | Фильтр по подразделению |
| `from_date` | date? | `first_seen_date >= from_date` |
| `to_date` | date? | `last_seen_date <= to_date` |
| `limit` | int=100 (≤1000) / `offset` | Пагинация |

**Элемент:** `id, product_id, product_name, department_id, price, prev_price, change_pct, first_seen_date, last_seen_date`.

### A.2 `GET /sku-weekly`
Недельные агрегаты по SKU × подразделение (`sku_weekly_summary`).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `product_id` | int? | Фильтр |
| `department_id` | uuid? | Фильтр |
| `from_week` / `to_week` | date? | Диапазон недель (`week_start`) |
| `limit` | int=200 (≤2000) / `offset` | Пагинация |

**Элемент:** `product_id, product_name, department_id, department_name, week_start, total_qty, total_revenue, total_cost, gross_profit, gp_margin, avg_price, avg_daily_qty, unique_receipts, days_with_sales, qty_cv, cost_coverage`.

### A.3 `GET /department-weekly`
Недельные агрегаты по подразделению (`department_weekly_summary`).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `department_id` | uuid? | Фильтр |
| `from_week` / `to_week` | date? | Диапазон недель |

**Элемент:** `department_id, department_name, week_start, total_revenue, total_cost, gross_profit, gp_margin, total_receipts, avg_receipt_sum, unique_guests, cost_coverage`.

### A.4 `POST /aggregate`
Ручной пересчёт витрин за период. Query: `from_date` (req), `to_date` (req). → `{status, price_history, sku_weekly, department_weekly}`.

### A.5 `POST /backfill`
Полный пересчёт всех витрин с нуля. → `{status, ...counts}`. **Тяжёлая операция.**

---

## B1. Роли меню — `/api/pricing-analytics/menu-roles`

### B1.1 `GET /menu-roles`
Роли позиций меню (`sku_menu_role`, кластеризация KMeans + ручной override).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `department_id` | uuid? | Фильтр |
| `effective_role` | string? | Фильтр по роли |
| `product_id` | int? | Фильтр |
| `limit` | int=200 (≤2000) / `offset` | Пагинация |

**Элемент:** `product_id, product_name, department_id, department_name, auto_role, manual_role, effective_role, features {qty_share, revenue_share, gp_margin, demand_cv, price_index}, cluster_meta {cluster_id, silhouette, centroid_dist, run_date, n_skus}`.

### B1.2 `GET /menu-roles/summary`
Распределение ролей. Query: `department_id?`. → `{distribution: {role: count}, total}`.

### B1.3 `PUT /menu-roles/{product_id}/{department_id}`
Ручное переопределение роли. Query: `manual_role` (одна из 5 ролей, или пусто — снять override).
→ `{status, effective_role}`. `400` при недопустимой роли, `404` если пары нет.

### B1.4 `POST /menu-roles/cluster`
Запуск кластеризации. Query: `lookback_days` (90, диапазон 30–365).
→ `{status, skus_classified, silhouette_score, role_distribution, lookback_days}`.
> Также выполняется планировщиком: воскресенье 03:15.

---

## B2. Эластичность — `/api/pricing-engine/elasticity`

Источник цен — `sku_catalog_price` (реальные приказы iiko), не средняя по чекам. 3-уровневая
иерархия (sku → group → global) с empirical-Bayes сжатием.

### B2.1 `GET /elasticity`
Список оценок эластичности (`sku_elasticity`).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `department_id` | uuid? | Фильтр |
| `product_id` | int? | Фильтр |
| `reliability_grade` | string? | `A`/`B`/`C`/`D` |
| `estimation_level` | string? | `sku`/`group`/`global` |
| `limit` | int=200 (≤2000) / `offset` | Пагинация |

**Элемент:** `product_id, department_id, product_name, elasticity_mean, elasticity_ci_lower, elasticity_ci_upper, elasticity_se, n_price_events, n_observations, estimation_level, reliability_grade, group_key, model_r_squared, model_version, updated_at`.

> **Near-zero ε:** `reliability_grade` отражает *количество данных*, не значимость. Оценка ε≈0 с
> `elasticity_ci_upper ≈ 0` означает «нет измеримого ценового сигнала», а не реальную
> неэластичность. Признак реального эффекта — весь 95% CI < 0.

### B2.2 `GET /elasticity/summary`
→ `{by_grade: {A,B,C,D}, by_level: {sku,group,global}, total, global_prior}`.

### B2.3 `POST /elasticity/estimate`
Ручной запуск переоценки. Query: `lookback_days` (540, диапазон 90–730).
→ отчёт `{status, total, upserted, global_prior, groups_estimated, by_grade, by_level, model_version}`.
> ⚠️ **Тяжёлый прогон (минуты).** Выполняется в threadpool и не блокирует event loop, но грузит
> CPU и держит соединение. Регулярная переоценка уже выполняется планировщиком в фоне
> (воскресенье 03:30, lookback 730). Ручной вызов — для отладки.

### B2.4 `GET /elasticity/{product_id}/{department_id}`
Одна оценка с диагностикой. → поля как в списке + `diagnostics` (JSONB, напр. `{global_prior: ...}`). `404` если нет.

---

## B3. Рекомендации цен — `/api/pricing-engine/recommendations`

Оптимизатор (grid-search GP-maximizer) с учётом эластичности и 8 бизнес-правил.

### B3.1 `POST /recommendations/generate`
Сгенерировать рекомендации для подразделения. Query: `department_id` (req), `min_gp_threshold` (500.0).
→ `{status, recommendations_created, skipped_no_cogs, ...}`.
> Также планировщик: ежедневно 05:00 по всем активным точкам.
>
> Семантика: каждый прогон **вытесняет** все открытые (`new`) рекомендации подразделения в
> `expired` и публикует свежий батч — открытый список всегда отражает последний расчёт,
> по одной рекомендации на SKU. `current_price` берётся из каталожных цен (`sku_catalog_price`,
> приказы iiko) с fallback на производную цену; прогноз спроса — среднее за 30 календарных
> дней; SKU без себестоимости пропускаются (`skipped_no_cogs`), иначе правило min_margin
> было бы необъективно. `constraints_applied` содержит правила, реально ограничившие
> пространство поиска (например `max_step`, `min_margin`).
>
> Эластичность для планирования: grade A/B — точечная `elasticity_mean`; grade C/D —
> консервативный край CI (`elasticity_ci_lower`), без записи — fallback −1.0. Поэтому
> ΔGP для ненадёжных оценок — нижняя граница, а не оптимистичный прогноз.

### B3.2 `GET /recommendations`
Список рекомендаций (`price_recommendation`).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `department_id` | uuid? | Фильтр |
| `status` | string? | `new`/`approved`/`rejected`/`expired`/`applied` |
| `batch_id` | uuid? | Фильтр по партии генерации |
| `rec_type` | string? | `optimizer` / `experiment` |
| `limit` | int=100 (≤1000) / `offset` | Пагинация |

**Элемент:** `id, product_id, product_name, department_id, department_name, batch_id, current_price, recommended_price, delta_pct, cogs, current_qty_forecast, new_qty_forecast, current_gp, expected_gp, delta_gp, elasticity_used, elasticity_grade, menu_role, constraints_applied, llm_explanation, status, created_at, reviewed_at, review_comment`. Сортировка по `delta_gp DESC`.

### B3.3 `GET /recommendations/export`
Экспорт в XLSX для ручной загрузки в iiko. Query: `department_id?`, `status` (default `approved`).
→ `.xlsx` (колонки: Подразделение, Код, Позиция, Роль, Текущая/Рекоменд. цена, Δ%, COGS, GP-поля, Эластичность, Надёжность, Статус).

### B3.4 `PUT /recommendations/{rec_id}/review`
Утвердить/отклонить одну. Query: `status` (`approved`/`rejected`, req), `comment?`, `reviewer_id?`.
→ обновлённая запись. `400` при ином статусе, `404` если запись не найдена или уже не `new`.

### B3.5 `POST /recommendations/batch-review`
Массовое решение. Query: `rec_ids` (CSV ID, req), `status` (`approved`/`rejected`, req), `reviewer_id?`, `comment?`.
→ `{updated: <фактически обновлено>, requested: <передано>}`. Обновляются только записи в статусе `new`. `400` при ином статусе.

### B3.6 `GET /recommendations/summary`
→ `{by_status: {new, approved, rejected, expired, applied}, total, total_delta_gp_new}` (потенциальный прирост GP по новым с `delta_gp>0`). Query: `department_id?`.

---

## FB. Фидбек-loop — `/api/pricing-engine` (applied / outcomes / baseline)

Замыкает цикл «рекомендация → приказ в iiko → измеренный эффект» (roadmap §7.4) и
фиксирует базу KPI для пилота (A3).

### FB.1 `POST /recommendations/detect-applied`
Пометить `approved`-рекомендации как `applied`, если в `sku_catalog_price` появился
интервал с рекомендованной ценой, начавшийся не раньше даты утверждения.
→ `{status, applied: <n>, ids}`. Выполняется автоматически после ежедневного синка цен (03:20).

### FB.2 `POST /outcomes/evaluate`
Оценить applied-рекомендации, у которых прошло полное окно (14 дней).
→ `{status, pending, evaluated, skipped}`. Планировщик: ежедневно 05:30.

### FB.3 `GET /outcomes`
Список оценённых результатов (`price_recommendation_outcome`). Query: `department_id?`, `limit`/`offset`.
**Элемент:** `recommendation_id, product_name, applied_at, old_price, new_price, qty_before/after,
gp_before/after, expected_delta_gp, actual_delta_gp, qty_change_pct, control_qty_change_pct,
adj_qty_change_pct, realized_elasticity, n_control_skus`. Контрольная группа — SKU той же
категории и точки без изменения каталожной цены за период наблюдения.

### FB.4 `GET /outcomes/summary`
→ `{total_evaluated, expected_delta_gp, actual_delta_gp, positive_outcomes, hit_rate, avg_realized_elasticity}`. Query: `department_id?`.

### FB.5 `POST /baseline/freeze`
Заморозить KPI за N полных ISO-недель как базу пилота. Query: `label` (req, напр. `pre-pilot-2026-06`), `weeks` (8, 2–26).
→ `{status, label, departments, baseline_from, baseline_to, weeks}`. Повторный вызов с тем же label перезаписывает.
Пишет строки `scope=department` (по точкам) + `scope=network` (агрегат).

### FB.6 `GET /baseline`
Снимки базы (`pricing_baseline_kpi`). Query: `label?`.
**Элемент:** `label, scope, department_name, baseline_from/to, weeks, total_revenue, total_cost,
gross_profit, gp_margin, total_receipts, avg_receipt_sum, weekly_gp_avg, weekly_gp_stddev,
active_skus, cost_coverage`.

---

## EX. Ценовые эксперименты — `/api/pricing-engine/experiments`

Контролируемые изменения цены для **измерения** эластичности grade C/D SKU (а не для max GP).

### EX.1 `POST /experiments/generate`
Query: `department_id` (req), `n` (10, ≤50), `delta_pct` (4.0, 2–5).
Кандидаты: grade C/D, известная себестоимость, без изменений цены ≥28 дней, ранжирование по
обороту (быстрее сигнал). Цена +delta% с округлением по роли, все бизнес-правила соблюдаются.
→ `{status, batch_id, candidates, experiments_created, items}`.
Созданные записи имеют `rec_type='experiment'` и идут обычным циклом approve → applied →
outcome; `realized_elasticity` из outcome — новое ценовое событие для будущих переоценок.
Оптимизатор не трогает SKU с открытым экспериментом и не вытесняет эксперименты ежедневным батчем.

---

## AU. Аудит — `GET /api/pricing-engine/audit-log`

Append-only журнал действий (ТЗ п.9.3, `pricing_audit_log`): утверждения/отклонения рекомендаций
(в т.ч. batch), `applied`-детекция, CRUD правил, override ролей меню, заморозка baseline,
генерация экспериментов.
Query: `entity_type?` (`recommendation`/`rule`/`menu_role`/`baseline`/`experiment`), `entity_id?`,
`action?`, `department_id?`, `limit`/`offset`.
**Элемент:** `entity_type, entity_id, action, actor, department_id, details (JSONB), created_at`.

---

## JB. Фоновые джобы — `/api/pricing-engine/jobs`

Тяжёлые ручные прогоны можно запускать без удержания HTTP-соединения:
`POST /elasticity/estimate?background=true` и `POST /pricing-analytics/backfill?background=true`
сразу возвращают `{status: "running", job_id}`.

### JB.1 `GET /jobs/{job_id}`
→ `{job_id, name, status: running|done|error, started_at, finished_at, result}`.
Реестр процесс-локальный (in-memory): очищается при рестарте контейнера, хранит последние 50
завершённых. Регулярные прогоны идут через планировщик, фоновый режим — для отладки.

---

## B4. Бизнес-правила — `/api/pricing-engine/rules`

9 типов ограничений со scope-каскадом (`product` > `department` > `segment` > `global`).
7 дефолтных глобальных правил засеяны (шаг ≤ +5%, маржа ≥ 60%, премиум-якоря только дорожают,
округление до 50₸ / флагманы 100₸, не чаще 1 изменения в 2 недели, ≤15 утверждённых
изменений на точку за 14 дней).

`max_changes_per_cycle` (`{"value": N, "window_days": D}`) — портфельное правило: проверяется
не на кандидате, а при утверждении (review/batch-review). Превышение → `409 Conflict` с
деталями (использовано/лимит/окно). Scope: `department` > `global`.

### B4.1 `GET /rules`
Список правил. Query: `rule_type?`, `scope_type?`, `is_active?`. → `{items, total}`.

### B4.2 `POST /rules`
Создать. Query: `rule_type` (req), `scope_type` (`global`), `scope_id?`, `params` (req — **JSON-строка**), `configured_by_role?`. `400` при невалидном JSON.

### B4.3 `PUT /rules/{rule_id}`
Обновить. Query: `params?` (JSON-строка), `is_active?`.

### B4.4 `DELETE /rules/{rule_id}`
Удалить правило (физическое удаление — освобождает UNIQUE-слот для пере-создания).

### B4.5 `GET /rules/effective/{product_id}/{department_id}`
Эффективный набор правил для позиции после scope-каскада. Query: `segment_type?`. → `{rules: [...]}`.

---

## RP. Отчёты по ценам — `/api/pricing-engine/reports`

C4: еженедельные/ежемесячные LLM-сводки по управлению ценами (`pricing_report`).
Сервис собирает метрики за период прямым SQL (активность рекомендаций, outcomes,
динамика KPI vs предыдущий период, baseline, топ-движения) и зовёт Claude-движок
существующей AI-подсистемы. Числа подаются модели JSON-блоком — не выдумываются.
Промпты `PricingWeeklyReportAgent` / `PricingMonthlyReportAgent` редактируются через
`/api/ai-recommendations/prompts`.

### RP.1 `GET /reports`
Список отчётов. Query: `report_type?` (`weekly`/`monthly`), `department_id?`
(NULL-скоуп = сеть), `limit` (50, ≤500) / `offset`.
**Элемент:** `id, report_type, scope (network|department), department_id, department_name,
period_start, period_end, kpis {gross_profit, gp_delta_pct, gp_margin, avg_receipt_sum,
recs_approved, recs_applied, outcomes_evaluated, actual_delta_gp, hit_rate}, provider,
model, status (ok|no_llm|error), created_at`. Без `data`/`narrative`.

### RP.2 `GET /reports/{id}`
Полный отчёт: поля как в списке + `data` (JSONB-снимок собранных метрик) + `narrative`
(текст LLM, Markdown). `404` если нет.

### RP.3 `POST /reports/generate`
Сгенерировать отчёт сейчас (зовёт LLM, ~15–60с). Query: `report_type` (req,
`weekly`/`monthly`), `department_id?` (без него — сеть), `period_start?`/`period_end?`
(без них — прошлая полная неделя / прошлый календарный месяц), `provider` (`claude`).
→ `{id, report_type, status, period_start, period_end, has_narrative}`.
> Также планировщик: пн 08:00 (weekly) и 1-е число 08:00 (monthly), network-уровень.

---

## Планировщик (автоматизация)

| Время | Задача | Эффект |
|-------|--------|--------|
| Вс 03:15 | Кластеризация меню (B1) | `sku_menu_role` |
| Ежедн. 03:20 | Синк цен из приказов iiko (+stale-маркировка отозванных, + детекция applied) | `sku_catalog_price`, `price_recommendation.status` |
| Вс 03:30 | Переоценка эластичности (B2, lookback 730) | `sku_elasticity` |
| Ежедн. 04:30 | Агрегация витрин (A2) | `sku_price_history`, `*_weekly_summary` |
| Ежедн. 05:00 | Генерация рекомендаций (B3) | `price_recommendation` |
| Ежедн. 05:30 | Оценка результатов applied-рекомендаций (FB) | `price_recommendation_outcome` |
| Пн 08:00 | Еженедельный LLM-отчёт (C4, network) | `pricing_report` |
| 1-е число 08:00 | Ежемесячный LLM-отчёт (C4, network) | `pricing_report` |

Ручные `POST`-эндпоинты (`/aggregate`, `/backfill`, `/elasticity/estimate`, `/recommendations/generate`,
`/menu-roles/cluster`) — для отладки/первичного наполнения; в норме всё обновляется планировщиком.

Каждый прогон pricing-джоба пишет итог (success/partial/error + счётчики) в `auto_sync_log`
(`sync_type`: `pricing_catalog_price`, `pricing_elasticity`, `pricing_optimization`,
`pricing_outcomes`, `pricing_analytics`, `menu_clustering`) — виден через
`GET /api/sales/auto-sync/status` и на странице «Синхронизация».

Методология эластичности: group/global-регрессии используют **within-оценку** (fixed effects
по паре SKU×dept) — ε идентифицируется только из временной вариации цен (реальные приказы),
межпозиционные различия уровней цен не загрязняют оценку; SE с поправкой степеней свободы
на поглощённые FE.

---

## Связанные документы
- [`docs/PRICING_SYSTEM_ROADMAP.md`](docs/PRICING_SYSTEM_ROADMAP.md) — дизайн, формулы, прогресс по этапам A–D
- [`docs/MENU_AND_RECEIPTS_ARCHITECTURE.md`](docs/MENU_AND_RECEIPTS_ARCHITECTURE.md) — слой данных (чеки, номенклатура, себестоимость, SKU-прогноз)
- [`Sandyq_pricing_summary.md`](Sandyq_pricing_summary.md) — управленческая записка по результатам
- [`API_DOCUMENTATION_LABOR_DEMAND.md`](API_DOCUMENTATION_LABOR_DEMAND.md) — сигнал спроса для TCO (потребляет данные ценообразования)

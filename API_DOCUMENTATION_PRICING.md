# API: Система интеллектуального ценообразования

Справочник по REST API подсистемы ценообразования Sales Forecast: аналитические витрины,
роли меню, эластичность, ценовые рекомендации и бизнес-правила.

- **Версия:** 1.0 (2026-06-10)
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
| `status` (рекомендации) | `new`, `approved`, `rejected` |
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
| `pricing_rule` | 6 (дефолтные глобальные) |

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
> ⚠️ **Тяжёлый синхронный прогон — на проде использует один воркер.** Регулярная переоценка
> уже выполняется планировщиком в фоне (воскресенье 03:30, lookback 730). Ручной вызов — для отладки.

### B2.4 `GET /elasticity/{product_id}/{department_id}`
Одна оценка с диагностикой. → поля как в списке + `diagnostics` (JSONB, напр. `{global_prior: ...}`). `404` если нет.

---

## B3. Рекомендации цен — `/api/pricing-engine/recommendations`

Оптимизатор (grid-search GP-maximizer) с учётом эластичности и 8 бизнес-правил.

### B3.1 `POST /recommendations/generate`
Сгенерировать рекомендации для подразделения. Query: `department_id` (req), `min_gp_threshold` (500.0).
→ `{status, recommendations_created, ...}`.
> Также планировщик: ежедневно 05:00 по всем активным точкам.

### B3.2 `GET /recommendations`
Список рекомендаций (`price_recommendation`).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `department_id` | uuid? | Фильтр |
| `status` | string? | `new`/`approved`/`rejected` |
| `batch_id` | uuid? | Фильтр по партии генерации |
| `limit` | int=100 (≤1000) / `offset` | Пагинация |

**Элемент:** `id, product_id, product_name, department_id, department_name, batch_id, current_price, recommended_price, delta_pct, cogs, current_qty_forecast, new_qty_forecast, current_gp, expected_gp, delta_gp, elasticity_used, elasticity_grade, menu_role, constraints_applied, llm_explanation, status, created_at, reviewed_at, review_comment`. Сортировка по `delta_gp DESC`.

### B3.3 `GET /recommendations/export`
Экспорт в XLSX для ручной загрузки в iiko. Query: `department_id?`, `status` (default `approved`).
→ `.xlsx` (колонки: Подразделение, Код, Позиция, Роль, Текущая/Рекоменд. цена, Δ%, COGS, GP-поля, Эластичность, Надёжность, Статус).

### B3.4 `PUT /recommendations/{rec_id}/review`
Утвердить/отклонить одну. Query: `status` (`approved`/`rejected`, req), `comment?`, `reviewer_id?`. → обновлённая запись.

### B3.5 `POST /recommendations/batch-review`
Массовое решение. Query: `rec_ids` (CSV ID, req), `status` (req), `reviewer_id?`. → `{updated: <n>}`.

### B3.6 `GET /recommendations/summary`
→ `{by_status: {new, approved, rejected}, total, total_delta_gp_new}` (потенциальный прирост GP по новым с `delta_gp>0`). Query: `department_id?`.

---

## B4. Бизнес-правила — `/api/pricing-engine/rules`

8 типов ограничений со scope-каскадом (`product` > `department` > `segment` > `global`).
6 дефолтных глобальных правил засеяны (шаг ≤ +5%, маржа ≥ 60%, премиум-якоря только дорожают,
округление до 50₸ / флагманы 100₸, не чаще 1 изменения в 2 недели).

### B4.1 `GET /rules`
Список правил. Query: `rule_type?`, `scope_type?`, `is_active?`. → `{items, total}`.

### B4.2 `POST /rules`
Создать. Query: `rule_type` (req), `scope_type` (`global`), `scope_id?`, `params` (req — **JSON-строка**), `configured_by_role?`. `400` при невалидном JSON.

### B4.3 `PUT /rules/{rule_id}`
Обновить. Query: `params?` (JSON-строка), `is_active?`.

### B4.4 `DELETE /rules/{rule_id}`
Удалить правило.

### B4.5 `GET /rules/effective/{product_id}/{department_id}`
Эффективный набор правил для позиции после scope-каскада. Query: `segment_type?`. → `{rules: [...]}`.

---

## Планировщик (автоматизация)

| Время | Задача | Эффект |
|-------|--------|--------|
| Вс 03:15 | Кластеризация меню (B1) | `sku_menu_role` |
| Вс 03:20 | Синк цен из приказов iiko | `sku_catalog_price` |
| Вс 03:30 | Переоценка эластичности (B2, lookback 730) | `sku_elasticity` |
| Ежедн. 04:30 | Агрегация витрин (A2) | `sku_price_history`, `*_weekly_summary` |
| Ежедн. 05:00 | Генерация рекомендаций (B3) | `price_recommendation` |

Ручные `POST`-эндпоинты (`/aggregate`, `/backfill`, `/elasticity/estimate`, `/recommendations/generate`,
`/menu-roles/cluster`) — для отладки/первичного наполнения; в норме всё обновляется планировщиком.

---

## Связанные документы
- [`docs/PRICING_SYSTEM_ROADMAP.md`](docs/PRICING_SYSTEM_ROADMAP.md) — дизайн, формулы, прогресс по этапам A–D
- [`docs/MENU_AND_RECEIPTS_ARCHITECTURE.md`](docs/MENU_AND_RECEIPTS_ARCHITECTURE.md) — слой данных (чеки, номенклатура, себестоимость, SKU-прогноз)
- [`Sandyq_pricing_summary.md`](Sandyq_pricing_summary.md) — управленческая записка по результатам
- [`API_DOCUMENTATION_LABOR_DEMAND.md`](API_DOCUMENTATION_LABOR_DEMAND.md) — сигнал спроса для TCO (потребляет данные ценообразования)

# Labor Optimization — архитектура

Подсистема оптимизации ФОТ: TCO («Учет рабочего времени») генерирует график работы
сотрудников, а Sales Forecast обогащает этот процесс сигналом спроса по локации.

**Статус**: дизайн (2026-05-02). Контур интеграции согласован с командой TCO 2026-06-10
(Вариант А — см. §0). Реализация эндпоинтов §2 не начата.

**Главное архитектурное решение**: солвер (генерация графика) **и** LLM-агенты (ревью/правка
графика) живут **в TCO**, не в Sales Forecast. Sales Forecast — **только поставщик сигнала спроса**.

**Принцип**: data gravity — вычисление живёт там, где живут данные. ~80% входных данных солвера
(сотрудники, ставки, ФОТ, отпуска, фактическое посещение, ТК, календарь, утверждение) и сами
LLM-агенты находятся в TCO. Sales Forecast отдаёт прогноз продаж и профиль меню.

---

## 0. Согласование с командой TCO (2026-06-10)

TCO дал обратную связь по первой версии этого документа. Ключевые договорённости (**Вариант А**):

**TCO уже реализовал у себя** (не дублируем в Sales Forecast):
- Солвер графика (OR-Tools) — совпадает с нашим решением «солвер в TCO».
- Собственную multi-agent LLM-систему (агенты по продажам, графику, рискам + финальный синтез),
  напрямую через Claude с prompt-caching.
- Расчёт потребности в персонале по ролям (`demand_by_role`) из собственной калибровки —
  у TCO есть факт-смены, посещаемость и ставки, на которых это калибруется.

**Поэтому из зоны Sales Forecast УБРАНО** (было в дизайне v1, теперь делает TCO):
- ❌ `labor_norms`, `forecast_to_demand()`, расчёт `demand_by_role` и плоский
  `GET /api/labor-demand` — TCO считает потребность сам, два источника истины не нужны.
- ❌ `POST /api/ai/review-schedule`, `POST /api/ai/edit-schedule` и агенты
  `ScheduleReviewerAgent` / `ScheduleNarrativeAgent` / `ScheduleEditorAgent` — ревью и правку
  графика TCO делает своими агентами.

**Что Sales Forecast делает** (приоритет по запросу TCO):
1. **§2.1 `/menu-mix`** — приоритет №1. `category_load` + `role_distribution` → агенты TCO
   рекомендуют не «сколько людей», а «каких» (повар горячего цеха / кондитер / бариста).
2. **§2.2 `/forecast`** — почасовая кривая спроса. Закрывает реальную дыру TCO: для будущих
   периодов у них нет почасового факта, сейчас фолбэк на среднее за 30 дней.
3. **§2.3 `/elasticity-signal`** — контекст «где нельзя экономить на персонале».

**Прочее**:
- Auth: общий `Authorization: Bearer $API_TOKEN`, как у остальных эндпоинтов, которые TCO уже
  потребляет (department-метаданные, hourly sales, `batch_with_postprocessing`, `forecast/comparison`).
- Таймзона: Asia/Almaty (UTC+5), ISO-8601 с явной зоной во всех новых эндпоинтах.
- `predicted_qty` зависит от ещё дообучаемой SKU-модели → всегда отдаём `data_quality`-флаги,
  TCO делает graceful-degradation.

---

## 1. Разделение ответственности

### Sales Forecast (этот проект)

Зона ответственности — **поставка сигнала спроса и профиля меню**:

| Компонент | Статус | Описание |
|---|---|---|
| LightGBM прогноз выручки (dept-level) | ✅ есть | MAPE 6.18%, `app/agents/sales_forecaster_agent.py` |
| SKU-прогноз количества по блюдам | ✅ есть | `app/agents/sku_forecaster_agent.py` (⚠️ требует дообучения на полных данных) |
| Кластеризация меню (5 ролей) | ✅ есть | `app/services/menu_clustering_service.py`, `sku_menu_role` |
| Ценовые витрины (weekly summaries) | ✅ есть | `sku_weekly_summary`, `department_weekly_summary` |
| Эластичность спроса | ✅ есть | `sku_elasticity` (движок B2) |
| `GET /api/labor-demand/{id}/menu-mix` | ⏳ TODO (P1) | Профиль меню: топ-блюда, роли, загрузка цехов (§2.1) |
| `GET /api/labor-demand/{id}/forecast` | ⏳ TODO (P2) | Дневной спрос + почасовая кривая (§2.2) |
| `GET /api/labor-demand/{id}/elasticity-signal` | ⏳ TODO (P3) | Экономический контекст флагманов (§2.3) |

**Что НЕ должно быть в Sales Forecast**:
- ❌ Солвер (OR-Tools, constraint programming) — в TCO
- ❌ LLM-ревью / правка графика и schedule-агенты — в TCO
- ❌ `labor_norms`, `forecast_to_demand()`, `demand_by_role` — потребность по ролям считает TCO
- ❌ Таблицы со сменами (`shifts`), ФОТ-выплатами (`payroll_records`), отпусками — в TCO
- ❌ Календарь / UI редактирования графика, workflow утверждения — в TCO
- ❌ Интеграция с 1С для ФОТ — в TCO

### Time Tracking / TCO (отдельный сервис)

Зона ответственности — **построение, ревью, утверждение и публикация графика**:

| Компонент | Описание |
|---|---|
| Solver (OR-Tools) | Генерация графика из (demand + employees + constraints) → минимум ФОТ при покрытии спроса |
| Расчёт `demand_by_role` | Конвертация сигнала спроса (от Sales Forecast) в потребность по ролям из своей калибровки |
| Multi-agent LLM (свой) | Агенты по продажам / графику / рискам + синтез, напрямую через Claude + prompt-caching |
| Календарь UI | Отображение графика, drag-and-drop редактирование, visual diff «было/стало» |
| Workflow утверждения | Draft → On Review → Approved → Published |
| Сотрудники, ставки, ФОТ | Из 1С |
| Отпуска / больничные / доступность / факт-посещение | Своя БД |
| ТК-ограничения РК | Constraints солвера |
| Уведомления сотрудникам | Telegram / email при публикации |

---

## 2. API контракты: Sales Forecast → TCO

Три read-only эндпоинта под namespace `/api/labor-demand/`. Строятся на уже существующих
данных (SKU-прогноз, кластеризация меню, ценовые витрины, эластичность) — новых ML-моделей
не требуют. Авторизация — общий `Authorization: Bearer $API_TOKEN`. Таймзона — Asia/Almaty (UTC+5).

**Зафиксированные решения**:

| Вопрос | Решение |
|---|---|
| Внутридневная кривая (`hourly_profile`) | **Историческая средняя** из `sales_by_hour` по дню недели за 4–8 недель. ML-прогноза по часам нет; внутридневной паттерн стабилен и для штатки достаточен. |
| Прогноз qty по блюдам (`predicted_qty`) | **SKU LightGBM** (`forecast/sku/batch`). ⚠️ SKU-модель требует дообучения на полных данных перед прод-использованием → отдаём `data_quality`-флаги. |
| Аутентификация | Общий `Authorization: Bearer $API_TOKEN` (`get_api_key_or_bypass`), как у эндпоинтов, которые TCO уже потребляет. |

### 2.1. `GET /api/labor-demand/{department_id}/menu-mix` — ⭐ профиль меню (ЧТО готовят) — P1

Главное обогащение. Вместо плоской суммы — разбивка по блюдам, ролям меню и категориям-цехам.

```http
GET /api/labor-demand/{department_id}/menu-mix?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&top_n=25
Authorization: Bearer ...
```

**Response**:
```json
{
  "department_id": "a1b2c3d4-...",
  "department_name": "Tary Astana Mega",
  "period": { "from": "2026-06-12", "to": "2026-06-18" },

  "role_distribution": {
    "traffic_driver":  { "sku_count": 38,  "qty_share": 0.46, "revenue_share": 0.31 },
    "margin_driver":   { "sku_count": 24,  "qty_share": 0.19, "revenue_share": 0.27 },
    "premium_anchor":  { "sku_count": 9,   "qty_share": 0.05, "revenue_share": 0.18 },
    "image_rare":      { "sku_count": 12,  "qty_share": 0.03, "revenue_share": 0.09 },
    "tail":            { "sku_count": 140, "qty_share": 0.27, "revenue_share": 0.15 }
  },

  "top_dishes": [
    {
      "product_id": 88123,
      "product_name": "Казан жаппа",
      "product_type": "DISH",
      "category_name": "Горячие блюда",
      "group_name": "Казахская кухня",
      "menu_role": "premium_anchor",
      "predicted_qty": 210,
      "qty_share": 0.08,
      "revenue_share": 0.11,
      "avg_price": 6490,
      "gp_margin": 0.62,
      "demand_cv": 0.34,
      "rank": 1
    },
    {
      "product_id": 88150,
      "product_name": "Бауырсақ балқаймақпен",
      "product_type": "DISH",
      "category_name": "Выпечка",
      "group_name": "Выпечка",
      "menu_role": "traffic_driver",
      "predicted_qty": 540,
      "qty_share": 0.20,
      "revenue_share": 0.09,
      "avg_price": 1990,
      "gp_margin": 0.71,
      "demand_cv": 0.22,
      "rank": 2
    }
  ],

  "category_load": [
    { "category_name": "Горячие блюда", "predicted_qty": 920, "qty_share": 0.34, "sku_count": 45 },
    { "category_name": "Выпечка",        "predicted_qty": 760, "qty_share": 0.28, "sku_count": 22 },
    { "category_name": "Напитки",        "predicted_qty": 610, "qty_share": 0.22, "sku_count": 31 },
    { "category_name": "Десерты",        "predicted_qty": 240, "qty_share": 0.09, "sku_count": 18 }
  ],

  "data_quality": {
    "cost_coverage": 0.865,
    "clustering_silhouette": 0.37,
    "menu_roles_run_date": "2026-05-26",
    "sku_model_trained": false
  }
}
```

**Семантика полей**:
- `role_distribution` — распределение по 5 ролям меню (из кластеризации KMeans). Роли:
  - `traffic_driver` — драйвер трафика (высокая доля qty, низкая маржа) → грузит кухню в пик.
  - `margin_driver` — драйвер маржи (высокая маржа, заметная выручка).
  - `premium_anchor` — премиум-якорь/флагман (высокий чек, низкое qty) → нужен опытный повар.
  - `image_rare` — имиджевые/редкие позиции.
  - `tail` — «хвост» (низкие qty/маржа/выручка).
- `top_dishes` — топ-`top_n` блюд по прогнозному вкладу. `predicted_qty` — SKU LightGBM на период;
  `qty_share`/`revenue_share`/`gp_margin`/`demand_cv` — из `sku_menu_role.features` и `sku_weekly_summary`.
- `category_load` — нагрузка по категориям = прокси загрузки цехов кухни. Мэппинг категория→цех
  делает TCO (см. §5).
- `data_quality` — флаги достоверности: `cost_coverage` (доля позиций с себестоимостью),
  `clustering_silhouette` (качество кластеризации), `menu_roles_run_date` (свежесть ролей),
  `sku_model_trained` (false, пока SKU-модель не дообучена — TCO делает graceful-degradation).

**Источники**: `forecast/sku/batch` (`predicted_qty`) + `sku_menu_role` (`effective_role`, `features`)
+ `sku_weekly_summary` (`gp_margin`, `qty_cv`) + `product` (`category_name`, `group_name`).

### 2.2. `GET /api/labor-demand/{department_id}/forecast` — временной сигнал (КОГДА грузит) — P2

Закрывает дыру TCO: для будущих периодов у них нет почасового факта (фолбэк на среднее за 30 дней).

```http
GET /api/labor-demand/{department_id}/forecast?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD
Authorization: Bearer ...
```

**Response**:
```json
{
  "department_id": "a1b2c3d4-...",
  "department_name": "Tary Astana Mega",
  "segment_type": "restaurant",
  "model_version": "v_20260607_030006",
  "days": [
    {
      "date": "2026-06-12",
      "day_of_week": "friday",
      "is_weekend": false,
      "predicted_revenue": 1842000,
      "predicted_receipts": 612,
      "predicted_total_qty": 2740,
      "confidence": "high",
      "hourly_profile": [
        { "hour": 11, "revenue_share": 0.04 },
        { "hour": 12, "revenue_share": 0.11 },
        { "hour": 13, "revenue_share": 0.14 },
        { "hour": 19, "revenue_share": 0.13 }
      ]
    }
  ]
}
```

**Семантика полей**:
- `predicted_revenue` — дневной прогноз выручки (LightGBM, dept-level, `forecast/batch`).
- `predicted_receipts` — оценка числа чеков (гостей) = `predicted_revenue / avg_receipt_sum` из `department_weekly_summary`.
- `predicted_total_qty` — сумма `predicted_qty` по всем SKU за день (из SKU-прогноза).
- `confidence` — `high` для горизонта 1–7 дней, `medium` для 8+ (hybrid-логика прогноза).
- `hourly_profile` — доля дневного оборота по часам (только часы с продажами). **Историческая
  средняя** по дню недели за 8 недель (не прогноз). Содержит **только `revenue_share`** —
  `sales_by_hour` хранит выручку, не количество, поэтому почасового `qty_share` нет.
  `revenue_share` суммируется в ~1.0. TCO умножает долю на `predicted_revenue` → форвардная
  почасовая кривая вместо `recent_30d`.

**Источники**: `forecast/batch` + `department_weekly_summary.avg_receipt_sum` + `sku_daily_sales` + `sales_by_hour`.

### 2.3. `GET /api/labor-demand/{department_id}/elasticity-signal` — экономический контекст — P3

Контекст «где нельзя экономить на персонале»: насколько «дорого» терять качество на флагманах.

```http
GET /api/labor-demand/{department_id}/elasticity-signal?grade=A,B
Authorization: Bearer ...
```

**Response**:
```json
{
  "department_id": "a1b2c3d4-...",
  "global_prior": -0.47,
  "items": [
    {
      "product_id": 88123,
      "product_name": "Казан жаппа",
      "menu_role": "premium_anchor",
      "elasticity_mean": -0.31,
      "reliability_grade": "B",
      "estimation_level": "sku"
    }
  ]
}
```

**Семантика полей**:
- `elasticity_mean` — точечная оценка эластичности ε (отрицательная; ближе к 0 = менее
  чувствителен к цене и к качеству → на таких позициях нельзя экономить на людях).
- `reliability_grade` — надёжность оценки: `A` (≥5 ценовых событий и ≥90 дней) … `D` (fallback).
- `estimation_level` — уровень иерархии оценки: `sku` / `group` / `global`.
- `global_prior` — глобальная эластичность сети (база, когда по SKU данных мало).

**Источник**: `sku_elasticity` (движок эластичности B2).

### 2.4. Привязка к ИИ-агентам TCO

Агенты живут в TCO; ниже — какой эндпоинт какой агент потребляет (по их контуру интеграции).

| Агент TCO | Тянет | Что извлекает |
|---|---|---|
| Sales | §2.2 `/forecast` `hourly_profile` | форвардная почасовая кривая вместо `recent_30d` |
| Schedule | §2.1 `/menu-mix` → `category_load` | загрузка цехов → состав смены (повар горячего / кондитер / бариста) |
| Risks | §2.1 `top_dishes` + §2.3 `/elasticity` | флагманы / низкая эластичность → где недокомплект бьёт по выручке сильнее |
| Orchestrator | оба блока через свой BusinessContext | сведение в финальную рекомендацию |

---

## 3. Поток работы (end-to-end)

```
1. Управляющий открывает TCO → "Расписание на следующую неделю" → "Сгенерировать"
                ↓
2. TCO собирает контекст: зовёт эндпоинты Sales Forecast (Promise.allSettled, graceful degradation):
   - GET /api/labor-demand/{id}/menu-mix     → category_load, role_distribution, top_dishes
   - GET /api/labor-demand/{id}/forecast      → дневной спрос + почасовая кривая
   - GET /api/labor-demand/{id}/elasticity-signal (опц.)
                ↓
3. TCO конвертирует сигнал в demand_by_role (своя калибровка) + прогоняет солвер (OR-Tools):
   - Входы: demand + employees + ставки + отпуска + ТК-constraints + menu-mix
   - Выход: optimal schedule
                ↓
4. TCO прогоняет СВОИ LLM-агенты (Sales / Schedule / Risks / Orchestrator) с обогащённым
   BusinessContext → warnings + narrative + рекомендации по составу смены
                ↓
5. TCO показывает в UI: график + AI-разбор + кнопки [Утвердить] [Редактировать]
                ↓
6. (опционально) Управляющий правит командой на естественном языке → СВОИ агенты TCO
   → патч → пере-прогон солвера → goto 4
                ↓
7. Управляющий жмёт [Утвердить] → TCO публикует график → уведомления сотрудникам
```

Sales Forecast участвует только в шаге 2 (отдаёт сигнал). Всё остальное — внутри TCO.

---

## 4. Roadmap (Sales Forecast)

Только зона Sales Forecast. Солвер, demand_by_role и LLM-агенты — отдельный roadmap TCO.

### Фаза 1 — эндпоинты сигнала спроса — ✅ ВЫПОЛНЕНО (2026-06-10)

- [x] `app/routers/labor_demand.py` + Pydantic-схемы (`app/schemas/labor_demand.py`) + регистрация в `main.py`
- [x] `GET /api/labor-demand/{id}/menu-mix` (P1) — агрегатор поверх `sku_menu_role` + SKU-прогноза + `sku_weekly_summary`
- [x] `GET /api/labor-demand/{id}/forecast` (P2) — dept-прогноз + почасовая кривая из `sales_by_hour` (только `revenue_share`)
- [x] `GET /api/labor-demand/{id}/elasticity-signal` (P3) — выборка из `sku_elasticity`
- [x] `data_quality`-флаги во всех ответах (`menu-mix`)
- [x] Логика в `app/services/labor_demand_service.py`; смоук-тесты `tests/integration/test_labor_demand_router.py` (13 passed)
- [ ] Поведение для неактивных/новых точек (см. §5 п.5) — сейчас пустые блоки + флаги; финализировать с TCO

### Фаза 2 — дообучение SKU-модели
**Срок**: параллельно

- [ ] Переобучить SKU LightGBM на полных данных (предпосылка для надёжного `predicted_qty`)
- [ ] Переключить `data_quality.sku_model_trained` → `true`
- [ ] До этого `/menu-mix` отдаёт `predicted_qty` с флагом → TCO делает graceful-degradation

### Фаза 3 — интеграция с TCO
**Срок**: 1 неделя

- [ ] Согласовать мэппинг категория→цех (см. §5 п.1) — справочник на стороне TCO
- [ ] End-to-end smoke test на 1 пилотной локации
- [ ] (опц.) Метрики потребления эндпоинтов TCO

---

## 5. Что согласовать с командой TCO

1. **Мэппинг категория → цех/станция** (для §2.1 `category_load`): Sales Forecast отдаёт
   `category_name` из номенклатуры iiko «как есть». Сопоставление «Горячие блюда → горячий цех»,
   «Выпечка → пекарня» и т.д. — на стороне TCO (это знание о составе бригады). Согласовать
   справочник категорий iiko ↔ роли персонала TCO.
2. **Глубина истории для `hourly_profile`**: 4 или 8 недель усреднения? Влияет на чувствительность
   к сезонным сдвигам трафика.
3. **Контракт `/forecast`**: TCO умножает `hourly_profile.*_share` на дневной `predicted_revenue` —
   подтвердить, что shares суммируются в ~1.0 и этого формата достаточно (vs абсолютные значения по часам).
4. **`data_quality` graceful-degradation**: согласовать, как именно TCO деградирует при
   `sku_model_trained=false` / низком `cost_coverage` (игнор блока / дисклеймер в промпте).
5. **Неактивные/новые точки**: department без 30 дней продаж или новое блюдо без истории —
   отдавать пусто, fallback на сегмент, или 404? (рекомендация: пустой блок + флаг в `data_quality`).
6. **SLA / частота вызовов**: как часто TCO дёргает эндпоинты (на каждую генерацию графика / cron),
   нужен ли rate limiting.

---

## 6. Открытые архитектурные вопросы

| Вопрос | Варианты | Решение |
|---|---|---|
| Кэширование `/menu-mix` (тяжёлая агрегация) | On-the-fly / материализованная витрина | TBD |
| Глубина усреднения `hourly_profile` | 4 нед / 8 нед | TBD (§5 п.2) |
| Поведение для неактивных/новых точек | Пусто+флаг / fallback сегмент / 404 | Рекомендация: пусто+флаг |
| Мэппинг категория→цех | Справочник в TCO / в Sales Forecast | Решено: в TCO (§5 п.1) |
| Rate limiting на `/api/labor-demand/*` | Нужен / не нужен | TBD (§5 п.6) |

---

## 7. Метрики успеха

Sales Forecast отвечает за **качество и доступность сигнала**, не за результат графика
(ФОТ, coverage и т.д. отслеживает TCO).

1. **Доступность эндпоинтов** `/api/labor-demand/*` (uptime, p95 latency)
2. **Свежесть данных**: `menu_roles_run_date`, актуальность SKU-прогноза
3. **Качество SKU-прогноза**: MAPE `predicted_qty` против факта (после дообучения модели)
4. **Покрытие себестоимости** (`cost_coverage`) — растёт по мере backfill
5. **Доля локаций с полным сигналом** (без флагов деградации в `data_quality`)

---

## 8. Связанные документы

- [`API_DOCUMENTATION_LABOR_DEMAND.md`](../API_DOCUMENTATION_LABOR_DEMAND.md) — **интеграционная документация по 3 эндпоинтам §2** (для команды TCO)
- [`AI_RECOMMENDATIONS_GUIDE.md`](AI_RECOMMENDATIONS_GUIDE.md) — мультиагентная подсистема Sales Forecast (отдельная от агентов TCO)
- [`PRICING_SYSTEM_ROADMAP.md`](PRICING_SYSTEM_ROADMAP.md) — кластеризация меню (B1), эластичность (B2), витрины (A2) — источники данных для §2
- [`MENU_AND_RECEIPTS_ARCHITECTURE.md`](MENU_AND_RECEIPTS_ARCHITECTURE.md) — SKU-прогноз, чеки, номенклатура
- [`FORECAST_IMPROVEMENT_PLAN.md`](FORECAST_IMPROVEMENT_PLAN.md) — улучшение прогноза продаж
- CLAUDE.md (раздел "Labor Optimization") — high-level overview для будущих сессий

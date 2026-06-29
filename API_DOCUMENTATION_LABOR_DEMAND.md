# API: Labor Demand Signal (Sales Forecast → TCO)

Интеграционная документация по read-only эндпоинтам, которыми Sales Forecast
снабжает ИИ-агентов TCO сигналом спроса по локации.

- **Версия:** 1.3 (2026-06-11)
- **Статус:** в проде на `https://aqniet.space`
- **Архитектура:** [`docs/LABOR_OPTIMIZATION_ARCHITECTURE.md`](docs/LABOR_OPTIMIZATION_ARCHITECTURE.md) §2
- **Зона ответственности:** Sales Forecast — только поставщик сигнала. Солвер, `demand_by_role`
  и LLM-агенты — на стороне TCO.

---

## Общее

### Base URL
```
https://aqniet.space
```

### Аутентификация
Все эндпоинты требуют Bearer-токен (тот же общий `API_TOKEN`, что TCO уже использует для
`department`-метаданных, `sales/hourly`, `forecast/*`):

```
Authorization: Bearer <API_TOKEN>
```

### Общие соглашения
- **Таймзона:** Asia/Almaty (UTC+5). Даты — `YYYY-MM-DD`.
- **`department_id`** — UUID подразделения (тип `DEPARTMENT`).
- **Доли** (`*_share`) — числа `[0..1]`, в сумме по группе ≈ 1.0.
- Денежные значения — в тенге (₸), без округления валюты.
- Все ответы — `application/json; charset=utf-8`.

### Коды ошибок (общие для всех эндпоинтов)
| Код | Когда |
|-----|-------|
| `400` | `department_id` не валидный UUID; `to_date < from_date`; диапазон > 31 дня; недопустимый `grade` |
| `401` / `403` | Отсутствует или неверный Bearer-токен |
| `404` | Подразделение с таким `department_id` не найдено |
| `422` | Отсутствует обязательный query-параметр (например, `from_date`) |

### Enum-значения
| Поле | Допустимые значения |
|------|---------------------|
| `menu_role` / ключи `role_distribution` | `traffic_driver`, `margin_driver`, `premium_anchor`, `image_rare`, `tail`, `unclassified` |
| `confidence` | `high` (горизонт 1–7 дней), `medium` (8+ дней) |
| `reliability_grade` | `A`, `B`, `C`, `D` |
| `estimation_level` | `sku`, `group`, `global` |

> `unclassified` появляется в `role_distribution`, если позиция спрогнозирована, но ещё не
> получила роль в кластеризации меню. Доли всё равно суммируются в ~1.0.

---

## 1. `GET /api/labor-demand/{department_id}/menu-mix`

⭐ **Приоритет №1.** Профиль меню за период: распределение по ролям, топ-блюда и нагрузка
по категориям (прокси загрузки цехов кухни). Позволяет агентам TCO рекомендовать *каких*
сотрудников ставить, а не только сколько.

### Параметры
| Параметр | Тип | Обяз. | По умолчанию | Описание |
|----------|-----|:----:|--------------|----------|
| `department_id` | UUID (path) | ✅ | — | Подразделение |
| `from_date` | date (query) | ✅ | — | Начало периода |
| `to_date` | date (query) | ❌ | = `from_date` | Конец периода (включительно). Макс. диапазон — 31 день |
| `top_n` | int (query) | ❌ | `25` | Кол-во блюд в `top_dishes` (1..200) |

### Пример запроса
```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.space/api/labor-demand/82e76bf2-903b-4ed9-9491-b875a33089ae/menu-mix?from_date=2026-06-12&to_date=2026-06-18&top_n=25"
```

### Структура ответа
| Поле | Тип | Описание |
|------|-----|----------|
| `department_id` | string | UUID подразделения |
| `department_name` | string\|null | Название |
| `period` | object | `{ "from": "YYYY-MM-DD", "to": "YYYY-MM-DD" }` |
| `role_distribution` | object | Ключ — роль меню; значение — `RoleStat` (см. ниже) |
| `top_dishes` | array | Топ-`top_n` блюд по прогнозному `predicted_qty` (`TopDish`) |
| `category_load` | array | Нагрузка по категориям, сорт. по `predicted_qty` (`CategoryLoad`) |
| `data_quality` | object | Флаги достоверности (`MenuDataQuality`) |

**`RoleStat`**
| Поле | Тип | Описание |
|------|-----|----------|
| `sku_count` | int | Кол-во SKU в роли |
| `qty_share` | float | Доля роли в суммарном прогнозном количестве за период |
| `revenue_share` | float | Доля роли в суммарной прогнозной выручке за период |

**`TopDish`**
| Поле | Тип | Описание |
|------|-----|----------|
| `product_id` | int | ID товара |
| `product_name` | string\|null | Название |
| `product_type` | string\|null | `DISH` / `GOODS` |
| `category_name` | string\|null | Категория iiko (→ цех на стороне TCO) |
| `group_name` | string\|null | Группа iiko |
| `menu_role` | string\|null | Роль меню (enum выше) |
| `predicted_qty` | float | Прогноз количества за период (SKU LightGBM) |
| `qty_share` | float | Доля блюда в общем прогнозном количестве |
| `revenue_share` | float | Доля блюда в общей прогнозной выручке |
| `avg_price` | float\|null | Реальная средняя цена = выручка/кол-во из `sku_weekly_summary` (fallback — прайс прогноза) |
| `gp_margin` | float\|null | Валовая маржа в диапазоне `[0..1]`. Вне диапазона → `null` (недостоверная себестоимость) |
| `demand_cv` | float\|null | Коэффициент вариации спроса (волатильность) |
| `rank` | int | Ранг по `predicted_qty` (1 = топ) |

**`CategoryLoad`**
| Поле | Тип | Описание |
|------|-----|----------|
| `category_name` | string\|null | Категория iiko |
| `predicted_qty` | float | Суммарный прогноз количества по категории |
| `qty_share` | float | Доля категории в общем прогнозном количестве |
| `sku_count` | int | Кол-во SKU в категории |

**`MenuDataQuality`**
| Поле | Тип | Описание |
|------|-----|----------|
| `cost_coverage` | float\|null | Доля позиций с известной себестоимостью (последняя неделя) |
| `clustering_silhouette` | float\|null | Качество кластеризации ролей меню |
| `menu_roles_run_date` | string\|null | Дата последней кластеризации (`YYYY-MM-DD`) |
| `sku_model_trained` | bool | Обучена ли SKU-модель. При `false` массивы пустые — деградируйте gracefully |

### Пример ответа
```json
{
  "department_id": "82e76bf2-903b-4ed9-9491-b875a33089ae",
  "department_name": "Мадлен Палуба",
  "period": { "from": "2026-06-12", "to": "2026-06-18" },
  "role_distribution": {
    "traffic_driver": { "sku_count": 38, "qty_share": 0.46, "revenue_share": 0.31 },
    "margin_driver":  { "sku_count": 24, "qty_share": 0.19, "revenue_share": 0.27 },
    "premium_anchor": { "sku_count": 9,  "qty_share": 0.05, "revenue_share": 0.18 },
    "image_rare":     { "sku_count": 12, "qty_share": 0.03, "revenue_share": 0.09 },
    "tail":           { "sku_count": 140,"qty_share": 0.27, "revenue_share": 0.15 }
  },
  "top_dishes": [
    {
      "product_id": 88123,
      "product_name": "Казан жаппа",
      "product_type": "DISH",
      "category_name": "Горячие блюда",
      "group_name": "Казахская кухня",
      "menu_role": "premium_anchor",
      "predicted_qty": 210.0,
      "qty_share": 0.08,
      "revenue_share": 0.11,
      "avg_price": 6490.0,
      "gp_margin": 0.62,
      "demand_cv": 0.34,
      "rank": 1
    }
  ],
  "category_load": [
    { "category_name": "Горячие блюда", "predicted_qty": 920.0, "qty_share": 0.34, "sku_count": 45 },
    { "category_name": "Выпечка",       "predicted_qty": 760.0, "qty_share": 0.28, "sku_count": 22 }
  ],
  "data_quality": {
    "cost_coverage": 0.865,
    "clustering_silhouette": 0.369,
    "menu_roles_run_date": "2026-06-07",
    "sku_model_trained": true
  }
}
```

> **Мэппинг категория → цех** — на стороне TCO. Sales Forecast отдаёт `category_name` из
> номенклатуры iiko «как есть».
>
> **Цена/выручка (v1.1):** `avg_price` и `revenue_share` берутся из реальных продаж
> (`sku_weekly_summary.avg_price` = выручка/кол-во), а не из `product.default_sale_price`
> (он разрежён на части доменов). `revenue_share` теперь распределён по всем ролям, а не
> вырождён в одну.
>
> **Маржа (v1.1):** `gp_margin` санитизируется — возвращается только при значении в `[0..1]`,
> иначе `null` (исходная себестоимость для части позиций недостоверна и давала отрицательные
> значения). Агрегатный сигнал достоверности — `data_quality.cost_coverage`.

---

## 2. `GET /api/labor-demand/{department_id}/forecast`

Дневной сигнал спроса (выручка / чеки / количество) + внутридневная кривая по часам.
Закрывает потребность TCO в форвардной почасовой кривой (вместо фолбэка на среднее за 30 дней).

### Параметры
| Параметр | Тип | Обяз. | По умолчанию | Описание |
|----------|-----|:----:|--------------|----------|
| `department_id` | UUID (path) | ✅ | — | Подразделение |
| `from_date` | date (query) | ✅ | — | Начало периода |
| `to_date` | date (query) | ❌ | = `from_date` | Конец периода. Макс. диапазон — 31 день |

### Пример запроса
```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.space/api/labor-demand/82e76bf2-903b-4ed9-9491-b875a33089ae/forecast?from_date=2026-06-12&to_date=2026-06-14"
```

### Структура ответа
| Поле | Тип | Описание |
|------|-----|----------|
| `department_id` | string | UUID |
| `department_name` | string\|null | Название |
| `segment_type` | string\|null | Сегмент подразделения (`restaurant`, `coffeehouse`, …) |
| `model_version` | string\|null | Версия модели прогноза (ISO-таймстамп обучения) |
| `days` | array | По одному элементу на каждый день периода (`ForecastDay`) |

**`ForecastDay`**
| Поле | Тип | Описание |
|------|-----|----------|
| `date` | string | `YYYY-MM-DD` |
| `day_of_week` | string | День недели (`monday`…`sunday`) |
| `is_weekend` | bool | Суббота/воскресенье |
| `predicted_revenue` | float\|null | Прогноз выручки (dept-level LightGBM). `null` если прогноз не удался |
| `predicted_receipts` | int\|null | Оценка числа чеков = `revenue / avg_receipt_sum` |
| `predicted_checks` | int\|null | **(v1.3)** Алиас `predicted_receipts` под именем, которое запросил TCO. Тот же вывод (нет отдельной модели чеков), `null` при отсутствии выручки или средн. чека |
| `predicted_total_qty` | float\|null | Сумма прогнозного `predicted_qty` по всем SKU. `null` если SKU-модель не обучена |
| `confidence` | string | `high` (≤7 дней вперёд) / `medium` (8+) |
| `hourly_profile` | array | Внутридневная кривая (`HourlyBucket`) |

**`HourlyBucket`**
| Поле | Тип | Описание |
|------|-----|----------|
| `hour` | int | Час суток (0–23), только часы с продажами/чеками |
| `revenue_share` | float | Доля дневной выручки в этот час; сумма по дню ≈ 1.0 |
| `checks_share` | float\|null | **(v1.3)** Доля дневных закрытых чеков в этот час; сумма по дню ≈ 1.0. `null`, если по дню недели нет истории чеков |

> **`revenue_share` vs `checks_share` (v1.3).** Обе доли — исторические средние по дню недели
> за 8 недель, каждая суммируется в ≈ 1.0 по дню, но это **разные кривые**: в обеденный час
> много дешёвых чеков (высокий `checks_share`, более низкий `revenue_share`). `revenue_share`
> — из `sales_by_hour` (выручка), `checks_share` — из `receipt` (счёт закрытых чеков по часу
> закрытия). Почасового `qty_share` нет — `sales_by_hour` хранит выручку, не количество.
>
> Форвардные кривые: `revenue_share × predicted_revenue`, `checks_share × predicted_checks`.

### Пример ответа
```json
{
  "department_id": "82e76bf2-903b-4ed9-9491-b875a33089ae",
  "department_name": "Мадлен Палуба",
  "segment_type": "restaurant",
  "model_version": "2026-06-07T03:00:06.668382",
  "days": [
    {
      "date": "2026-06-12",
      "day_of_week": "friday",
      "is_weekend": false,
      "predicted_revenue": 1878727.88,
      "predicted_receipts": 264,
      "predicted_checks": 264,
      "predicted_total_qty": 5571.4,
      "confidence": "high",
      "hourly_profile": [
        { "hour": 9,  "revenue_share": 0.0103, "checks_share": 0.0011 },
        { "hour": 10, "revenue_share": 0.042,  "checks_share": 0.0464 },
        { "hour": 11, "revenue_share": 0.0581, "checks_share": 0.0539 },
        { "hour": 12, "revenue_share": 0.11,   "checks_share": 0.0972 }
      ]
    }
  ]
}
```

---

## 3. `GET /api/labor-demand/{department_id}/elasticity-signal`

Экономический контекст: на каких позициях недокомплект персонала бьёт по выручке сильнее.
Позиции отсортированы по возрастанию `|elasticity_mean|` — наименее эластичные сверху
(их нельзя «ронять» по качеству → там нельзя экономить на людях).

### Параметры
| Параметр | Тип | Обяз. | По умолчанию | Описание |
|----------|-----|:----:|--------------|----------|
| `department_id` | UUID (path) | ✅ | — | Подразделение |
| `grade` | string (query) | ❌ | все | Фильтр по надёжности, CSV: `A,B`. Допустимо `A`/`B`/`C`/`D` |

### Пример запроса
```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.space/api/labor-demand/82e76bf2-903b-4ed9-9491-b875a33089ae/elasticity-signal?grade=A,B"
```

### Структура ответа
| Поле | Тип | Описание |
|------|-----|----------|
| `department_id` | string | UUID |
| `global_prior` | float\|null | Глобальная эластичность сети (база при нехватке данных по SKU) |
| `items` | array | Позиции с оценкой эластичности (`ElasticityItem`) |

**`ElasticityItem`**
| Поле | Тип | Описание |
|------|-----|----------|
| `product_id` | int | ID товара |
| `product_name` | string\|null | Название |
| `menu_role` | string\|null | Роль меню |
| `elasticity_mean` | float | Точечная оценка ε (отрицательная; ближе к 0 = менее чувствителен к цене) |
| `elasticity_ci_lower` | float\|null | Нижняя граница 95% доверительного интервала ε |
| `elasticity_ci_upper` | float\|null | Верхняя граница 95% CI ε |
| `elasticity_se` | float\|null | Стандартная ошибка оценки |
| `significant` | bool | `true`, если весь 95% CI < 0 (эффект цены статистически отличим от нуля) |
| `reliability_grade` | string | `A` (≥5 ценовых событий и ≥90 дней) … `D` (fallback) |
| `estimation_level` | string | Уровень оценки: `sku` / `group` / `global` |

> **⚠️ Важно про near-zero ε и `significant` (v1.2).** `reliability_grade` отражает **количество
> данных** (число ценовых событий + дней продаж), **не** значимость оценки. Поэтому даже у грейда
> A/B `elasticity_mean` может быть ≈ 0 — это означает «**нет измеримого ценового сигнала**»
> (оценщик прижал ε к 0, не выявив эффекта), а **не** реальную near-perfect неэластичность.
> Такие позиции имеют `significant=false` и `elasticity_ci_upper = 0.0`.
>
> **Рекомендация:** при выводе «наименее эластичных позиций» (где нельзя экономить на людях)
> **фильтруйте `significant=true`**, а уже потом сортируйте по `|elasticity_mean|`. Это надёжнее
> плоского порога `|ε| < 0.05`: значимая позиция с малым ε (например `-0.03`, CI `[-0.05,-0.01]`)
> — реальная, её порог по магнитуде ошибочно отсёк бы.
>
> Пример (Tary Astana, grade B): из 45 A/B-позиций 23 значимы. Шум: `ε=0.0000, CI=[-0.12, 0.0],
> significant=false`. Реальная: `ε=-0.076, CI=[-0.15, -0.0008], significant=true`.

### Пример ответа
```json
{
  "department_id": "82e76bf2-903b-4ed9-9491-b875a33089ae",
  "global_prior": -0.1063,
  "items": [
    {
      "product_id": 88123,
      "product_name": "Казан жаппа",
      "menu_role": "premium_anchor",
      "elasticity_mean": -0.31,
      "elasticity_ci_lower": -0.42,
      "elasticity_ci_upper": -0.20,
      "elasticity_se": 0.056,
      "significant": true,
      "reliability_grade": "B",
      "estimation_level": "sku"
    }
  ]
}
```

> **Замечание по данным:** часть позиций имеет `elasticity_mean ≈ 0` при `significant=false` —
> это «нет измеримого сигнала», а не реальная неэластичность (см. блок выше). Берите
> `significant=true` для надёжного сигнала.

---

## 4. `GET /api/labor-demand/{department_id}/category-load-hourly`

**(v1.3)** Историческая нагрузка цехов по часам суток, в разрезе категорий. `menu-mix` (§1)
отдаёт `category_load` за период целиком — этот эндпоинт раскладывает её **по часам**, чтобы
агенты TCO ставили нужную станцию в нужное время (горячий цех вечером, кондитерка утром).

Агрегат за период из `receipt_item` (час закрытия чека, Asia/Almaty). Это **факт** (история),
не прогноз — форвардную долю чеков по часам берите из §2 `hourly_profile.checks_share`.

### Параметры
| Параметр | Тип | Обяз. | По умолчанию | Описание |
|----------|-----|:----:|--------------|----------|
| `department_id` | UUID (path) | ✅ | — | Подразделение |
| `from_date` | date (query) | ✅ | — | Начало периода |
| `to_date` | date (query) | ❌ | = `from_date` | Конец периода (включительно). Макс. диапазон — 31 день |

### Пример запроса
```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.space/api/labor-demand/82e76bf2-903b-4ed9-9491-b875a33089ae/category-load-hourly?from_date=2026-06-05&to_date=2026-06-11"
```

### Структура ответа
| Поле | Тип | Описание |
|------|-----|----------|
| `department_id` | string | UUID |
| `department_name` | string\|null | Название |
| `period` | object | `{ "from": "YYYY-MM-DD", "to": "YYYY-MM-DD" }` |
| `categories` | array | Категории, сорт. по `items_count` убыв. (`CategoryHourlyLoad`) |
| `data_quality` | object | `{ "has_receipts": bool }` — `false`, если за период нет чеков (деградируйте gracefully) |

**`CategoryHourlyLoad`**
| Поле | Тип | Описание |
|------|-----|----------|
| `category` | string\|null | Категория iiko (→ цех на стороне TCO) |
| `items_count` | int | Всего позиций (строк чека) по категории за период |
| `dish_qty` | float | Всего проданных единиц (`SUM(qty)`) по категории за период |
| `hourly` | array | По одному элементу на каждый час суток с продажами (`CategoryHourBucket`) |

**`CategoryHourBucket`**
| Поле | Тип | Описание |
|------|-----|----------|
| `hour` | int | Час суток (0–23, Asia/Almaty), час закрытия чека |
| `items_count` | int | Позиций (строк) этой категории в этот час |
| `dish_qty` | float | Проданных единиц (`SUM(qty)`) — точнее отражает загрузку станции |
| `share_of_day` | float | Доля часа в периодном итоге категории (по `items_count`); сумма по `hourly` ≈ 1.0 |

> **`items_count` vs `dish_qty`.** `items_count` — число строк чека (как в §1 `/sales/checks-hourly`
> и `Receipt.items_count`). `dish_qty` — сумма `qty` (одна строка «Латте ×3» = 3 единицы). Для
> загрузки кухонной станции точнее `dish_qty`; для consistency с остальным API даём оба.
>
> **Сырой режим:** если удобнее агрегировать самим — те же данные в плоском виде доступны через
> `GET /api/sales/checks-hourly` (чеки/позиции по часам без разбивки по категориям).

### Пример ответа
```json
{
  "department_id": "82e76bf2-903b-4ed9-9491-b875a33089ae",
  "department_name": "Мадлен Палуба",
  "period": { "from": "2026-06-05", "to": "2026-06-11" },
  "categories": [
    {
      "category": "Горячие блюда",
      "items_count": 1685,
      "dish_qty": 2250.0,
      "hourly": [
        { "hour": 11, "items_count": 49,  "dish_qty": 69.0,  "share_of_day": 0.0291 },
        { "hour": 12, "items_count": 142, "dish_qty": 188.0, "share_of_day": 0.0843 },
        { "hour": 13, "items_count": 175, "dish_qty": 240.0, "share_of_day": 0.1039 }
      ]
    }
  ],
  "data_quality": { "has_receipts": true }
}
```

---

## Привязка к агентам TCO

| Агент TCO | Эндпоинт | Что извлекает |
|-----------|----------|---------------|
| Sales | §2 `/forecast` `hourly_profile` (`revenue_share` + `checks_share`) + `predicted_checks` | форвардная почасовая кривая выручки/чеков вместо `recent_30d` |
| Schedule | §1 `/menu-mix` `category_load` + §4 `/category-load-hourly` | загрузка цехов по часам → состав и тайминг смены (повар горячего / кондитер / бариста) |
| Risks | §1 `top_dishes` + §3 `/elasticity-signal` | флагманы / низкая эластичность → где недокомплект дороже |
| Orchestrator | все блоки сводно | финальная рекомендация |

## Рекомендации по интеграции
- Тяните три эндпоинта параллельно (`Promise.allSettled`) — падение одного не должно ронять сбор контекста.
- Проверяйте `data_quality.sku_model_trained` в `/menu-mix`: при `false` блюда/категории пустые — деградируйте gracefully.
- Кэшируйте на стороне TCO: данные обновляются раз в сутки (ночные синки + кластеризация по воскресеньям).

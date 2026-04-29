# 07. Примеры конфигов для всех 10+ локаций

Реальные значения процентов, грейдов и слотов — из документов KPI 2026.  
Эти данные используются в `seeds/` для заливки в БД.

## Sandyq Kainar

### Управляющий
```json
{
  "model": "flat_by_kpi",
  "kpis": [
    {"code": "staffing", "source": "hr_staffing_percent", "target": 100, "direction": "higher_is_better"},
    {"code": "negative_reviews", "source": "crm_negative_reviews_share", "target": 5, "direction": "lower_is_better"},
    {"code": "audit", "source": "manual_audit", "target": 100, "direction": "higher_is_better"},
    {"code": "apc_growth", "source": "iiko_apc_growth", "target": 5, "direction": "higher_is_better"},
    {"code": "profitability", "source": "manual_profitability", "target_metric": "monthly_plan_profitability", "direction": "higher_is_better"}
  ],
  "grades": [
    {"from": 70, "to": 79, "value": 80000},
    {"from": 80, "to": 84, "value": 100000},
    {"from": 85, "to": 89, "value": 130000},
    {"from": 90, "to": 97, "value": 150000},
    {"from": 98, "to": 100, "value": 170000}
  ]
}
```

### Менеджер (Администратор-кассир)
```json
{
  "model": "revenue_percent_by_kpi",
  "kpis": [
    {"code": "restaurant_rating", "source": "crm_restaurant_rating", "target": 5, "direction": "binary"},
    {"code": "sales_plan", "source": "iiko_sales_plan_location", "target_metric": "monthly_plan_sales", "direction": "higher_is_better"},
    {"code": "negative_reviews", "source": "crm_negative_reviews_share", "target": 5, "direction": "lower_is_better"},
    {"code": "audit_quality", "source": "manual_audit", "target": 80, "direction": "higher_is_better"}
  ],
  "revenue_source": "iiko_revenue_with_discount",
  "grades": [
    {"from": 70, "to": 79, "rate": 0.0005},
    {"from": 80, "to": 84, "rate": 0.001},
    {"from": 85, "to": 89, "rate": 0.0013},
    {"from": 90, "to": 97, "rate": 0.0015},
    {"from": 98, "to": 100, "rate": 0.002}
  ],
  "apply_shifts_proration": true
}
```

### Бариста (Sandyq Kainar)
```json
{
  "model": "combined_products",
  "components": [
    {
      "code": "ready_products",
      "name": "Готовая продукция",
      "source": "iiko_personal_ready_products_with_discount",
      "rate": 0.001
    },
    {
      "code": "prepared_products",
      "name": "Приготовленная продукция",
      "source": "iiko_personal_prepared_products_with_discount",
      "rate": 0.013
    }
  ],
  "apply_shifts_proration": false,
  "require_no_violations": true
}
```

### Официант
```json
{
  "model": "revenue_percent_by_kpi",
  "kpis": [
    {"code": "sales_plan", "source": "iiko_sales_plan_personal", "target_metric": "monthly_plan_sales", "direction": "higher_is_better"},
    {"code": "individual_negative_reviews", "source": "crm_individual_negative_reviews", "target": 3, "direction": "lower_is_better"},
    {"code": "margin_share", "source": "iiko_margin_share", "target": 40, "direction": "higher_is_better"}
  ],
  "revenue_source": "iiko_personal_revenue_with_discount",
  "grades": [
    {"from": 70, "to": 79, "rate": 0.03},
    {"from": 80, "to": 84, "rate": 0.035},
    {"from": 85, "to": 89, "rate": 0.04},
    {"from": 90, "to": 97, "rate": 0.042},
    {"from": 98, "to": 100, "rate": 0.045}
  ],
  "apply_shifts_proration": true
}
```

---

## Tary Kainar

Бариста отличается от Sandyq Kainar по `prepared_products.rate`:
```json
{
  "model": "combined_products",
  "components": [
    {"code": "ready_products", "source": "iiko_personal_ready_products_with_discount", "rate": 0.001},
    {"code": "prepared_products", "source": "iiko_personal_prepared_products_with_discount", "rate": 0.016}
  ]
}
```

Кассир (есть в Tary Kainar):
```json
{
  "model": "revenue_direct",
  "revenue_source": "iiko_revenue_without_discount",
  "rate": 0.002,
  "apply_shifts_proration": true
}
```

Старший бариста:
```json
{
  "model": "revenue_direct",
  "revenue_source": "iiko_revenue_with_discount",
  "rate": 0.007,
  "apply_shifts_proration": true,
  "shifts_proration_formula": "revenue / norm_shifts * worked_shifts * rate"
}
```

Управляющий, Менеджер, Официант — те же конфиги, что в Sandyq Kainar.

---

## Sandyq Astana

Все базовые позиции аналогичны, но:

### Кассир
```json
{
  "model": "revenue_direct",
  "revenue_source": "iiko_revenue_without_discount",
  "rate": 0.0007,
  "apply_shifts_proration": true
}
```

### Старший бариста
```json
{
  "model": "revenue_direct",
  "revenue_source": "iiko_revenue_with_discount",
  "rate": 0.0033,
  "apply_shifts_proration": true,
  "shifts_proration_formula": "revenue / norm_shifts * worked_shifts * rate"
}
```

### Бариста (middle)
```json
{
  "model": "combined_products",
  "components": [
    {"code": "ready_products", "source": "iiko_personal_ready_products_with_discount", "rate": 0.0015},
    {"code": "prepared_products", "source": "iiko_personal_prepared_products_with_discount", "rate": 0.003}
  ]
}
```

### Бариста (senior)
```json
{
  "model": "combined_products",
  "components": [
    {"code": "ready_products", "source": "iiko_personal_ready_products_with_discount", "rate": 0.001},
    {"code": "prepared_products", "source": "iiko_personal_prepared_products_with_discount", "rate": 0.007}
  ]
}
```

### KITCHEN — ВАЖНО
Создаётся как `team` со схемой:
```json
{
  "model": "team_revenue_by_kpi",
  "kpis": [
    {"code": "sales_plan", "source": "iiko_sales_plan_location", "target_metric": "monthly_plan_sales", "direction": "higher_is_better"},
    {"code": "kitchen_audit", "source": "manual_kitchen_audit", "target": 100, "direction": "higher_is_better"},
    {"code": "kitchen_negative_reviews", "source": "crm_kitchen_reviews", "target": 3, "direction": "lower_is_better"}
  ],
  "revenue_source": "iiko_revenue_with_discount",
  "grades": [
    {"from": 70, "to": 79, "rate": 0.03},
    {"from": 80, "to": 84, "rate": 0.035},
    {"from": 85, "to": 89, "rate": 0.04},
    {"from": 90, "to": 97, "rate": 0.042},
    {"from": 98, "to": 100, "rate": 0.045}
  ],
  "below_threshold_bonus_zero": true,
  "distribution_formula": "revenue * slot_weight * shifts_ratio",
  "apply_shifts_proration": true,
  "exclude_probation_period": true
}
```

**Слоты команды KITCHEN (из Таблицы №3 документа):**
| slot | display_name | distribution_weight |
|---|---|---|
| chef | Шеф-повар | 0.0013 |
| sous_chef_1 | Су-шеф 1 | 0.0009 |
| sous_chef_2 | Су-шеф 2 | 0.0006 |
| senior_shift_cook_1 | Повар старшей смены 1 | 0.0008 |
| senior_shift_cook_2 | Повар старшей смены 2 | 0.0008 |
| hot_cook_1 | Повар горячего цеха 1 | 0.0007 |
| hot_cook_2 | Повар горячего цеха 2 | 0.0004 |
| cold_cook_1 | Повар холодного цеха 1 | 0.0006 |
| cold_cook_2 | Повар холодного цеха 2 | 0.0004 |
| junior_cook_1 | Младший повар 1 | 0.0005 |
| junior_cook_2 | Младший повар 2 | 0.0003 |
| senior_meat_prep | Старший заготовщик мяса | 0.0008 |
| junior_meat_prep | Младший заготовщик мяса | 0.0005 |
| staff_cook_1 | Стафф-повар 1 | 0.0005 |
| staff_cook_2 | Стафф-повар 2 | 0.0005 |
| pastry_chef | Шеф-кондитер | 0.0007 |
| senior_pastry | Старший кондитер | 0.0006 |
| pastry_1 | Кондитер 1 | 0.0006 |
| pastry_2 | Кондитер 2 | 0.0004 |
| baker_1 | Пекарь 1 | 0.0005 |
| baker_2 | Пекарь 2 | 0.0003 |

---

## Sandyq Almaty

Полностью аналогична Sandyq Astana по составу + KITCHEN. Сверять документ при заливке.

---

## Tary Алматы (Аюсай + Шопан)

В документе **2 локации в одном файле** — нужно создать обе.

- Tary Auysai — полный набор + KITCHEN
- Tary Шопан — полный набор без KITCHEN

KITCHEN Tary Auysai по структуре идентична Sandyq Astana KITCHEN.

---

## Tary Астана + Tary Европа Сити

В одном документе. Обе локации без кассира и без KITCHEN. Бариста + Старший бариста + Официант + Менеджер + Управляющий.

---

## Tary Бурабай / Колсай / Чарын

Каждая в своём документе. Структура идентичная: без кассира, без KITCHEN. Полный набор остальных позиций.

---

## Tary Сарайшык

Минимальный набор: Управляющий, Менеджер (Администратор-кассир), Старший бариста, Бариста, Официант. Без кассира и KITCHEN.

---

## Sandyq Туркестан + Tary Туркестан

В одном документе. Обе локации в одном юрлице.

- Sandyq Туркестан — Упр, Мен, Кассир, Бариста, Официант
- Tary Туркестан — только Официант (!)

---

## Что должно лежать в `seeds/`

```
seeds/
├── 01_companies.py       # 4-5 юрлиц
├── 02_locations.py       # 12+ точек
├── 03_positions.py       # все должности (manager, cashier, chef, sous_chef, ...)
├── 04_kpi_definitions.py # все KPI
├── 05_monthly_plans.py   # план продаж и рентабельности на 2026
├── 06_schemes.py         # схемы для всех индивидуальных позиций
├── 07_kitchen_teams.py   # KITCHEN для 3 локаций (Sandyq Astana, Sandyq Almaty, Tary Auysai)
├── 08_kitchen_slots.py   # 21 слот для каждого KITCHEN (одинаково по составу, но привязка разная)
└── run_all.py            # запускает все по порядку
```

Каждый файл — async function:
```python
async def seed(session: AsyncSession) -> None:
    ...
```

`run_all.py` — последовательно вызывает все.

## Когда менять конфиги

- **Если бизнес поменял ставку** → создать новую версию схемы через API (закрыть старую, создать новую с новой `effective_from`)
- **Если добавили слот в KITCHEN** → POST `/teams/{id}/positions`
- **Если поменяли вес слота** → PATCH `/teams/{id}/positions/{slot}` (создаёт новую запись)
- **Если новая локация** → SQL/API: добавить `location` → создать схемы
- **Если новое подразделение типа KITCHEN** → создать `team` + наполнить `team_position` + создать `bonus_scheme`

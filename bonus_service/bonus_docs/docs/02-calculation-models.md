# 02. Модели расчёта

В системе **5 моделей** расчёта бонусов. Каждая — отдельный класс, реализующий интерфейс `BaseBonusModel`.

## Базовый интерфейс

```python
# app/calculator/base.py
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import date

class BaseBonusModel(ABC):
    """Базовый класс для всех моделей расчёта бонуса."""
    
    code: str  # 'flat_by_kpi', 'revenue_percent_by_kpi', ...
    
    @abstractmethod
    def validate_config(self, config: dict) -> None:
        """Проверить валидность config схемы. Бросить ValueError если не ок."""
    
    @abstractmethod
    async def calculate(
        self,
        scheme: BonusScheme,
        target: Employee | Team,
        period: PeriodKey,
        context: CalculationContext,
    ) -> BonusResult:
        """Посчитать бонус. Вернуть результат с breakdown."""
    
    def get_required_kpi_sources(self, config: dict) -> list[str]:
        """Какие источники KPI нужны (для предзагрузки)."""
        return [k["source"] for k in config.get("kpis", [])]
    
    def get_required_revenue_sources(self, config: dict) -> list[str]:
        """Какие источники выручки нужны."""
        return [config.get("revenue_source")] if "revenue_source" in config else []
```

---

## Модель 1: `flat_by_kpi`

**Идея:** % выполнения KPI → грейд → **фиксированная сумма** в тенге.

**Кто использует:** Управляющий

**Формула:**
```
1. overall_kpi = avg(kpi_values)
2. grade = find_grade(grades, overall_kpi)  # если < min_threshold → bonus = 0
3. bonus = grade.value
4. (опционально) bonus = bonus × (worked_shifts / norm_shifts)
5. bonus -= penalties
```

**Пример (Управляющий Sandyq Kainar):**
- Укомплектованность: 95%, Отзывы: 96%, Аудит: 90%, APC: 88%, Рентабельность: 85%
- avg = 90.8% → грейд 90-97% → **150 000 тг**

**Config:**
```json
{
  "model": "flat_by_kpi",
  "kpis": [
    {"code": "staffing", "source": "hr_staffing", "target": 100},
    {"code": "negative_reviews", "source": "crm_negative_reviews", "target": 5, "direction": "lower_is_better"},
    {"code": "audit", "source": "manual_audit", "target": 100},
    {"code": "apc_growth", "source": "iiko_apc_growth", "target": 5},
    {"code": "profitability", "source": "manual_profitability", "target_per_month": "monthly_plan_profitability"}
  ],
  "grades": [
    {"from": 70, "to": 79, "value": 80000},
    {"from": 80, "to": 84, "value": 100000},
    {"from": 85, "to": 89, "value": 130000},
    {"from": 90, "to": 97, "value": 150000},
    {"from": 98, "to": 100, "value": 170000}
  ],
  "below_threshold_bonus": 0,
  "apply_shifts_proration": false
}
```

---

## Модель 2: `revenue_percent_by_kpi`

**Идея:** % KPI → грейд (как процент!) → **выручка × коэффициент**.

**Кто использует:** Менеджер (администратор), Официант

**Формула:**
```
1. overall_kpi = avg(kpi_values)
2. grade_rate = find_grade(grades, overall_kpi)   # 0.045 (4.5%) и т.д.
3. revenue = fetch_revenue(scheme.revenue_source, target, period, only_worked_days=True)
4. bonus = revenue × grade_rate
5. (опционально) bonus = bonus × (worked_shifts / norm_shifts)  # для менеджера
6. bonus -= penalties
```

**Пример (Официант Sandyq Astana):**
- Выручка официанта по «сумме со скидкой» = 2 500 000 тг
- KPI: план продаж 100%, отзывы 0%, маржинальность 95% → avg = 65% → ниже 70% → **0**
- Если бы был 95% → грейд 90-97% → 4,2% → 2 500 000 × 0,042 = **105 000 тг**

**Config:**
```json
{
  "model": "revenue_percent_by_kpi",
  "kpis": [
    {"code": "sales_plan", "source": "iiko_sales_plan_personal", "target_per_month": "monthly_plan_sales"},
    {"code": "individual_negative_reviews", "source": "crm_individual_reviews", "target": 3, "direction": "lower_is_better"},
    {"code": "margin_share", "source": "iiko_margin_share", "target": 40}
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

## Модель 3: `revenue_direct`

**Идея:** Просто **выручка × фиксированный процент**, без KPI.

**Кто использует:** Кассир, Старший бариста

**Формула:**
```
1. revenue = fetch_revenue(scheme.revenue_source, target, period)
2. bonus = revenue × scheme.rate
3. (опционально) bonus = bonus × (worked_shifts / norm_shifts)
4. bonus -= penalties
```

**Пример (Кассир Sandyq Astana):**
- Выручка точки «без скидки» за месяц = 25 000 000 тг
- 25 000 000 × 0,07% = **17 500 тг**

**Пример (Старший бариста Sandyq Astana):**
- Выручка бара «со скидкой» = 25 000 000 тг
- 25 000 000 / 22 (норма) × 20 (факт) × 0,33% = **75 000 тг**

**Config:**
```json
{
  "model": "revenue_direct",
  "revenue_source": "iiko_revenue_without_discount",
  "rate": 0.0007,
  "apply_shifts_proration": true,
  "shifts_proration_formula": "revenue / norm_shifts * worked_shifts * rate"
}
```

---

## Модель 4: `combined_products`

**Идея:** Несколько компонентов выручки, у каждого свой процент. Сумма = бонус.

**Кто использует:** Бариста (готовая продукция × ставка_1 + приготовленная × ставка_2)

**Формула:**
```
1. components = scheme.components  # список
2. for each component:
     revenue = fetch_revenue(component.source, target, period)
     part = revenue × component.rate
3. bonus = sum(parts)
4. (опционально) bonus = bonus × (worked_shifts / norm_shifts)
5. bonus -= penalties
```

**Пример (Бариста Tary Kainar):**
- Готовая продукция: 2 000 000 × 0,1% = 2 000 тг
- Приготовленная: 3 000 000 × 1,6% = 48 000 тг
- Итого: **50 000 тг** (минус удержания, если есть)

**Config:**
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
      "rate": 0.016
    }
  ],
  "apply_shifts_proration": false,
  "require_no_violations": true
}
```

---

## Модель 5: `team_revenue_by_kpi`

**Идея:** Коллективный расчёт. KPI команды → грейд → выручка × коэф = пул. Пул распределяется на сотрудников по слотам команды.

**Кто использует:** KITCHEN (Sandyq Astana, Sandyq Almaty, Tary Auysai). В будущем — BAR_TEAM, DELIVERY и др.

**Формула:**
```
1. overall_kpi = avg(team_kpi_values)
2. grade_rate = find_grade(grades, overall_kpi)
3. revenue = fetch_revenue(scheme.revenue_source, team.location, period)

   # Распределение по слотам команды:
4. for each employee_assignment in team:
     team_position = get_team_position(team, assignment.slot, period)
     shifts = fetch_shifts(employee, period)
     
     individual_bonus = revenue × team_position.weight × (shifts.worked / shifts.norm)
     # Замечание: вес слота уже учитывает grade_rate "встроенно" по документу
     # см. ниже про два варианта формулы
     
     individual_bonus -= penalties
     save(employee, individual_bonus, ...)
```

### Два варианта формулы (важно уточнить у бизнеса!)

**Вариант A (буквально по документу):**
- Веса слотов уже **финальные**: `chef = 0,13%` — это сразу применяется к выручке
- `grade_rate` влияет на бонус **только** через множитель: если KPI <70%, бонус = 0
- Формула: `bonus = revenue × slot_weight × (worked/norm) × (1 if grade else 0)`

**Вариант B (логично, но не описано в доке):**
- `grade_rate` — это пул в %, веса слотов — доли распределения
- Формула: `bonus = revenue × grade_rate × (slot_weight / sum_of_weights) × (worked/norm)`

**По документу скорее вариант A.** В config храним явно:
```json
"distribution_formula": "revenue * slot_weight * shifts_ratio"
```

**Config:**
```json
{
  "model": "team_revenue_by_kpi",
  "kpis": [
    {"code": "sales_plan", "source": "iiko_sales_plan", "target_per_month": "monthly_plan_sales"},
    {"code": "kitchen_audit", "source": "manual_kitchen_audit", "target": 100},
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
  "exclude_probation_period": true,
  "exclude_violators": true
}
```

Веса слотов хранятся в **`team_position.distribution_weight`**, а не в config (потому что меняются часто и редактируются построчно в админке).

---

## Сводная таблица

| Модель | Должности | KPI | Выручка | Грейд → ? |
|---|---|---|---|---|
| `flat_by_kpi` | Управляющий | да | нет | сумма (тг) |
| `revenue_percent_by_kpi` | Менеджер, Официант | да | да | процент |
| `revenue_direct` | Кассир, Ст. бариста | нет | да | (нет грейда) |
| `combined_products` | Бариста | нет | да (×N) | (нет грейда) |
| `team_revenue_by_kpi` | KITCHEN (команда) | да | да | процент |

## Если появится новая модель

Допустим, придумают «бонус от чаевых»:

1. Создать `app/calculator/models/tips_based.py`
2. Зарегистрировать декоратором `@register_model('tips_based')`
3. Реализовать `validate_config` и `calculate`
4. Добавить мок источника `tips_data` в `data_sources/`
5. Создать схему через админку с `model = 'tips_based'`

**Никаких правок в `BonusCalculatorService`, базовых классах, или БД.**

## KPI Engine — отдельный модуль

KPI скорится единообразно по `direction`:

```python
def score_kpi(fact: Decimal, target: Decimal, direction: str) -> Decimal:
    """Возвращает % выполнения (0..N, не обрезаем сверху)."""
    if direction == "higher_is_better":
        # план продаж: факт/план × 100
        return (fact / target) * 100
    elif direction == "lower_is_better":
        # негативные отзывы: цель = 5%, факт = 3% → выполнено на (5/3)×100 = 166%
        # но обычно режут до 100% (не даём бонус сверх плана)
        return min((target / fact) * 100, Decimal("100")) if fact > 0 else Decimal("100")
    elif direction == "binary":
        # рейтинг = 5 → 100%, иначе линейно (4 → 80%, 3 → 60%)
        return (fact / target) * 100
```

Точные правила скоринга — в `docs/04-domain-rules.md`.

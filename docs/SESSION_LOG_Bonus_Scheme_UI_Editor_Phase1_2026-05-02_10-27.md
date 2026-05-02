# Session Log: Bonus Scheme UI — Phase 1 (Metadata Foundation)

**Дата**: 2026-05-02, 10:27
**Задача**: Подготовить почву для полноценного визуального редактора схем расчёта бонусов. Сейчас на странице `/bonus/schemes` конфиг показывается как сырой JSON — это непонятно HR/финдиректору. Целевое состояние: всё, что хранится в `bonus_scheme.config` (KPI, грейды, источники выручки, опции), управляется через формы с человекочитаемыми названиями, dropdown'ами и подсказками.
**Статус этапа**: Завершён локально, не задеплоен (ждём подтверждения)
**Ветка**: `master`

---

## Контекст и зачем

Изначально подсистема бонусов (см. `BONUS_SYSTEM_GUIDE.md`) спроектирована так, что **все ставки/проценты/грейды живут в БД** (`bonus_scheme.config` JSONB). Это правильно — изменение коэффициента бариста = `UPDATE` строки, а не правка кода. Но MVP UI показывал config как `<pre>{JSON.stringify(config)}</pre>` в диалоге, без кнопки «Создать»/«Редактировать». Все 56 схем созданы seed-скриптом `app/bonus/seeds/run_all.py`.

Чтобы построить визуальный редактор (раздел 12.6 в `BONUS_SYSTEM_GUIDE.md`, оценка 5-7 дней), сначала нужно обогатить API метаданными:

- API `GET /config/data-sources` возвращал только массив строк `["iiko_personal_revenue_with_discount", "manual_audit", …]` — без названий, описаний, единиц измерения
- API `GET /config/calculation-models` возвращал только массив кодов 5 моделей
- В коде `BonusDataSource` тоже не было `name`/`description` — был только `code`

Без этой информации нельзя построить осмысленные dropdown'ы вроде «Личная выручка официанта (iiko · KZT)» вместо `iiko_personal_revenue_with_discount`.

---

## Архитектурные решения

| Решение | Обоснование |
|---|---|
| Метаданные источников — атрибуты класса `BonusDataSource`, не отдельная таблица | Источники определены в коде (плагинная архитектура), их метаданные тоже должны жить рядом. Не нужна миграция, не нужен seed |
| Метаданные моделей расчёта — отдельный модуль `app/bonus/calculator/metadata.py`, словарь `CALCULATION_MODEL_METADATA` | Модели описаны Pydantic-схемами в `schemas/calc_configs/`, но там — только структура для валидации. UI-метаданные (label, hint, типы виджетов) — отдельная плоскость, разносим |
| Поле `is_stub: bool` у источников | Заглушки (CRM, iiko-products, HR) технически работают, но возвращают фиктивные значения. UI должен явно отмечать их badge'ем «заглушка», иначе HR подумает что всё ок |
| Поле `value_type` ("revenue"/"kpi_percent"/"kpi_value"/"shifts") | Управляет UI-валидацией: source с `value_type="revenue"` подходит для `revenue_source` блока, но не для KPI; `value_type="shifts"` — особый тип для `tco_shifts` |
| `metadata()` как `classmethod` на `BonusDataSource` | Источники регистрируются как instance'ы (`DataSourceRegistry.register(IikoLocationRevenueDishSum())`). Classmethod корректно вызывается и от инстанса |
| Промежуточный шаг — читабельный просмотр перед редактором | Не строим сразу весь редактор. Сначала превратим показ JSON в нормальные таблицы, чтобы HR хотя бы _читал_ конфиги. Редактор — следующая итерация |

---

## Что сделано

### Backend (этап 1.1–1.3 из плана)

**1. `app/bonus/data_sources/base.py`** — расширен `BonusDataSource`:

```python
class BonusDataSource(ABC):
    code: str = ""
    # NEW
    name: str = ""              # «Личная выручка официанта (со скидкой)»
    description: str = ""       # подробное описание + откуда читает
    value_type: str = ""        # revenue | kpi_percent | kpi_value | shifts
    unit: str = ""              # KZT | % | count | stars | shifts
    category: str = ""          # iiko_location | iiko_personal | iiko_plan | iiko_products | manual | crm | hr | tco
    is_stub: bool = False       # True → UI показывает warning badge

    @classmethod
    def metadata(cls) -> dict: ...
```

**2. Заполнены метаданные у всех 19 источников:**
- `app/bonus/data_sources/iiko/revenue.py` — 6 классов (location/personal × dish_sum/with_discount + sales plan location/personal)
- `app/bonus/data_sources/iiko/products.py` — 2 класса (ready/prepared products, оба `is_stub=True`)
- `app/bonus/data_sources/manual/manual_kpi.py` — 10 классов (audit, kitchen_audit, profitability, hr_staffing_percent, crm × 4, iiko_apc_growth, iiko_margin_share)
- `app/bonus/data_sources/tco/shifts.py` — 1 класс (TcoShifts с `is_stub=True`)

**3. `app/bonus/data_sources/registry.py`** — добавлен метод `list_metadata()`.

**4. `app/bonus/calculator/metadata.py`** (новый файл) — `CALCULATION_MODEL_METADATA` со всеми 5 моделями:

```python
"flat_by_kpi": {
    "code": "flat_by_kpi",
    "name": "Фикс. сумма по KPI",
    "description": "...",
    "typical_positions": ["restaurant_director"],
    "requires_kpis": True,
    "requires_revenue_source": False,
    "requires_grades": True,
    "grade_type": "flat",          # колонки: from%, to%, value (₸)
    "supports_components": False,
    "supports_shifts_proration": True,
    "options": [                   # каждая опция → виджет в UI
        {"key": "apply_shifts_proration", "type": "bool", "default": False,
         "label": "Пропорционально сменам",
         "hint": "Бонус × (отработано / норма)"},
        ...
    ],
}
```

Эта структура **управляет рендером редактора**: фронт смотрит на `requires_kpis` — рендерит блок KPI; смотрит на `grade_type` — рендерит таблицу грейдов с нужными колонками; пробегает по `options[]` — рендерит switch'и/select'ы с пояснениями.

**5. `app/bonus/routers/dictionary.py`** — поменяны 2 эндпоинта:
- `GET /api/bonus/config/data-sources` → теперь возвращает `DataSourceInfo[]` с метаданными вместо `string[]`
- `GET /api/bonus/config/calculation-models` → теперь возвращает `CalculationModelInfo[]`

### Frontend (этап 1.4)

**6. `frontend/src/types/bonus.ts`** — добавлены типы:
- `DataSourceInfo`, `DataSourceValueType`, `DataSourceCategory`
- `CalculationModelInfo`, `CalculationModelOption`, `GradeType`

**7. `frontend/src/hooks/use-bonus.ts`** — `useDataSources()` и `useCalculationModels()` теперь типизированы новыми интерфейсами.

**8. `frontend/src/components/bonus/scheme-config-view.tsx`** (новый) — компонент читабельного рендера конфига:
- **KPI** → таблица «KPI / Источник / Направление / Цель» с человеческими названиями (из `bonus_kpi_definition`), badge заглушки, описанием категории
- **Источник выручки** → карточка с человеческим именем + категория + единица + код мелким шрифтом
- **Грейды** → отдельные таблицы для `grade_type=flat` (колонка «Сумма ₸» с локализацией `170 000 ₸`) и `grade_type=rate` (колонка «Ставка %» с автоконвертацией `0.045 → 4.5%`)
- **Компоненты** (только для `combined_products`) → таблица «Продукт / Источник / Ставка»
- **Опции** → grid карточек с label + hint; bool отображается «Да/Нет», enum — текстом из `options[].label`, money — отформатированной суммой

**9. `frontend/src/pages/bonus-schemes-page.tsx`** — переделан диалог:
- Заголовок диалога теперь показывает локацию, должность/команду, версию (вместо просто «Конфиг схемы #N»)
- Tabs: «Параметры» (новый рендер) / «JSON» (старый сырой вид сохранён для разработчиков)
- Колонка «Модель» в таблице теперь использует `name` из API + tooltip с `description`

---

## Проверка

| Проверка | Результат |
|---|---|
| `python -m pytest tests/bonus/` | **53/53 passed** в 0.47s |
| API `/config/data-sources` через временный mount в контейнере | 19 источников, все с `name/description/value_type/unit/category/is_stub` |
| API `/config/calculation-models` | 5 моделей с полными метаданными |
| `pnpm build` (TypeScript + Vite) | **OK**, 2483 модуля, без ошибок типов |

---

## Что осталось сделать

### Этап 2 — Визуальный редактор (5-7 дней)

Задача: на странице `/bonus/schemes` появляется кнопка «Создать схему» / «Новая версия», и форма позволяет HR создать/изменить схему **без знания JSON**.

**2.1. Wizard-форма** (Dialog или отдельная страница `/bonus/schemes/new`):
- Шаг 1 — контекст: `DepartmentSelect`, радио «Должность/Команда», Select должности или команды, Select модели расчёта (с описанием), `effective_from`, notes
- Шаг 2 — блоки конфига, рендер зависит от модели (используя метаданные `requires_*`, `grade_type`, `supports_components`, `options[]`)
- Шаг 3 — превью + кнопка «Проверить» (`POST /schemes/validate`) + diff против активной версии + «Сохранить» (`POST /schemes`)

**2.2. KPI-редактор:**
- Inline-таблица с кнопкой «+ Добавить KPI»
- Каждая строка: Select KPI (из `/kpi-definitions` — отображает `name`), направление (auto-fill из definition, override опционально), `target` (number с unit-подсказкой), `target_metric` (опц., для `monthly_plan_*`)

**2.3. Грейды-редактор:**
- Inline-таблица с колонками в зависимости от `grade_type`
- Live-валидация: непрерывность диапазонов (`gradei.to + 1 == gradei+1.from`), сортировка по `from`, отсутствие пересечений
- Для rate: input в процентах (4.5%), конвертация в долю (0.045) при сохранении

**2.4. Revenue source — Select:**
- Группировка по `category` (iiko_location → iiko_personal → manual → ...)
- Фильтрация по `value_type === "revenue"`
- Под Select — описание из метаданных
- Badge «заглушка» рядом с `is_stub=true` источниками

**2.5. Компоненты-редактор** (только `combined_products`):
- Inline-таблица: code, name, source (Select), rate (% input)

**2.6. Опции-редактор:**
- Цикл по `modelMeta.options[]`:
  - `type=bool` → Switch (нужно добавить компонент `switch.tsx` — сейчас его нет в `components/ui/`)
  - `type=enum` → RadioGroup или Select с `options[].label`
  - `type=money` → NumberInput с подсказкой «₸»
- Каждый виджет — с `label` сверху и `hint` мелким шрифтом снизу

### Этап 3 — Дополнения (опционально, 2-3 дня)

**3.1.** Тестовый расчёт (sandbox):
- На странице создания схемы — поле «При KPI=__%, выручке=__₸, отработано __ из __ смен → бонус будет ХХХ₸»
- Эндпоинт `POST /schemes/preview-calculation` (новый) — принимает config + mock-параметры, прогоняет через тот же `BaseBonusModel.calculate()`, возвращает breakdown без сохранения

**3.2.** Diff против активной версии:
- При создании новой версии — таблица «Что меняется»: было/стало по каждому полю
- Особенно важно для грейдов: «90-97% было 4.2% → станет 4.5%»
- Используется в финальном confirm-диалоге

**3.3.** Слоты KITCHEN-команд:
- Сейчас `bonus_team_position.distribution_weight` редактируется только через SQL
- Страница `/bonus/teams/{id}` с inline-редактированием весов слотов (с версионированием через `effective_to`)

**3.4.** История версий схемы:
- На каждой строке таблицы схем — кнопка «История»
- Timeline всех версий пары `(department, position)` с диффами

### Этап 4 — Деплой текущих изменений

Локально всё работает; перед деплоем нужно:
- `docker-compose -f docker-compose.prod.yml build sales-forecast-app`
- `docker-compose -f docker-compose.prod.yml up -d sales-forecast-app`
- Smoke-проверка: `curl /api/bonus/config/data-sources | jq '.[0]'` должен вернуть объект, не строку
- Открыть `/bonus/schemes`, кликнуть «Показать» → убедиться что вкладка «Параметры» рендерится

---

## Изменённые файлы

**Backend (8 файлов):**
- `app/bonus/data_sources/base.py` (расширен `BonusDataSource`)
- `app/bonus/data_sources/iiko/revenue.py` (метаданные 6 источников)
- `app/bonus/data_sources/iiko/products.py` (метаданные 2 заглушек)
- `app/bonus/data_sources/manual/manual_kpi.py` (метаданные 10 источников)
- `app/bonus/data_sources/tco/shifts.py` (метаданные TcoShifts)
- `app/bonus/data_sources/registry.py` (`list_metadata()`)
- `app/bonus/calculator/metadata.py` (новый — `CALCULATION_MODEL_METADATA`)
- `app/bonus/routers/dictionary.py` (поменяны 2 эндпоинта)

**Frontend (4 файла):**
- `frontend/src/types/bonus.ts` (новые типы)
- `frontend/src/hooks/use-bonus.ts` (типизация)
- `frontend/src/components/bonus/scheme-config-view.tsx` (новый — рендер)
- `frontend/src/pages/bonus-schemes-page.tsx` (Tabs + новый рендер)

**Документация:**
- `docs/SESSION_LOG_Bonus_Scheme_UI_Editor_Phase1_2026-05-02_10-27.md` (этот файл)
- `docs/BONUS_SYSTEM_GUIDE.md` (обновлён раздел 12.6 — отметить что часть готова)

---

## Известные ограничения

- На фронте используется `title` атрибут для tooltip'ов источников и моделей. Когда появится shadcn-компонент `Tooltip`, заменить на нормальный popover
- `Switch` компонент ещё не создан в `frontend/src/components/ui/` — потребуется на этапе 2 для `type=bool` опций
- Эндпоинт `POST /schemes/preview-calculation` пока не реализован (этап 3.1)
- Метаданные моделей расчёта (`calculator/metadata.py`) дублируют часть информации из `schemas/calc_configs/*.py`. Когда (и если) появится автогенерация JSON-Schema из Pydantic — можно объединить

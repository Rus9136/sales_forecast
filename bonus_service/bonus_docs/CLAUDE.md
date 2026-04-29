# CLAUDE.md — Инструкции для Claude Code

Этот файл — точка входа для Claude Code. Прочитай его **до начала любой работы**.

## Что это за проект

Сервис расчёта бонусов сотрудников ресторанной сети. Подробности — в `README.md` и `docs/00-context.md`.

## Порядок работы

1. **Прочитай всю документацию** в указанном в `README.md` порядке. Не приступай к коду, пока не понятна предметная область.
2. **Следуй плану** в `docs/09-implementation-plan.md` — он разбит на этапы. Делай этап за этапом, не прыгай вперёд.
3. **Проверяй тесты** после каждого этапа: `pytest tests/`. Не переходи дальше, если красные.
4. **Сверяйся с тест-кейсами** из `docs/10-testing.md` — там есть конкретные ожидаемые числа из реальных документов.

## Принципы кода

### Архитектура
- **Чистый слоёный код**: API → Service → Repository → Model. Не смешивать.
- **Все настройки бонусов — в БД**, не в коде. Если коэффициент захардкожен — это баг.
- **Calculation models — плагины** через registry. Каждая модель в своём файле.
- **Data sources — плагины** через registry. iiko/TCO/CRM не упоминаются в коде калькулятора.

### Стиль
- Python 3.12, type hints везде (`from __future__ import annotations` в начале каждого файла)
- SQLAlchemy 2.0 async (`AsyncSession`, `select()`, `Mapped[...]`)
- Pydantic v2 для всех schemas (`model_config = ConfigDict(...)`)
- Decimal для денег и процентов — никаких float
- Datetime всегда с tz-aware (UTC внутри, локальное только на границах)

### Конкретные требования
- Все денежные значения — `Decimal` (тенге, без копеек: `Decimal("170000")`)
- Все процентные значения — `Decimal` в долях: 0.045, не 4.5
- В БД проценты хранить с точностью `DECIMAL(8, 6)` (до 6 знаков, чтобы 0.000700 хранилось точно)
- Деньги — `DECIMAL(14, 2)` (хватит до триллионов тенге с копейками)
- Никаких `print()` — только `logging` через `app.core.logging`
- Никаких голых `except Exception` — ловить конкретное

### Тесты
- Каждая модель расчёта — свой файл тестов в `tests/unit/calculator/models/`
- Каждый тест должен использовать конкретные числа из документов (см. `docs/10-testing.md`)
- Интеграционный тест: «полный цикл расчёта для локации за период» — обязательно

## Что НЕЛЬЗЯ делать

❌ **Хардкодить ставки** в коде Python — всё в БД через seeds  
❌ **Писать кастомный калькулятор для KITCHEN** — это просто `team_revenue_by_kpi` с команды  
❌ **Создавать таблицу под конкретное подразделение** (`KitchenDistribution`, `BarStaff` и т.д.) — использовать `team` + `team_position`  
❌ **Звать iiko/TCO напрямую из калькулятора** — только через `DataSourceRegistry`  
❌ **Использовать float для денег** — только `Decimal`  
❌ **Удалять схемы расчёта** — версионировать через `effective_to`  

## Что ОБЯЗАТЕЛЬНО делать

✅ **Сохранять снапшот** при расчёте (KPI значения, использованная версия схемы) — для аудита  
✅ **Логировать** каждый расчёт с подробной разбивкой (зачем взято такое число)  
✅ **Поддерживать proration по сменам** — везде, где модель этого требует  
✅ **Валидировать config JSONB** через Pydantic-схему модели расчёта при сохранении  
✅ **Возвращать BonusBreakdown** с детализацией: KPI значения → грейд → ставка → итог  

## Если что-то не понятно

1. Сначала перечитай документацию ещё раз
2. Проверь `docs/07-config-examples.md` — там есть конфиги под все 10 локаций
3. Проверь `docs/10-testing.md` — там примеры с числами
4. Если всё равно не ясно — спроси у меня (Rus), не угадывай

## Команды для разработки

```bash
# Установка
uv sync

# БД
docker compose up -d postgres

# Миграции
alembic revision --autogenerate -m "описание"
alembic upgrade head

# Сиды (заливка справочников)
python -m app.seeds.run_all

# Тесты
pytest                          # все
pytest tests/unit/              # только юнит
pytest tests/unit/calculator/   # один модуль
pytest -k "test_kitchen"        # по имени
pytest --cov=app                # с покрытием

# Линт/форматирование
ruff check app/ tests/
ruff format app/ tests/
mypy app/

# Запуск API
uvicorn app.main:app --reload --port 8000
```

## Структура коммитов

Каждый этап из `docs/09-implementation-plan.md` = отдельный коммит (или серия). Сообщения:

```
feat(scheme): add BonusScheme model with versioning
feat(calculator): implement flat_by_kpi model
feat(api): add /calculations/run endpoint
test(calculator): cover team_revenue_by_kpi cases
fix(grading): handle <70% case (zero bonus)
refactor(seeds): split kitchen seeds by location
docs: update API spec for breakdown response
```

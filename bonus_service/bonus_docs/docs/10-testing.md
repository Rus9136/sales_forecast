# 10. Тесты — стратегия и тест-кейсы с конкретными числами

## Стратегия

### Уровни тестирования

1. **Unit-тесты** — чистая логика без БД и без сети
   - `kpi_engine`, `grading`, каждая модель расчёта
   - Запускаются за секунды, гоняются часто
2. **Repository-тесты** — с реальной БД (PostgreSQL в Docker)
   - Через `pytest-asyncio` фикстуры
3. **Service-тесты** — бизнес-логика с моками data sources
4. **Integration-тесты** — полный стек: API → service → calculator → mock data → БД
   - 5-10 ключевых сценариев

### Целевое покрытие

- `app/calculator/` — **>= 95%** (критичный код, формулы)
- `app/services/` — **>= 85%**
- `app/repositories/` — **>= 80%**
- `app/api/` — **>= 70%** (smoke тесты на эндпоинты)

### Инструменты

- `pytest`, `pytest-asyncio`, `pytest-cov`
- `factory_boy` — фабрики моделей
- `httpx.AsyncClient` — для API-тестов
- `pytest-postgresql` или просто docker-compose поднятая БД для CI

---

## Конкретные тест-кейсы (числа из реальных документов)

### Модель `flat_by_kpi`: Управляющий

#### TC-01. Идеальная производительность
```
INPUT:
  KPI: staffing=100%, reviews=100%, audit=100%, apc=100%, profitability=100%
  → overall = 100%
EXPECTED:
  grade: 98-100% → value=170 000
  bonus: 170 000 KZT
```

#### TC-02. Среднее значение
```
INPUT:
  KPI: 95, 96, 90, 88, 85 → avg = 90.8 → ceil = 91
EXPECTED:
  grade: 90-97% → value=150 000
  bonus: 150 000 KZT
```

#### TC-03. Ниже порога
```
INPUT:
  KPI: 60, 65, 70, 80, 50 → avg = 65 → ниже 70%
EXPECTED:
  grade: None
  bonus: 0 KZT
```

#### TC-04. На границе
```
INPUT:
  overall = 79.5 → ceil = 80
EXPECTED:
  grade: 80-84% → value=100 000
  bonus: 100 000 KZT
```

#### TC-05. Ровно на границе грейда
```
INPUT:
  overall = 90 (точно)
EXPECTED:
  grade: 90-97%
  bonus: 150 000 KZT
```

---

### Модель `revenue_direct`: Кассир Sandyq Astana

#### TC-10. Полный месяц (без proration)
```
INPUT:
  revenue_without_discount = 25 000 000
  rate = 0.0007
  shifts: not applied (apply_shifts_proration=false для этого случая)
EXPECTED:
  bonus = 25 000 000 × 0.0007 = 17 500 KZT
```

#### TC-11. С proration по сменам
```
INPUT:
  revenue = 25 000 000, rate = 0.0007
  shifts: worked=11, norm=22 → ratio 0.5
EXPECTED:
  bonus = 17 500 × 0.5 = 8 750 KZT
```

---

### Модель `revenue_direct`: Старший бариста Sandyq Astana

#### TC-12. Формула с делением на норму
```
INPUT:
  revenue (бар, со скидкой) = 25 000 000
  rate = 0.0033
  shifts: worked=20, norm=22
  formula: revenue / norm * worked * rate
EXPECTED:
  bonus = 25 000 000 / 22 × 20 × 0.0033 = 75 000 KZT
```

#### TC-13. Старший бариста Tary Kainar (другая ставка)
```
INPUT: revenue=25 000 000, rate=0.007, worked=22, norm=22
EXPECTED: bonus = 25 000 000 × 0.007 = 175 000 KZT
```

---

### Модель `combined_products`: Бариста Tary Kainar

#### TC-20. Стандартный пример из документа
```
INPUT:
  ready_products_revenue = 2 000 000, rate1 = 0.001
  prepared_products_revenue = 3 000 000, rate2 = 0.016
EXPECTED:
  ready_bonus = 2 000 × 0.001 × 1000 = 2 000   ну ты понял
  prepared_bonus = 3 000 000 × 0.016 = 48 000
  total = 50 000 KZT
```

Уточнение по документу:
> 2 000 000 × 0,1% = 2 000 тенге  
> 3 000 000 × 1,6% = 48 000 тенге  
> Итого: 50 000 тенге

#### TC-21. Бариста Sandyq Kainar (rate приготовленной = 0.013)
```
INPUT: ready=2M, prepared=3M, rates=[0.001, 0.013]
EXPECTED: 2 000 + 39 000 = 41 000 KZT
```
(точно совпадает с примером из документа Sandyq Kainar — приложение №6)

#### TC-22. Бариста senior Sandyq Astana (rates=[0.001, 0.007])
```
INPUT: ready=2M, prepared=5M, rates=[0.001, 0.007]
EXPECTED: 2 000 + 35 000 = 37 000 KZT
```

#### TC-23. Бариста middle Sandyq Astana (rates=[0.0015, 0.003])
```
INPUT: ready=2M, prepared=5M
EXPECTED: 3 000 + 15 000 = 18 000 KZT
```

---

### Модель `revenue_percent_by_kpi`: Официант

#### TC-30. Идеальный официант (пример Алихан из документа)
```
INPUT:
  KPI: sales_plan=100%, neg_reviews=100% (0 негативных), margin_share=100%
  → overall = 100%
  grade: 98-100% → rate = 0.045
  personal_revenue = 2 500 000
  shifts: worked=22, norm=22 (или вариант когда не нужна proration т.к. revenue уже за дни смен)
EXPECTED:
  bonus = 2 500 000 × 0.045 = 112 500 KZT
```

#### TC-31. KPI 85%
```
INPUT:
  overall = 85
  grade: 85-89% → rate = 0.04
  revenue = 2 000 000
EXPECTED:
  bonus = 80 000 KZT
```

#### TC-32. Ниже порога
```
INPUT: overall = 65
EXPECTED: bonus = 0
```

---

### Модель `revenue_percent_by_kpi`: Менеджер Sandyq Astana

#### TC-35. Стандартный расчёт
```
INPUT:
  KPI: rating=100, sales=100, reviews=100, audit=100 → overall=100%
  grade: 98-100% → rate = 0.002
  ОВТ (с НДС, минус сервис) = 50 000 000
  shifts: worked=22, norm=22 → ratio=1
EXPECTED:
  bonus = 50 000 000 × 0.002 = 100 000 KZT
```

#### TC-36. С proration
```
INPUT:
  same KPI, но worked=11
EXPECTED:
  bonus = 100 000 × (11/22) = 50 000 KZT
```

---

### Модель `team_revenue_by_kpi`: KITCHEN Sandyq Astana

#### TC-40. Шеф-повар, идеальный месяц
```
INPUT:
  team_kpi: sales=100, audit=100, neg_reviews=100 → overall=100%
  grade: 98-100% → rate=0.045 (но используется только для проверки порога)
  revenue (с НДС, со скидкой) = 50 000 000
  slot: chef, weight=0.0013
  shifts: worked=22, norm=22 → ratio=1
  formula: revenue × slot_weight × shifts_ratio
EXPECTED:
  bonus = 50 000 000 × 0.0013 × 1 = 65 000 KZT
```

#### TC-41. Су-шеф 1, частичные смены
```
INPUT: revenue=50M, slot=sous_chef_1 (weight=0.0009), worked=11, norm=22
EXPECTED: 50 000 000 × 0.0009 × 0.5 = 22 500 KZT
```

#### TC-42. KITCHEN ниже порога KPI
```
INPUT: overall_kpi = 65 (ниже 70%)
EXPECTED: для всех слотов bonus = 0
```

#### TC-43. Сотрудник на испытательном сроке
```
INPUT:
  employee.employment_type = 'probation'
  employee.probation_until = '2026-04-30'
  scheme.config.exclude_probation_period = true
  period = 2026-04 (попадает в probation)
EXPECTED:
  bonus = 0 (с пометкой `is_probation_period: true`)
```

#### TC-44. Распределение на 21 слот (полная команда)
```
INPUT:
  revenue = 50 000 000, все 21 слот заняты, у всех ratio=1
EXPECTED:
  суммарный пул = revenue × sum_of_weights × 1
  где sum_of_weights = 0.0013 + 0.0009 + 0.0006 + 0.0008×2 + 0.0007 + 0.0004 + 
                       0.0006 + 0.0004 + 0.0005 + 0.0003 + 0.0008 + 0.0005 +
                       0.0005×2 + 0.0007 + 0.0006 + 0.0006 + 0.0004 + 0.0005 + 0.0003
                     = 0.0127
  total = 50 000 000 × 0.0127 = 635 000 KZT
  
  каждому слоту своя доля.
```

---

### KPI Engine

#### TC-50. higher_is_better (план продаж)
```
score_kpi(fact=100, target=100, direction='higher_is_better') = 100
score_kpi(fact=120, target=100, direction='higher_is_better', cap_at_100=True) = 100
score_kpi(fact=120, target=100, direction='higher_is_better', cap_at_100=False) = 120
score_kpi(fact=80, target=100, direction='higher_is_better') = 80
score_kpi(fact=0, target=100, direction='higher_is_better') = 0
```

#### TC-51. lower_is_better (негативные отзывы)
```
score_kpi(fact=3, target=5, direction='lower_is_better') = 100 (cap)
score_kpi(fact=5, target=5, direction='lower_is_better') = 100
score_kpi(fact=10, target=5, direction='lower_is_better') = 50
score_kpi(fact=0, target=5, direction='lower_is_better') = 100
```

#### TC-52. binary (рейтинг)
```
score_kpi(fact=5, target=5, direction='binary') = 100
score_kpi(fact=4, target=5, direction='binary') = 80
score_kpi(fact=3, target=5, direction='binary') = 60
```

---

### Grading

#### TC-60. Все диапазоны
```
find_grade(grades, 70) → 70-79
find_grade(grades, 79) → 70-79
find_grade(grades, 80) → 80-84
find_grade(grades, 87) → 85-89
find_grade(grades, 90) → 90-97
find_grade(grades, 97) → 90-97
find_grade(grades, 98) → 98-100
find_grade(grades, 100) → 98-100
find_grade(grades, 69) → None
find_grade(grades, 0) → None
```

#### TC-61. Дырка между грейдами (89.5 → 90% после ceil)
```
percent = 89.5
percent_int = ceil(89.5) = 90
find_grade(grades, 90) → 90-97
```

---

## Интеграционные тесты

### IT-01. Полный расчёт для официанта Sandyq Astana

```python
async def test_full_waiter_calculation():
    # Setup: seeded data
    await run_seeds()
    
    # Создаём сотрудника
    employee = await EmployeeFactory.create(
        location_code="sandyq_astana",
        position_code="waiter",
    )
    
    # Вводим manual KPI
    await client.post("/manual-kpi", json={
        "location_code": "sandyq_astana",
        "kpi_code": "individual_negative_reviews",
        "year": 2026, "month": 4,
        "fact_value": 0
    })
    
    # Запускаем расчёт
    response = await client.post("/calculations/run", json={
        "location_code": "sandyq_astana",
        "year": 2026, "month": 4,
        "scope": f"employee:{employee.id}"
    })
    
    # Ждём завершения
    job_id = response.json()["job_id"]
    await wait_for_job(job_id)
    
    # Проверяем результат
    calc = await client.get(f"/calculations?employee_id={employee.id}")
    assert calc.json()[0]["final_bonus"] == 112500  # из mock данных
    assert calc.json()[0]["status"] == "draft"
    assert "breakdown" in calc.json()[0]
```

### IT-02. KITCHEN: расчёт всей команды

```python
async def test_kitchen_team_calculation():
    # 21 сотрудник назначен на 21 слот
    employees = await create_kitchen_team(location="sandyq_astana", count=21)
    
    await run_calculation(location="sandyq_astana", year=2026, month=4, scope="team:kitchen")
    
    # Проверяем, что все 21 получили бонус
    calculations = await get_calculations(location="sandyq_astana", year=2026, month=4)
    assert len(calculations) == 21
    
    # Проверяем сумму = ожидаемому пулу
    total = sum(c.final_bonus for c in calculations)
    assert total == 635_000  # см. TC-44
```

### IT-03. Версионирование схемы

```python
async def test_scheme_versioning():
    # Создаём v1
    v1 = await create_scheme(rate=0.001, effective_from="2026-01-01")
    
    # Делаем расчёт за январь
    calc_jan = await run_calculation(period="2026-01")
    assert calc_jan.scheme_version == 1
    
    # Создаём v2
    v2 = await create_scheme(rate=0.0015, effective_from="2026-02-01")
    
    # v1 закрылась
    v1_refresh = await get_scheme(v1.id)
    assert v1_refresh.effective_to == "2026-01-31"
    
    # Расчёт за январь (повторно) использует v1
    calc_jan_2 = await run_calculation(period="2026-01")
    assert calc_jan_2.scheme_version == 1
    
    # Расчёт за февраль использует v2
    calc_feb = await run_calculation(period="2026-02")
    assert calc_feb.scheme_version == 2
```

---

## Фикстуры

### `tests/conftest.py`

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.main import app
from app.core.db import Base

@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("postgresql+asyncpg://test:test@localhost:5433/bonus_test")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    async with AsyncSession(db_engine) as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

### `tests/factories.py`

```python
import factory
from app.models import Employee, Location, BonusScheme

class LocationFactory(factory.Factory):
    class Meta:
        model = Location
    code = factory.Sequence(lambda n: f"location_{n}")
    name = factory.Faker("company")
    # ...

class EmployeeFactory(factory.Factory):
    class Meta:
        model = Employee
    full_name = factory.Faker("name")
    iiko_id = factory.Sequence(lambda n: f"iiko_{n}")
    # ...
```

---

## CI / CD

### GitHub Actions (черновик)

```yaml
name: tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: bonus_test
        ports: ['5433:5432']
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v1
      - run: uv sync
      - run: uv run alembic upgrade head
      - run: uv run pytest --cov=app --cov-report=xml
      - run: uv run ruff check
      - run: uv run mypy app/
```

# 05. Источники данных (адаптеры)

## Архитектура

Все внешние данные идут через **`DataSourceRegistry`**. Калькулятор не знает, что под капотом — iiko, TCO, или мок.

```python
# app/data_sources/base.py
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import date
from typing import Any

class DataSource(ABC):
    """Базовый класс для всех источников данных."""
    
    code: str  # 'iiko_revenue_with_discount', 'tco_shifts', etc.
    
    @abstractmethod
    async def fetch(self, params: dict[str, Any]) -> Any:
        """Получить данные. params зависит от источника."""

# app/data_sources/registry.py
class DataSourceRegistry:
    _sources: dict[str, DataSource] = {}
    
    @classmethod
    def register(cls, source: DataSource):
        cls._sources[source.code] = source
    
    @classmethod
    def get(cls, code: str) -> DataSource:
        if code not in cls._sources:
            raise ValueError(f"Unknown data source: {code}")
        return cls._sources[code]
```

## Список источников (для MVP — все моки)

### iiko-источники

| Код | Что возвращает | Параметры |
|---|---|---|
| `iiko_revenue_with_discount` | Decimal — выручка точки «Сумма со скидкой» | `location_id, period` |
| `iiko_revenue_without_discount` | Decimal — выручка «Сумма без скидки» | `location_id, period` |
| `iiko_personal_revenue_with_discount` | Decimal — выручка по ФИО (для официантов) | `location_id, employee_iiko_id, period, only_worked_days=True/False` |
| `iiko_personal_ready_products_with_discount` | Decimal — выручка по готовой продукции | `location_id, employee_iiko_id, period` |
| `iiko_personal_prepared_products_with_discount` | Decimal — выручка по приготовленной продукции | `location_id, employee_iiko_id, period` |
| `iiko_sales_plan_personal` | Decimal — продажи по сотруднику (для KPI плана продаж) | `location_id, employee_iiko_id, period` |
| `iiko_sales_plan_location` | Decimal — общие продажи точки | `location_id, period` |
| `iiko_apc` | Decimal — средний чек | `location_id, period` |
| `iiko_margin_share` | Decimal — доля маржинальных позиций (%) | `location_id, employee_iiko_id, period` |

### TCO источники

| Код | Что возвращает | Параметры |
|---|---|---|
| `tco_shifts` | `ShiftStats(worked_days, norm_days, worked_hours, norm_hours)` | `employee_tco_id, period` |
| `tco_worked_dates` | list[date] — список конкретных дат смен (для фильтра выручки) | `employee_tco_id, period` |

### CRM источники

| Код | Что возвращает | Параметры |
|---|---|---|
| `crm_negative_reviews_share` | Decimal — % негативных отзывов | `location_id, period` |
| `crm_individual_negative_reviews` | Decimal — % индивидуальных негативных отзывов | `location_id, employee_id, period` |
| `crm_kitchen_reviews` | Decimal — % негативных отзывов на кухню | `location_id, period` |
| `crm_restaurant_rating` | Decimal — рейтинг ресторана (1-5) | `location_id, period` |

### HR источники

| Код | Что возвращает | Параметры |
|---|---|---|
| `hr_staffing_percent` | Decimal — % укомплектованности штата | `location_id, period` |

### Ручной ввод

| Код | Что возвращает | Параметры |
|---|---|---|
| `manual_audit` | Decimal — % качества по аудиту | `location_id, period, kpi_code='audit'` |
| `manual_kitchen_audit` | Decimal — результат аудита кухни | `location_id, period` |
| `manual_profitability` | Decimal — % выполнения плана рентабельности | `location_id, period` |

### Системные (вспомогательные)

| Код | Что возвращает | Параметры |
|---|---|---|
| `monthly_plan_sales` | Decimal — план продаж на месяц (из `monthly_plan`) | `location_id, year, month` |
| `monthly_plan_profitability` | Decimal — план рентабельности на месяц | `location_id, year, month` |

## Реализация моков для MVP

```python
# app/data_sources/mock/iiko_mocks.py
from decimal import Decimal
from app.data_sources.base import DataSource
from app.data_sources.registry import DataSourceRegistry

class MockIikoRevenueWithDiscount(DataSource):
    code = "iiko_revenue_with_discount"
    
    # Предзаготовленные данные для тестов
    _data = {
        ("sandyq_astana", 2026, 4): Decimal("56000000"),
        ("tary_kainar", 2026, 4): Decimal("48000000"),
        ("sandyq_almaty", 2026, 4): Decimal("62000000"),
        # ... остальные локации/периоды
    }
    
    async def fetch(self, params: dict) -> Decimal:
        key = (params["location_code"], params["period"].year, params["period"].month)
        return self._data.get(key, Decimal("0"))


# Регистрация при старте приложения
def register_mock_sources():
    DataSourceRegistry.register(MockIikoRevenueWithDiscount())
    DataSourceRegistry.register(MockIikoPersonalRevenueWithDiscount())
    DataSourceRegistry.register(MockTcoShifts())
    # ...

# В app/main.py:
from app.data_sources.mock import register_mock_sources
if settings.use_mock_data_sources:
    register_mock_sources()
else:
    register_real_sources()  # для прода
```

## Структура CalculationContext

В калькулятор передаётся объединённый контекст с предзагруженными данными:

```python
@dataclass
class CalculationContext:
    period: PeriodKey                       # year, month
    location: Location
    employee: Employee | None               # None для team расчётов
    team: Team | None
    
    # Предзагруженные данные (чтобы не делать запросы из калькулятора)
    kpi_values: dict[str, KpiFact]          # {"sales_plan": KpiFact(fact=..., target=..., percent=...)}
    revenue_values: dict[str, Decimal]      # {"iiko_revenue_with_discount": Decimal(...)}
    shifts: ShiftStats
    
    # Метаданные
    monthly_plans: dict[str, Decimal]       # {"sales": ..., "profitability": ...}
```

## Прелоадер

Перед расчётом сервис делает один проход:

```python
class CalculationPreloader:
    async def preload(self, scheme: BonusScheme, target: Employee | Team, period) -> CalculationContext:
        model = CALCULATION_MODELS[scheme.calculation_model]
        
        # Узнаём, какие источники нужны
        kpi_sources = model.get_required_kpi_sources(scheme.config)
        revenue_sources = model.get_required_revenue_sources(scheme.config)
        
        # Параллельно тянем
        kpi_values = await asyncio.gather(*[self.fetch_kpi(...) for src in kpi_sources])
        revenue_values = await asyncio.gather(*[self.fetch_revenue(...) for src in revenue_sources])
        shifts = await DataSourceRegistry.get("tco_shifts").fetch({...})
        
        return CalculationContext(...)
```

## Реальные интеграции (после MVP)

### iiko
- Sandyq уже есть MCP-сервер `mcp.madlen.space` (наработки Rus'а)
- Нужно перенести логику в `IikoRealAdapter`
- Endpoints: `/forecast`, `/hourly_sales`, `/payroll`, `/employees_revenue`
- Авторизация: API token + login/password

### TCO
- Своя система (FastAPI), API уже есть
- Нужный endpoint: `/api/v1/shifts?employee_id=...&from=...&to=...`
- JWT авторизация

### CRM
- Уточнить, что за CRM (Bitrix? самописная?)
- Обычно есть REST API, нужно договориться с командой CRM

### HR
- Источник — 1С:ЗУП
- Скорее всего ручной экспорт или периодическая синхронизация

## Кэширование

- На уровне DataSource: можно кэшировать через Redis (источник + параметры → значение)
- TTL: для исторических данных (закрытые периоды) — навсегда; для текущего периода — 5-15 минут
- Для MVP: без кэша

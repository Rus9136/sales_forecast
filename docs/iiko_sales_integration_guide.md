# Интеграция с iiko API: Загрузка продаж

## Содержание
1. [Обзор](#1-обзор)
2. [Аутентификация](#2-аутентификация)
3. [OLAP-отчёт по продажам](#3-olap-отчёт-по-продажам)
4. [Структура запроса](#4-структура-запроса)
5. [Структура ответа](#5-структура-ответа)
6. [Обработка данных с pandas](#6-обработка-данных-с-pandas)
7. [Готовый код для интеграции](#7-готовый-код-для-интеграции)
8. [Сохранение в базу данных](#8-сохранение-в-базу-данных)
9. [Автоматическая загрузка по расписанию](#9-автоматическая-загрузка-по-расписанию)
10. [Проверка пропусков данных](#10-проверка-пропусков-данных)
11. [Обработка ошибок и нюансы](#11-обработка-ошибок-и-нюансы)
12. [Примечания и рекомендации](#12-примечания-и-рекомендации)

---

## 1. Обзор

Для получения данных о продажах используется OLAP-отчёт iiko API. Данные приходят в формате JSON, содержат информацию по каждому заказу: подразделение, время закрытия, номер заказа и сумму.

### Общая схема

```
Ваше приложение
      │
      ├── 1. GET  /resto/api/auth                  →  Получить токен
      │
      ├── 2. POST /resto/api/v2/reports/olap        →  Получить сырые данные продаж (JSON)
      │
      ├── 3. Обработка данных (pandas)
      │      ├── Группировка по подразделению + дате     →  Дневные итоги
      │      └── Группировка по подразделению + дате + часу  →  Почасовые итоги
      │
      └── 4. Сохранение в БД
             ├── sales_summary  (дневные итоги)
             └── sales_by_hour  (почасовые итоги)
```

---

## 2. Аутентификация

Аутентификация идентична загрузке подразделений (см. `iiko_departments_integration_guide.md`).

### Краткое напоминание

```
GET {base_url}/resto/api/auth?login={login}&pass={password}
→ Ответ: токен (plain text), живёт 60 минут
```

**Важно**: для запросов продаж рекомендуется **всегда получать свежий токен** перед каждым запросом, а не использовать кэшированный. Это гарантирует стабильную работу при длительных загрузках.

```python
# Принудительное обновление токена перед запросом продаж
token = await auth_service._refresh_token()  # force refresh
```

---

## 3. OLAP-отчёт по продажам

### Эндпоинт

```
POST {base_url}/resto/api/v2/reports/olap
```

### Параметры

| Параметр | Расположение | Тип    | Обязательный | Описание                   |
|----------|-------------|--------|--------------|----------------------------|
| `key`    | Query       | string | Да           | Токен аутентификации       |
| body     | Body (JSON) | object | Да           | Параметры OLAP-отчёта      |

### Пример вызова через curl

```bash
curl -X POST "https://your-org.iiko.it/resto/api/v2/reports/olap?key=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reportType": "SALES",
    "groupByRowFields": ["Department.Id", "CloseTime", "OrderNum"],
    "aggregateFields": ["DishSumInt"],
    "filters": {
      "OpenDate.Typed": {
        "filterType": "DateRange",
        "periodType": "CUSTOM",
        "from": "2025-03-01",
        "to": "2025-03-31"
      },
      "OrderDeleted": {
        "filterType": "IncludeValues",
        "values": ["NOT_DELETED"]
      },
      "DeletedWithWriteoff": {
        "filterType": "IncludeValues",
        "values": ["NOT_DELETED"]
      }
    }
  }'
```

---

## 4. Структура запроса

### Полная структура тела запроса (JSON)

```json
{
    "reportType": "SALES",
    "groupByRowFields": [
        "Department.Id",
        "CloseTime",
        "OrderNum"
    ],
    "aggregateFields": [
        "DishSumInt"
    ],
    "filters": {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": "2025-03-01",
            "to": "2025-03-31"
        },
        "OrderDeleted": {
            "filterType": "IncludeValues",
            "values": ["NOT_DELETED"]
        },
        "DeletedWithWriteoff": {
            "filterType": "IncludeValues",
            "values": ["NOT_DELETED"]
        }
    }
}
```

### Описание полей запроса

#### `reportType`
- Тип отчёта. Для продаж всегда `"SALES"`

#### `groupByRowFields` — поля группировки
Определяют, по каким полям группируются данные:

| Поле             | Описание                                      |
|------------------|-----------------------------------------------|
| `Department.Id`  | UUID подразделения (ресторан/кафе)             |
| `CloseTime`      | Время закрытия заказа (datetime)               |
| `OrderNum`       | Номер заказа (для детализации до каждого чека) |

Дополнительные поля, которые можно добавить:

| Поле               | Описание                        |
|--------------------|---------------------------------|
| `Department.Name`  | Название подразделения          |
| `WaiterName`       | Имя официанта                   |
| `TableNum`         | Номер стола                     |
| `OrderType`        | Тип заказа (зал, доставка)      |
| `DishName`         | Название блюда                  |
| `DishCategory`     | Категория блюда                 |
| `DishGroup`        | Группа блюд                    |
| `OpenDate.Typed`   | Дата открытия заказа            |

#### `aggregateFields` — поля агрегации

| Поле          | Описание                                      |
|---------------|-----------------------------------------------|
| `DishSumInt`  | Сумма продаж (основное поле для суммы заказа)  |
| `DishAmount`  | Количество блюд                                |
| `DishDiscount`| Сумма скидки                                   |

#### `filters` — фильтры

##### `OpenDate.Typed` — диапазон дат
```json
{
    "filterType": "DateRange",
    "periodType": "CUSTOM",
    "from": "2025-03-01",
    "to": "2025-03-31"
}
```

Возможные значения `periodType`:
- `"CUSTOM"` — произвольный диапазон (используем `from` / `to`)
- `"TODAY"` — сегодня
- `"YESTERDAY"` — вчера
- `"THIS_WEEK"` — текущая неделя
- `"LAST_WEEK"` — прошлая неделя
- `"THIS_MONTH"` — текущий месяц
- `"LAST_MONTH"` — прошлый месяц

##### `OrderDeleted` — фильтр удалённых заказов
```json
{
    "filterType": "IncludeValues",
    "values": ["NOT_DELETED"]
}
```
Значения: `"NOT_DELETED"`, `"DELETED"`, `"DELETED_WITH_WRITEOFF"`

##### `DeletedWithWriteoff` — фильтр удалённых со списанием
```json
{
    "filterType": "IncludeValues",
    "values": ["NOT_DELETED"]
}
```

---

## 5. Структура ответа

### Формат ответа (JSON)

```json
{
    "data": [
        {
            "Department.Id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "CloseTime": "2025-03-15T14:30:00",
            "OrderNum": 1234,
            "DishSumInt": 15600.50
        },
        {
            "Department.Id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "CloseTime": "2025-03-15T18:45:00",
            "OrderNum": 1235,
            "DishSumInt": 8200.00
        },
        {
            "Department.Id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "CloseTime": "2025-03-15 09:15:00.000",
            "OrderNum": 501,
            "DishSumInt": 3400.75
        }
    ]
}
```

### Описание полей ответа

| Поле             | Тип      | Описание                                                       |
|------------------|----------|----------------------------------------------------------------|
| `Department.Id`  | string   | UUID подразделения                                             |
| `CloseTime`      | string   | Время закрытия заказа (формат может варьироваться — см. ниже)  |
| `OrderNum`       | int      | Номер заказа                                                   |
| `DishSumInt`     | float    | Сумма продаж по заказу                                         |

### Формат `CloseTime`

**Важно**: iiko возвращает `CloseTime` в **разных форматах** в зависимости от версии сервера:

```
"2025-03-15T14:30:00"          # ISO формат
"2025-03-15 14:30:00.000"      # С миллисекундами
"2025-03-15T14:30:00.000"      # ISO с миллисекундами
"15.03.2025 14:30:00"          # Европейский формат
```

Для корректного парсинга используйте `format='mixed'` в pandas:

```python
df['CloseTime'] = pd.to_datetime(df['CloseTime'], format='mixed')
```

---

## 6. Обработка данных с pandas

Сырые данные из iiko — это список заказов. Для аналитики нужно агрегировать их в дневные и почасовые итоги.

### Конвертация и извлечение компонентов

```python
import pandas as pd

# Из списка словарей в DataFrame
df = pd.DataFrame(sales_data)

# Парсинг даты (mixed формат — обрабатывает разные форматы)
df['CloseTime'] = pd.to_datetime(df['CloseTime'], format='mixed')

# Извлечение даты и часа
df['date'] = df['CloseTime'].dt.date
df['hour'] = df['CloseTime'].dt.hour
```

### Агрегация: дневные итоги

```python
# Группировка по подразделению + дате → сумма продаж за день
daily_summary = df.groupby(['Department.Id', 'date']).agg(
    total_sales=('DishSumInt', 'sum')
).reset_index()

# Результат:
# Department.Id                          | date       | total_sales
# a1b2c3d4-e5f6-7890-abcd-ef1234567890  | 2025-03-15 | 23800.50
# b2c3d4e5-f6a7-8901-bcde-f12345678901  | 2025-03-15 | 3400.75
```

### Агрегация: почасовые итоги

```python
# Группировка по подразделению + дате + час → сумма продаж за час
hourly_summary = df.groupby(['Department.Id', 'date', 'hour']).agg(
    sales_amount=('DishSumInt', 'sum')
).reset_index()

# Результат:
# Department.Id                          | date       | hour | sales_amount
# a1b2c3d4-e5f6-7890-abcd-ef1234567890  | 2025-03-15 | 9    | 5200.00
# a1b2c3d4-e5f6-7890-abcd-ef1234567890  | 2025-03-15 | 14   | 15600.50
# a1b2c3d4-e5f6-7890-abcd-ef1234567890  | 2025-03-15 | 18   | 3000.00
```

### Конвертация обратно в список словарей

```python
# Дневные записи
summary_records = []
for _, row in daily_summary.iterrows():
    summary_records.append({
        'department_id': row['Department.Id'],
        'date': row['date'],
        'total_sales': float(row['total_sales'])
    })

# Почасовые записи
hourly_records = []
for _, row in hourly_summary.iterrows():
    hourly_records.append({
        'department_id': row['Department.Id'],
        'date': row['date'],
        'hour': int(row['hour']),
        'sales_amount': float(row['sales_amount'])
    })
```

---

## 7. Готовый код для интеграции

### Полный пример: загрузка продаж (async)

```python
import httpx
import pandas as pd
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


class IikoAuthService:
    """Аутентификация в iiko API."""

    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None

    async def get_token(self) -> str:
        if self.token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.token
        return await self._refresh_token()

    async def _refresh_token(self) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/resto/api/auth",
                params={"login": self.login, "pass": self.password},
            )
            response.raise_for_status()
            self.token = response.text.strip()
            self.token_expires_at = datetime.now() + timedelta(minutes=55)
            logger.info(f"Получен токен iiko для {self.base_url}")
            return self.token


class IikoSalesLoader:
    """Загрузка и обработка данных о продажах из iiko API."""

    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.auth = IikoAuthService(base_url, login, password)

    async def fetch_sales(
        self,
        from_date: date,
        to_date: date,
    ) -> List[dict]:
        """
        Получить сырые данные продаж из iiko OLAP API.

        Args:
            from_date: Начальная дата
            to_date: Конечная дата (должна отличаться от from_date!)

        Returns:
            Список словарей с данными по каждому заказу
        """
        # Всегда получаем свежий токен для надёжности
        token = await self.auth._refresh_token()

        request_body = {
            "reportType": "SALES",
            "groupByRowFields": [
                "Department.Id",
                "CloseTime",
                "OrderNum",
            ],
            "aggregateFields": [
                "DishSumInt",
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": from_date.strftime("%Y-%m-%d"),
                    "to": to_date.strftime("%Y-%m-%d"),
                },
                "OrderDeleted": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"],
                },
                "DeletedWithWriteoff": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"],
                },
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/resto/api/v2/reports/olap",
                params={"key": token},
                json=request_body,
            )
            response.raise_for_status()

        data = response.json()
        sales = data.get("data", [])
        logger.info(f"Получено {len(sales)} записей продаж из {self.base_url}")
        return sales

    def process_sales(
        self,
        sales_data: List[dict],
    ) -> tuple[List[dict], List[dict]]:
        """
        Обработать сырые данные продаж: агрегировать по дням и часам.

        Args:
            sales_data: Сырые данные из iiko API

        Returns:
            Кортеж (дневные_итоги, почасовые_итоги)
        """
        if not sales_data:
            return [], []

        df = pd.DataFrame(sales_data)

        # Парсинг даты (mixed формат для совместимости)
        df["CloseTime"] = pd.to_datetime(df["CloseTime"], format="mixed")
        df["date"] = df["CloseTime"].dt.date
        df["hour"] = df["CloseTime"].dt.hour

        # Дневные итоги: сумма по подразделению + дате
        daily = (
            df.groupby(["Department.Id", "date"])
            .agg(total_sales=("DishSumInt", "sum"))
            .reset_index()
        )

        # Почасовые итоги: сумма по подразделению + дате + часу
        hourly = (
            df.groupby(["Department.Id", "date", "hour"])
            .agg(sales_amount=("DishSumInt", "sum"))
            .reset_index()
        )

        # Конвертация в списки словарей
        summary_records = [
            {
                "department_id": row["Department.Id"],
                "date": row["date"],
                "total_sales": float(row["total_sales"]),
            }
            for _, row in daily.iterrows()
        ]

        hourly_records = [
            {
                "department_id": row["Department.Id"],
                "date": row["date"],
                "hour": int(row["hour"]),
                "sales_amount": float(row["sales_amount"]),
            }
            for _, row in hourly.iterrows()
        ]

        logger.info(
            f"Обработано: {len(summary_records)} дневных, "
            f"{len(hourly_records)} почасовых записей"
        )
        return summary_records, hourly_records


# --- Использование ---

async def main():
    loader = IikoSalesLoader(
        base_url="https://your-org.iiko.it",
        login="your_login",
        password="your_password_hash",
    )

    # Загрузка за период
    from_date = date(2025, 3, 1)
    to_date = date(2025, 3, 31)

    # 1. Получаем сырые данные
    raw_sales = await loader.fetch_sales(from_date, to_date)
    print(f"Получено {len(raw_sales)} сырых записей")

    # 2. Обрабатываем
    daily, hourly = loader.process_sales(raw_sales)

    print(f"\nДневные итоги ({len(daily)} записей):")
    for record in daily[:5]:
        print(f"  {record['date']} | {record['department_id'][:8]}... | {record['total_sales']:,.0f}")

    print(f"\nПочасовые итоги ({len(hourly)} записей):")
    for record in hourly[:5]:
        print(f"  {record['date']} {record['hour']:02d}:00 | {record['department_id'][:8]}... | {record['sales_amount']:,.0f}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Полный пример: загрузка продаж (sync, requests)

```python
import requests
import pandas as pd
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


class IikoSalesLoaderSync:
    """Синхронная загрузка продаж из iiko API."""

    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None

    def _get_token(self) -> str:
        response = requests.get(
            f"{self.base_url}/resto/api/auth",
            params={"login": self.login, "pass": self.password},
            timeout=30,
        )
        response.raise_for_status()
        self.token = response.text.strip()
        self.token_expires_at = datetime.now() + timedelta(minutes=55)
        return self.token

    def fetch_sales(self, from_date: date, to_date: date) -> List[dict]:
        """Получить данные продаж."""
        token = self._get_token()

        request_body = {
            "reportType": "SALES",
            "groupByRowFields": ["Department.Id", "CloseTime", "OrderNum"],
            "aggregateFields": ["DishSumInt"],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": from_date.strftime("%Y-%m-%d"),
                    "to": to_date.strftime("%Y-%m-%d"),
                },
                "OrderDeleted": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"],
                },
                "DeletedWithWriteoff": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"],
                },
            },
        }

        response = requests.post(
            f"{self.base_url}/resto/api/v2/reports/olap",
            params={"key": token},
            json=request_body,
            timeout=60,
        )
        response.raise_for_status()

        return response.json().get("data", [])

    def process_sales(self, sales_data: List[dict]) -> tuple:
        """Агрегировать по дням и часам."""
        if not sales_data:
            return [], []

        df = pd.DataFrame(sales_data)
        df["CloseTime"] = pd.to_datetime(df["CloseTime"], format="mixed")
        df["date"] = df["CloseTime"].dt.date
        df["hour"] = df["CloseTime"].dt.hour

        daily = (
            df.groupby(["Department.Id", "date"])
            .agg(total_sales=("DishSumInt", "sum"))
            .reset_index()
        )
        hourly = (
            df.groupby(["Department.Id", "date", "hour"])
            .agg(sales_amount=("DishSumInt", "sum"))
            .reset_index()
        )

        return (
            daily.to_dict("records"),
            hourly.to_dict("records"),
        )


# --- Использование ---

loader = IikoSalesLoaderSync(
    base_url="https://your-org.iiko.it",
    login="your_login",
    password="your_password_hash",
)

raw = loader.fetch_sales(date(2025, 3, 1), date(2025, 3, 31))
daily, hourly = loader.process_sales(raw)
print(f"Дневных: {len(daily)}, почасовых: {len(hourly)}")
```

---

## 8. Сохранение в базу данных

### Модели SQLAlchemy

```python
from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class Department(Base):
    """Подразделение (должно быть загружено заранее)."""
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    type = Column(String(50), default="DEPARTMENT")


class SalesSummary(Base):
    """Дневные итоги продаж по подразделениям."""
    __tablename__ = "sales_summary"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
    )
    date = Column(Date, nullable=False, index=True)
    total_sales = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department")


class SalesByHour(Base):
    """Почасовые данные продаж по подразделениям."""
    __tablename__ = "sales_by_hour"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id"),
        nullable=False,
        index=True,
    )
    date = Column(Date, nullable=False, index=True)
    hour = Column(Integer, nullable=False, index=True)  # 0-23
    sales_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department")
```

### Alembic-миграция

```python
"""create sales tables

Revision ID: 002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade():
    # Дневные итоги
    op.create_table(
        "sales_summary",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("total_sales", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("synced_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_sales_summary_dept_id", "sales_summary", ["department_id"])
    op.create_index("ix_sales_summary_date", "sales_summary", ["date"])
    op.create_unique_constraint("uq_sales_summary_dept_date", "sales_summary", ["department_id", "date"])

    # Почасовые итоги
    op.create_table(
        "sales_by_hour",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("hour", sa.Integer, nullable=False),
        sa.Column("sales_amount", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("synced_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_sales_by_hour_dept_id", "sales_by_hour", ["department_id"])
    op.create_index("ix_sales_by_hour_date", "sales_by_hour", ["date"])
    op.create_index("ix_sales_by_hour_hour", "sales_by_hour", ["hour"])
    op.create_unique_constraint("uq_sales_by_hour_dept_date_hour", "sales_by_hour", ["department_id", "date", "hour"])


def downgrade():
    op.drop_table("sales_by_hour")
    op.drop_table("sales_summary")
```

### Функция синхронизации с БД (upsert)

```python
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List


def sync_daily_sales(db: Session, records: List[dict]) -> dict:
    """
    Сохранить дневные итоги в БД.
    Если запись уже существует (department_id + date) — обновить.
    """
    new_count = 0
    updated_count = 0
    skipped_count = 0

    for record in records:
        # Проверяем существование подразделения
        dept = db.query(Department).filter(
            Department.id == record["department_id"]
        ).first()

        if not dept:
            skipped_count += 1
            logger.warning(f"Подразделение {record['department_id']} не найдено, пропуск")
            continue

        # Ищем существующую запись
        existing = db.query(SalesSummary).filter(
            SalesSummary.department_id == record["department_id"],
            SalesSummary.date == record["date"],
        ).first()

        if existing:
            existing.total_sales = record["total_sales"]
            existing.updated_at = datetime.utcnow()
            existing.synced_at = datetime.utcnow()
            updated_count += 1
        else:
            db.add(SalesSummary(
                department_id=record["department_id"],
                date=record["date"],
                total_sales=record["total_sales"],
                synced_at=datetime.utcnow(),
            ))
            new_count += 1

    db.commit()
    return {"new": new_count, "updated": updated_count, "skipped": skipped_count}


def sync_hourly_sales(db: Session, records: List[dict]) -> dict:
    """
    Сохранить почасовые итоги в БД.
    Если запись уже существует (department_id + date + hour) — обновить.
    """
    new_count = 0
    updated_count = 0
    skipped_count = 0

    for record in records:
        dept = db.query(Department).filter(
            Department.id == record["department_id"]
        ).first()

        if not dept:
            skipped_count += 1
            continue

        existing = db.query(SalesByHour).filter(
            SalesByHour.department_id == record["department_id"],
            SalesByHour.date == record["date"],
            SalesByHour.hour == record["hour"],
        ).first()

        if existing:
            existing.sales_amount = record["sales_amount"]
            existing.updated_at = datetime.utcnow()
            existing.synced_at = datetime.utcnow()
            updated_count += 1
        else:
            db.add(SalesByHour(
                department_id=record["department_id"],
                date=record["date"],
                hour=record["hour"],
                sales_amount=record["sales_amount"],
                synced_at=datetime.utcnow(),
            ))
            new_count += 1

    db.commit()
    return {"new": new_count, "updated": updated_count, "skipped": skipped_count}
```

---

## 9. Автоматическая загрузка по расписанию

Для автоматической ежедневной загрузки используется **APScheduler**.

### Установка

```bash
pip install apscheduler
```

### Настройка планировщика

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

# Ежедневная загрузка продаж в 02:00
scheduler.add_job(
    func=run_daily_sales_sync,
    trigger="cron",
    hour=2,
    minute=0,
    id="daily_sales_sync",
)

# Проверка пропусков в 10:00
scheduler.add_job(
    func=run_gap_check,
    trigger="cron",
    hour=10,
    minute=0,
    id="daily_gap_check",
)

scheduler.start()
```

### Функция ежедневной загрузки

```python
import asyncio
from datetime import date, timedelta


def run_daily_sales_sync():
    """Ежедневная автоматическая загрузка продаж за вчера."""

    async def _sync():
        yesterday = date.today() - timedelta(days=1)
        today = date.today()

        # ВАЖНО: from_date и to_date должны быть разными!
        # iiko API возвращает ошибку 409 если from_date == to_date
        loader = IikoSalesLoader(
            base_url="https://your-org.iiko.it",
            login="your_login",
            password="your_password",
        )

        raw_sales = await loader.fetch_sales(yesterday, today)
        daily, hourly = loader.process_sales(raw_sales)

        # Сохранение в БД
        # db = get_db_session()
        # sync_daily_sales(db, daily)
        # sync_hourly_sales(db, hourly)

        return {
            "status": "success",
            "date": str(yesterday),
            "daily_records": len(daily),
            "hourly_records": len(hourly),
        }

    # Запуск async кода из sync контекста
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_sync())
        logger.info(f"Авто-синхронизация завершена: {result}")
        return result
    finally:
        loop.close()
```

### Логирование автозагрузок

```python
class AutoSyncLog(Base):
    """Лог автоматических загрузок."""
    __tablename__ = "auto_sync_log"

    id = Column(Integer, primary_key=True, index=True)
    sync_date = Column(Date, nullable=False, index=True)
    sync_type = Column(String(50), nullable=False)     # 'daily_auto', 'gap_resync', 'manual'
    status = Column(String(20), nullable=False)         # 'success', 'error'
    message = Column(String(500), nullable=True)
    summary_records = Column(Integer, default=0)        # Кол-во дневных записей
    hourly_records = Column(Integer, default=0)         # Кол-во почасовых записей
    total_raw_records = Column(Integer, default=0)      # Кол-во сырых записей из iiko
    error_details = Column(String(1000), nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## 10. Проверка пропусков данных

Данные из iiko могут приходить неполными (сервер был недоступен, смена закрылась поздно и т.д.). Рекомендуется ежедневно проверять последние 7 дней на пропуски.

### Алгоритм

```python
from sqlalchemy import func


async def check_and_resync_gaps(
    db: Session,
    loader: IikoSalesLoader,
    days_back: int = 7,
    min_expected_departments: int = 30,
) -> List[dict]:
    """
    Проверить последние N дней на пропуски и перезагрузить при необходимости.

    Args:
        db: Сессия БД
        loader: Экземпляр IikoSalesLoader
        days_back: Сколько дней назад проверять
        min_expected_departments: Минимальное ожидаемое количество подразделений с продажами

    Returns:
        Список дат, которые были перезагружены
    """
    # Определяем "активные" подразделения (были продажи за последние 30 дней)
    active_depts = db.query(
        SalesSummary.department_id
    ).filter(
        SalesSummary.date >= date.today() - timedelta(days=30)
    ).distinct().count()

    expected_count = max(active_depts, min_expected_departments)
    resynced = []

    for i in range(days_back):
        check_date = date.today() - timedelta(days=i + 1)

        # Считаем подразделения с данными за этот день
        actual_count = db.query(
            func.count(SalesSummary.department_id.distinct())
        ).filter(
            SalesSummary.date == check_date
        ).scalar() or 0

        logger.info(f"{check_date}: {actual_count}/{expected_count} подразделений")

        # Если значительно меньше ожидаемого — перезагружаем
        if actual_count < expected_count - 2:
            logger.warning(f"Обнаружен пропуск: {check_date} ({actual_count} подразделений)")

            raw = await loader.fetch_sales(check_date, check_date + timedelta(days=1))
            daily, hourly = loader.process_sales(raw)
            sync_daily_sales(db, daily)
            sync_hourly_sales(db, hourly)

            resynced.append({
                "date": str(check_date),
                "before": actual_count,
                "after": len(daily),
            })

    return resynced
```

---

## 11. Обработка ошибок и нюансы

### Ошибка 409: from_date == to_date

**Проблема**: iiko API возвращает `409 Conflict` если `from_date` и `to_date` совпадают.

**Решение**: Всегда устанавливайте `to_date = from_date + 1 день`:

```python
# НЕПРАВИЛЬНО — ошибка 409
from_date = date(2025, 3, 15)
to_date = date(2025, 3, 15)  # ❌

# ПРАВИЛЬНО
from_date = date(2025, 3, 15)
to_date = date(2025, 3, 16)  # ✅ следующий день
```

### Несуществующее подразделение

Продажи могут содержать `Department.Id`, которого нет в таблице `departments`. Всегда проверяйте существование подразделения перед сохранением:

```python
dept = db.query(Department).filter(Department.id == record["department_id"]).first()
if not dept:
    logger.warning(f"Подразделение {record['department_id']} не найдено, пропуск")
    continue
```

### Множество доменов

Если организация использует несколько iiko-серверов, загружайте с каждого и объединяйте:

```python
async def fetch_from_all_domains(
    domains: List[str],
    login: str,
    password: str,
    from_date: date,
    to_date: date,
) -> List[dict]:
    """Загрузить продажи со всех доменов."""
    all_sales = []

    for domain in domains:
        try:
            loader = IikoSalesLoader(domain, login, password)
            sales = await loader.fetch_sales(from_date, to_date)
            all_sales.extend(sales)
            logger.info(f"Из {domain}: {len(sales)} записей")
        except Exception as e:
            logger.error(f"Ошибка {domain}: {e}")
            continue  # продолжаем с другими доменами

    return all_sales
```

### Таймауты

Для больших диапазонов дат (месяц и более) ответ может быть большим. Увеличьте таймаут:

```python
async with httpx.AsyncClient(timeout=120.0) as client:  # 2 минуты
    response = await client.post(...)
```

### Типичные HTTP ошибки

| Код  | Причина                                 | Решение                                    |
|------|-----------------------------------------|--------------------------------------------|
| 401  | Невалидный / истёкший токен             | Получить новый токен                       |
| 409  | `from_date == to_date`                  | Сделать `to_date = from_date + 1 день`     |
| 500  | Ошибка сервера iiko                     | Повторить через несколько секунд           |
| Timeout | Слишком большой диапазон дат          | Уменьшить диапазон или увеличить таймаут   |

---

## 12. Примечания и рекомендации

### Зависимости (requirements.txt)

```
httpx>=0.25.0           # async HTTP клиент
pandas>=2.0.0           # обработка данных
sqlalchemy>=2.0.0       # ORM
psycopg2-binary>=2.9.0  # PostgreSQL драйвер
alembic>=1.12.0         # миграции
apscheduler>=3.10.0     # планировщик (для автозагрузки)
tenacity>=8.2.0         # retry (опционально)
```

### Порядок интеграции

```
1. Настроить .env с credentials
2. Создать таблицу departments (см. iiko_departments_integration_guide.md)
3. Загрузить подразделения из iiko
4. Создать таблицы sales_summary и sales_by_hour
5. Загрузить продажи из iiko
6. (Опционально) Настроить автоматическую загрузку
```

### Рекомендуемая частота загрузки

| Задача                          | Частота         | Время  |
|---------------------------------|-----------------|--------|
| Загрузка продаж за вчера        | Ежедневно       | 02:00  |
| Проверка пропусков (7 дней)     | Ежедневно       | 10:00  |
| Полная перезагрузка подразделений | Еженедельно    | 01:00  |

### Объём данных (ориентировочно)

- ~30-50 подразделений: ~1000-3000 сырых записей/день
- Дневные итоги: ~30-50 записей/день
- Почасовые итоги: ~300-600 записей/день (10-15 часов работы на подразделение)

### Переменные окружения (.env)

```bash
IIKO_BASE_URL=https://your-org.iiko.it
IIKO_BASE_URL_2=https://your-second-org.iiko.it
IIKO_LOGIN=your_login
IIKO_PASSWORD=your_password_hash
DATABASE_URL=postgresql://user:password@localhost:5432/your_db
```

---

## Краткая шпаргалка

```
1. GET  /resto/api/auth?login={login}&pass={password}  →  token

2. POST /resto/api/v2/reports/olap?key={token}
   Body: {
     "reportType": "SALES",
     "groupByRowFields": ["Department.Id", "CloseTime", "OrderNum"],
     "aggregateFields": ["DishSumInt"],
     "filters": {
       "OpenDate.Typed": {"filterType":"DateRange","periodType":"CUSTOM","from":"...","to":"..."},
       "OrderDeleted": {"filterType":"IncludeValues","values":["NOT_DELETED"]},
       "DeletedWithWriteoff": {"filterType":"IncludeValues","values":["NOT_DELETED"]}
     }
   }
   → JSON { "data": [ {"Department.Id", "CloseTime", "OrderNum", "DishSumInt"}, ... ] }

3. Агрегация через pandas:
   - По dept + date         →  SalesSummary  (дневные)
   - По dept + date + hour  →  SalesByHour   (почасовые)

4. Upsert в БД с проверкой существования подразделения

⚠ from_date ≠ to_date (иначе 409)
⚠ Всегда получать свежий токен перед запросом
⚠ Проверять Department.id в БД перед сохранением
```

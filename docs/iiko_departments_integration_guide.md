# Интеграция с iiko API: Получение подразделений

## Содержание
1. [Обзор](#1-обзор)
2. [Аутентификация](#2-аутентификация)
3. [Получение подразделений](#3-получение-подразделений)
4. [Парсинг XML-ответа](#4-парсинг-xml-ответа)
5. [Структура данных подразделений](#5-структура-данных-подразделений)
6. [Иерархия подразделений](#6-иерархия-подразделений)
7. [Готовый код для интеграции](#7-готовый-код-для-интеграции)
8. [Сохранение в базу данных](#8-сохранение-в-базу-данных)
9. [Обработка ошибок](#9-обработка-ошибок)
10. [Примечания и рекомендации](#10-примечания-и-рекомендации)

---

## 1. Обзор

iiko — система управления ресторанным бизнесом. Для получения списка подразделений (ресторанов, кафе, кофеен и т.д.) используется REST API iiko с XML-ответами.

### Общая схема взаимодействия

```
Ваше приложение
      │
      ├── 1. POST /resto/api/auth  →  Получить токен
      │
      └── 2. GET /resto/api/corporation/departments?key={token}  →  Список подразделений (XML)
```

### Базовые URL серверов iiko

Каждая организация имеет свой поддомен на `iiko.it`:

```
https://{your-organization}.iiko.it
```

Примеры:
- `https://sandy-co-co.iiko.it`
- `https://madlen-group-so.iiko.it`

---

## 2. Аутентификация

### Эндпоинт

```
GET {base_url}/resto/api/auth
```

### Параметры запроса (Query Parameters)

| Параметр | Тип    | Обязательный | Описание                    |
|----------|--------|--------------|-----------------------------|
| `login`  | string | Да           | Логин пользователя iiko     |
| `pass`   | string | Да           | Пароль (SHA1-хеш или plain) |

### Пример запроса

```bash
curl "https://your-org.iiko.it/resto/api/auth?login=MyUser&pass=my_password_hash"
```

### Ответ

- **Content-Type**: `text/plain`
- **Тело ответа**: Токен в виде строки (например: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`)

### Время жизни токена

- Токен действителен **60 минут** с момента получения
- Рекомендуется обновлять токен каждые **55 минут** (за 5 минут до истечения)
- При истечении токена API вернёт ошибку `401 Unauthorized`

### Пример на Python

```python
import httpx
from datetime import datetime, timedelta


class IikoAuthService:
    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.token = None
        self.token_expires_at = None

    async def get_token(self) -> str:
        """Получить токен. Если текущий токен ещё валиден — вернуть его."""
        if self.token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.token
        return await self._refresh_token()

    async def _refresh_token(self) -> str:
        """Запросить новый токен у iiko API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/resto/api/auth",
                params={
                    "login": self.login,
                    "pass": self.password
                }
            )
            response.raise_for_status()

            self.token = response.text.strip()
            # Обновляем за 5 минут до истечения (токен живёт 60 минут)
            self.token_expires_at = datetime.now() + timedelta(minutes=55)
            return self.token
```

### Синхронная версия (requests)

```python
import requests
from datetime import datetime, timedelta


class IikoAuthServiceSync:
    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.token = None
        self.token_expires_at = None

    def get_token(self) -> str:
        if self.token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.token
        return self._refresh_token()

    def _refresh_token(self) -> str:
        response = requests.get(
            f"{self.base_url}/resto/api/auth",
            params={"login": self.login, "pass": self.password}
        )
        response.raise_for_status()

        self.token = response.text.strip()
        self.token_expires_at = datetime.now() + timedelta(minutes=55)
        return self.token
```

---

## 3. Получение подразделений

### Эндпоинт

```
GET {base_url}/resto/api/corporation/departments
```

### Параметры запроса (Query Parameters)

| Параметр       | Тип    | Обязательный | Описание                                         |
|----------------|--------|--------------|--------------------------------------------------|
| `key`          | string | Да           | Токен аутентификации (из шага 2)                 |
| `revisionFrom` | int    | Нет          | Ревизия для инкрементальной загрузки. `-1` = все |

### Пример запроса

```bash
# Получить все подразделения
curl "https://your-org.iiko.it/resto/api/corporation/departments?key=YOUR_TOKEN&revisionFrom=-1"
```

### Параметр `revisionFrom`

- `-1` — получить **все** подразделения (полная загрузка)
- `0` или конкретное число — получить только изменения с указанной ревизии (инкрементальная загрузка)
- Для первой загрузки всегда используйте `-1`

---

## 4. Парсинг XML-ответа

### Формат ответа

API возвращает XML. Корневой элемент содержит список `<corporateItemDto>`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<corporateItemDtoes>
  <corporateItemDto>
    <id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</id>
    <parentId>00000000-0000-0000-0000-000000000000</parentId>
    <code>001</code>
    <name>Ресторан "Центральный"</name>
    <type>DEPARTMENT</type>
    <taxpayerIdNumber>123456789012</taxpayerIdNumber>
  </corporateItemDto>

  <corporateItemDto>
    <id>b2c3d4e5-f6a7-8901-bcde-f12345678901</id>
    <parentId>a1b2c3d4-e5f6-7890-abcd-ef1234567890</parentId>
    <code>002</code>
    <name>Кофейня "На углу"</name>
    <type>DEPARTMENT</type>
    <taxpayerIdNumber></taxpayerIdNumber>
  </corporateItemDto>

  <corporateItemDto>
    <id>c3d4e5f6-a7b8-9012-cdef-123456789012</id>
    <parentId></parentId>
    <code></code>
    <name>ТОО "Компания"</name>
    <type>JURPERSON</type>
    <taxpayerIdNumber>987654321098</taxpayerIdNumber>
  </corporateItemDto>
</corporateItemDtoes>
```

### Поля `<corporateItemDto>`

| Поле                 | Тип    | Описание                                             |
|----------------------|--------|------------------------------------------------------|
| `id`                 | UUID   | Уникальный идентификатор подразделения               |
| `parentId`           | UUID   | ID родительского подразделения (может быть пустым)   |
| `code`               | string | Код подразделения (может быть пустым)                |
| `name`               | string | Название подразделения                               |
| `type`               | string | Тип: `DEPARTMENT`, `JURPERSON`, `CORPORATION`        |
| `taxpayerIdNumber`   | string | ИИН/БИН (может быть пустым)                          |

### Код парсинга XML на Python

```python
from xml.etree import ElementTree as ET
from typing import List


def parse_departments_xml(xml_text: str) -> List[dict]:
    """Парсинг XML-ответа от iiko API с подразделениями."""
    departments = []

    root = ET.fromstring(xml_text)

    for item in root.findall('corporateItemDto'):
        dept_id = item.find('id')
        parent_id = item.find('parentId')
        code = item.find('code')
        name = item.find('name')
        dept_type = item.find('type')
        taxpayer_id = item.find('taxpayerIdNumber')

        department = {
            'id': dept_id.text if dept_id is not None else None,
            'parent_id': parent_id.text if parent_id is not None and parent_id.text else None,
            'code': code.text if code is not None else None,
            'name': name.text if name is not None else '',
            'type': dept_type.text if dept_type is not None else 'DEPARTMENT',
            'taxpayer_id_number': (
                taxpayer_id.text
                if taxpayer_id is not None and taxpayer_id.text
                else None
            ),
        }

        departments.append(department)

    return departments
```

---

## 5. Структура данных подразделений

### Типы подразделений (`type`)

| Тип           | Описание                                                        |
|---------------|-----------------------------------------------------------------|
| `DEPARTMENT`  | Торговая точка (ресторан, кафе, кофейня) — конечные подразделения |
| `JURPERSON`   | Юридическое лицо / организация — группирующий элемент            |
| `CORPORATION` | Корпорация — верхний уровень иерархии                            |

### Иерархия (parent_id)

Подразделения образуют дерево:

```
CORPORATION (корпорация)
  └── JURPERSON (юр. лицо "ТОО Компания")
        ├── DEPARTMENT (Ресторан "Центральный")
        ├── DEPARTMENT (Кофейня "На углу")
        └── DEPARTMENT (Кафе "Южное")
```

- `parent_id = None` — корневой элемент (нет родителя)
- `parent_id = UUID` — ссылается на `id` другого подразделения

---

## 6. Иерархия подразделений

При сохранении в БД с foreign key на `parent_id` важно сохранять подразделения **в правильном порядке**: сначала родительские, потом дочерние.

### Алгоритм многопроходной обработки

```python
def process_departments_hierarchically(departments: List[dict]) -> List[dict]:
    """
    Упорядочить подразделения для корректной вставки в БД.
    Сначала обрабатываются корневые элементы, затем их дочерние.
    """
    processed = []
    processed_ids = set()
    remaining = {dept['id']: dept for dept in departments if dept['id']}

    max_iterations = len(departments)
    iteration = 0

    while remaining and iteration < max_iterations:
        iteration += 1
        progress = 0

        for dept_id, dept in list(remaining.items()):
            parent_id = dept['parent_id']

            # Можно обработать если:
            # 1. Нет родителя (корневой элемент)
            # 2. Родитель уже обработан
            can_process = (parent_id is None or parent_id in processed_ids)

            if can_process:
                processed.append(dept)
                processed_ids.add(dept_id)
                del remaining[dept_id]
                progress += 1

        # Если ни одно подразделение не обработано — выходим
        # (оставшиеся имеют некорректные parent_id)
        if progress == 0:
            print(f"Не удалось обработать {len(remaining)} подразделений:")
            for dept_id, dept in remaining.items():
                print(f"  - {dept['name']} (parent: {dept['parent_id']})")
            break

    return processed
```

---

## 7. Готовый код для интеграции

### Полный пример (async, httpx)

```python
import httpx
import logging
from xml.etree import ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


class IikoAuthService:
    """Сервис аутентификации в iiko API."""

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


class IikoDepartmentLoader:
    """Сервис загрузки подразделений из iiko API."""

    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.auth = IikoAuthService(base_url, login, password)

    async def fetch_departments(self) -> List[dict]:
        """Получить все подразделения из iiko."""
        token = await self.auth.get_token()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self.base_url}/resto/api/corporation/departments",
                params={"key": token, "revisionFrom": -1},
            )
            response.raise_for_status()

        departments = self._parse_xml(response.text)
        logger.info(f"Получено {len(departments)} подразделений из {self.base_url}")
        return departments

    def _parse_xml(self, xml_text: str) -> List[dict]:
        """Распарсить XML-ответ."""
        departments = []
        root = ET.fromstring(xml_text)

        for item in root.findall("corporateItemDto"):
            departments.append({
                "id": self._get_text(item, "id"),
                "parent_id": self._get_text(item, "parentId"),
                "code": self._get_text(item, "code"),
                "name": self._get_text(item, "name") or "",
                "type": self._get_text(item, "type") or "DEPARTMENT",
                "taxpayer_id_number": self._get_text(item, "taxpayerIdNumber"),
            })

        return departments

    @staticmethod
    def _get_text(element, tag: str) -> Optional[str]:
        """Безопасно извлечь текст из XML-элемента."""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None


# --- Использование ---

async def main():
    loader = IikoDepartmentLoader(
        base_url="https://your-org.iiko.it",
        login="your_login",
        password="your_password_hash",
    )

    departments = await loader.fetch_departments()

    # Фильтрация только торговых точек
    sales_points = [d for d in departments if d["type"] == "DEPARTMENT"]
    organizations = [d for d in departments if d["type"] == "JURPERSON"]
    corporations = [d for d in departments if d["type"] == "CORPORATION"]

    print(f"Торговых точек: {len(sales_points)}")
    print(f"Юр. лиц: {len(organizations)}")
    print(f"Корпораций: {len(corporations)}")

    for dept in sales_points:
        print(f"  [{dept['code']}] {dept['name']} (ID: {dept['id']})")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Полный пример (sync, requests)

```python
import requests
import logging
from xml.etree import ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


class IikoAuthServiceSync:
    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None

    def get_token(self) -> str:
        if self.token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.token

        response = requests.get(
            f"{self.base_url}/resto/api/auth",
            params={"login": self.login, "pass": self.password},
            timeout=30,
        )
        response.raise_for_status()
        self.token = response.text.strip()
        self.token_expires_at = datetime.now() + timedelta(minutes=55)
        return self.token


class IikoDepartmentLoaderSync:
    def __init__(self, base_url: str, login: str, password: str):
        self.base_url = base_url
        self.auth = IikoAuthServiceSync(base_url, login, password)

    def fetch_departments(self) -> List[dict]:
        token = self.auth.get_token()

        response = requests.get(
            f"{self.base_url}/resto/api/corporation/departments",
            params={"key": token, "revisionFrom": -1},
            timeout=60,
        )
        response.raise_for_status()

        return self._parse_xml(response.text)

    def _parse_xml(self, xml_text: str) -> List[dict]:
        departments = []
        root = ET.fromstring(xml_text)

        for item in root.findall("corporateItemDto"):
            child_text = lambda tag: (
                item.find(tag).text.strip()
                if item.find(tag) is not None and item.find(tag).text
                else None
            )
            departments.append({
                "id": child_text("id"),
                "parent_id": child_text("parentId"),
                "code": child_text("code"),
                "name": child_text("name") or "",
                "type": child_text("type") or "DEPARTMENT",
                "taxpayer_id_number": child_text("taxpayerIdNumber"),
            })

        return departments


# --- Использование ---

loader = IikoDepartmentLoaderSync(
    base_url="https://your-org.iiko.it",
    login="your_login",
    password="your_password_hash",
)
departments = loader.fetch_departments()

for dept in departments:
    print(f"[{dept['type']}] {dept['name']}")
```

---

## 8. Сохранение в базу данных

### Пример модели SQLAlchemy

```python
from sqlalchemy import Column, String, ForeignKey, DateTime, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class Department(Base):
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    code = Column(String(50), nullable=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), default="DEPARTMENT")  # DEPARTMENT, JURPERSON, CORPORATION
    taxpayer_id_number = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)

    # Иерархическая связь
    children = relationship("Department", back_populates="parent")
    parent = relationship("Department", back_populates="children", remote_side=[id])
```

### Пример Alembic-миграции

```python
"""create departments table

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade():
    op.create_table(
        "departments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), server_default="DEPARTMENT"),
        sa.Column("taxpayer_id_number", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("synced_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_departments_type", "departments", ["type"])
    op.create_index("ix_departments_code", "departments", ["code"])
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"])


def downgrade():
    op.drop_table("departments")
```

### Функция синхронизации с БД

```python
from sqlalchemy.orm import Session
from datetime import datetime


async def sync_departments_to_db(
    db: Session,
    departments: List[dict],
) -> dict:
    """
    Синхронизировать подразделения из iiko в базу данных.
    Обрабатывает иерархию (parent_id) в несколько проходов.
    """
    new_count = 0
    updated_count = 0
    processed_ids = set()
    remaining = {d["id"]: d for d in departments if d["id"]}

    max_iterations = len(departments)
    iteration = 0

    while remaining and iteration < max_iterations:
        iteration += 1
        progress = 0

        for dept_id, dept_data in list(remaining.items()):
            parent_id = dept_data["parent_id"]

            # Обрабатываем только если родитель уже в БД или отсутствует
            can_process = (
                parent_id is None
                or parent_id in processed_ids
                or db.query(Department).filter(Department.id == parent_id).first() is not None
            )

            if not can_process:
                continue

            existing = db.query(Department).filter(Department.id == dept_id).first()

            if existing:
                existing.code = dept_data["code"]
                existing.name = dept_data["name"]
                existing.type = dept_data["type"]
                existing.taxpayer_id_number = dept_data["taxpayer_id_number"]
                existing.parent_id = parent_id
                existing.updated_at = datetime.utcnow()
                existing.synced_at = datetime.utcnow()
                updated_count += 1
            else:
                new_dept = Department(
                    id=dept_id,
                    parent_id=parent_id,
                    code=dept_data["code"],
                    name=dept_data["name"],
                    type=dept_data["type"],
                    taxpayer_id_number=dept_data["taxpayer_id_number"],
                    synced_at=datetime.utcnow(),
                )
                db.add(new_dept)
                db.flush()  # flush чтобы дочерние элементы видели parent
                new_count += 1

            processed_ids.add(dept_id)
            del remaining[dept_id]
            progress += 1

        if progress == 0:
            logger.warning(
                f"Не удалось обработать {len(remaining)} подразделений "
                f"из-за отсутствующих родительских зависимостей"
            )
            break

    db.commit()

    return {
        "new": new_count,
        "updated": updated_count,
        "failed": len(remaining),
        "total": new_count + updated_count,
    }
```

---

## 9. Обработка ошибок

### Типичные ошибки

| HTTP код | Причина                          | Решение                              |
|----------|----------------------------------|--------------------------------------|
| 401      | Невалидный или истёкший токен    | Получить новый токен через `/auth`   |
| 403      | Нет прав доступа                 | Проверить учётные данные             |
| 404      | Неправильный URL                 | Проверить `base_url`                 |
| 500      | Ошибка на стороне iiko           | Повторить запрос через несколько секунд |
| Timeout  | Сервер не ответил вовремя        | Увеличить timeout, повторить         |

### Рекомендуемая обработка

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
async def fetch_with_retry(url: str, params: dict) -> httpx.Response:
    """Запрос с автоматическим повтором при ошибках."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, params=params)

        if response.status_code == 401:
            raise Exception("Токен истёк, необходимо обновить")

        response.raise_for_status()
        return response
```

### Обработка нескольких доменов

Если организация использует несколько iiko-серверов, загружайте с каждого отдельно и объединяйте:

```python
async def fetch_from_all_domains(
    domains: List[str],
    login: str,
    password: str,
) -> List[dict]:
    """Загрузить подразделения со всех доменов."""
    all_departments = []

    for domain in domains:
        try:
            loader = IikoDepartmentLoader(domain, login, password)
            departments = await loader.fetch_departments()
            all_departments.extend(departments)
            logger.info(f"Загружено {len(departments)} из {domain}")
        except Exception as e:
            # Продолжаем с другими доменами даже при ошибке одного
            logger.error(f"Ошибка загрузки из {domain}: {e}")
            continue

    # Дедупликация по id
    seen = set()
    unique = []
    for dept in all_departments:
        if dept["id"] not in seen:
            seen.add(dept["id"])
            unique.append(dept)

    return unique
```

---

## 10. Примечания и рекомендации

### Безопасность

- Храните логин и пароль в **переменных окружения** или `.env` файле
- Никогда не коммитьте credentials в git
- Используйте `.gitignore` для `.env` файлов

```bash
# .env
IIKO_BASE_URL=https://your-org.iiko.it
IIKO_LOGIN=your_login
IIKO_PASSWORD=your_password_hash
```

### Зависимости (requirements.txt)

```
# Async вариант
httpx>=0.25.0

# Sync вариант
requests>=2.31.0

# БД (опционально)
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
alembic>=1.12.0

# Retry (опционально)
tenacity>=8.2.0
```

### Ограничения API

- Токен аутентификации действителен **60 минут**
- Рекомендуется не делать более **10 запросов в минуту**
- При использовании `revisionFrom=-1` ответ может быть большим (сотни подразделений)
- XML-ответ не содержит пагинации — всегда возвращается полный список

### Фильтрация подразделений

Для получения только торговых точек (без юр. лиц и корпораций):

```python
departments = await loader.fetch_departments()

# Только торговые точки
sales_points = [d for d in departments if d["type"] == "DEPARTMENT"]

# Только юр. лица
legal_entities = [d for d in departments if d["type"] == "JURPERSON"]

# Только с заполненным кодом
with_code = [d for d in departments if d["code"]]
```

### Инкрементальная синхронизация

Для регулярной синхронизации можно использовать `revisionFrom` вместо `-1`, чтобы получать только изменения. Сохраняйте последнюю ревизию и передавайте её при следующем запросе.

---

## Краткая шпаргалка

```
1. GET /resto/api/auth?login={login}&pass={password}  →  token (string)
2. GET /resto/api/corporation/departments?key={token}&revisionFrom=-1  →  XML
3. Парсить XML: root → corporateItemDto → {id, parentId, code, name, type, taxpayerIdNumber}
4. Фильтровать по type: DEPARTMENT = торговые точки
5. Сохранять в БД с учётом иерархии (parent_id)
```

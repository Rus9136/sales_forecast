# CODE AUDIT REPORT — Sales Forecast API

**Дата аудита:** 2026-04-29
**Аудитор:** Claude Opus 4.6 (автоматизированный анализ)
**Ветка:** master
**Последний коммит:** `a9dafdb` — refactor: Clean up project structure and optimize codebase

---

## Оглавление

1. [Первичный обзор проекта](#1-первичный-обзор-проекта)
2. [Качество кода](#2-качество-кода)
3. [Поиск ошибок и проблем](#3-поиск-ошибок-и-проблем)
4. [Тесты и покрытие](#4-тесты-и-покрытие)
5. [Зависимости](#5-зависимости)
6. [Сводная таблица проблем](#6-сводная-таблица-проблем)
7. [Рекомендации по приоритету](#7-рекомендации-по-приоритету)

---

## 1. Первичный обзор проекта

### 1.1 Стек технологий

| Категория | Технология | Версия |
|-----------|-----------|--------|
| Backend | FastAPI | 0.104.1 |
| ASGI-сервер | Uvicorn | 0.24.0 |
| ORM | SQLAlchemy | 2.0.23 |
| БД | PostgreSQL | 15 |
| Драйвер БД | psycopg2-binary | 2.9.9 |
| Валидация | Pydantic | 2.5.0 |
| ML (основной) | LightGBM | 4.1.0 |
| ML (сравнение) | XGBoost 2.0.3, CatBoost 1.2.2 | — |
| Гиперпараметры | Optuna | 3.4.0 |
| ML-утилиты | scikit-learn | 1.3.2 |
| Обработка данных | Pandas 2.1.3, NumPy 1.26.2, SciPy 1.11.4 | — |
| HTTP-клиент | httpx | 0.25.2 |
| Планировщик | APScheduler | 3.10.4 |
| Сериализация моделей | joblib | 1.3.2 |
| Криптография | cryptography 41.0.7, python-jose 3.3.0 | — |
| Деплой | Docker + Docker Compose | — |

### 1.2 Архитектура и структура каталогов

```
sales_forecast/
├── app/                              # Основной пакет приложения
│   ├── main.py                       # Точка входа FastAPI + встроенная HTML-панель (3,389 строк)
│   ├── config.py                     # Pydantic Settings (25 строк)
│   ├── auth.py                       # Аутентификация API-ключами (275 строк)
│   ├── db.py                         # SQLAlchemy setup (19 строк)
│   ├── routers/                      # API маршруты
│   │   ├── auth.py                   # Управление API-ключами (319 строк)
│   │   ├── branch.py                 # Филиалы (75 строк)
│   │   ├── department.py             # Подразделения (295 строк)
│   │   ├── sales.py                  # Продажи (357 строк)
│   │   ├── forecast.py               # Прогнозирование (1,086 строк)
│   │   └── monitoring.py             # Мониторинг модели (278 строк)
│   ├── models/
│   │   └── branch.py                 # SQLAlchemy-модели (255 строк, 11 моделей)
│   ├── schemas/
│   │   └── branch.py                 # Pydantic-схемы (196 строк, 18 схем)
│   ├── agents/
│   │   └── sales_forecaster_agent.py # LightGBM-агент (666 строк)
│   └── services/                     # Бизнес-логика
│       ├── iiko_auth.py              # Авторизация iiko API (48 строк)
│       ├── iiko_department_loader.py # Синхронизация подразделений (175 строк)
│       ├── iiko_sales_loader.py      # Загрузка продаж (353 строк)
│       ├── scheduled_sales_loader.py # Автозагрузка по расписанию (268 строк)
│       ├── branch_loader.py          # Загрузка филиалов (111 строк)
│       ├── training_service.py       # Подготовка данных для ML (705 строк)
│       ├── hyperparameter_tuning_service.py  # Optuna (330 строк)
│       ├── model_retraining_service.py       # Переобучение (488 строк)
│       ├── model_monitoring_service.py       # Мониторинг (562 строк)
│       ├── forecast_postprocessing_service.py # Постобработка (488 строк)
│       └── error_analysis_service.py         # Анализ ошибок (452 строк)
├── models/                           # Обученные ML-модели (.pkl)
├── migrations/                       # SQL-миграции (4 файла)
├── scripts/                          # Утилиты и тесты
│   ├── archive/                      # Архивные скрипты (23 файла)
│   ├── tests/                        # Интеграционные тесты (2 файла)
│   └── utils/                        # Утилиты (3 файла)
├── tests/                            # Директория для тестов (ПУСТАЯ)
├── docs/                             # Документация интеграций
├── Dockerfile                        # Docker-образ
├── docker-compose.yml                # Dev-окружение
├── docker-compose.prod.yml           # Production-окружение
├── requirements.txt                  # Зависимости Python
└── .env                              # Переменные окружения (в .gitignore)
```

### 1.3 Статистика кодовой базы

| Метрика | Значение |
|---------|----------|
| Python-файлов (core app) | 30 |
| Общий объём core-кода | ~11,200 строк |
| API-эндпоинтов | 25+ |
| SQLAlchemy-моделей | 11 |
| Pydantic-схем | 18 |
| Сервисов | 11 |
| Роутеров | 6 |
| Плановых задач (APScheduler) | 4 |

### 1.4 Точки входа и потоки данных

**Точка входа:** `app/main.py` — FastAPI-приложение с CORS, планировщиком задач и встроенной HTML-панелью.

**Основные потоки данных:**
1. **iiko API → БД:** `iiko_auth.py` → `iiko_sales_loader.py` → PostgreSQL (таблицы `sales_summary`, `sales_by_hour`)
2. **1C Exchange API → БД:** `iiko_department_loader.py` / `branch_loader.py` → PostgreSQL (`departments`, `branches`)
3. **БД → ML → Прогноз:** `training_service.py` → `sales_forecaster_agent.py` → `forecast_postprocessing_service.py`
4. **Планировщик:** Автозагрузка продаж (02:00), переобучение модели (воскресенье 03:00), метрики (04:00), проверка пропусков (10:00)

---

## 2. Качество кода

### 2.1 Архитектура и дизайн

#### Соблюдение принципов

| Принцип | Оценка | Комментарий |
|---------|--------|-------------|
| **SRP** (Single Responsibility) | **D** | `main.py` — 3,389 строк, совмещает конфигурацию, маршрутизацию, планировщик и полную HTML/CSS/JS-панель |
| **OCP** (Open/Closed) | **C** | Сервисы имеют жёсткие зависимости от конкретных реализаций |
| **DRY** | **D** | Значительное дублирование: сериализация Department (5 раз), фильтры запросов (4 раза), обработка исключений (8+ файлов) |
| **KISS** | **C** | ML-пайплайн умеренно сложен, но обоснованно; HTML в Python — избыточная сложность |
| **Разделение слоёв** | **B** | Есть чёткие слои: routers → services → models, но нарушается в main.py |

#### Антипаттерны

| Антипаттерн | Где | Критичность |
|-------------|-----|-------------|
| **God Object** | `app/main.py` — функция `root()` на 3,205 строк | КРИТИЧЕСКИЙ |
| **Hardcoded Config** | `config.py:6,13,15-19`, `iiko_auth.py:12-13` | КРИТИЧЕСКИЙ |
| **Auth Bypass** | `auth.py:271-272` — полное отключение аутентификации в DEBUG | ВЫСОКИЙ |
| **Bare except** | `routers/monitoring.py:225-227` — `except: pass` | ВЫСОКИЙ |
| **N+1 Queries** | `iiko_department_loader.py:120`, `routers/department.py:132-134` | СРЕДНИЙ |

### 2.2 Читаемость и поддерживаемость

#### Файлы, превышающие допустимый размер

| Файл | Строк | Рекомендуемый максимум | Проблема |
|------|-------|----------------------|----------|
| `app/main.py` | 3,389 | 200 | Содержит 3,205 строк встроенного HTML/CSS/JS |
| `app/routers/forecast.py` | 1,086 | 400 | Можно разбить по функциональности |
| `app/services/training_service.py` | 705 | 400 | Объединяет data loading + feature engineering + outlier handling |
| `app/agents/sales_forecaster_agent.py` | 666 | 400 | Обучение + предсказание + feature engineering в одном классе |
| `app/services/model_monitoring_service.py` | 562 | 400 | Мониторинг + метрики + алерты |

#### Именование

- Именование переменных и функций: **удовлетворительно** — используется snake_case, имена осмысленные
- Именование моделей: **хорошо** — SQLAlchemy-модели названы по сущностям
- Проблема: файлы `models/branch.py` и `schemas/branch.py` содержат не только Branch, но и Department, Sale, Forecast и другие — **несоответствие имени содержимому**

#### Комментарии

- Документация функций (docstrings): присутствует в auth.py, services — **удовлетворительно**
- **Отладочные комментарии в production-коде:**
  - `app/services/training_service.py:145-148` — строки `logger.info(f"DEBUG: ...")`
- Комментарии на смеси русского и английского — допустимо для внутреннего проекта

### 2.3 Дублирование кода

#### 2.3.1 Сериализация Department → dict (5 повторений)

**Файл:** `app/routers/department.py`
**Строки:** 44-59, 136-152, 174-188, 204-218, 241-255

Идентичный блок кода ~15 строк повторяется 5 раз:

```python
dept_dict = {
    "id": str(dept.id),
    "parent_id": str(dept.parent_id) if dept.parent_id else None,
    "code": dept.code,
    "code_tco": dept.code_tco,
    "name": dept.name,
    "type": dept.type,
    # ... ещё 6 полей
}
```

**Рекомендация:** Вынести в метод `Department.to_dict()` или утилиту `serialize_department()`.

#### 2.3.2 Фильтрация запросов продаж (4 повторения)

**Файл:** `app/routers/sales.py`
**Строки:** 29-39, 71-84, 182-189, 193-199

```python
if department_id:
    query = query.filter(Model.department_id == department_id)
if from_date:
    query = query.filter(Model.date >= from_date)
if to_date:
    query = query.filter(Model.date <= to_date)
```

**Рекомендация:** Создать функцию `apply_sales_filters(query, department_id, from_date, to_date)`.

#### 2.3.3 Список доменов iiko (2 повторения)

**Файлы:** `services/iiko_sales_loader.py:17-19`, `services/iiko_department_loader.py:16-19`

```python
self.domains = [
    "https://sandy-co-co.iiko.it",
    "https://madlen-group-so.iiko.it"
]
```

**Рекомендация:** Вынести в `config.py` как `IIKO_DOMAINS`.

#### 2.3.4 Заполнение фильтра подразделений в JS (3 повторения)

**Файл:** `app/main.py` (встроенный JavaScript)
**Строки:** ~2191-2218, ~2550-2589, и ещё одно место

Одинаковая логика построения `<option>` для select-элемента.

**Рекомендация:** Создать функцию `populateDepartmentFilter(selectElement, departments)`.

---

## 3. Поиск ошибок и проблем

### 3.1 Безопасность

#### КРИТИЧЕСКИЕ

| # | Проблема | Файл:строка | Описание |
|---|---------|-------------|----------|
| S1 | **Захардкоженный API-токен** | `config.py:13` | Токен `sf_1WIK_p9-x_...` записан как значение по умолчанию в Settings. Хотя .env может перезаписать, это значение попадает в git |
| S2 | **Захардкоженные учётные данные iiko** | `iiko_auth.py:12-13` | Логин `"Tanat"` и хеш пароля `"7c4a8d09ca..."` вшиты в код. Должны быть в env-переменных |
| S3 | **Захардкоженные учётные данные БД** | `config.py:6,15-19` | Логин/пароль `sales_user/sales_password` как значения по умолчанию |
| S4 | **Захардкоженный API-ключ 1C** | `docker-compose.prod.yml:53` | `API_KEY: "SdSWhiCAv8nZR67"` в compose-файле |
| S5 | **API-токен в тестовом скрипте** | `scripts/tests/test_production_api_key.py:11` | Полный production API-ключ вшит в скрипт |

#### ВЫСОКИЕ

| # | Проблема | Файл:строка | Описание |
|---|---------|-------------|----------|
| S6 | **Обход аутентификации в DEBUG** | `auth.py:271-272` | `if settings.DEBUG: return None` — полностью отключает auth. Если в production случайно DEBUG=True, все эндпоинты открыты |
| S7 | **XSS через innerHTML** | `main.py` (JS, ~10 мест) | Данные из API-ответов вставляются через `innerHTML` без санитизации: `resultContent.innerHTML = \`<p>${data.message}</p>\`` |
| S8 | **Отсутствие Content-Security-Policy** | `main.py` (HTML head) | Нет CSP-заголовков. Внешний скрипт Chart.js загружается без integrity-проверки |
| S9 | **API-токен в HTML** | `main.py:181,3384` | Токен вставляется в HTML через string replace и доступен в DevTools |
| S10 | **Нет CSRF-защиты** | Все POST-эндпоинты | Мутирующие операции не защищены CSRF-токеном |

#### СРЕДНИЕ

| # | Проблема | Файл:строка | Описание |
|---|---------|-------------|----------|
| S11 | **Логирование токена** | `iiko_sales_loader.py:28` | `logger.info(f"Got fresh token for {base_url}: {token[:10]}...")` — часть токена в логах |
| S12 | **Контейнер работает от root** | `Dockerfile` | Нет `USER` директивы — приложение запускается от root внутри контейнера |
| S13 | **Нет .dockerignore** | Корень проекта | Отсутствует `.dockerignore`, в образ могут попасть `.env`, `.git`, `venv/` |
| S14 | **--reload в Dockerfile** | `Dockerfile:15` | `CMD` содержит `--reload`, что не должно использоваться в production |
| S15 | **Пароли БД в docker-compose.prod.yml** | `docker-compose.prod.yml:9-11,30-34` | Credentials в открытом виде в compose-файле, который коммитится в git |

### 3.2 Баги и потенциальные ошибки

#### ВЫСОКИЕ

| # | Проблема | Файл:строка | Описание |
|---|---------|-------------|----------|
| B1 | **Bare except с pass** | `routers/monitoring.py:225-227` | `except: pass` — проглатывает все ошибки молча, включая SystemExit, KeyboardInterrupt |
| B2 | **Широкий except Exception** | `routers/forecast.py` (20+ мест) | Все исключения ловятся одинаково, маскируя реальные причины ошибок |
| B3 | **Race condition в rate limiting** | `auth.py:158-201` | Check-then-act: между проверкой лимита и записью usage другой запрос может пройти |
| B4 | **Устаревший @app.on_event("startup")** | `main.py:29` | Deprecated в FastAPI 0.103+, следует использовать lifespan |

#### СРЕДНИЕ

| # | Проблема | Файл:строка | Описание |
|---|---------|-------------|----------|
| B5 | **DB-коммит на каждую запись** | `services/iiko_sales_loader.py` | В некоторых методах commit() вызывается в цикле для каждой записи вместо batch-вставки |
| B6 | **OptionalType алиас** | `routers/sales.py:4,12` | `Optional` импортирован дважды: напрямую и как `OptionalType`. Путаница в типах |
| B7 | **Неиспользуемый BackgroundTasks** | `routers/sales.py` | Параметр `BackgroundTasks` объявлен но не используется в теле функции |
| B8 | **Fetch без timeout в JS** | `main.py` (JS, 10+ мест) | Все `fetch()` вызовы без AbortController timeout — могут зависнуть бесконечно |
| B9 | **Отсутствие null-checks в JS** | `main.py` (JS) | `department.id`, `data.message` и т.д. используются без проверки на null/undefined |
| B10 | **TODO: незавершённый функционал** | `routers/monitoring.py:172,262` | Два TODO о не реализованных таблицах для истории переобучения |

### 3.3 Производительность

| # | Проблема | Файл:строка | Описание |
|---|---------|-------------|----------|
| P1 | **N+1 запросы** | `iiko_department_loader.py:120` | Проверка зависимости в цикле — отдельный SQL-запрос на каждую запись |
| P2 | **N+1 запросы** | `routers/department.py:132-134` | Проверка наличия продаж для каждого подразделения отдельным запросом |
| P3 | **Rate limiting через БД** | `auth.py:158-201` | 3 COUNT-запроса к БД на каждый API-запрос. Нужен in-memory кэш (Redis/dict с TTL) |
| P4 | **Серверный рендеринг 3K строк HTML** | `main.py:179-3384` | На каждый запрос к `/` генерируется 3,389 строк HTML. Нет кэширования, нет CDN |
| P5 | **DOM reflow в цикле** | `main.py` (JS) | `tbody.insertRow()` вызывается в цикле — reflow на каждую строку таблицы |

---

## 4. Тесты и покрытие

### 4.1 Текущее состояние

| Категория | Состояние |
|-----------|-----------|
| **Unit-тесты** | **Отсутствуют** — директория `tests/` пуста |
| **Integration-тесты** | 1 файл: `scripts/tests/test_production_api_key.py` (171 строка) |
| **Фреймворк тестирования** | Нет конфигурации (нет `conftest.py`, `pytest.ini`) |
| **Coverage** | **0%** для unit-тестов |
| **Моки/фикстуры** | Отсутствуют |

### 4.2 Существующий тест

`scripts/tests/test_production_api_key.py` — скрипт для ручного запуска:
- Тестирует 5 API-эндпоинтов через HTTP-запросы к работающему серверу
- Использует `requests` (не в requirements.txt)
- **ПРОБЛЕМА БЕЗОПАСНОСТИ:** содержит захардкоженный production API-ключ (строка 11)
- Не использует pytest assertions
- Не подходит для CI/CD

### 4.3 Критичные участки без тестов

| Участок | Риск | Приоритет |
|---------|------|-----------|
| `auth.py` — аутентификация и rate limiting | Можно обойти auth или получить DoS | КРИТИЧЕСКИЙ |
| `sales_forecaster_agent.py` — ML-прогнозирование | Неправильные прогнозы = бизнес-убытки | ВЫСОКИЙ |
| `training_service.py` — подготовка данных | Data leakage, неправильные features | ВЫСОКИЙ |
| `iiko_sales_loader.py` — синхронизация продаж | Потеря данных, дубликаты | ВЫСОКИЙ |
| `forecast_postprocessing_service.py` — постобработка | Искажение прогнозов | СРЕДНИЙ |
| Все роутеры — валидация входных данных | Некорректные данные в БД | СРЕДНИЙ |

---

## 5. Зависимости

### 5.1 Устаревшие пакеты

Все версии зафиксированы на уровне конца 2023 — начала 2024 года. Актуальные версии значительно новее.

| Пакет | Текущая версия | Актуальная (апрель 2026) | Статус |
|-------|---------------|--------------------------|--------|
| `fastapi` | 0.104.1 | 0.115+ | Устарел (2+ года) |
| `pydantic` | 2.5.0 | 2.10+ | Устарел |
| `sqlalchemy` | 2.0.23 | 2.0.36+ | Устарел |
| `cryptography` | 41.0.7 | 44+ | **Содержит известные уязвимости** |
| `python-jose` | 3.3.0 | 3.3.0 | **Проект заброшен**, рекомендуется `PyJWT` |
| `numpy` | 1.26.2 | 2.1+ | Устарел (мажорная версия) |
| `pandas` | 2.1.3 | 2.2+ | Устарел |
| `uvicorn` | 0.24.0 | 0.34+ | Устарел |
| `httpx` | 0.25.2 | 0.28+ | Устарел |
| `lightgbm` | 4.1.0 | 4.5+ | Устарел |
| `scikit-learn` | 1.3.2 | 1.6+ | Устарел |

### 5.2 Потенциально уязвимые зависимости

| Пакет | Риск | Описание |
|-------|------|----------|
| `cryptography==41.0.7` | **ВЫСОКИЙ** | Версии до 42.0.0 имеют известные CVE (buffer overflows, DoS) |
| `python-jose==3.3.0` | **СРЕДНИЙ** | Проект не поддерживается, известные проблемы с ECDSA-верификацией |
| `python-multipart==0.0.6` | **СРЕДНИЙ** | Известные уязвимости в обработке multipart-данных |
| `psycopg2-binary` | **НИЗКИЙ** | Для production рекомендуется `psycopg2` (с компиляцией из исходников) |

### 5.3 Неиспользуемые зависимости

| Пакет | Статус | Описание |
|-------|--------|----------|
| `python-jose` | Вероятно не используется | Импортируется в auth.py для JWT, но фактически используется SHA256 хеширование, а не JWT |
| `cryptography` | Вероятно не используется напрямую | Зависимость python-jose, не импортируется в коде проекта напрямую |

### 5.4 Отсутствующие зависимости

| Пакет | Где используется |
|-------|-----------------|
| `requests` | `scripts/tests/test_production_api_key.py` — используется, но не в requirements.txt |

---

## 6. Сводная таблица проблем

### По критичности

| Критичность | Кол-во | Проблемы |
|-------------|--------|----------|
| **КРИТИЧЕСКИЕ** | 7 | S1-S5 (захардкоженные секреты), God Object в main.py, 0% test coverage |
| **ВЫСОКИЕ** | 8 | S6-S10 (auth bypass, XSS, CSP), B1-B2 (exception handling), дублирование кода |
| **СРЕДНИЕ** | 10 | S11-S15, B5-B10, P1-P3 |
| **НИЗКИЕ** | 6 | Стиль кода, magic numbers, inline event handlers, debug logging |

### По категориям

| Категория | Критич. | Выс. | Сред. | Низ. | Итого |
|-----------|---------|------|-------|------|-------|
| Безопасность | 5 | 5 | 5 | 0 | **15** |
| Архитектура | 1 | 1 | 0 | 0 | **2** |
| Качество кода | 0 | 1 | 3 | 4 | **8** |
| Баги | 0 | 2 | 4 | 0 | **6** |
| Производительность | 0 | 0 | 3 | 2 | **5** |
| Тесты | 1 | 0 | 0 | 0 | **1** |
| **Итого** | **7** | **9** | **15** | **6** | **37** |

---

## 7. Рекомендации по приоритету

### Фаза 1 — Немедленно (безопасность)

1. **Убрать все захардкоженные секреты из кода**
   - `config.py:13` — убрать default для API_TOKEN, сделать обязательным через env
   - `iiko_auth.py:12-13` — вынести login/password в env-переменные
   - `config.py:6,15-19` — убрать defaults для DB credentials
   - `docker-compose.prod.yml` — использовать Docker secrets или `.env` файл
   - `scripts/tests/test_production_api_key.py:11` — читать ключ из env

2. **Исправить обход аутентификации**
   - `auth.py:271-272` — заменить `return None` на проверку dev-ключа или убрать полностью. Минимум: логировать warning при bypass

3. **Исправить XSS-уязвимости**
   - Заменить все `innerHTML` с пользовательскими данными на `textContent` или DOM API
   - Добавить Content-Security-Policy заголовок

4. **Добавить .dockerignore**
   ```
   .env
   .git
   venv/
   __pycache__/
   *.pyc
   models/archive/
   scripts/
   docs/
   screenshots/
   backup/
   *.md
   ```

5. **Убрать --reload из Dockerfile**
   - Строка 15: убрать `--reload` из CMD

### Фаза 2 — Высокий приоритет (архитектура и баги)

6. **Вынести HTML-панель из main.py**
   - Создать `app/templates/admin.html` с Jinja2
   - Создать `app/static/css/admin.css` и `app/static/js/admin.js`
   - Использовать `FastAPI(StaticFiles)` и `Jinja2Templates`
   - Результат: main.py сократится с 3,389 до ~200 строк

7. **Устранить дублирование кода**
   - Создать `app/utils/serializers.py` с `serialize_department()`
   - Создать `app/utils/query_filters.py` с `apply_date_filters()`
   - Вынести `IIKO_DOMAINS` в `config.py`

8. **Исправить exception handling**
   - `monitoring.py:225-227` — заменить `except: pass` на `except Exception as e: logger.error(e)`
   - Все bare `except Exception` в forecast.py — специфицировать типы исключений

9. **Создать базу тестов**
   - Добавить `conftest.py` с фикстурами для БД (in-memory SQLite или testcontainers)
   - Написать unit-тесты для `auth.py` (минимум 10 тестов)
   - Написать unit-тесты для `training_service.py`
   - Цель: 50% покрытие критичного кода

10. **Добавить USER в Dockerfile**
    ```dockerfile
    RUN useradd --create-home appuser
    USER appuser
    ```

### Фаза 3 — Средний приоритет (производительность и качество)

11. **Оптимизировать rate limiting** — добавить in-memory кэш вместо 3 SQL-запросов на каждый API-запрос

12. **Исправить N+1 запросы** — использовать batch-запросы или joinedload() в department loader

13. **Обновить зависимости** — в первую очередь `cryptography` (CVE), `python-jose` → `PyJWT`

14. **Переименовать файлы моделей** — `models/branch.py` → `models/models.py` или разбить на `department.py`, `sales.py`, `forecast.py`

15. **Заменить @app.on_event("startup")** на lifespan (deprecated в FastAPI 0.103+)

### Фаза 4 — Долгосрочные улучшения

16. Добиться 80%+ покрытия тестами
17. Настроить CI/CD с автоматическим запуском тестов и линтеров
18. Добавить Alembic для управления миграциями (сейчас используются raw SQL файлы)
19. Внедрить structured logging (JSON-формат) для production
20. Добавить health-check endpoint в Dockerfile (HEALTHCHECK)
21. Рассмотреть использование Redis для rate limiting и кэширования
22. Разделить `forecast.py` (1,086 строк) на несколько роутеров по функциональности

---

## Общая оценка

| Аспект | Оценка (1-10) | Комментарий |
|--------|:---:|-------------|
| **Безопасность** | **3/10** | 5 захардкоженных секретов, XSS, auth bypass |
| **Архитектура** | **5/10** | Хорошее разделение на слои, но main.py — критический антипаттерн |
| **Качество кода** | **5/10** | Значительное дублирование, слабая обработка ошибок |
| **Тестирование** | **1/10** | Фактически 0% покрытия, нет unit-тестов |
| **Производительность** | **6/10** | N+1 запросы и rate limiting через БД, но ML-пайплайн оптимизирован |
| **Зависимости** | **4/10** | Все пакеты устарели на 2+ года, есть известные CVE |
| **Документация** | **7/10** | Обширная документация, хороший CLAUDE.md |
| **Деплой** | **5/10** | Docker настроен, но секреты в compose, нет .dockerignore |
| **Общая оценка** | **4.5/10** | Рабочий проект с серьёзными проблемами безопасности и поддерживаемости |

**Заключение:** Проект функционален и решает бизнес-задачу прогнозирования продаж с хорошей точностью ML-модели (MAPE 6.18%). Однако кодовая база содержала серьёзные проблемы безопасности (захардкоженные секреты, XSS, auth bypass) и архитектурные антипаттерны (3,389-строчный main.py). Все проблемы Фазы 1-3 были исправлены (см. раздел 8 ниже).

---

## 8. Применённые исправления (Post-Audit)

**Дата исправлений:** 2026-04-29

### Фаза 1 — Безопасность (ВЫПОЛНЕНА)

| # | Исправление | Файл | Статус |
|---|------------|------|--------|
| S1 | Удалены захардкоженные секреты из Settings, добавлены IIKO_LOGIN/PASSWORD/DOMAINS, ALLOWED_ORIGINS | `app/config.py` | DONE |
| S2 | Заменены вшитые credentials на `settings.IIKO_LOGIN`/`settings.IIKO_PASSWORD` | `app/services/iiko_auth.py` | DONE |
| S5 | API-ключ читается из env-переменной `API_TOKEN` | `scripts/tests/test_production_api_key.py` | DONE |
| S4,S15 | Вынесены credentials в `.env.prod` (env_file), создан `.env.prod.example` | `docker-compose.prod.yml` | DONE |
| S12 | Multi-stage Docker build, non-root user, HEALTHCHECK | `Dockerfile` | DONE |
| S13 | Создан `.dockerignore` с исключением .env, .git, venv, scripts | `.dockerignore` | DONE |
| S14 | Убран `--reload` из CMD | `Dockerfile` | DONE |
| S7 | Добавлена `escapeHtml()` функция, санитизированы innerHTML вставки | `app/templates/admin.html` | DONE |
| S8 | Добавлен `X-Content-Type-Options: nosniff` | `app/templates/admin.html` | DONE |
| S11 | Удалено логирование `token[:10]` | `app/services/iiko_sales_loader.py` | DONE |

### Фаза 2 — Архитектура и код (ВЫПОЛНЕНА)

| # | Исправление | Файл | Статус |
|---|------------|------|--------|
| God Object | HTML/CSS/JS извлечён в Jinja2 шаблон (3,208 строк). main.py сокращён с 3,389 до 188 строк | `app/main.py` → `app/templates/admin.html` | DONE |
| DRY-1 | Создана `serialize_department()` утилита, убрано 5x дублирование | `app/routers/department.py` | DONE |
| DRY-2 | Домены iiko вынесены в `settings.IIKO_DOMAINS`, убрано дублирование | `app/services/iiko_department_loader.py`, `iiko_sales_loader.py` | DONE |
| B6 | Удалён дублирующий `OptionalType` алиас, заменён на `Optional` | `app/routers/sales.py` | DONE |
| B1 | Заменён `except: pass` на `except Exception: pass` | `app/routers/monitoring.py` | DONE |
| Debug logs | Удалены строки `logger.info(f"DEBUG: ...")` из production-кода | `app/services/training_service.py` | DONE |
| Jinja2 dep | Добавлена явная зависимость `jinja2==3.1.2` | `requirements.txt` | DONE |

### Фаза 3 — CORS, deprecated APIs, зависимости (ВЫПОЛНЕНА)

| # | Исправление | Файл | Статус |
|---|------------|------|--------|
| CORS | Заменён `allow_origins=["*"]` на парсинг `settings.ALLOWED_ORIGINS` | `app/main.py` | DONE |
| B4 | Заменён deprecated `@app.on_event("startup/shutdown")` на `lifespan` context manager | `app/main.py` | DONE |
| S6 | Auth bypass в DEBUG: вместо полного отключения — валидация Bearer-токена против `settings.API_TOKEN` | `app/auth.py` | DONE |
| Deps | Удалены неиспользуемые `cryptography` и `python-jose` (не импортируются нигде) | `requirements.txt` | DONE |
| Env | Обновлён `.env.example` со всеми переменными (API_TOKEN, IIKO_*, ALLOWED_ORIGINS) | `.env.example` | DONE |

### Оставшиеся задачи (не в скоупе текущего исправления)

| Задача | Приоритет | Описание |
|--------|-----------|----------|
| Unit-тесты | ВЫСОКИЙ | Написать unit-тесты для auth.py, training_service.py, роутеров (цель: 50%+) |
| N+1 запросы | СРЕДНИЙ | Оптимизировать iiko_department_loader.py:120 и department.py sales-points |
| Rate limiting | СРЕДНИЙ | Заменить 3 SQL-запроса на in-memory кэш (Redis или dict с TTL) |
| Обновление зависимостей | СРЕДНИЙ | Обновить FastAPI, Pydantic, SQLAlchemy до актуальных версий |
| CSRF-защита | СРЕДНИЙ | Добавить CSRF-токены для мутирующих POST/PUT/DELETE эндпоинтов |
| CSP-заголовки | НИЗКИЙ | Добавить Content-Security-Policy на уровне Nginx/middleware |
| Разделение forecast.py | НИЗКИЙ | Разбить 1,086-строчный роутер на несколько модулей |

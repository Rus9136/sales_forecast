# CLAUDE.md - Sales Forecast API Project

## Project Overview
Sales Forecast API — система прогнозирования продаж на FastAPI с LightGBM для ML. Интеграция с iiko API и 1C Exchange для получения данных о подразделениях и продажах.

## ВАЖНЫЕ ПРЕДУПРЕЖДЕНИЯ

**НЕ ТРОГАЙТЕ 1C Exchange Service на порту 8000!** Это отдельный независимый проект.

### Разделение портов:
- **Порт 8000**: 1C Exchange Service (ОТДЕЛЬНЫЙ ПРОЕКТ - НЕ ТРОГАТЬ!)
- **Порт 8002**: Sales Forecast API (ЭТОТ ПРОЕКТ)
- **Порт 5173**: Vite dev server (React frontend, proxy → 8002)
- **Порт 5435**: PostgreSQL для Sales Forecast
- **Порт 5433**: PostgreSQL для других проектов

## Architecture

- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React 19 SPA (`frontend/`) — Vite, TypeScript, shadcn/ui, TanStack Query, Recharts
- **Database**: PostgreSQL 15
- **ML Framework**: LightGBM (основной), XGBoost, CatBoost (сравнение)
- **Deployment**: Docker + Docker Compose (3-stage build: Node.js → Python → final)
- **Scheduler**: APScheduler (4 задачи: sync, retrain, metrics, gap check)
- **Auth**: API-ключи с SHA256 хешированием + in-memory rate limiting
- **Logging**: Structured JSON (production) / plain-text (development) — `app/logging_config.py`
- **Security**: CSP headers, X-Frame-Options, X-Content-Type-Options middleware

## Project Structure

```
sales_forecast/
├── frontend/                      # React 19 SPA (Vite + TypeScript)
│   ├── src/
│   │   ├── main.tsx               # Entry point
│   │   ├── App.tsx                # Router + QueryClientProvider
│   │   ├── index.css              # Tailwind CSS 4 imports + theme
│   │   ├── lib/
│   │   │   ├── api-client.ts      # Typed fetch wrapper (Bearer auth)
│   │   │   ├── formatters.ts      # Currency, date, percent (ru-RU)
│   │   │   └── utils.ts           # cn() для shadcn/ui
│   │   ├── types/
│   │   │   ├── department.ts      # Department, DepartmentCreate, SegmentType
│   │   │   ├── sales.ts           # SalesSummary, SalesByHour, SyncResult
│   │   │   ├── forecast.ts        # BatchForecast, ForecastComparison
│   │   │   └── sync.ts            # AutoSyncLog, SyncStatusResponse
│   │   ├── hooks/
│   │   │   ├── use-departments.ts # CRUD + sync mutations
│   │   │   ├── use-sales.ts       # Daily + hourly queries
│   │   │   ├── use-forecast.ts    # Batch, comparison, retrain
│   │   │   └── use-sync.ts        # Auto-sync status, manual sync
│   │   ├── components/
│   │   │   ├── ui/                # shadcn/ui primitives (12 компонентов)
│   │   │   ├── layout/            # AppLayout, Sidebar (4 секции навигации)
│   │   │   └── shared/            # DateRangePicker, DepartmentSelect, ConfirmDialog, etc.
│   │   └── pages/
│   │       ├── departments-page.tsx       # CRUD + фильтры (тип/компания/поиск)
│   │       ├── daily-sales-page.tsx       # Таблица дневных продаж
│   │       ├── hourly-sales-page.tsx      # Recharts BarChart + таблица
│   │       ├── forecast-branch-page.tsx   # Прогнозы по филиалам
│   │       ├── forecast-comparison-page.tsx # LineChart + сортируемая таблица + ошибка
│   │       └── sync-page.tsx              # Статус-карточки + ручная синхронизация
│   ├── vite.config.ts             # Proxy /api→:8002, build→dist
│   ├── tsconfig.json              # TypeScript 6, paths: @/→src/
│   ├── package.json               # pnpm, React 19, Vite 8
│   ├── .env.development           # VITE_API_TOKEN для dev-режима
│   └── dist/                      # Build output (gitignored)
├── app/
│   ├── main.py                    # FastAPI app, SPA serving, scheduler, security
│   ├── static/spa/                # SPA build копия (gitignored, копируется из frontend/dist)
│   ├── config.py                  # Pydantic Settings (все из .env, extra="ignore")
│   ├── logging_config.py          # JSON/plain-text logging setup
│   ├── auth.py                    # API-ключи, in-memory rate limiting, DEBUG-валидация
│   ├── db.py                      # SQLAlchemy engine + session
│   ├── templates/
│   │   └── admin.html             # Legacy Jinja2 admin panel (fallback)
│   ├── routers/
│   │   ├── auth.py                # API key management endpoints
│   │   ├── branch.py              # Branches CRUD
│   │   ├── department.py          # Departments CRUD + serialize_department()
│   │   ├── sales.py               # Sales sync, summary, hourly, stats
│   │   ├── forecast/              # ML forecasting package
│   │   │   ├── __init__.py        # Router aggregation
│   │   │   ├── core.py            # Retrain, model info, comparison, batch, CSV export
│   │   │   ├── tuning.py          # Optuna hyperparameter optimization, model comparison
│   │   │   ├── error_analysis.py  # Error segments, problematic branches, temporal errors
│   │   │   └── postprocessing.py  # Forecast smoothing, business rules, settings
│   │   └── monitoring.py          # Model health, performance, alerts
│   ├── models/                    # SQLAlchemy models (11 моделей, разделены по файлам)
│   │   ├── __init__.py            # Re-exports all models for mapper registration
│   │   ├── department.py          # Department
│   │   ├── sales.py               # SalesSummary, SalesByHour, AutoSyncLog
│   │   ├── forecast.py            # Forecast, ForecastAccuracyLog, PostprocessingSettings
│   │   ├── ml.py                  # ModelVersion, ModelRetrainingLog
│   │   └── branch.py              # Branch, Sale (legacy) + backward-compat re-exports
│   ├── schemas/
│   │   └── branch.py              # Pydantic schemas (18 схем)
│   ├── agents/
│   │   └── sales_forecaster_agent.py  # LightGBM agent
│   └── services/
│       ├── iiko_auth.py               # iiko API auth (credentials из settings)
│       ├── iiko_department_loader.py   # Department sync (N+1 optimized)
│       ├── iiko_sales_loader.py       # Sales sync (domains из settings)
│       ├── scheduled_sales_loader.py  # Auto-sync scheduler wrapper
│       ├── branch_loader.py           # Branch loading
│       ├── training_service.py        # ML data preparation + feature engineering
│       ├── hyperparameter_tuning_service.py  # Optuna integration
│       ├── model_retraining_service.py       # Auto-retraining logic
│       ├── model_monitoring_service.py       # Performance monitoring
│       ├── forecast_postprocessing_service.py # Post-processing rules
│       └── error_analysis_service.py         # Error analysis
├── models/                        # Trained ML models (.pkl)
├── migrations/                    # SQL migration files
├── scripts/                       # Utilities and test scripts
├── tests/                         # Test suite
├── docs/                          # Documentation + session logs
├── Dockerfile                     # 3-stage build (Node.js + Python + final), non-root user
├── docker-compose.yml             # Dev environment
├── docker-compose.prod.yml        # Production (env_file based)
├── requirements.txt               # Python dependencies (pinned versions)
├── .env                           # Local env vars (in .gitignore)
├── .env.example                   # Template for .env
├── .env.prod.example              # Template for production .env
└── .dockerignore                  # Docker build exclusions
```

## Frontend (React SPA)

### Стек
- **React 19** + **Vite 8** + **TypeScript 6**
- **TanStack Query** — серверное состояние, кеширование, mutations
- **shadcn/ui** (Radix UI + Tailwind CSS 4) — UI-компоненты
- **React Router 7** — клиентская маршрутизация
- **Recharts 3** — графики (BarChart, LineChart)
- **pnpm** — пакетный менеджер

### Роутинг (6 страниц)
| Путь | Страница | API |
|------|----------|-----|
| `/departments` | Подразделения (CRUD + фильтры) | GET/POST/PUT/DELETE `/api/departments/` |
| `/sales/daily` | Продажи по дням | GET `/api/sales/summary` |
| `/sales/hourly` | Продажи по часам + BarChart | GET `/api/sales/hourly` |
| `/forecast/branches` | Прогноз по филиалам | GET `/api/forecast/batch` |
| `/forecast/comparison` | Сравнение факт/прогноз + LineChart | GET `/api/forecast/comparison` |
| `/sync` | Синхронизация данных | POST `/api/sales/sync`, GET `/api/sales/auto-sync/status` |

### Auth-токен
- **Production**: FastAPI (`_serve_spa()` в `main.py`) инжектирует `<script>window.__API_TOKEN__="..."</script>` в `index.html`
- **Development**: `VITE_API_TOKEN` из `frontend/.env.development`
- `api-client.ts` читает `window.__API_TOKEN__` || `import.meta.env.VITE_API_TOKEN`

### SPA Serving (backend)
- `app/main.py`: `_serve_spa()` → читает `app/static/spa/index.html`, инжектирует токен
- Catch-all route `/{full_path:path}` → отдаёт `index.html` для React Router
- SPA assets: `/assets` → `StaticFiles(app/static/spa/assets/)`
- **Fallback**: если `app/static/spa/index.html` не существует → Jinja2 `admin.html`

### Сборка и деплой
```bash
# Сборка frontend
cd frontend && pnpm build

# Копирование в бэкенд (для локальной проверки)
cp -r frontend/dist/* app/static/spa/

# Docker автоматически делает это через 3-stage build
```

## Environment Variables

Все секреты хранятся в `.env` файлах, НЕ в коде. Шаблоны: `.env.example`, `.env.prod.example`.

### Обязательные переменные:
```bash
# Application
API_TOKEN=<your-token>          # Bearer-токен для API авторизации
DEBUG=False                      # True = plain-text logs + dev auth; False = JSON logs + full DB auth
LOG_LEVEL=INFO                   # Уровень логирования (DEBUG, INFO, WARNING, ERROR)

# Database
DATABASE_URL=postgresql://user:pass@host:port/db
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=sales_forecast
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# External API
API_BASE_URL=http://tco.aqnietgroup.com:5555/v1

# iiko Integration
IIKO_LOGIN=<login>
IIKO_PASSWORD=<password-hash>
IIKO_DOMAINS=https://sandy-co-co.iiko.it,https://madlen-group-so.iiko.it

# CORS
ALLOWED_ORIGINS=https://aqniet.site
```

### Security Model:
- **Production (DEBUG=False):** API-ключи в БД (SHA256), in-memory rate limiting (sliding window), JSON логирование
- **Development (DEBUG=True):** Bearer-токен валидируется против `API_TOKEN` из env, plain-text логирование
- **Admin panel (SPA):** Токен инжектируется сервером через `window.__API_TOKEN__` в index.html
- **Admin panel (legacy):** Токен инжектируется через Jinja2 `{{ api_token }}`
- **CORS:** Ограничен списком доменов из `ALLOWED_ORIGINS`
- **Security headers:** CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy (middleware в main.py)
- **Config:** `extra="ignore"` — неизвестные переменные в .env не ломают запуск

## Key Components

### Database Models (11 моделей в `app/models/`)
| Файл | Модели | Описание |
|------|--------|----------|
| `department.py` | Department | Подразделения, организации, сегменты |
| `sales.py` | SalesSummary, SalesByHour, AutoSyncLog | Продажи и логи синхронизации |
| `forecast.py` | Forecast, ForecastAccuracyLog, PostprocessingSettings | Прогнозы и настройки |
| `ml.py` | ModelVersion, ModelRetrainingLog | Версии моделей и логи переобучения |
| `branch.py` | Branch, Sale | Legacy модели + re-export всех остальных |

**Backward compatibility:** Все импорты `from ..models.branch import X` продолжают работать через re-exports.

### API Endpoints
- `/api/departments/` — CRUD подразделений + serialize_department()
- `/api/departments/sync` — Синхронизация с 1C Exchange API
- `/api/sales/sync` — Синхронизация продаж из iiko API
- `/api/sales/summary` — Дневные итоги
- `/api/sales/hourly` — Почасовые данные
- `/api/sales/stats` — Статистика
- `/api/sales/auto-sync/status` — Статус автозагрузок
- `/api/forecast/retrain` — Переобучение модели
- `/api/forecast/batch` — Массовые прогнозы
- `/api/forecast/comparison` — Сравнение с фактом
- `/api/forecast/export/csv` — CSV экспорт
- `/api/forecast/optimize` — Hyperparameter tuning (Optuna)
- `/api/forecast/compare_models` — Сравнение LightGBM/XGBoost/CatBoost
- `/api/forecast/error-analysis/` — Анализ ошибок по сегментам
- `/api/forecast/postprocess` — Post-processing прогнозов
- `/api/forecast/postprocessing/settings` — Настройки post-processing
- `/api/monitoring/health` — Здоровье модели
- `/api/monitoring/performance/summary` — Метрики производительности
- `/api/monitoring/alerts/recent` — Уведомления
- `/api/auth/` — Управление API-ключами
- `/` — React SPA (fallback: Jinja2 admin.html)
- `/health` — Health check

### Scheduled Tasks (APScheduler via lifespan)
- **02:00** — Daily sales auto-sync
- **03:00 Sun** — Weekly model retraining
- **04:00** — Daily performance metrics calculation
- **10:00** — Daily sales gap check

## External Dependencies

### 1C Exchange Service
- **URL**: http://tco.aqnietgroup.com:5555/v1/objects
- **Purpose**: Данные о подразделениях и организациях

### iiko API Integration
- **Domains**: Конфигурируются через `IIKO_DOMAINS` в .env
- **Authentication**: Username/password с 1-hour token refresh
- **Endpoints**: /resto/api/auth, /resto/api/v2/reports/olap

## Common Commands

### Development
```bash
# Backend (НА ПОРТУ 8002!)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

# Frontend (dev server с proxy на 8002)
cd frontend && pnpm dev
# Открыть http://localhost:5173

# Сборка frontend
cd frontend && pnpm build

# Копирование SPA в бэкенд (для проверки через :8002)
cp -r frontend/dist/* app/static/spa/

# Тесты
pytest

# Миграции
alembic upgrade head
```

### Production (Docker)
```bash
# Запуск
docker-compose -f docker-compose.prod.yml up -d

# Перестройка (включая frontend)
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app

# Логи
docker-compose -f docker-compose.prod.yml logs -f sales-forecast-app
```

### API Operations
```bash
# Синхронизация подразделений
curl -X POST http://localhost:8002/api/departments/sync

# Синхронизация продаж
curl -X POST "http://localhost:8002/api/sales/sync?from_date=2025-03-01&to_date=2025-03-31"

# Health check
curl http://localhost:8002/health

# Model health
curl http://localhost:8002/api/monitoring/health
```

### ML Commands
```bash
# Прогноз для филиала
curl "http://localhost:8002/api/forecast/2025-07-01/branch-uuid"

# Переобучение модели
curl -X POST http://localhost:8002/api/forecast/retrain

# Hyperparameter tuning (Optuna)
curl -X POST "http://localhost:8002/api/forecast/optimize" \
  -H "Content-Type: application/json" \
  -d '{"n_trials": 50, "timeout": 1800, "cv_folds": 3, "days": 365}'

# Сравнение моделей
curl -X POST "http://localhost:8002/api/forecast/compare_models" \
  -H "Content-Type: application/json" \
  -d '{"days": 365}'
```

## ML System v2.3

- **Test MAPE**: 6.18%
- **R2**: 0.9962+
- **Features**: 64 признака (weekend features, temporal smoothing)
- **Weekend Logic**: PostgreSQL DOW конвертация `postgres_dow = (python_dow + 1) % 7`
- **Temporal Smoothing**: +-50% ограничение от среднего по дню недели за 4 недели
- **Hybrid Forecasting**: Short-term (1-7 days, MAPE 5-15%) / Long-term (8+ days, MAPE 15-25%)

## Deployment

### Production Server: aqniet.site
- **Domain**: https://aqniet.site/
- **Port Mapping**: 8002:8000 (sales-forecast-app)
- **Database Port**: 5435:5432 (sales-forecast-db)
- **Nginx**: Proxy to Docker containers
- **Docker**: 3-stage build (Node.js frontend → Python deps → final image), non-root user, healthcheck

## Known Issues & Solutions

### 1. Branch Sync Foreign Key Violations
**Problem**: Foreign key constraint errors during department sync
**Solution**: Multi-pass processing (parents first, children second)

### 2. Sales Data Processing
**Problem**: Large volume aggregation needed
**Solution**: Pandas groupby for daily/hourly aggregation

### 3. TypeScript 6 — baseUrl deprecated
**Problem**: `baseUrl` в tsconfig.json вызывает ошибку TS5101
**Solution**: Использовать `paths` без `baseUrl` (TS 6+ поддерживает `paths` самостоятельно)

## Version Control

- **Repository**: https://github.com/Rus9136/sales_forecast.git
- **Branch**: master

## Code Audit (2026-04-29)

Проведён полный аудит кодовой базы. Обнаружено 37 проблем, исправлено все кроме unit-тестов.

### Выполненные исправления:

**Фаза 1 — Безопасность:**
- Секреты вынесены из кода в .env (iiko credentials, API tokens, domains)
- Dockerfile: multi-stage build, non-root user, healthcheck
- XSS-защита в admin.html шаблоне
- .dockerignore, .env.example, .env.prod.example созданы

**Фаза 2 — Архитектура и качество кода:**
- HTML админ-панель извлечена из main.py в `app/templates/admin.html` (Jinja2)
- Устранено дублирование кода (iiko domains, token logging, OptionalType alias)
- Исправлена обработка исключений (bare except → except Exception)
- Удалено DEBUG-логирование в production-коде

**Фаза 3 — Инфраструктура:**
- CORS из settings, deprecated lifespan APIs исправлены
- Auth bypass в DEBUG-режиме: валидация против API_TOKEN вместо полного пропуска
- CSP security headers middleware (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP)

**Дополнительные оптимизации:**
- N+1 запросы исправлены (iiko_department_loader.py, routers/department.py)
- Rate limiting: SQL COUNT запросы → in-memory sliding window (deque + threading)
- Зависимости обновлены до актуальных стабильных версий
- forecast.py (1,087 строк) разделён на пакет `routers/forecast/` (4 модуля)
- models/branch.py (11 моделей) разделён на 5 файлов по доменам
- Structured JSON logging для production, plain-text для development
- Config: `extra="ignore"` для устойчивости к неизвестным .env переменным

## Frontend Migration (2026-04-29)

Фронтенд переписан с Jinja2 HTML (~3200 строк) на React 19 SPA.

### Что сделано:
- **41 файл** React/TypeScript кода в `frontend/src/`
- **12 shadcn/ui компонентов** (Button, Card, Dialog, Table, Select, Alert, Badge, Progress, etc.)
- **6 страниц** — полная функциональная замена admin.html
- **4 TanStack Query хука** — типизированные CRUD-операции с кешированием
- **Recharts** — заменил Chart.js (BarChart для часовых продаж, LineChart для сравнения)
- **Smart chart scaling** — auto-switch linear/logarithmic (percentile-based)
- **Typed API client** — Bearer auth, error handling
- **3-stage Dockerfile** — Node.js build + Python deps + final image
- **SPA serving** — FastAPI раздаёт React SPA с инжекцией токена, catch-all для React Router
- **Fallback** — если SPA не собран, показывается старый Jinja2 шаблон

### Оставшиеся задачи:
- Unit-тесты (auth.py, training_service, роутеры)
- Удаление `app/templates/admin.html` после подтверждения работы SPA на production

Полный отчёт аудита: `CODE_AUDIT_REPORT.md`

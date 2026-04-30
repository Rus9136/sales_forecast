# CLAUDE.md - Sales Forecast API Project

## Project Overview
Sales Forecast API — система прогнозирования продаж на FastAPI с LightGBM для ML. Интеграция с iiko API и 1C Exchange для получения данных о подразделениях и продажах.

## Production Server

**Этот проект расположен на production-сервере (aqniet.site).** Все изменения в коде напрямую влияют на боевой сервис.

- **Сервер**: aqniet.site (VPS, Linux)
- **Домен**: https://aqniet.site/
- **Проект на диске**: `/root/projects/SalesForecast/sales_forecast/`
- **Docker Compose**: `docker-compose.prod.yml` — основной файл для запуска
- **Nginx**: reverse proxy → Docker containers

## ВАЖНЫЕ ПРЕДУПРЕЖДЕНИЯ

**НЕ ТРОГАЙТЕ 1C Exchange Service на порту 8000!** Это отдельный независимый проект.

### Разделение портов:
- **Порт 8000**: 1C Exchange Service (ОТДЕЛЬНЫЙ ПРОЕКТ - НЕ ТРОГАТЬ!)
- **Порт 8002**: Sales Forecast API (ЭТОТ ПРОЕКТ, маппинг 8002→8000 внутри контейнера)
- **Порт 5173**: Vite dev server (React frontend, proxy → 8002) — только для разработки
- **Порт 5435**: PostgreSQL для Sales Forecast (маппинг 5435→5432 внутри контейнера)
- **Порт 5433**: PostgreSQL для других проектов

## Architecture

- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React 19 SPA (`frontend/`) — Vite, TypeScript, shadcn/ui, TanStack Query, Recharts
- **Database**: PostgreSQL 15
- **ML Framework**: LightGBM (основной), XGBoost, CatBoost (сравнение)
- **AI Recommendations**: Multi-agent анализ (Claude/OpenAI) — `app/services/ai/`, прямые SQL без MCP
- **Deployment**: Docker + Docker Compose (3-stage build: Node.js → Python → final)
- **Scheduler**: APScheduler (7 задач: employees, sales, waiter sales, retrain, metrics, gap check, bonus auto-calc)
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
│   │   │   ├── sync.ts            # AutoSyncLog, SyncStatusResponse
│   │   │   ├── waiter.ts          # Employee, SalesByWaiter, WaiterSyncResult
│   │   │   └── ai.ts              # AIProvider, AIAnalyzeRequest, AIPromptInfo, AIAnalysisDetail
│   │   ├── hooks/
│   │   │   ├── use-departments.ts    # CRUD + sync mutations
│   │   │   ├── use-sales.ts          # Daily + hourly queries
│   │   │   ├── use-forecast.ts       # Batch, comparison, retrain
│   │   │   ├── use-sync.ts           # Auto-sync status, manual sync
│   │   │   ├── use-waiter-sales.ts   # Employees + waiter sales queries / mutations
│   │   │   └── use-ai-recommendations.ts # 7 хуков: providers/prompts/history/analyze/rerun
│   │   ├── components/
│   │   │   ├── ui/                # shadcn/ui primitives (Tabs, Textarea, и др.)
│   │   │   ├── layout/            # AppLayout, Sidebar (5 секций навигации)
│   │   │   └── shared/            # DateRangePicker, DepartmentSelect, ConfirmDialog, etc.
│   │   └── pages/
│   │       ├── departments-page.tsx       # CRUD + фильтры (тип/компания/поиск)
│   │       ├── daily-sales-page.tsx       # Таблица дневных продаж
│   │       ├── hourly-sales-page.tsx      # Recharts BarChart + таблица
│   │       ├── waiter-sales-page.tsx      # Продажи по официантам + ручной sync
│   │       ├── forecast-branch-page.tsx   # Прогнозы по филиалам
│   │       ├── forecast-comparison-page.tsx # LineChart + сортируемая таблица + ошибка
│   │       ├── sync-page.tsx              # Статус-карточки + ручная синхронизация
│   │       └── ai-recommendations-page.tsx # Мультиагентный анализ + редактор промптов + история
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
│   │   ├── employee.py            # Employees catalog (list + sync)
│   │   ├── sales.py               # Sales sync, summary, hourly, by-waiter, stats
│   │   ├── ai_recommendations.py  # AI multi-agent analysis (8 endpoints)
│   │   ├── forecast/              # ML forecasting package
│   │   │   ├── __init__.py        # Router aggregation
│   │   │   ├── core.py            # Retrain, model info, comparison, batch, CSV export
│   │   │   ├── tuning.py          # Optuna hyperparameter optimization, model comparison
│   │   │   ├── error_analysis.py  # Error segments, problematic branches, temporal errors
│   │   │   └── postprocessing.py  # Forecast smoothing, business rules, settings
│   │   └── monitoring.py          # Model health, performance, alerts
│   ├── models/                    # SQLAlchemy models (16 моделей, разделены по файлам)
│   │   ├── __init__.py            # Re-exports all models for mapper registration
│   │   ├── department.py          # Department
│   │   ├── sales.py               # SalesSummary, SalesByHour, AutoSyncLog
│   │   ├── forecast.py            # Forecast, ForecastAccuracyLog, PostprocessingSettings
│   │   ├── ml.py                  # ModelVersion, ModelRetrainingLog
│   │   ├── employee.py            # Employee, SalesByWaiter
│   │   ├── ai.py                  # AIRecommendation, AIPromptLog, AIPrompt
│   │   └── branch.py              # Branch, Sale (legacy) + backward-compat re-exports
│   ├── schemas/
│   │   ├── branch.py              # Pydantic schemas (18 схем)
│   │   └── ai.py                  # AnalyzeRequest/Response, HistoryItem, PromptInfo, RerunAgentRequest
│   ├── agents/
│   │   └── sales_forecaster_agent.py  # LightGBM agent
│   └── services/
│       ├── iiko_auth.py                  # iiko API auth (credentials из settings)
│       ├── iiko_department_loader.py     # Department sync (N+1 optimized)
│       ├── iiko_sales_loader.py          # Daily/hourly sales sync (domains из settings)
│       ├── iiko_employee_loader.py       # Employees catalog sync (XML, includeDeleted=true)
│       ├── iiko_waiter_sales_loader.py   # Per-waiter sales OLAP + name→employee_id resolve
│       ├── scheduled_sales_loader.py     # Auto-sync scheduler wrapper (sales + gap check)
│       ├── scheduled_waiter_loader.py    # Scheduler wrappers for employees + waiter sales
│       ├── branch_loader.py              # Branch loading
│       ├── training_service.py           # ML data preparation + feature engineering
│       ├── hyperparameter_tuning_service.py  # Optuna integration
│       ├── model_retraining_service.py       # Auto-retraining logic
│       ├── model_monitoring_service.py       # Performance monitoring
│       ├── forecast_postprocessing_service.py # Post-processing rules
│       ├── error_analysis_service.py         # Error analysis
│       └── ai/                               # AI Recommendations subsystem
│           ├── data_collector.py             # Direct SQL (replaces hr-miniapp MCP)
│           ├── multi_agent_system.py         # Phase 1→2 orchestrator + compress + render
│           ├── prompts.py                    # Default prompts + DB-backed get/upsert
│           └── engines/                      # AI provider engines
│               ├── base.py                   # BaseEngine ABC + AgentResult dataclass
│               ├── claude_engine.py          # AsyncAnthropic + 529 backoff + isolated keys
│               ├── openai_engine.py          # AsyncOpenAI + RateLimit handling
│               ├── gemini_engine.py          # Stub (not implemented)
│               ├── dispatcher.py             # Provider routing + lru_cache singleton
│               └── _logging.py               # Audit log to ai_prompt_logs
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

### Роутинг (8 страниц)
| Путь | Страница | API |
|------|----------|-----|
| `/departments` | Подразделения (CRUD + фильтры) | GET/POST/PUT/DELETE `/api/departments/` |
| `/sales/daily` | Продажи по дням | GET `/api/sales/summary` |
| `/sales/hourly` | Продажи по часам + BarChart | GET `/api/sales/hourly` |
| `/sales/waiters` | Продажи по официантам + ручной sync | GET `/api/sales/by-waiter`, POST `/api/sales/sync-waiters`, POST `/api/employees/sync` |
| `/forecast/branches` | Прогноз по филиалам | GET `/api/forecast/batch` |
| `/forecast/comparison` | Сравнение факт/прогноз + LineChart | GET `/api/forecast/comparison` |
| `/sync` | Синхронизация данных | POST `/api/sales/sync`, GET `/api/sales/auto-sync/status` |
| `/ai-recommendations` | Мультиагентный анализ (Sales/Optimization/Narrative) + редактор промптов + история | `/api/ai-recommendations/*` (8 endpoints) |

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

# UI auth bootstrap (создаёт первого admin при старте, если admin отсутствует)
BOOTSTRAP_ADMIN_PHONE=                       # Любой формат, нормализуется до digits-only
BOOTSTRAP_ADMIN_NAME=Администратор

# AI Recommendations (Claude/OpenAI)
ANTHROPIC_API_KEY=sk-ant-api03-...           # Основной ключ Claude
ANTHROPIC_API_KEY_PAYROLL=                   # Опционально: per-agent ключи (fallback на основной)
ANTHROPIC_API_KEY_STAFFING=
ANTHROPIC_API_KEY_NARRATIVE=
ANTHROPIC_API_KEY_REPUTATION=
OPENAI_API_KEY=                              # Опционально (если включаете OpenAI как provider)
OPENAI_MODEL=gpt-4o
CLAUDE_MODEL=claude-sonnet-4-20250514
```

### Security Model:
- **Production (DEBUG=False):** API-ключи в БД (SHA256), in-memory rate limiting (sliding window), JSON логирование
- **Development (DEBUG=True):** Bearer-токен валидируется против `API_TOKEN` из env, plain-text логирование
- **Admin panel (SPA):** Токен инжектируется сервером через `window.__API_TOKEN__` в index.html
- **Admin panel (legacy):** Токен инжектируется через Jinja2 `{{ api_token }}`
- **CORS:** Ограничен списком доменов из `ALLOWED_ORIGINS`
- **Security headers:** CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy (middleware в main.py)
- **Config:** `extra="ignore"` — неизвестные переменные в .env не ломают запуск

## UI Auth & Roles

Поверх API-токена добавлен слой UI-авторизации: вход в SPA по номеру телефона + role-based видимость разделов sidebar. **Это визуальная защита, не security.** Все API-эндпоинты (кроме `/api/auth/*` и `/api/users/*`) по-прежнему авторизуются общим `API_TOKEN` — пользователь с DevTools технически может дёрнуть любой endpoint напрямую.

### Поток
1. Открытие SPA → `AuthProvider` читает `localStorage["sf.session_token"]` → `GET /api/auth/me`
2. Нет токена / 401 → редирект на `/login` (форма с одним полем «телефон»)
3. `POST /api/auth/login {phone}` → если `app_user.phone` существует и `is_active=true` → возврат `{session_token, user}`
4. Токен отправляется в каждом запросе как `X-Session-Token`. При 401 чистится автоматически
5. `Sidebar` фильтрует пункты меню по `user.allowed_sections`; `ProtectedRoute` редиректит на `/forbidden` при прямом заходе на запрещённый URL
6. `/` ведёт на первый доступный раздел роли (HomeRedirect)

### Таблицы (миграция `011_app_users_and_roles.sql`)
- `app_role` — `code` PK, `name`, `allowed_sections` JSONB (массив section keys), `is_system` (системные нельзя удалить/переименовать)
- `app_user` — `id` UUID, `phone` UNIQUE (digits-only с auto-нормализацией `8XXX→7XXX`), `full_name`, `role_code` FK, `password_hash` зарезервировано на будущее, `is_active`, `last_login_at`
- `app_session` — `token` PK (43 chars `secrets.token_urlsafe(32)`), `user_id` FK, `expires_at` (TTL 30 дней)

### Системные роли (засеяны при старте)
| Code | Name | Дефолтные разделы |
|------|------|-------------------|
| `admin` | Администратор | все 15 секций (включая `users`, `roles`) |
| `manager` | Менеджер | departments, employees, sales.*, forecast.*, ai.recommendations, sync |
| `accountant` | Бухгалтер | departments, employees, sales.daily, sales.waiters, bonus.* |
| `viewer` | Наблюдатель | sales.daily, sales.hourly, forecast.* |

Права ролей **редактируются через UI** (`/roles`) — admin отмечает чекбоксы. Имена системных ролей менять нельзя.

### Section keys (15 шт)
`departments`, `employees`, `sales.daily`, `sales.hourly`, `sales.waiters`, `forecast.branches`, `forecast.comparison`, `bonus.calculations`, `bonus.schemes`, `bonus.manual-kpi`, `bonus.monthly-plans`, `ai.recommendations`, `sync`, `users`, `roles`. Список захардкожен в `app/auth_ui.py::AVAILABLE_SECTIONS` — при добавлении нового раздела нужно дописать туда + в `frontend/src/types/auth.ts::SectionKey` + в `sidebar.tsx`.

### Backend (`app/auth_ui.py`, `app/routers/users_ui.py`)
- `get_current_user` (Depends) читает `X-Session-Token` (или `Authorization: Session <token>`) → валидирует `app_session` → возвращает `AppUser`
- `require_admin` — guard для admin-эндпоинтов (роль `admin`)
- `seed_default_roles(db)` — идемпотентно создаёт 4 системные роли при старте
- `bootstrap_admin(db, phone, name)` — если задан `BOOTSTRAP_ADMIN_PHONE` и нет ни одного admin, создаёт первого
- Эндпоинты:
  - `POST /api/auth/login` — `{phone}` → `{session_token, expires_at, user}`
  - `POST /api/auth/logout` — удаляет текущую сессию по токену
  - `GET /api/auth/me` — текущий пользователь + `allowed_sections`
  - `GET /api/auth/roles` — список ролей + `available_sections`
  - `PUT /api/auth/roles/{code}` — admin only, `{name?, allowed_sections?}` (имя системной роли менять нельзя)
  - `GET/POST/PUT/DELETE /api/users/` — admin only, CRUD пользователей. Защита: нельзя деактивировать/удалить себя, нельзя снять admin с последнего активного admin

### Frontend (`frontend/src/`)
- `contexts/auth-context.tsx` — `AuthProvider`, `useAuth()` (`status`, `user`, `login`, `logout`, `hasSection(key)`, `isAdmin`)
- `lib/api-client.ts` — добавляет `X-Session-Token` ко всем запросам, при 401 чистит сессию + триггерит redirect
- `components/auth/protected-route.tsx` — guard роутов, опционально `<ProtectedRoute section="..."/>`
- `components/auth/home-redirect.tsx` — `/` → первый доступный раздел роли
- `pages/login-page.tsx`, `pages/forbidden-page.tsx`
- `pages/users-page.tsx` — таблица + dialog-форма создания/редактирования (телефон, ФИО, роль, активность)
- `pages/roles-page.tsx` — карточки ролей с чекбокс-матрицей разделов
- `components/layout/sidebar.tsx` — фильтрует пункты по `hasSection(item.section)`, секция «АДМИНИСТРИРОВАНИЕ» (`/users`, `/roles`), блок текущего пользователя + кнопка «Выйти»

### Bootstrap
Установить `BOOTSTRAP_ADMIN_PHONE` в `.env.prod` → перезапустить контейнер. На startup создастся admin-пользователь с указанным телефоном (если admin ещё не существует).

```bash
# Создать admin вручную через psql
docker exec -it sales-forecast-db psql -U sales_user -d sales_forecast \
  -c "INSERT INTO app_user (phone, full_name, role_code, is_active) VALUES ('77001234567', 'Администратор', 'admin', true);"
```

## Key Components

### Database Models (16 моделей в `app/models/`)
| Файл | Модели | Описание |
|------|--------|----------|
| `department.py` | Department | Подразделения, организации, сегменты |
| `sales.py` | SalesSummary, SalesByHour, AutoSyncLog | Продажи и логи синхронизации |
| `forecast.py` | Forecast, ForecastAccuracyLog, PostprocessingSettings | Прогнозы и настройки |
| `ml.py` | ModelVersion, ModelRetrainingLog | Версии моделей и логи переобучения |
| `employee.py` | Employee, SalesByWaiter | Каталог сотрудников iiko + продажи по официантам |
| `ai.py` | AIRecommendation, AIPromptLog, AIPrompt | Запуски AI-анализа, аудит промптов, шаблоны |
| `branch.py` | Branch, Sale | Legacy модели + re-export всех остальных |

**Backward compatibility:** Все импорты `from ..models.branch import X` продолжают работать через re-exports.

### API Endpoints
- `/api/departments/` — CRUD подразделений + serialize_department()
- `/api/departments/sync` — Синхронизация с 1C Exchange API
- `/api/employees/` — Список сотрудников (фильтры: search, role_code, department_code, include_deleted)
- `/api/employees/sync` — Синхронизация каталога сотрудников из iiko (XML)
- `/api/sales/sync` — Синхронизация продаж из iiko API
- `/api/sales/summary` — Дневные итоги
- `/api/sales/hourly` — Почасовые данные
- `/api/sales/by-waiter` — Продажи по официантам (фильтры: department_id, employee_id, waiter_name, период)
- `/api/sales/sync-waiters` — Синхронизация продаж по официантам (OLAP)
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
- `/api/ai-recommendations/analyze` — Запуск мультиагентного анализа (POST)
- `/api/ai-recommendations/history` — История запусков (фильтр `department_id`)
- `/api/ai-recommendations/analysis/{id}` — Детали запуска
- `/api/ai-recommendations/prompts/{analysis_id}` — UI-shaped payload для вкладок (агент → результат + лог промпта)
- `/api/ai-recommendations/prompts` — GET/PUT шаблонов промптов (DB > default)
- `/api/ai-recommendations/rerun-agent` — Перезапуск одного агента в существующем анализе (POST)
- `/api/ai-recommendations/providers` — Информация о настроенных AI-провайдерах
- `/` — React SPA (fallback: Jinja2 admin.html)
- `/health` — Health check

### Scheduled Tasks (APScheduler via lifespan)
- **01:30** — Daily employees catalog sync (iiko XML)
- **02:00** — Daily sales auto-sync
- **02:30** — Daily waiter sales sync (per-waiter OLAP)
- **03:00 Sun** — Weekly model retraining
- **04:00** — Daily performance metrics calculation
- **10:00** — Daily sales gap check
- **11:00** — Daily waiter sales gap check
- **5th @ 05:00** — Monthly bonus auto-calculation (draft за прошлый месяц)

## External Dependencies

### 1C Exchange Service
- **URL**: http://tco.aqnietgroup.com:5555/v1/objects
- **Purpose**: Данные о подразделениях и организациях

### iiko API Integration
- **Domains**: Конфигурируются через `IIKO_DOMAINS` в .env
- **Authentication**: Username/password с 1-hour token refresh (`/resto/api/auth`)
- **Sales OLAP** (`POST /resto/api/v2/reports/olap`):
  - Daily/hourly: `groupBy=[Department.Id, CloseTime, OrderNum]`, `aggregate=DishSumInt`
  - Per-waiter: `groupBy=[Department.Id, WaiterName, OpenDate]`, `aggregate=[DishSumInt, DishDiscountSumInt]`
  - **Важно**: фильтр периода — `OpenDate.Typed` (не `OpenDate` из публичного PDF)
- **Employees** (`GET /resto/api/employees?includeDeleted=true`): XML, мерж по UUID между доменами
- **Resolution `WaiterName → employee_id`**: `WaiterName` из OLAP — это `employee.name` из справочника. На вставке делается lookup; FK `employee_id` остаётся NULL при 0 или >1 совпадений

## Common Commands

### Development (локальная разработка без Docker)
```bash
# Backend (НА ПОРТУ 8002!)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

# Frontend (dev server с proxy на 8002)
cd frontend && pnpm dev
# Открыть http://localhost:5173

# Сборка frontend
cd frontend && pnpm build

# Тесты
pytest

# Миграции
alembic upgrade head
```

### API Operations
```bash
# Синхронизация подразделений
curl -X POST http://localhost:8002/api/departments/sync

# Синхронизация продаж
curl -X POST "http://localhost:8002/api/sales/sync?from_date=2025-03-01&to_date=2025-03-31"

# Синхронизация каталога сотрудников (XML)
curl -X POST -H "Authorization: Bearer $API_TOKEN" http://localhost:8002/api/employees/sync

# Синхронизация продаж по официантам (OLAP)
curl -X POST -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/sales/sync-waiters?from_date=2025-04-01&to_date=2025-04-03"

# Список сотрудников с фильтром по роли (например, официанты WR1)
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/employees/?role_code=WR1&limit=50"

# Health check
curl http://localhost:8002/health

# Model health
curl http://localhost:8002/api/monitoring/health
```

### Bonus Commands
```bash
# Залить справочники (компании, должности, KPI), схемы и KITCHEN-команды
docker exec sales-forecast-app python -m app.bonus.seeds.run_all

# Список схем
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8002/api/bonus/schemes

# Ввести план продаж (для KPI sales_plan)
curl -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/bonus/monthly-plans \
  -d '{"department_id": "<uuid>", "metric": "sales", "year": 2026, "month": 4, "target_value": "50000000"}'

# Ввести ручной KPI (например, аудит)
curl -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/bonus/manual-kpi \
  -d '{"department_id": "<uuid>", "kpi_code": "manual_audit", "period_year": 2026, "period_month": 4, "fact_value": "95"}'

# Запустить расчёт за период (всех с активным assignment)
curl -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/bonus/calculations/run \
  -d '{"department_id": "<uuid>", "year": 2026, "month": 4, "scope": "all"}'

# Список расчётов с итогом
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/bonus/calculations?year=2026&month=4&status=draft"

# Утвердить расчёт
curl -X POST -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/bonus/calculations/<id>/approve"
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

### AI Recommendations Commands
```bash
# Информация о провайдерах (что настроено)
curl -H "Authorization: Bearer $API_TOKEN" \
  http://localhost:8002/api/ai-recommendations/providers

# Запуск анализа (Claude, ~90-110с)
curl -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/ai-recommendations/analyze \
  -d '{"department_id":"<uuid>","date_start":"2026-03-01","date_end":"2026-03-07","provider":"claude"}'

# История запусков
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/ai-recommendations/history?limit=10"

# UI-shaped данные одного анализа (агенты + промпты + логи)
curl -H "Authorization: Bearer $API_TOKEN" \
  http://localhost:8002/api/ai-recommendations/prompts/<analysis_id>

# Перезапустить одного агента в существующем анализе
curl -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  http://localhost:8002/api/ai-recommendations/rerun-agent \
  -d '{"analysis_id":1,"agent_name":"SalesAnalysisAgent","provider":"claude"}'

# Просмотр текущих шаблонов промптов
curl -H "Authorization: Bearer $API_TOKEN" \
  http://localhost:8002/api/ai-recommendations/prompts
```

## ML System v2.3

- **Test MAPE**: 6.18%
- **R2**: 0.9962+
- **Features**: 64 признака (weekend features, temporal smoothing)
- **Weekend Logic**: PostgreSQL DOW конвертация `postgres_dow = (python_dow + 1) % 7`
- **Temporal Smoothing**: +-50% ограничение от среднего по дню недели за 4 недели
- **Hybrid Forecasting**: Short-term (1-7 days, MAPE 5-15%) / Long-term (8+ days, MAPE 15-25%)

## Bonus Subsystem

Подсистема расчёта KPI-бонусов сотрудников. Находится в `app/bonus/`, переиспользует `departments`/`employees`/`sales_by_waiter` из основного приложения.

### Архитектура
- **Слои**: API (`routers/`) → Service (`services/`) → Repository (`repositories/`) → Model + Calculator (`calculator/`) → Data sources (`data_sources/`)
- **Calculator engine** — чистая логика без БД. 5 моделей расчёта зарегистрированы через `@register_model`:
  - `flat_by_kpi` — KPI → грейд → фикс. сумма (Управляющий)
  - `revenue_percent_by_kpi` — KPI → ставка × выручка (Менеджер, Официант)
  - `revenue_direct` — выручка × фикс. % (Кассир, Старший бариста)
  - `combined_products` — выручка по компонентам с разными ставками (Бариста)
  - `team_revenue_by_kpi` — коллективный (KITCHEN с распределением по слотам)
- **Data sources** — 19 источников зарегистрированы в `DataSourceRegistry`. Реальные читают из `sales_by_waiter`/`sales_summary`. Заглушки: ready/prepared products, CRM-отзывы, HR-укомплектованность (через `bonus_manual_kpi`)
- **Versioning** — схемы (`bonus_scheme`) и слоты команд (`bonus_team_position`) версионируются через `effective_from`/`effective_to`
- **Snapshots** — каждый `bonus_calculation` сохраняет `scheme_config_snapshot`, `kpi_values`, `breakdown` (JSONB) для аудита

### Database tables (12)
- `bonus_company` — юрлица
- `bonus_position` — должности с маппингом `iiko_role_code` → `employees.main_role_code`
- `bonus_team`, `bonus_team_position` — команды (KITCHEN) и слоты с весами
- `bonus_kpi_definition` — справочник KPI
- `bonus_monthly_plan` — планы продаж/рентабельности/норма смен
- `bonus_employee_assignment` — назначения сотрудника на должность/слот
- `bonus_scheme` — схемы расчёта (department × position/team)
- `bonus_manual_kpi` — ручной ввод KPI (аудит, отзывы, укомплектованность)
- `bonus_calculation`, `bonus_calculation_penalty` — расчёты + удержания
- `departments.company_id` — добавлено к `departments` для связи с юрлицом

### API endpoints (под `/api/bonus/`)
- `GET /companies` `/positions` `/kpi-definitions` `/config/calculation-models` `/config/data-sources`
- `GET /schemes` `/schemes/{id}`, `POST /schemes`, `POST /schemes/validate`
- `GET /teams` `/teams/{id}`
- `GET/POST /manual-kpi`, `DELETE /manual-kpi/{id}`
- `GET/POST /monthly-plans`
- `POST /calculations/run` (`scope: all|employee:<uuid>|position:<code>`)
- `GET /calculations` `/calculations/{id}`
- `POST /calculations/{id}/penalties` `/approve` `/reject`
- `GET /reports/summary?year=&month=`

### Frontend pages (`/bonus/*`)
- `/bonus/calculations` — список расчётов, batch-запуск, детали с breakdown, approve/reject
- `/bonus/schemes` — список схем по department, просмотр config (JSONB)
- `/bonus/manual-kpi` — таблица + форма ввода KPI
- `/bonus/monthly-plans` — таблица + форма планов

### Tests
53 unit-теста в `tests/bonus/`:
- `test_kpi_engine.py` — score/overall (TC-50..52)
- `test_grading.py` — find_grade с ceil-rounding (TC-60..61)
- `test_calculation_models.py` — все 5 моделей с числами из `bonus_service/bonus_docs/10-testing.md`

```bash
docker exec sales-forecast-app python -m pytest tests/bonus/ -v
```

### Документация моделей
Полная спецификация в `bonus_service/bonus_docs/`. Конфиги локаций — `07-config-examples.md`. Числовые тест-кейсы — `10-testing.md`.

### Правила доработки bonus subsystem

**❌ НЕЛЬЗЯ:**
- Хардкодить ставки/проценты/грейды в Python — всё через БД (`bonus_scheme.config` JSONB) и seeds
- Делать отдельные таблицы под конкретное подразделение (`KitchenDistribution`, `BarStaff`) — использовать `bonus_team` + `bonus_team_position`
- Звать iiko/TCO/CRM напрямую из калькулятора или service — только через `DataSourceRegistry`
- Использовать `float` для денег и процентов — только `Decimal` (см. `app/bonus/utils/decimal_utils.py`)
- Удалять `bonus_scheme` записи — версионировать через `effective_to` (старая закрывается, новая создаётся с `version+1`)
- Изменять старые `bonus_calculation` со статусом `approved`/`paid` — перерасчёт даёт новую запись со статусом `recalculated`

**✅ ОБЯЗАТЕЛЬНО:**
- Сохранять снапшот при расчёте (`scheme_config_snapshot`, `kpi_values`, `breakdown` JSONB) — для аудита через 6 месяцев
- Валидировать `bonus_scheme.config` через Pydantic-схему модели расчёта при сохранении (`SchemeService.create()`)
- Возвращать `BonusBreakdown` с детализацией: KPI значения → грейд → ставка → выручка → смены → итог
- Поддерживать proration по сменам там, где `apply_shifts_proration: true` в config
- Логировать каждый расчёт с разбивкой через `app.logging_config`

**Точность Decimal в БД:**
- Деньги — `DECIMAL(14, 2)` (тенге с тиынами)
- Проценты-доли — `DECIMAL(8, 6)` (`0.000700` хранится точно — это 0.07%)
- Грейды (5..100) — `DECIMAL(5, 2)`
- Веса слотов команды — `DECIMAL(8, 6)` (распределение KITCHEN)

**Добавление новой модели расчёта:**
1. Создать `app/bonus/calculator/models/<name>.py` с классом, унаследованным от `BaseBonusModel`
2. Декоратор `@register_model('<code>')` — попадает в `CALCULATION_MODELS` registry
3. Создать Pydantic-схему конфига в `app/bonus/schemas/calc_configs/<name>.py` и зарегистрировать в `CONFIG_VALIDATORS`
4. Добавить тесты в `tests/bonus/test_calculation_models.py` с конкретными числами

**Добавление нового источника данных:**
1. Создать класс, унаследованный от `BonusDataSource`, с `code = '<name>'` и методом `fetch(db, params)`
2. Зарегистрировать в `app/bonus/data_sources/bootstrap.py` через `DataSourceRegistry.register(...)`
3. Можно ссылаться на новый код в `bonus_scheme.config["revenue_source"]` или `kpis[*].source`

## AI Recommendations Subsystem

Мультиагентный AI-анализ работы подразделения. Портирован из `hr-miniapp` (Node.js); MCP-зависимость убрана — данные читаются прямыми SQL к локальной БД. Основные файлы — `app/services/ai/`, `app/routers/ai_recommendations.py`, `app/models/ai.py`, `frontend/src/pages/ai-recommendations-page.tsx`.

### Архитектура
- **Слои**: Router → `MultiAgentSystem` (orchestrator) → `BaseEngine` (Claude/OpenAI/Gemini) → `data_collector` (SQL).
- **Phase 1 → Phase 2**: Phase 1 — агенты, потребляющие сырые данные (Sales/Payroll/Staffing/Reputation). Phase 2 — синтез (Optimization → Narrative) использует результаты Phase 1.
- **Provider isolation**: `EngineDispatcher` — синглтон через `lru_cache`, выбирает движок по `provider` (`claude`/`openai`/`gemini`).
- **Per-agent изолированные ключи** (Claude): `ANTHROPIC_API_KEY_PAYROLL/_STAFFING/_NARRATIVE/_REPUTATION` — fallback на основной `ANTHROPIC_API_KEY`. Это разнесённые rate-limit'ы, как в hr-miniapp.
- **Retry**: для 529 (overload) — экспоненциальный backoff 30/90/180/360/600s + jitter; для прочих 5xx — стандартный exponential backoff cap 30s.
- **Variant A (текущий)**: 3 агента включены — `SalesAnalysisAgent`, `OptimizationAgent`, `NarrativeAgent`. 3 агента (`PayrollAnalysisAgent`, `StaffingAgent`, `ReputationAgent`) лежат в registry с `enabled=False` — данные `payroll`/`reviews` сейчас `None`.
- **Промпты**: `DEFAULT_PROMPTS` (hardcoded) + `ai_prompts` таблица. DB-row побеждает дефолт. Шаблоны редактируются через UI (PUT `/api/ai-recommendations/prompts`).
- **Token compression**: `compress_data_for_tokens()` — сжимает суммы в `Nk`, обрезает forecast/plan_vs_fact до 10 строк, `hourly_sales` до 168 (7 дней × 24 часа), сокращает агенту-результаты до 500 символов.
- **Audit log**: каждый вызов AI пишется в `ai_prompt_logs` (full_prompt, response_text, tokens, success, request/response timestamps). Не валит транзакцию при ошибке.
- **Snapshot входа**: при `analyze` сырые данные складываются в `ai_recommendations.mcp_response` JSONB (имя унаследовано от hr-miniapp; смысл — `input_data`). Это позволяет `rerun-agent` повторно прогнать одного агента без перезапроса БД.

### Database tables (3)
- `ai_recommendations` — запуск анализа (department_id, period, mcp_response JSONB, agent_results JSONB, provider)
- `ai_prompt_logs` — аудит каждого вызова AI (analysis_id FK, agent_name, full_prompt, response_text, tokens_used, success)
- `ai_prompts` — редактируемые шаблоны промптов (agent_name PK, prompt_text)

### Реальные метрики (Claude Sonnet 4, 7-дневный период)
- SalesAnalysisAgent: ~7k токенов / 20-25с
- OptimizationAgent: ~3k токенов / 28-35с
- NarrativeAgent: ~5k токенов / 28-30с
- Полный цикл: ~90-110 секунд

**Nginx таймаут**: для `/api/ai-recommendations/` в `aqniet.conf` стоит `proxy_read_timeout 180s` — без этого 60-секундный дефолт обрывал запросы.

### Правила доработки

**❌ НЕЛЬЗЯ:**
- Использовать `httpx.get(MCP_URL)` или другой внешний HTTP — данные только через `data_collector.py` (прямой SQL)
- Хардкодить промпты в коде — они в `DEFAULT_PROMPTS` и могут перезаписываться через `ai_prompts`. Обновлять — только через `upsert_prompt()`
- Удалять записи из `ai_prompt_logs` — это аудит-лог, нужен для воспроизводимости
- Изменять `ai_recommendations.agent_results` без `flag_modified(rec, "agent_results")` — SQLAlchemy не увидит in-place мутацию JSONB
- Делать sync-вызовы к Claude/OpenAI — все engine-методы async, оркестратор использует `asyncio.sleep` для пауз между агентами

**✅ ОБЯЗАТЕЛЬНО:**
- Логировать каждый AI-вызов через `log_prompt()` — даже при ошибке
- При добавлении нового агента — заполнить `AGENTS` registry в `multi_agent_system.py` с `data_fields` и `enabled=False` пока данные не подъехали; добавить дефолтный промпт в `DEFAULT_PROMPTS`
- При добавлении нового AI-провайдера — наследоваться от `BaseEngine`, реализовать `analyze_with_agent` + `is_configured`, зарегистрировать в `EngineDispatcher.__init__`
- Проверять `cfg.enabled` перед запуском агента — отключённые агенты должны попадать в `skipped`, а не падать с ошибкой

### Включение отключённых агентов

Когда появятся источники данных:
1. **Payroll/Staffing**: заполнить `payroll` секцию в `data_collector.collect_dashboard_data()` (например, через `sales_by_waiter` + смены из новой таблицы или подключение к hr-miniapp DB на 5437)
2. **Reputation**: подключиться к `reviews-parser` (порт 8004) и заполнить `reviews` секцию
3. В `multi_agent_system.AGENTS` поменять `enabled=False` на `True` — оркестратор сам подхватит. Промпты уже в `DEFAULT_PROMPTS`.

## Deployment (Production)

### Инфраструктура
- **Сервер**: aqniet.site (VPS)
- **Домен**: https://aqniet.site/
- **Nginx**: reverse proxy → `localhost:8002`
- **Docker Compose**: `docker-compose.prod.yml`
- **Контейнеры**:
  - `sales-forecast-app` — FastAPI + React SPA (порт 8002→8000)
  - `sales-forecast-db` — PostgreSQL 15 (порт 5435→5432)
  - `exchange-service` — 1C Exchange (порт 8000→8000, отдельный проект)

### Env-файлы (обязательны для запуска)
- `.env.prod` — переменные для sales-forecast-app и sales-forecast-db
- `.env.exchange` — переменные для exchange-service
- Шаблоны: `.env.prod.example`, `.env.exchange.example`

### Деплой (пошагово)

```bash
# 1. Перейти в директорию проекта
cd /root/projects/SalesForecast/sales_forecast

# 2. Пересобрать образ (frontend + backend в одном образе)
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app

# 3. Перезапустить контейнер
docker-compose -f docker-compose.prod.yml up -d sales-forecast-app

# 4. Проверить что запустился
docker-compose -f docker-compose.prod.yml ps
curl -s http://localhost:8002/health
curl -s https://aqniet.site/health

# 5. Посмотреть логи (если что-то не так)
docker-compose -f docker-compose.prod.yml logs -f --tail=50 sales-forecast-app
```

### Деплой только backend (без пересборки frontend)
Если изменения только в Python-коде, Docker всё равно пересобирает frontend (кеш).
Для ускорения можно использовать `--build` вместо `--no-cache`:
```bash
docker-compose -f docker-compose.prod.yml build sales-forecast-app
docker-compose -f docker-compose.prod.yml up -d sales-forecast-app
```

### Деплой frontend отдельно (без Docker)
Для быстрой проверки можно собрать frontend локально и скопировать в контейнер:
```bash
cd frontend && pnpm build
cp -r dist/* ../app/static/spa/
# Перезапуск контейнера не нужен — FastAPI читает файлы с диска
# Но volume не смонтирован для SPA, поэтому нужен rebuild Docker
```

### Полный перезапуск всех сервисов
```bash
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

### Откат к предыдущей версии
```bash
# Посмотреть историю коммитов
git log --oneline -10

# Откатить до нужного коммита
git checkout <commit-hash> -- .

# Пересобрать и перезапустить
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app
docker-compose -f docker-compose.prod.yml up -d sales-forecast-app
```

### Docker: 3-stage build
1. **Stage 1** (`node:20-slim`): `pnpm install` + `pnpm build` → `frontend/dist/`
2. **Stage 2** (`python:3.11-slim`): `pip install` requirements
3. **Stage 3** (`python:3.11-slim`): копирует Python deps + app + SPA build, `libgomp1` для LightGBM, non-root user, healthcheck

### Git
- **Repository**: https://github.com/Rus9136/sales_forecast.git
- **Branch**: master
- **SSH-ключ для GitHub** не настроен на сервере — `git push` требует настройки SSH или переключения на HTTPS с токеном

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

### 4. iiko OLAP — `OpenDate` vs `OpenDate.Typed`
**Problem**: Запросы с фильтром `OpenDate` (как в публичном PDF iiko) возвращают `OLAP-запрос отклонен, поскольку в запросе не найден ни один из необходимых фильтров: Учетный день (OpenDate.Typed)`
**Solution**: Всегда использовать `OpenDate.Typed` в фильтрах OLAP

### 5. Waiter sales — резолв имени в employee_id
**Problem**: OLAP-отчёт `Выручка по официантам` возвращает только строку `WaiterName`. Поле `OrderWaiter.Id` существует, но соответствует владельцу заказа (терминал/кассир), а не назначенному официанту
**Solution**: Использовать `WaiterName` как естественный ключ. Сотрудника резолвить через lookup `employees.name`. Перед синхронизацией продаж обновить справочник (`includeDeleted=true`), иначе уволенные официанты не привяжутся. FK `employee_id` остаётся NULL при 0 или >1 совпадений по имени — UI показывает баджик «не найден»

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

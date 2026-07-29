# CLAUDE.md - Sales Forecast API Project

## Project Overview
Sales Forecast API — система прогнозирования продаж на FastAPI с LightGBM для ML. Интеграция с iiko API и 1C Exchange для получения данных о подразделениях и продажах.

## Production Server

**Этот проект расположен на production-сервере (aqniet.space).** Все изменения в коде напрямую влияют на боевой сервис.

- **Сервер**: aqniet.space (VPS, Linux)
- **Домен**: https://aqniet.space/
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

> **Ценообразование:** полная карта подсистемы (поток данных, семантика ε, статусная машина, джобы, грабли, правила доработки) — [`docs/PRICING_SYSTEM_GUIDE.md`](docs/PRICING_SYSTEM_GUIDE.md). Читать ПЕРЕД любыми изменениями в pricing-коде.

- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React 19 SPA (`frontend/`) — Vite, TypeScript, shadcn/ui, TanStack Query, Recharts
- **Database**: PostgreSQL 15
- **ML Framework**: LightGBM (основной), XGBoost, CatBoost (сравнение)
- **AI Recommendations**: Multi-agent анализ (Claude/OpenAI) — `app/services/ai/`, прямые SQL без MCP
- **Deployment**: Docker + Docker Compose (3-stage build: Node.js → Python → final)
- **Scheduler**: APScheduler (22 задачи: nomenclature, employees, sales, receipts, inventory documents, waiter sales, retrain, SKU retrain, recipes, menu clustering, catalog price sync + applied detection, elasticity estimation, price optimization, outcome evaluation, recommendation LLM explanations, weekly/monthly pricing LLM reports, metrics, pricing analytics, gap checks ×3)
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
│   │   │   ├── ai.ts              # AIProvider, AIAnalyzeRequest, AIPromptInfo, AIAnalysisDetail
│   │   │   └── receipts.ts        # Receipt, ReceiptItem, ReceiptDetail, ProductSalesStats
│   │   ├── hooks/
│   │   │   ├── use-departments.ts    # CRUD + sync mutations
│   │   │   ├── use-sales.ts          # Daily + hourly queries
│   │   │   ├── use-forecast.ts       # Batch, comparison, retrain
│   │   │   ├── use-sync.ts           # Auto-sync status, manual sync
│   │   │   ├── use-waiter-sales.ts   # Employees + waiter sales queries / mutations
│   │   │   ├── use-ai-recommendations.ts # 7 хуков: providers/prompts/history/analyze/rerun
│   │   │   └── use-receipts.ts       # Receipts list/detail, product sales stats, sync
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
│   │       ├── ai-recommendations-page.tsx # Мультиагентный анализ + редактор промптов + история
│   │       └── receipts/
│   │           ├── receipts-page.tsx      # Журнал чеков + диалог деталей
│   │           └── stats-by-product-page.tsx # Топ блюд по выручке
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
│   │   │   ├── core.py            # Retrain (global + per-segment), model info, comparison, batch, CSV export
│   │   │   ├── tuning.py          # Optuna hyperparameter optimization, model comparison
│   │   │   ├── error_analysis.py  # Error segments, problematic branches, temporal errors
│   │   │   └── postprocessing.py  # Forecast smoothing, business rules, settings
│   │   ├── receipts.py            # Receipts list/detail, stats by product, sync
│   │   ├── pricing_analytics.py   # Price history, weekly summaries, menu roles, clustering trigger
│   │   └── monitoring.py          # Model health, performance, alerts
│   ├── models/                    # SQLAlchemy models (16 моделей, разделены по файлам)
│   │   ├── __init__.py            # Re-exports all models for mapper registration
│   │   ├── department.py          # Department
│   │   ├── sales.py               # SalesSummary, SalesByHour, AutoSyncLog
│   │   ├── forecast.py            # Forecast, ForecastAccuracyLog, PostprocessingSettings
│   │   ├── ml.py                  # ModelVersion, ModelRetrainingLog
│   │   ├── employee.py            # Employee, SalesByWaiter
│   │   ├── ai.py                  # AIRecommendation, AIPromptLog, AIPrompt
│   │   ├── receipts.py            # Receipt, ReceiptItem (partitioned by open_date)
│   │   ├── pricing_analytics.py   # SkuPriceHistory, SkuWeeklySummary, DepartmentWeeklySummary, SkuMenuRole, SkuCatalogPrice, PricingReport
│   │   ├── sku_forecast.py        # SkuDailySales, SkuForecast (SKU-level forecasting)
│   │   └── branch.py              # Branch, Sale (legacy) + backward-compat re-exports
│   ├── schemas/
│   │   ├── branch.py              # Pydantic schemas (18 схем)
│   │   ├── ai.py                  # AnalyzeRequest/Response, HistoryItem, PromptInfo, RerunAgentRequest
│   │   ├── receipts.py            # Receipt/Item/Detail/SyncResponse, ProductSalesStats
│   │   ├── sku_forecast.py        # SKU forecast request/response schemas
│   │   └── pricing_analytics.py  # Price history, weekly summaries, menu role schemas
│   ├── agents/
│   │   ├── sales_forecaster_agent.py  # LightGBM agent (department-level revenue)
│   │   └── sku_forecaster_agent.py    # LightGBM agent (SKU-level quantity)
│   └── services/
│       ├── iiko_auth.py                  # iiko API auth (credentials из settings)
│       ├── iiko_department_loader.py     # Department sync (N+1 optimized)
│       ├── iiko_sales_loader.py          # Daily/hourly sales sync (domains из settings)
│       ├── iiko_employee_loader.py       # Employees catalog sync (XML, includeDeleted=true)
│       ├── iiko_waiter_sales_loader.py   # Per-waiter sales OLAP + name→employee_id resolve
│       ├── scheduled_sales_loader.py     # Auto-sync scheduler wrapper (sales + gap check)
│       ├── scheduled_waiter_loader.py    # Scheduler wrappers for employees + waiter sales
│       ├── iiko_receipts_loader.py       # Receipts OLAP sync (DishId→product, batch upsert)
│       ├── scheduled_receipts_loader.py  # Scheduler wrappers for receipts sync + gap check
│       ├── scheduled_inventory_loader.py  # Ежедневный синк складских документов (скользящее окно)
│       ├── branch_loader.py              # Branch loading
│       ├── training_service.py           # ML data preparation + feature engineering (dept-level)
│       ├── sku_training_service.py      # SKU-level feature engineering (~74 features)
│       ├── sku_daily_aggregation_service.py  # receipt_item → sku_daily_sales aggregation
│       ├── sku_model_retraining_service.py  # SKU model auto-retrain (weekly)
│       ├── hyperparameter_tuning_service.py  # Optuna integration
│       ├── model_retraining_service.py       # Auto-retraining logic (dept-level)
│       ├── model_monitoring_service.py       # Performance monitoring
│       ├── forecast_postprocessing_service.py # Post-processing rules
│       ├── error_analysis_service.py         # Error analysis
│       ├── iiko_inventory_loader.py         # Списания (JSON) + приходные накладные (XML, потоково)
│       ├── inventory_analytics_service.py   # Аналитика списаний + петля поставка→продажа→списание
│       ├── procurement_recommendation_service.py # Заявка на цех (newsvendor)
│       ├── pricing_analytics_service.py     # A2: price history + weekly summary aggregation
│       ├── menu_clustering_service.py       # B1: KMeans menu role classification (5 roles)
│       ├── scheduled_pricing_analytics.py   # Scheduler wrappers for A2 + B1
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

### Роутинг (23 страницы)
| Путь | Страница | API |
|------|----------|-----|
| `/departments` | Подразделения (CRUD + фильтры) | GET/POST/PUT/DELETE `/api/departments/` |
| `/sales/daily` | Продажи по дням | GET `/api/sales/summary` |
| `/sales/hourly` | Продажи по часам + BarChart | GET `/api/sales/hourly` |
| `/sales/waiters` | Продажи по официантам + ручной sync | GET `/api/sales/by-waiter`, POST `/api/sales/sync-waiters`, POST `/api/employees/sync` |
| `/forecast/branches` | Прогноз по филиалам | GET `/api/forecast/batch` |
| `/forecast/comparison` | Сравнение факт/прогноз + LineChart | GET `/api/forecast/comparison` |
| `/forecast/sku` | Прогноз по блюдам (SKU qty) | GET `/api/forecast/sku/batch`, POST `/api/forecast/sku/retrain` |
| `/menu/products` | Номенклатура (фильтры + поиск) | GET `/api/menu/products`, POST `/api/menu/sync` |
| `/menu/groups` | Группы номенклатуры (дерево) | GET `/api/menu/groups/tree` |
| `/receipts` | Журнал чеков + диалог деталей | GET `/api/receipts`, GET `/api/receipts/{id}` |
| `/receipts/stats` | Продажи по блюдам (топ) | GET `/api/receipts/stats/by-product` |
| `/inventory/writeoffs` | Списания: склад × причина, топ позиций, динамика | `/api/inventory/writeoffs/*` |
| `/sync` | Синхронизация данных | POST `/api/sales/sync`, GET `/api/sales/auto-sync/status` |
| `/ai-recommendations` | Мультиагентный анализ (Sales/Optimization/Narrative) + редактор промптов + история | `/api/ai-recommendations/*` (8 endpoints) |
| `/pricing/dashboard` | Дашборд ценообразования (KPI, динамика) | GET `/api/pricing-analytics/department-weekly`, `/api/pricing-engine/recommendations/summary` |
| `/pricing/recommendations` | Рекомендации цен (approve/reject + XLSX) | `/api/pricing-engine/recommendations*` |
| `/pricing/position/:productId/:departmentId` | Карточка позиции (C3) | price-history, sku-weekly, elasticity/{id}/{id}, menu-roles, recs/outcomes по SKU |
| `/pricing/rules` | Правила цен (B4 UI) | `/api/pricing-engine/rules` CRUD |
| `/pricing/outcomes` | Результаты пилота (FB) | `/api/pricing-engine/outcomes*`, `/baseline`, `/experiments/generate` |
| `/pricing/elasticity` | Эластичность (B2 explorer) | `/api/pricing-engine/elasticity*` |
| `/pricing/menu-roles` | Роли меню (B1 explorer + override) | `/api/pricing-analytics/menu-roles*` |
| `/pricing/audit` | Журнал действий (AU) | `/api/pricing-engine/audit-log` |
| `/pricing/reports` | Отчёты по ценам (C4 weekly/monthly LLM) | `/api/pricing-engine/reports*` |

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
ALLOWED_ORIGINS=https://aqniet.space

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
OPENROUTER_API_KEY=sk-or-...                 # OpenRouter (openai-совместимый шлюз, openrouter.ai/keys)
OPENROUTER_MODEL=anthropic/claude-sonnet-4.6 # Слаг vendor/model
AI_DEFAULT_PROVIDER=claude                   # Дефолтный провайдер фоновых LLM-задач: claude|openai|openrouter|gemini
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
| `admin` | Администратор | все 24 секции (включая `users`, `roles`) |
| `manager` | Менеджер | dashboard, departments, employees, sales.*, forecast.*, ai.recommendations, pricing.*, sync |
| `accountant` | Бухгалтер | dashboard, departments, employees, sales.daily, sales.waiters |
| `viewer` | Наблюдатель | dashboard, sales.daily, sales.hourly, forecast.* |

### Доменные роли ценообразования (C5, несистемные, засеяны при старте)
| Code | Name | Доступ |
|------|------|--------|
| `restaurant_manager` | Управляющий рестораном | pricing.dashboard/recommendations/position_detail/rules/outcomes |
| `commercial_director` | Коммерческий директор | все pricing.* |
| `finance_director` | Финансовый директор | pricing.dashboard/recommendations/rules/outcomes |
| `pricing_analyst` | Аналитик | все pricing.* + forecast.* + menu.* + receipts.* |

Тонкая грануляция ТЗ (read-only / «только маржа» / стоп-лист) section-моделью не выражается.

Права ролей **редактируются через UI** (`/roles`) — admin отмечает чекбоксы. Имена системных ролей менять нельзя.

### Section keys (25 шт)
`dashboard`, `departments`, `employees`, `sales.daily`, `sales.hourly`, `sales.waiters`, `forecast.branches`, `forecast.comparison`, `forecast.sku`, `menu.products`, `menu.groups`, `receipts.list`, `receipts.stats`, `inventory.writeoffs`, `ai.recommendations`, `pricing.dashboard`, `pricing.recommendations`, `pricing.rules`, `pricing.position_detail`, `pricing.outcomes`, `pricing.analytics`, `pricing.reports`, `sync`, `users`, `roles`. Список захардкожен в `app/auth_ui.py::AVAILABLE_SECTIONS` — при добавлении нового раздела нужно дописать туда + в `frontend/src/types/auth.ts::SectionKey` + `roles-page.tsx` (лейбл) + `home-redirect.tsx` (map+priority) + `App.tsx` (route) + `sidebar.tsx`. ⚠️ Системные роли (admin/manager) автоматически мерджат новые секции из `DEFAULT_ROLES` при старте (`seed_default_roles`); **несистемные роли** (pricing-роли C5) — НЕ мерджат, новый key им добавляется ручным SQL.

### Backend (`app/auth_ui.py`, `app/routers/users_ui.py`)
- `get_current_user` (Depends) читает `X-Session-Token` (или `Authorization: Session <token>`) → валидирует `app_session` → возвращает `AppUser`
- `require_admin` — guard для admin-эндпоинтов (роль `admin`)
- `seed_default_roles(db)` — идемпотентно создаёт 4 системные + 4 доменные pricing-роли (C5) при старте; в системные до-мёрджит новые секции, несистемные не трогает
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

### Database Models (28 моделей в `app/models/`)
| Файл | Модели | Описание |
|------|--------|----------|
| `department.py` | Department | Подразделения, организации, сегменты, iiko_source_domain |
| `sales.py` | SalesSummary, SalesByHour, AutoSyncLog | Продажи и логи синхронизации |
| `forecast.py` | Forecast, ForecastAccuracyLog, PostprocessingSettings | Прогнозы и настройки |
| `ml.py` | ModelVersion, ModelRetrainingLog | Версии моделей и логи переобучения |
| `employee.py` | Employee, SalesByWaiter | Каталог сотрудников iiko + продажи по официантам |
| `ai.py` | AIRecommendation, AIPromptLog, AIPrompt | Запуски AI-анализа, аудит промптов, шаблоны |
| `menu.py` | NomenclatureCategory, NomenclatureGroup, Product | Каталог номенклатуры iiko (категории, группы, товары) |
| `receipts.py` | Receipt, ReceiptItem | Чеки + позиции (партиционировано по open_date) |
| `sku_forecast.py` | SkuDailySales, SkuForecast | Агрегированные продажи по SKU + хранение прогнозов |
| `pricing_analytics.py` | SkuPriceHistory, SkuWeeklySummary, DepartmentWeeklySummary, SkuMenuRole, SkuCatalogPrice, PricingReport | Ценовые события, недельные агрегаты, роли меню, каталожные цены, LLM-отчёты (C4) |
| `inventory.py` | Store, IikoAccount, Supplier, MeasureUnit, WriteoffDocument, WriteoffItem, IncomingInvoice, IncomingInvoiceItem, InventorySyncLog | Складской контур: акты списания и приходные накладные iiko |
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
- `/api/sales/avg-check-by-waiter` — Средний чек по официанту из `receipt` (checks_count, revenue, avg_check, guests_count, avg_per_guest; фильтры: department_id опц., from_date, to_date, waiter_name)
- `/api/sales/sync-waiters` — Синхронизация продаж по официантам (OLAP)
- `/api/sales/stats` — Статистика
- `/api/sales/auto-sync/status` — Статус автозагрузок
- `/api/forecast/retrain` — Переобучение глобальной модели
- `/api/forecast/retrain-segmented` — Переобучение per-segment моделей (отдельный LightGBM на каждый segment_type, fallback на global)
- `/api/forecast/batch` — Массовые прогнозы по дням × подразделениям (без `department_id` скрывает DEPARTMENT без продаж за 30 дней — `INACTIVE_THRESHOLD_DAYS`)
- `/api/forecast/batch_with_postprocessing` — Прогнозы с применённым post-processing (сглаживание, anomaly detection, confidence intervals)
- `/api/forecast/comparison` — Сравнение прогноза с фактом (тот же фильтр неактивных точек)
- `/api/forecast/export/csv` — CSV экспорт прогнозов (с опцией `include_actual=true` для comparison-формата)
- `/api/forecast/optimize` — Hyperparameter tuning (Optuna)
- `/api/forecast/compare_models` — Сравнение LightGBM/XGBoost/CatBoost
- `/api/forecast/model/info` — Метаданные текущей модели (версия, фичи, метрики)
- `/api/forecast/error-analysis/` — Анализ ошибок по сегментам
- `/api/forecast/postprocess` — Post-processing одного прогноза (query params, не JSON body)
- `/api/forecast/postprocess/batch` — Batch post-processing (body — массив, опции — query)
- `/api/forecast/postprocessing/settings` — Настройки post-processing
- `/api/forecast/test_smoothing` — Отладка temporal smoothing для одной точки × даты
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
- `/api/menu/categories` — Категории номенклатуры
- `/api/menu/groups` — Группы номенклатуры (flat)
- `/api/menu/groups/tree` — Группы (дерево)
- `/api/menu/products` — Продукты (фильтры: search, source, group, category, type + пагинация)
- `/api/menu/products/{id}` — Детали продукта
- `/api/menu/sync` — Синхронизация каталога номенклатуры (POST)
- `/api/receipts` — Чеки (фильтры: from_date, to_date, department_id, waiter_name, min_sum + пагинация)
- `/api/receipts/{id}?open_date=` — Детали чека с позициями (open_date для partition pruning)
- `/api/receipts/stats/by-product` — Топ блюд по выручке (from_date, to_date, department_id, limit)
- `/api/receipts/sync` — Синхронизация чеков из iiko OLAP (POST, from_date, to_date)
- `/api/forecast/sku/retrain` — Обучение SKU-модели (POST, days, active_window_days)
- `/api/forecast/sku/model/info` — Метаданные SKU-модели (GET)
- `/api/forecast/sku/batch` — Прогноз по SKU для подразделения (GET, department_id required, from_date, to_date, top_n)
- `/api/forecast/sku/top-n` — Топ-N SKU по выручке (GET, department_id optional, period_days, n)
- `/api/forecast/sku/comparison` — Факт vs прогноз SKU (GET, department_id, from_date, to_date)
- `/api/forecast/sku/export/csv` — CSV экспорт прогнозов SKU (GET)
- `/api/forecast/sku/aggregate/backfill` — Backfill sku_daily_sales агрегации (POST)
- `/api/pricing-analytics/price-history` — История ценовых изменений SKU (GET, product_id, department_id, from_date, to_date)
- `/api/pricing-analytics/sku-weekly` — Недельные агрегаты SKU (GET, product_id, department_id, from_week, to_week)
- `/api/pricing-analytics/department-weekly` — Недельные агрегаты подразделений (GET, department_id, from_week, to_week)
- `/api/pricing-analytics/aggregate` — Ручной запуск агрегации витрин (POST, from_date, to_date)
- `/api/pricing-analytics/backfill` — Полный backfill витрин (POST)
- `/api/pricing-analytics/menu-roles` — Роли позиций меню (GET, department_id, effective_role, product_id)
- `/api/pricing-analytics/menu-roles/summary` — Распределение ролей (GET, department_id)
- `/api/pricing-analytics/menu-roles/{product_id}/{department_id}` — Ручное переопределение роли (PUT, manual_role)
- `/api/pricing-analytics/menu-roles/cluster` — Запуск кластеризации (POST, lookback_days)
- `/api/pricing-engine/elasticity|recommendations|rules` — Ценовой движок: эластичность (B2), рекомендации (B3), правила (B4) — см. API_DOCUMENTATION_PRICING.md + docs/PRICING_SYSTEM_GUIDE.md (карта подсистемы)
- `/api/pricing-engine/experiments/generate` — Ценовые эксперименты для grade C/D (POST, измерение эластичности)
- `/api/pricing-engine/recommendations/detect-applied` — Детекция применённых цен по каталогу (POST)
- `/api/pricing-engine/outcomes` — Пост-анализ applied-рекомендаций: факт vs ожидание, реализованная эластичность (GET, + /summary, + POST /evaluate)
- `/api/pricing-engine/baseline` — KPI-база пилота (GET, + POST /freeze)
- `/api/pricing-engine/audit-log` — Append-only журнал действий ценообразования (GET)
- `/api/pricing-engine/reports` — Weekly/Monthly LLM-отчёты (C4): GET список, GET `/{id}` детали, POST `/generate` (report_type weekly/monthly, department_id?, period?)
- `/api/pricing-engine/jobs/{id}` — Статус фоновых джобов (`?background=true` на estimate/backfill)
- `/api/inventory/writeoffs/summary|by-product|trend` — Аналитика списаний (склад × причина, топ позиций с долей потерь, понедельная динамика)
- `/api/inventory/supply-loop` — По каждому SKU: поставлено → продано → списано за период
- `/api/inventory/order-recommendation` — Рекомендуемая заявка на цех (newsvendor: уровень сервиса = наценка позиции). **Только API — раздел из админки убран**
- `/api/inventory/suppliers|stores` — Поставщики точки за период, склады подразделения
- `/api/inventory/sync` — Загрузка списаний и накладных из iiko (POST, from_date, to_date, department_id?)
- `/api/labor-demand/{department_id}/menu-mix` — Сигнал для TCO: роли меню, топ-блюда, загрузка цехов (GET, from_date, to_date, top_n)
- `/api/labor-demand/{department_id}/forecast` — Сигнал для TCO: дневной спрос + почасовая кривая (GET, from_date, to_date)
- `/api/labor-demand/{department_id}/elasticity-signal` — Сигнал для TCO: эластичность флагманов (GET, grade)
- `/` — React SPA (fallback: Jinja2 admin.html)
- `/health` — Health check

### Scheduled Tasks (APScheduler via lifespan)
- **01:00** — Daily nomenclature catalog sync (products + groups + categories)
- **01:30** — Daily employees catalog sync (iiko XML)
- **02:00** — Daily sales auto-sync
- **02:15** — Daily receipts sync (per-dish OLAP)
- **02:30** — Daily waiter sales sync (per-waiter OLAP)
- **02:45** — Daily inventory documents sync (списания + приходные накладные, скользящее окно `INVENTORY_SYNC_LOOKBACK_DAYS`)
- **03:00 Sun** — Weekly model retraining (department-level)
- **03:15 Sun** — Weekly menu role clustering (KMeans → sku_menu_role)
- **03:20** — Daily catalog price sync (iiko orders → sku_catalog_price) + детекция applied-рекомендаций
- **03:30 Sun** — Weekly price elasticity estimation (B2, lookback 730д → sku_elasticity)
- **03:30 Sun** — Weekly recipe sync
- **03:45 Sun** — Weekly SKU model retraining
- **04:00** — Daily performance metrics calculation
- **04:30** — Daily pricing analytics aggregation (price history + weekly summaries)
- **05:00** — Daily price optimization (B3 → recommendations)
- **05:30** — Daily recommendation outcome evaluation (applied recs, 14д окно → price_recommendation_outcome)
- **05:45** — Daily recommendation LLM explanations (C4', топ-N по ΔGP на подразделение → `price_recommendation.llm_explanation`)
- **08:00 Mon** — Weekly pricing LLM report (C4, network → pricing_report)
- **08:00 1st** — Monthly pricing LLM report (C4, network → pricing_report)
- **10:00** — Daily sales gap check
- **11:00** — Daily waiter sales gap check
- **11:30** — Daily receipts gap check

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

### ML Commands
```bash
# Прогноз на диапазон (один филиал)
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/forecast/batch?from_date=2026-05-04&to_date=2026-05-10&department_id=<uuid>"

# Прогноз на диапазон (все активные филиалы — DEPARTMENT без продаж за 30д исключаются)
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/forecast/batch?from_date=2026-05-04&to_date=2026-05-10"

# Прогноз с post-processing (сглаживание, anomaly score, confidence intervals)
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8002/api/forecast/batch_with_postprocessing?from_date=2026-05-04&to_date=2026-05-10"

# Переобучение глобальной модели
curl -X POST http://localhost:8002/api/forecast/retrain

# Переобучение per-segment моделей (по segment_type)
curl -X POST http://localhost:8002/api/forecast/retrain-segmented \
  -H "Content-Type: application/json" \
  -d '{"days": 365}'

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

## ML System v2.3 (Department-level)

- **Test MAPE**: 6.18%
- **R2**: 0.9962+
- **Features**: 64 признака (weekend features, temporal smoothing)
- **Weekend Logic**: PostgreSQL DOW конвертация `postgres_dow = (python_dow + 1) % 7`
- **Temporal Smoothing**: +-50% ограничение от среднего по дню недели за 4 недели
- **Hybrid Forecasting**: Short-term (1-7 days, MAPE 5-15%) / Long-term (8+ days, MAPE 15-25%)

## ML System — SKU-level (Phase 5.3)

Прогноз количества продаж (qty) по каждому блюду/товару на каждое подразделение на каждый день.

- **Target**: SUM(qty) per (department_id, product_id, date), type IN ('DISH', 'GOODS')
- **Model**: LightGBM (600 trees, lr=0.03, depth=7, log1p target transform)
- **Features**: ~74 признака: time(23) + dept(18) + operational(11) + SKU static(8) + SKU rolling(11) + cross(4)
- **Data flow**: receipt_item → sku_daily_sales (aggregation) → SkuTrainingDataService (features) → SkuForecasterAgent (train/predict)
- **Model path**: `models/sku_lgbm_model.pkl`
- **Singleton**: `get_sku_forecaster_agent()`
- **Auto-retrain**: Sunday 03:45 via `run_sku_auto_retrain()`
- **Key tables**: `sku_daily_sales` (pre-aggregated), `sku_forecasts` (predictions for monitoring)
- **Prerequisite**: История чеков 6+ месяцев, backfill sku_daily_sales через POST `/api/forecast/sku/aggregate/backfill`

## AI Recommendations Subsystem

Мультиагентный AI-анализ работы подразделения. Портирован из `hr-miniapp` (Node.js); MCP-зависимость убрана — данные читаются прямыми SQL к локальной БД. Основные файлы — `app/services/ai/`, `app/routers/ai_recommendations.py`, `app/models/ai.py`, `frontend/src/pages/ai-recommendations-page.tsx`.

### Архитектура
- **Слои**: Router → `MultiAgentSystem` (orchestrator) → `BaseEngine` (Claude/OpenAI/Gemini) → `data_collector` (SQL).
- **Phase 1 → Phase 2**: Phase 1 — агенты, потребляющие сырые данные (Sales/Payroll/Staffing/Reputation). Phase 2 — синтез (Optimization → Narrative) использует результаты Phase 1.
- **Provider isolation**: `EngineDispatcher` — синглтон через `lru_cache`, выбирает движок по `provider` (`claude`/`openai`/`openrouter`/`gemini`). Дефолт — `AI_DEFAULT_PROVIDER` из .env (используется pricing-объяснениями C4' и отчётами C4). `OpenRouterEngine` наследует `OpenAIEngine` (тот же SDK, `base_url=https://openrouter.ai/api/v1`).
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

## Labor Optimization (Schedule Generation)

Подсистема оптимизации ФОТ: TCO («Учет рабочего времени») генерирует график сотрудников, а Sales Forecast обогащает процесс **сигналом спроса по локации**. **Статус: дизайн, контур согласован с TCO 2026-06-10 (Вариант А), эндпоинты §2 не реализованы.** Полная архитектура — [`docs/LABOR_OPTIMIZATION_ARCHITECTURE.md`](docs/LABOR_OPTIMIZATION_ARCHITECTURE.md).

### Ключевое архитектурное решение

**Solver (генерация графика) И LLM-агенты (ревью/правка графика) живут в TCO, не здесь.** Принцип data gravity: ~80% входов солвера (сотрудники, ставки, ФОТ, отпуска, фактическое посещение, ТК, календарь, утверждение) и сами агенты — в TCO. Sales Forecast — **только поставщик сигнала спроса** (read-only эндпоинты). У TCO уже есть свой солвер (OR-Tools) и своя multi-agent LLM-система — не дублируем.

### Что остаётся в Sales Forecast (Вариант А)

Три read-only эндпоинта под `/api/labor-demand/`. Auth — общий `Bearer $API_TOKEN`. Таймзона Asia/Almaty (UTC+5). Строятся на уже готовых данных (SKU-прогноз, кластеризация меню, витрины, эластичность) — новых ML-моделей не нужно.

| Эндпоинт | Приоритет | Что отдаёт | Источники |
|---|---|---|---|
| `GET /api/labor-demand/{id}/menu-mix` | **P1** | `role_distribution` (5 ролей меню), `top_dishes` (predicted_qty), `category_load` (загрузка цехов), `data_quality` | `sku_menu_role` + `forecast/sku/batch` + `sku_weekly_summary` + `product` |
| `GET /api/labor-demand/{id}/forecast` | **P2** | Дневной спрос (revenue/receipts/qty) + почасовая кривая (`hourly_profile`, историческая средняя) | `forecast/batch` + `department_weekly_summary` + `sales_by_hour` |
| `GET /api/labor-demand/{id}/elasticity-signal` | **P3** | `elasticity_mean`, `reliability_grade`, `global_prior` по флагманам | `sku_elasticity` |

### Что строится / уже есть в TCO (НЕ здесь)

- **Solver (OR-Tools)** — генерация графика из (demand + employees + constraints)
- **Расчёт `demand_by_role`** — TCO конвертирует сигнал в потребность по ролям из своей калибровки (факт-смены + посещаемость + ставки у них)
- **Своя multi-agent LLM-система** — агенты Sales / Schedule / Risks / Orchestrator, напрямую Claude + prompt-caching
- Календарь UI, workflow утверждения, хранение сотрудников/ставок/ФОТ, отпуска, ТК-ограничения, уведомления

### Поток end-to-end

1. Управляющий в TCO жмёт «Сгенерировать график»
2. TCO собирает контекст: зовёт `/menu-mix` + `/forecast` + `/elasticity-signal` (Promise.allSettled, graceful degradation)
3. TCO конвертирует сигнал в `demand_by_role` + прогоняет свой солвер → optimal schedule
4. TCO прогоняет СВОИ LLM-агенты с обогащённым контекстом → warnings + narrative + состав смены по цехам
5. UI: график + AI-разбор + [Утвердить]/[Редактировать]; правки — через агенты TCO
6. [Утвердить] → публикация + уведомления (всё внутри TCO)

Sales Forecast участвует только в шаге 2.

### Правила доработки

**❌ НЕЛЬЗЯ:**
- Создавать в Sales Forecast `labor_norms`, `forecast_to_demand()`, расчёт `demand_by_role`, плоский `GET /api/labor-demand` — потребность по ролям считает TCO (убрано из дизайна v1)
- Делать LLM-ревью/правку графика и schedule-агентов (`ScheduleReviewerAgent` и пр.) — это агенты TCO
- Реализовывать логику OR-Tools / constraint solving / ТК-валидацию
- Создавать таблицы `shifts`, `payroll_records`, `employee_vacations` — всё в TCO
- Отдавать через `/api/labor-demand/*` уже сгенерированный график — только сигнал спроса

**✅ ОБЯЗАТЕЛЬНО:**
- Во всех ответах отдавать `data_quality`-флаги (`cost_coverage`, `clustering_silhouette`, `sku_model_trained`) — TCO делает graceful-degradation, пока SKU-модель дообучается
- Эндпоинты — read-only, авторизация общим `Bearer $API_TOKEN`, ISO-8601 с зоной `+05:00`
- `hourly_profile.*_share` суммируются в ~1.0 (TCO умножает на дневной `predicted_revenue`)
- Мэппинг `category_name` → цех/станция НЕ делать здесь — отдаём категории iiko «как есть», сопоставление на стороне TCO

### Что согласовать с командой TCO

- Мэппинг категория iiko → цех/станция (справочник на стороне TCO)
- Глубина усреднения `hourly_profile` (4 vs 8 недель)
- Поведение для неактивных/новых точек (рекомендация: пустой блок + флаг в `data_quality`)
- SLA / частота вызовов эндпоинтов, нужен ли rate limiting

## Deployment (Production)

### Инфраструктура
- **Сервер**: aqniet.space (VPS)
- **Домен**: https://aqniet.space/
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
curl -s https://aqniet.space/health

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

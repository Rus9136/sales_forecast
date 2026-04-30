# План переноса фичи «Рекомендации ИИ» из hr-miniapp в SalesForecast

**Источник**: `/root/projects/hr-miniapp` (Node.js / Express)
**Цель**: `/root/projects/SalesForecast/sales_forecast` (FastAPI / Python)
**Стартовая дата**: 2026-04-30
**Вариант**: **A** — переносим только агентов, которым хватает локальных данных (Sales/Forecast/Hourly).
**Статус**: ✅ КОД ГОТОВ И ПРОТЕСТИРОВАН ЛОКАЛЬНО · ⏳ Ожидает деплоя на прод

---

## Контекст и решения

### Что переносим
- ✅ `SalesAnalysisAgent` — данные есть (`forecasts`, `sales_summary`, `sales_by_hour`)
- ✅ `OptimizationAgent` — синтезирует результаты других агентов
- ✅ `NarrativeAgent` — итоговый отчёт
- ❌ `PayrollAnalysisAgent` — нет данных о ФОТ (отложено)
- ❌ `StaffingAgent` — нет данных о сменах (отложено)
- ❌ `ReputationAgent` — нет источника отзывов (отложено)

Архитектура поддерживает добавление этих агентов потом — их конфиги остаются в коде, но помечаются `enabled: False`.

### Ключевые архитектурные решения
1. **MCP убирается полностью**. Данные берутся прямыми SQL-запросами к локальной БД.
2. **department_id**: используем `Department.id` (UUID) напрямую. `forecasts.branch_id` хранит тот же UUID — проверено (2266 forecast записей JOIN-ятся 1:1 с departments).
3. **Промпты**: первый деплой создаёт дефолтные промпты в БД при первом обращении (метод `initialize_default_prompts()`). Можно править через UI.
4. **Ключи API**: те же 5 ключей Claude через `app/config.py`. Если ключи `_PAYROLL`/`_STAFFING`/`_NARRATIVE`/`_REPUTATION` не заданы — fallback на основной `ANTHROPIC_API_KEY`.
5. **hr-miniapp**: после успешного запуска SalesForecast-версии — фичу в hr-miniapp оставляем как есть, со временем удалим.

### Данные, доступные локально

| Поле для агента | Источник | Состояние |
|-----------------|----------|-----------|
| `forecast` | `SELECT FROM forecasts` | ✅ 2266 записей |
| `plan_vs_fact` | JOIN `forecasts` + `sales_summary` | ✅ |
| `hourly_sales` | `SELECT FROM sales_by_hour` | ✅ 260k записей |
| `department_info` | `SELECT FROM departments` | ✅ 91 запись |
| `payroll` | — | ❌ `None` |
| `reviews` | — | ❌ `None` |

---

## Структура нового кода

```
app/
├── models/
│   └── ai.py                              # NEW — AIRecommendation, AIPromptLog, AIPrompt
├── services/
│   └── ai/                                # NEW — package
│       ├── __init__.py
│       ├── data_collector.py              # Замена MCP — прямые SQL запросы
│       ├── multi_agent_system.py          # Оркестратор 3 агентов
│       ├── prompts.py                     # Дефолтные промпты + работа с БД
│       └── engines/
│           ├── __init__.py
│           ├── base.py                    # BaseEngine ABC
│           ├── claude_engine.py           # anthropic SDK
│           ├── openai_engine.py           # openai SDK
│           ├── gemini_engine.py           # Заглушка
│           └── dispatcher.py              # Выбор движка
├── routers/
│   └── ai_recommendations.py              # NEW — FastAPI router
└── schemas/
    └── ai.py                              # NEW — Pydantic схемы

frontend/src/
├── types/ai.ts                            # NEW
├── hooks/use-ai-recommendations.ts        # NEW
└── pages/ai-recommendations-page.tsx      # NEW

migrations/
└── 010_ai_recommendations.sql             # NEW
```

---

## Прогресс по фазам

### ✅ Фаза 1 — БД миграция + SQLAlchemy модели — ГОТОВО

**Цель**: Создать таблицы и модели для хранения анализов и промптов.

- [x] `migrations/010_ai_recommendations.sql` — три таблицы созданы
- [x] `app/models/ai.py` — SQLAlchemy модели созданы
- [x] Регистрация в `app/models/__init__.py`
- [x] Миграция применена на dev-БД (порт 5435), три таблицы на месте
- [ ] Применить на prod-БД (при деплое — Фаза 8)

**Результат**: `\dt ai_*` показывает 3 таблицы (ai_recommendations, ai_prompt_logs, ai_prompts). Импорт моделей работает.

---

### ✅ Фаза 2 — Data collector (замена MCP) — ГОТОВО

**Цель**: Заменить HTTP-вызов к MCP API на прямые SQL запросы.

- [x] `app/services/ai/__init__.py` — пакет создан
- [x] `app/services/ai/data_collector.py` — `collect_dashboard_data()` готов
  - `forecast` — JOIN forecasts + sales_summary
  - `plan_vs_fact` — sales_summary с LEFT JOIN forecasts + расчёт error_percentage
  - `hourly_sales` — прямой SELECT из sales_by_hour
  - `department_info` — JOIN departments + parent (для object_company)
  - `payroll`, `reviews` — None (Вариант A)
- [x] Smoke-тест на реальных данных (Sandyq Turkestan, 11 forecast / 11 plan_vs_fact / 79 hourly)

**Результат**: Собирает данные за период из БД, формат совместим с агентами hr-miniapp.

---

### ✅ Фаза 3 — AI движки (Claude/OpenAI/Gemini) — ГОТОВО

**Готово**:
- [x] `engines/base.py` — `BaseEngine` ABC + `AgentResult` dataclass
- [x] `engines/_logging.py` — общая функция логирования в `ai_prompt_logs`
- [x] `engines/claude_engine.py` — асинхронный клиент `anthropic`, retry с экспоненциальным backoff (529: 30/90/180/360/600s, 5xx: стандартный)
- [x] `engines/openai_engine.py` — `openai.AsyncOpenAI`, обработка `RateLimitError`/`APIStatusError`
- [x] `engines/gemini_engine.py` — заглушка
- [x] `engines/dispatcher.py` — `EngineDispatcher`, кешированный `get_dispatcher()`
- [x] Smoke-тест: `providers_info()` возвращает корректный JSON, Claude сконфигурирован

---

### ✅ Фаза 4 — Мультиагентная система — ГОТОВО

**Готово**:
- [x] `prompts.py` — DEFAULT_PROMPTS для 6 агентов, `get_prompt(db, name)` (DB > default), `upsert_prompt`, `list_all_prompts`
- [x] `multi_agent_system.py`:
  - Реестр AGENTS с флагом `enabled` (3 включены, 3 на будущее)
  - `compress_data_for_tokens()` — портирован
  - `render_prompt()` с подстановкой `{forecast}`, `{plan_vs_fact}`, `{hourly_sales}`, `{department_info}`, `{agent_results}`
  - `MultiAgentSystem.run_analysis()` async — Phase 1 → Phase 2, паузы `asyncio.sleep`
  - `run_single_agent()` для rerun-agent
  - Возвращает `AnalysisOutcome` (success, results, errors, skipped, metadata)
- [x] Smoke-тест: компрессия → рендеринг промпта → enabled agents = 3

---

### ✅ Фаза 5 — API роутер — ГОТОВО

**Готово**:
- [x] `app/schemas/ai.py` — Pydantic схемы (AnalyzeRequest, HistoryItem, AnalyzeResponse, PromptInfo, RerunAgentRequest, AnalysisPromptsResponse...)
- [x] `app/routers/ai_recommendations.py` — все 8 endpoints:
  - `POST /api/ai-recommendations/analyze`
  - `GET /api/ai-recommendations/history` (с `department_id` фильтром)
  - `GET /api/ai-recommendations/analysis/{id}`
  - `GET /api/ai-recommendations/prompts/{analysis_id}` — данные для UI вкладок
  - `GET /api/ai-recommendations/prompts`
  - `PUT /api/ai-recommendations/prompts`
  - `POST /api/ai-recommendations/rerun-agent` (с `flag_modified` для JSONB)
  - `GET /api/ai-recommendations/providers`
- [x] Все защищены `Depends(get_api_key_or_bypass)`
- [x] Зарегистрирован в `app/main.py`
- [x] **End-to-end тест прошёл**: реальный анализ Sandyq Turkestan (01-07.03.2026), 3 агента отработали, всё в БД (analysis_id=1, 3 prompt_logs, токены 4682/3063/5200)

**Подтверждённые метрики**:
- SalesAnalysisAgent: prompt 6853 chars → response 2468 chars, 20s, 4682 токенов
- OptimizationAgent: 2738 chars → 3648 chars, 28s, 3063 токенов
- NarrativeAgent: 6750 chars → 4204 chars, 28s, 5200 токенов
- Полный цикл: ~91 секунда

---

### ✅ Фаза 6 — Конфигурация и зависимости — ГОТОВО

**Готово**:
- [x] `app/config.py` — добавлены `ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_*`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `CLAUDE_MODEL`
- [x] `requirements.txt` — `anthropic==0.42.0`, `openai==1.59.2`
- [x] Установлены в `venv`, импорт работает
- [ ] `.env.example` — обновить (Phase 8)

---

### ✅ Фаза 7 — Frontend (React + TanStack Query) — ГОТОВО

**Готово**:
- [x] `frontend/src/types/ai.ts` — все типы (AIProvider, AIAnalyzeRequest, AIHistoryItem, AIPromptInfo, AIPromptLog, AIAnalysisDetail...)
- [x] `frontend/src/hooks/use-ai-recommendations.ts` — 7 хуков:
  - `useAIProviders`, `useAIPrompts`, `useUpdateAIPrompts`
  - `useAIHistory`, `useAIAnalysisPrompts`
  - `useRunAIAnalysis`, `useRerunAgent`
- [x] `frontend/src/components/ui/tabs.tsx` — обёртка над `@radix-ui/react-tabs`
- [x] `frontend/src/components/ui/textarea.tsx` — для редактора промптов
- [x] `frontend/src/pages/ai-recommendations-page.tsx`:
  - Форма запуска (department + период + provider) с прогрессом
  - Тулбар с кнопкой «Промпты агентов» (Dialog с textarea для каждого агента)
  - Боковая панель истории анализов
  - Таб для каждого агента с под-табами «Результат» / «Промпт» (показывает токены, время, status)
  - Кнопка «Перезапустить агента» внутри каждой вкладки
- [x] `Sidebar` — новый раздел «AI АНАЛИТИКА» → «Рекомендации ИИ»
- [x] `App.tsx` — роут `/ai-recommendations`
- [x] **TypeScript-сборка прошла**: `pnpm build` → 0 ошибок, 859kB JS bundle

---

### 🟡 Фаза 8 — Тестирование и деплой — ЛОКАЛЬНОЕ ГОТОВО, ДЕПЛОЙ ЗА ПОЛЬЗОВАТЕЛЕМ

**Локальные проверки выполнены**:
- [x] Smoke-test всех 8 endpoints (`/providers`, `/history`, `/analysis/{id}`, `/prompts`, `/prompts/{id}`, PUT `/prompts`, `/analyze`, `/rerun-agent`)
- [x] Реальный анализ через Claude Sonnet 4 (Sandyq Turkestan, 7 дней) — успех, ~91 секунда
- [x] Логи в `ai_prompt_logs` корректны (3 агента, токены посчитаны)
- [x] PUT `/prompts` обновляет БД, GET `/prompts` показывает `source=db`
- [x] SPA отдаётся на `/ai-recommendations` через FastAPI catch-all
- [x] `.env.example` и `.env.prod.example` — добавлены секции AI

**Шаги деплоя на прод (выполнить вручную)**:
```bash
cd /root/projects/SalesForecast/sales_forecast

# 1. Применить миграцию на проде:
docker exec -i sales-forecast-db psql -U sales_user -d sales_forecast \
    < migrations/010_ai_recommendations.sql

# 2. Добавить в .env.prod ключи:
#    ANTHROPIC_API_KEY=sk-ant-api03-...
#    (опционально: ANTHROPIC_API_KEY_PAYROLL, _STAFFING, _NARRATIVE, _REPUTATION)
#    (опционально: OPENAI_API_KEY=...)

# 3. Пересобрать и перезапустить:
docker-compose -f docker-compose.prod.yml build sales-forecast-app
docker-compose -f docker-compose.prod.yml up -d sales-forecast-app

# 4. Проверка:
curl -s https://aqniet.site/health
curl -s -H "Authorization: Bearer $API_TOKEN" \
    https://aqniet.site/api/ai-recommendations/providers
```

**Критерий завершения**: Анализ запускается с прода (https://aqniet.site/ai-recommendations) и сохраняется в БД.

---

## Журнал работы

### 2026-04-30 — старт + полный порт
- ✅ Изучена структура SalesForecast и hr-miniapp
- ✅ Согласован Вариант A (3 агента: Sales, Optimization, Narrative)
- ✅ Создан план-документ + TaskList на 8 фаз
- ✅ **Phase 1**: миграция `010_ai_recommendations.sql` + `app/models/ai.py` — применено локально
- ✅ **Phase 2**: `app/services/ai/data_collector.py` — заменяет MCP, smoke-тест на Sandyq Turkestan (11 forecast / 79 hourly)
- ✅ **Phase 3**: `engines/` — Claude/OpenAI/Gemini c retry-логикой и логированием
- ✅ **Phase 6**: добавлены 8 env-переменных, поставлены `anthropic==0.42.0` + `openai==1.59.2`
- ✅ **Phase 4**: `multi_agent_system.py` — 3 включённых агента, `compress_data_for_tokens`, async-оркестрация
- ✅ **Phase 5**: 8 endpoints в `routers/ai_recommendations.py`, **end-to-end тест с реальным Claude прошёл**:
  - 91 секунда на 3 агента
  - SalesAnalysisAgent: 4682 токена, 20с
  - OptimizationAgent: 3063 токена, 28с
  - NarrativeAgent: 5200 токенов, 28с
- ✅ **Phase 7**: React страница, sidebar пункт «AI АНАЛИТИКА», новые UI-компоненты (Tabs/Textarea), `pnpm build` без ошибок
- 🟡 **Phase 8**: локальные проверки прошли, остался деплой на прод (вручную: миграция + ключи + docker rebuild)

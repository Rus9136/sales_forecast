# Session Log: Перенос фичи «Рекомендации ИИ» из hr-miniapp в SalesForecast

**Дата**: 2026-04-30
**Время**: 09:18 (локальное)
**Длительность сессии**: ~2.5 часа
**Исполнитель**: Claude (Opus 4.7 1M)
**Заказчик**: abdunazarovryskeldy@gmail.com
**Статус**: ✅ Код готов и протестирован локально · ⏳ Деплой за пользователем

---

## 🎯 Постановка задачи

Перенести фичу «Рекомендации ИИ» (мультиагентный анализ продаж/ФОТ/отзывов) из проекта **hr-miniapp** (`/root/projects/hr-miniapp`, Node.js) в проект **SalesForecast** (`/root/projects/SalesForecast/sales_forecast`, Python/FastAPI).

**Главная цель**: убрать зависимость от MCP API сервера (`mcp.madlen.space`) — данные `forecast`, `plan_vs_fact`, `hourly_sales` уже лежат в локальной PostgreSQL базе SalesForecast.

**Согласованный подход — Вариант A**: переносить только тех агентов, которым хватает локальных данных. Payroll/Staffing/Reviews — отложены (нет источников данных в SalesForecast).

---

## 📋 Что было сделано

### Изученные источники
- `/root/projects/hr-miniapp/backend/routes/ai-recommendations.js` (656 строк)
- `/root/projects/hr-miniapp/backend/services/multi-agent-system.js` (890 строк)
- `/root/projects/hr-miniapp/backend/services/mcp-client.js` (202 строки)
- `/root/projects/hr-miniapp/backend/services/anthropic-client.js` (391 строка)
- `/root/projects/hr-miniapp/backend/engines/*` (5 файлов)
- `/root/projects/hr-miniapp/ai-recommendations.js` (1878 строк frontend)
- Структура SalesForecast (FastAPI + React 19 + TanStack Query)

### Ключевые архитектурные решения
1. **MCP убран полностью** — заменён прямыми SQL-запросами к локальной БД
2. **department_id**: используется `Department.id` (UUID). Подтверждено: `forecasts.branch_id` 1:1 совпадает с `departments.id` (2266 записей JOIN-ятся)
3. **Только 3 агента включены**: `SalesAnalysisAgent`, `OptimizationAgent`, `NarrativeAgent`
4. **3 агента отключены** (`enabled=False`) с заглушками, чтобы можно было включить позже без изменения архитектуры: `PayrollAnalysisAgent`, `StaffingAgent`, `ReputationAgent`
5. **API ключи**: 5 изолированных Claude-ключей (как в hr-miniapp). Если специальный ключ агента не задан — fallback на основной `ANTHROPIC_API_KEY`
6. **Промпты**: дефолтные хардкоженые в `prompts.py` + DB-таблица `ai_prompts` для редактирования. DB-row имеет приоритет над дефолтом.
7. **Логирование**: каждый вызов AI пишется в `ai_prompt_logs` с полным промптом, ответом, токенами и временем

---

## 🛠 Реализация по фазам

### Phase 1 — БД и SQLAlchemy модели ✅
**Файлы**:
- `migrations/010_ai_recommendations.sql` — 3 таблицы:
  - `ai_recommendations` (id, department_id UUID FK, date_start, date_end, mcp_response JSONB, agent_results JSONB, provider, created_at)
  - `ai_prompt_logs` (id, analysis_id FK, agent_name, provider, full_prompt, response_text, success, tokens_used, request/response_timestamp)
  - `ai_prompts` (agent_name PK, prompt_text, updated_at)
- `app/models/ai.py` — `AIRecommendation`, `AIPromptLog`, `AIPrompt`
- Регистрация в `app/models/__init__.py`

**Применено локально** на dev-БД (порт 5435). Все 3 таблицы созданы.

### Phase 2 — Data collector (замена MCP) ✅
**Файл**: `app/services/ai/data_collector.py`

Функция `collect_dashboard_data(db, department_id, date_start, date_end)` возвращает dict в формате, совместимом с агентами hr-miniapp:
- `forecast` — JOIN `forecasts` + `sales_summary`
- `plan_vs_fact` — `sales_summary` LEFT JOIN `forecasts` + расчёт `error_percentage`
- `hourly_sales` — прямой SELECT из `sales_by_hour`
- `department_info` — JOIN `departments` + parent (для `object_company`)
- `payroll`, `reviews` → `None` (Variant A)

**Smoke-тест**: Sandyq Turkestan, 11 forecast / 11 plan_vs_fact / 79 hourly за 11 дней.

### Phase 3 — AI движки ✅
**Файлы**:
- `app/services/ai/engines/base.py` — `BaseEngine` ABC + `AgentResult` dataclass
- `app/services/ai/engines/_logging.py` — общая функция логирования в `ai_prompt_logs`
- `app/services/ai/engines/claude_engine.py` — `anthropic.AsyncAnthropic` с retry (529: 30/90/180/360/600s)
- `app/services/ai/engines/openai_engine.py` — `openai.AsyncOpenAI` с обработкой `RateLimitError`/`APIStatusError`
- `app/services/ai/engines/gemini_engine.py` — заглушка
- `app/services/ai/engines/dispatcher.py` — `EngineDispatcher`, кешированный `get_dispatcher()`

**Smoke-тест**: `providers_info()` возвращает корректный JSON, Claude сконфигурирован.

### Phase 4 — Мультиагентная система ✅
**Файлы**:
- `app/services/ai/prompts.py` — `DEFAULT_PROMPTS` для 6 агентов, `get_prompt(db, name)`, `upsert_prompt`, `list_all_prompts`
- `app/services/ai/multi_agent_system.py`:
  - `AGENTS` registry с `enabled` flag (3 включены)
  - `compress_data_for_tokens()` — портирован из JS
  - `render_prompt()` с подстановкой `{forecast}`, `{plan_vs_fact}`, `{hourly_sales}`, `{department_info}`, `{agent_results}`
  - `MultiAgentSystem.run_analysis()` async — Phase 1 → Phase 2, паузы `asyncio.sleep`
  - `run_single_agent()` для rerun-agent
  - Возвращает `AnalysisOutcome` (success, results, errors, skipped, metadata)

### Phase 5 — API роутер ✅
**Файлы**:
- `app/schemas/ai.py` — Pydantic схемы (AnalyzeRequest, HistoryItem, AnalyzeResponse, PromptInfo, RerunAgentRequest, AnalysisPromptsResponse...)
- `app/routers/ai_recommendations.py` — 8 endpoints:
  - `POST /api/ai-recommendations/analyze`
  - `GET /api/ai-recommendations/history` (с `department_id` фильтром)
  - `GET /api/ai-recommendations/analysis/{id}`
  - `GET /api/ai-recommendations/prompts/{analysis_id}` — UI tabs
  - `GET /api/ai-recommendations/prompts`
  - `PUT /api/ai-recommendations/prompts`
  - `POST /api/ai-recommendations/rerun-agent` (с `flag_modified` для JSONB)
  - `GET /api/ai-recommendations/providers`

Все защищены `Depends(get_api_key_or_bypass)`. Зарегистрирован в `app/main.py`.

### Phase 6 — Конфигурация и зависимости ✅
**Изменения**:
- `app/config.py` — добавлены 8 переменных:
  - `ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_PAYROLL`, `_STAFFING`, `_NARRATIVE`, `_REPUTATION`
  - `OPENAI_API_KEY`, `OPENAI_MODEL`, `CLAUDE_MODEL`
- `requirements.txt` — `anthropic==0.42.0`, `openai==1.59.2`
- Установлены в venv: `pip install anthropic==0.42.0 openai==1.59.2` ✅
- `.env.example` и `.env.prod.example` — добавлена секция `### AI Recommendations ###`

### Phase 7 — Frontend (React) ✅
**Файлы**:
- `frontend/src/types/ai.ts` — 11 интерфейсов (AIProvider, AIAnalyzeRequest, AIHistoryItem, AIPromptInfo, AIPromptLog, AIAnalysisDetail...)
- `frontend/src/hooks/use-ai-recommendations.ts` — 7 хуков:
  - `useAIProviders`, `useAIPrompts`, `useUpdateAIPrompts`
  - `useAIHistory`, `useAIAnalysisPrompts`
  - `useRunAIAnalysis`, `useRerunAgent`
- `frontend/src/components/ui/tabs.tsx` — обёртка над `@radix-ui/react-tabs`
- `frontend/src/components/ui/textarea.tsx` — для редактора промптов
- `frontend/src/pages/ai-recommendations-page.tsx`:
  - Форма запуска (department + период + provider) с прогрессом
  - Тулбар с кнопкой «Промпты агентов» (Dialog)
  - Боковая панель истории анализов
  - Tabs для агентов с под-табами «Результат» / «Промпт» (показывает токены, время, status)
  - Кнопка «Перезапустить агента»
- `Sidebar` — раздел «AI АНАЛИТИКА» → «Рекомендации ИИ»
- `App.tsx` — роут `/ai-recommendations`

**TypeScript-сборка**: `pnpm build` → 0 ошибок, 859kB JS bundle.

### Phase 8 — Локальное тестирование ✅
**End-to-end тест с реальным Claude**:
```bash
POST /api/ai-recommendations/analyze
{
  "department_id": "e8cba932-e56d-4fe7-bbc9-01c92b765a4c",
  "date_start": "2026-03-01",
  "date_end": "2026-03-07",
  "provider": "claude"
}
```

**Результат**: HTTP 200, 91.4 секунды:

| Агент | Prompt chars | Response chars | Tokens | Время |
|-------|-------------:|---------------:|-------:|------:|
| SalesAnalysisAgent | 6853 | 2468 | 4682 | 20.0с |
| OptimizationAgent | 2738 | 3648 | 3063 | 27.8с |
| NarrativeAgent | 6750 | 4204 | 5200 | 27.8с |

Все 3 агента отработали, результаты в `agent_results` JSONB, логи в `ai_prompt_logs`.

**Проверены endpoints**:
- ✅ `GET /providers` — возвращает корректный JSON с `configured: true` для Claude
- ✅ `GET /history` — показывает запись после анализа
- ✅ `GET /analysis/{id}` — полные данные
- ✅ `GET /prompts/{analysis_id}` — UI-данные с агентами и промптами
- ✅ `GET /prompts` — 6 шаблонов (3 default-source × 3 active + 3 disabled)
- ✅ `PUT /prompts` — обновление работает, `source` меняется на `db`
- ✅ SPA отдаётся на `/ai-recommendations` через FastAPI catch-all

---

## 📂 Созданные/изменённые файлы

### Новые backend файлы (12)
```
migrations/010_ai_recommendations.sql
app/models/ai.py
app/schemas/ai.py
app/routers/ai_recommendations.py
app/services/ai/__init__.py
app/services/ai/data_collector.py
app/services/ai/multi_agent_system.py
app/services/ai/prompts.py
app/services/ai/engines/__init__.py
app/services/ai/engines/_logging.py
app/services/ai/engines/base.py
app/services/ai/engines/claude_engine.py
app/services/ai/engines/openai_engine.py
app/services/ai/engines/gemini_engine.py
app/services/ai/engines/dispatcher.py
```

### Новые frontend файлы (5)
```
frontend/src/types/ai.ts
frontend/src/hooks/use-ai-recommendations.ts
frontend/src/components/ui/tabs.tsx
frontend/src/components/ui/textarea.tsx
frontend/src/pages/ai-recommendations-page.tsx
```

### Изменённые файлы
```
app/config.py             — добавлены 8 env-переменных
app/models/__init__.py    — регистрация AI моделей
app/main.py               — регистрация роутера ai_recommendations
requirements.txt          — anthropic, openai
.env.example              — секция AI Recommendations
.env.prod.example         — секция AI Recommendations
frontend/src/App.tsx      — роут /ai-recommendations
frontend/src/components/layout/sidebar.tsx — пункт "AI АНАЛИТИКА"
```

### Документация
```
AI_RECOMMENDATIONS_MIGRATION_PLAN.md  — план + прогресс по 8 фазам
SESSION_LOG_AI_RECOMMENDATIONS_MIGRATION_20260430_091808.md  — этот лог
```

---

## 🚀 Что осталось сделать пользователю

Деплой на прод (не выполнено в этой сессии, поскольку требует вмешательства в `.env.prod` и боевой контейнер):

```bash
cd /root/projects/SalesForecast/sales_forecast

# 1. Применить миграцию на prod-БД
docker exec -i sales-forecast-db psql -U sales_user -d sales_forecast \
    < migrations/010_ai_recommendations.sql

# 2. Прописать в .env.prod минимум:
#    ANTHROPIC_API_KEY=sk-ant-api03-...
#    (опционально: специализированные _PAYROLL/_STAFFING/_NARRATIVE/_REPUTATION ключи)
#    (опционально: OPENAI_API_KEY=...)

# 3. Пересобрать и перезапустить контейнер
docker-compose -f docker-compose.prod.yml build sales-forecast-app
docker-compose -f docker-compose.prod.yml up -d sales-forecast-app

# 4. Проверить
curl -s https://aqniet.site/health
curl -s -H "Authorization: Bearer $API_TOKEN" \
    https://aqniet.site/api/ai-recommendations/providers

# 5. Открыть UI
# https://aqniet.site/ai-recommendations
```

---

## 🔮 Возможные расширения

Для включения отключённых агентов (Phase 2 в будущем):

### 1. Включить `PayrollAnalysisAgent` и `StaffingAgent`
Источники данных:
- **Вариант A**: использовать существующий `sales_by_waiter` + ввести таблицу `shifts` (структура смен)
- **Вариант B**: подключиться к hr-miniapp PostgreSQL (порт 5437) через `psycopg2` второй сессией БД и брать `payroll`/смены оттуда

После того как данные будут доступны:
1. В `app/services/ai/data_collector.py` заполнить `payroll` секцию вместо `None`
2. В `app/services/ai/multi_agent_system.py` поменять `enabled=True` для нужных агентов
3. Готово — оркестратор уже умеет их запускать

### 2. Включить `ReputationAgent`
Нужен источник отзывов. Можно подключить к `reviews-parser` сервису (видел его на `:8004`).

### 3. Прогресс-индикация в UI
Сейчас при запуске анализа frontend ждёт 60-90 секунд без прогресса. Можно сделать через:
- WebSocket → стримить per-agent статус
- SSE
- Polling: добавить endpoint `GET /analyze-status/{id}` который будет читать `ai_prompt_logs`

### 4. Экспорт результатов
Добавить endpoints:
- `GET /api/ai-recommendations/{id}/export/pdf`
- `GET /api/ai-recommendations/{id}/export/markdown`

---

## 📊 Метрики

- **Строк кода написано**: ~2300 (backend Python ~1500, frontend TS ~600, SQL ~80, docs ~200)
- **Файлов создано**: 17 новых, 8 изменённых
- **Endpoints**: 8 (POST analyze, GET history/analysis/prompts/providers, GET/PUT prompts, POST rerun-agent)
- **Агентов реализовано**: 6 в коде (3 включены сразу + 3 готовы к включению)
- **AI провайдеров**: 3 (Claude — полный, OpenAI — полный, Gemini — заглушка)
- **Время реального анализа Claude**: 91 секунда на 3 агента (12,945 токенов суммарно)
- **TypeScript-сборка**: 0 ошибок, 859kB bundle (предупреждение о размере, можно code-split)

---

## 🐛 Возникшие проблемы и решения

| Проблема | Решение |
|----------|---------|
| `openai==1.59.0` не существует на PyPI | Использован `1.59.2` (ближайшая stable) |
| `jinja2` не установлен в venv | `pip install jinja2==3.1.6 apscheduler==3.11.2` |
| `EmptyState` принимает только `text`, не `icon`+`title` | Заменены вызовы на простую сигнатуру |
| `forecasts.branch_id` хранит UUID как string, не FK | SQL JOIN с `::text` cast — работает |
| SQLAlchemy не видит изменения `agent_results` JSONB | Добавлен `flag_modified(rec, "agent_results")` в rerun-agent |
| `uvicorn` exited когда работал из `/root` без cd | Запуск через `cd /root/projects/SalesForecast/sales_forecast && ./venv/bin/uvicorn` |

---

## 🎓 Уроки и наблюдения

1. **Прямой SQL быстрее MCP**: hr-miniapp ждал 30+ секунд только на MCP вызов. SalesForecast версия делает то же самое за миллисекунды.
2. **JSONB в PostgreSQL** — отличный формат для хранения mcp_response и agent_results: гибко, индексируемо, не нужны миграции при изменении структуры данных.
3. **Изолированные API-ключи** работают через простой dict-mapping в `claude_engine.py` — не нужны 5 разных классов как в hr-miniapp.
4. **Async/await в Python** напрямую переносится из JS Promises — `await asyncio.sleep()` ↔ `await new Promise(setTimeout)`.
5. **TanStack Query** — отличный кеш для UI: автоматическая инвалидация после mutations упрощает код страницы.
6. **Архитектура с `enabled` flag** даёт безболезненное расширение: добавить агента — это поменять `False` на `True`, ничего другого трогать не надо.

---

**Конец сессии**: 2026-04-30 09:18
**Следующий шаг**: деплой на прод (за пользователем)

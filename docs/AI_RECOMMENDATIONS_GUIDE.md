# AI Recommendations — руководство

Подсистема мультиагентного AI-анализа работы подразделения. Портирована из `hr-miniapp` (Node.js) в SalesForecast (FastAPI). MCP-зависимость убрана: данные читаются прямыми SQL-запросами к локальной PostgreSQL.

**Последний деплой**: 2026-04-30, коммит `19406cc`. Endpoint доступен на `https://aqniet.space/ai-recommendations`.

---

## 1. Что работает сейчас (Variant A)

### Включённые агенты (3)

| Агент | Роль | Источники данных | Phase |
|---|---|---|---|
| `SalesAnalysisAgent` | Аналитик динамики выручки, пиков и провалов | `forecasts`, `sales_summary`, `sales_by_hour` | 1 |
| `OptimizationAgent` | Консультант по оптимизации (синтез) | результаты Phase 1 | 2 |
| `NarrativeAgent` | Бизнес-консультант, итоговый отчёт | результаты Phase 1 + `department_info` | 2 |

### Отключённые агенты (3) — структура готова, нет данных

| Агент | Роль | Что нужно для включения |
|---|---|---|
| `PayrollAnalysisAgent` | Аналитик ФОТ | Источник payroll — нет в SalesForecast |
| `StaffingAgent` | Оптимизация смен | Расписание смен — нет в SalesForecast |
| `ReputationAgent` | Анализ отзывов | Парсер отзывов — нет в SalesForecast |

В `multi_agent_system.py` лежат с `enabled=False`. Промпты для них уже есть в `DEFAULT_PROMPTS`. Чтобы включить — заполнить соответствующую секцию в `data_collector.py` и поменять флаг.

### AI-провайдеры

| Провайдер | Статус | Реализация |
|---|---|---|
| Claude (Anthropic) | ✅ Production | `anthropic.AsyncAnthropic`, retry на 529 (30/90/180/360/600s + jitter), per-agent изолированные ключи |
| OpenAI | ✅ Реализован, не настроен (нет ключа) | `openai.AsyncOpenAI`, retry на 429/5xx |
| Gemini | ❌ Заглушка | Заглушка возвращает «not implemented» |

### Реальные метрики (Claude Sonnet 4, период 7 дней)

| Агент | Prompt | Response | Tokens | Время |
|---|---:|---:|---:|---:|
| SalesAnalysisAgent | ~11k chars | ~2.5k chars | ~6800 | 20-25с |
| OptimizationAgent | ~3k chars | ~4k chars | ~3300 | 28-35с |
| NarrativeAgent | ~7k chars | ~4.5k chars | ~5500 | 28-30с |
| **Итого** | | | **~15-16k** | **~90-110с** |

---

## 2. Архитектура

### Слои

```
HTTP request (Bearer auth)
    ↓
Router (app/routers/ai_recommendations.py — 8 endpoints)
    ↓
MultiAgentSystem.run_analysis() (app/services/ai/multi_agent_system.py)
    ├─ Phase 1: SalesAnalysisAgent (+ Payroll/Staffing/Reputation если enabled)
    └─ Phase 2: OptimizationAgent → NarrativeAgent (используют результаты Phase 1)
        ↓
    BaseEngine.analyze_with_agent() (app/services/ai/engines/{claude,openai,gemini}_engine.py)
        ↓
    HTTP → Anthropic / OpenAI API
        ↓
    log_prompt() → ai_prompt_logs
```

### Поток данных

1. **Endpoint `/analyze`** принимает `department_id`, `date_start`, `date_end`, `provider`.
2. **`collect_dashboard_data()`** делает 4 SQL-запроса:
   - `forecast`: JOIN `forecasts` + `sales_summary` (предсказание + факт по датам)
   - `plan_vs_fact`: `sales_summary` LEFT JOIN `forecasts` + расчёт `error_percentage`
   - `hourly_sales`: SELECT из `sales_by_hour`
   - `department_info`: SELECT `departments` + parent (для object_company)
3. Создаётся запись `ai_recommendations` с `mcp_response = raw_data` (JSONB снапшот).
4. **`compress_data_for_tokens()`** сжимает суммы до `Nk`-формата, обрезает выборки (forecast `[:10]`, plan_vs_fact `[:10]`, hourly_sales `[-168:]` = 7 дней).
5. **Phase 1**: для каждого `enabled` агента, чьи `data_fields` присутствуют в данных:
   - `render_prompt()` подставляет плейсхолдеры `{forecast}`, `{plan_vs_fact}`, `{hourly_sales}` и т.д.
   - `engine.analyze_with_agent()` шлёт запрос провайдеру, ловит retry, логирует через `log_prompt()`.
   - Результат сохраняется в `results: dict[agent_name, str]`.
   - Пауза `pause_after_seconds` через `asyncio.sleep` (5с по умолчанию).
6. **Phase 2** работает аналогично, но в шаблон промпта подставляется `{agent_results}` — конкатенация результатов Phase 1 (обрезанных до 500 символов каждый).
7. После всех агентов `ai_recommendations.agent_results` обновляется JSONB-объектом `{agent_name: response_text}`.

### Изолированные ключи Claude

Каждому агенту можно задать отдельный API-ключ через `.env.prod`:

```
ANTHROPIC_API_KEY=sk-ant-...           # Основной (fallback для всех)
ANTHROPIC_API_KEY_PAYROLL=sk-ant-...   # PayrollAnalysisAgent
ANTHROPIC_API_KEY_STAFFING=sk-ant-...  # StaffingAgent
ANTHROPIC_API_KEY_NARRATIVE=sk-ant-... # NarrativeAgent
ANTHROPIC_API_KEY_REPUTATION=sk-ant-...# ReputationAgent
```

Зачем: каждая Anthropic-организация имеет независимый rate limit. С разнесёнными ключами 5 агентов могут идти параллельно без 529-ошибок. SalesAnalysisAgent / OptimizationAgent всегда используют основной ключ.

Если per-agent ключ пустой — fallback на `ANTHROPIC_API_KEY`. Логика в `claude_engine.py:_resolve_key()`.

### Retry-логика

**Claude:**
- 529 (overload): backoff `[30, 90, 180, 360, 600]` секунд + случайный jitter 0-15с. Жёстко, потому что 529 — реальная перегрузка серверов Anthropic, мгновенный ретрай только усугубит.
- 5xx прочие: exponential backoff `5 × 2^(attempt-1)` с потолком 30с.
- 4xx: не ретраится, моментальный фейл.
- Network errors: ретраится с тем же exponential backoff.

**OpenAI:**
- 429 (rate limit): `15 × 2^(attempt-1)` с потолком 240с.
- 5xx: exponential до 30с.
- 4xx (кроме 429): не ретраится.

Максимум 5 попыток на агента.

### Compression / token economy

`compress_data_for_tokens()` (multi_agent_system.py:104):
- Денежные суммы → `Nk` (округление до тысяч): `1234567 → "1235k"`.
- `forecast`: первые 10 строк.
- `plan_vs_fact`: первые 10 строк.
- `hourly_sales`: последние 168 строк (7 дней × 24 часа). Без этого лимита 30-дневный период давал бы 720 строк → промпт ~25k chars.
- `agent_results` (для Phase 2): каждый ответ обрезается до 500 символов.

Цель — держать промпт ниже 12k символов на агента.

### Audit log

Каждый вызов AI-провайдера пишет строку в `ai_prompt_logs`:
- `analysis_id` (FK → `ai_recommendations`, NULL для отдельных смок-тестов)
- `agent_name`, `provider`
- `full_prompt` (полный текст), `system_prompt`, `prompt_length`
- `response_text`, `response_length`
- `request_timestamp`, `response_timestamp` (для расчёта времени ответа)
- `success`, `error_message`
- `tokens_used` (input + output для Claude, total для OpenAI)

Защитное логирование: если `db.add(log)` падает, ошибка swallow'ится — анализ не должен валиться из-за проблем с аудитом.

### Snapshot для воспроизводимости

В `ai_recommendations.mcp_response` хранится сырой ответ data_collector'а (JSONB). Это позволяет:
- Запустить `rerun-agent` без повторного SQL-запроса.
- Воспроизвести анализ через 6 месяцев (даже если sales_summary поменялся).
- Дебажить — видно какие именно данные ушли в LLM.

---

## 3. База данных

### Таблицы (3)

```sql
ai_recommendations (
  id              SERIAL PRIMARY KEY,
  department_id   UUID FK → departments.id ON DELETE CASCADE,
  date_start      DATE,
  date_end        DATE,
  mcp_response    JSONB,             -- snapshot входных данных (имя устаревшее, унаследовано от hr-miniapp)
  agent_results   JSONB,             -- {agent_name: response_text}
  provider        VARCHAR(50),       -- 'claude' | 'openai' | 'gemini'
  created_at      TIMESTAMP
);

ai_prompt_logs (
  id                  SERIAL PRIMARY KEY,
  analysis_id         INTEGER FK → ai_recommendations.id ON DELETE CASCADE (NULL ok),
  agent_name          VARCHAR(100),
  provider            VARCHAR(50),
  full_prompt         TEXT,
  prompt_length       INTEGER,
  system_prompt       TEXT,
  response_text       TEXT,
  response_length     INTEGER,
  request_timestamp   TIMESTAMP,
  response_timestamp  TIMESTAMP,
  success             BOOLEAN,
  error_message       TEXT,
  tokens_used         INTEGER
);

ai_prompts (
  agent_name   VARCHAR(50) PRIMARY KEY,
  prompt_text  TEXT,
  updated_at   TIMESTAMP
);
```

### Индексы

- `ai_recommendations`: department_id, created_at DESC, (date_start, date_end)
- `ai_prompt_logs`: analysis_id, agent_name, request_timestamp DESC

### Миграция

Файл: `migrations/010_ai_recommendations.sql` (idempotent — `CREATE IF NOT EXISTS`).

```bash
docker exec -i sales-forecast-db psql -U sales_user -d sales_forecast \
  < migrations/010_ai_recommendations.sql
```

---

## 4. API endpoints

Все защищены `Depends(get_api_key_or_bypass)` (Bearer-токен или DB API key).

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/ai-recommendations/providers` | Список настроенных AI-провайдеров с моделями |
| POST | `/api/ai-recommendations/analyze` | Запуск мультиагентного анализа (90-110с) |
| GET | `/api/ai-recommendations/history` | История запусков (фильтр `department_id`, пагинация) |
| GET | `/api/ai-recommendations/analysis/{id}` | Детали одного анализа |
| GET | `/api/ai-recommendations/prompts/{analysis_id}` | UI-shaped: агенты + результаты + логи промптов для табов |
| GET | `/api/ai-recommendations/prompts` | Все шаблоны промптов (DB > default) |
| PUT | `/api/ai-recommendations/prompts` | Обновить шаблоны промптов |
| POST | `/api/ai-recommendations/rerun-agent` | Перезапустить одного агента в существующем анализе |

### Примеры

```bash
# Запуск анализа
curl -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  https://aqniet.space/api/ai-recommendations/analyze \
  -d '{
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "date_start": "2026-03-01",
    "date_end": "2026-03-07",
    "provider": "claude"
  }'

# Перезапуск агента с новым промптом
curl -X POST -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  https://aqniet.space/api/ai-recommendations/rerun-agent \
  -d '{
    "analysis_id": 2,
    "agent_name": "SalesAnalysisAgent",
    "new_prompt": "...",
    "provider": "claude"
  }'
```

---

## 5. Frontend

**Страница**: `/ai-recommendations` (`frontend/src/pages/ai-recommendations-page.tsx`)

**Компоненты**:
- Форма запуска: department selector + date range + provider + кнопка «Запустить анализ»
- Прогресс-бар на 1-2 минуты с пояснением «3 агента последовательно»
- Боковая панель «История анализов» — список прошлых запусков
- Tabs по агентам, в каждом — sub-tabs «Результат» / «Промпт» (с метриками: токены, время, статус, system prompt)
- Кнопка «Перезапустить агента» в каждом табе
- Dialog «Промпты агентов» — редактор всех 6 шаблонов через Textarea, отображает `source: db | default`

**Hooks** (`frontend/src/hooks/use-ai-recommendations.ts`):
- `useAIProviders` — какие провайдеры настроены
- `useAIPrompts` / `useUpdateAIPrompts`
- `useAIHistory` — история запусков
- `useAIAnalysisPrompts` — UI-shaped данные одного анализа
- `useRunAIAnalysis` — POST /analyze (mutation)
- `useRerunAgent` — POST /rerun-agent (mutation)

---

## 6. Конфигурация

### Environment variables

```bash
# Минимально — основной ключ Claude
ANTHROPIC_API_KEY=sk-ant-api03-...

# Опционально — изолированные per-agent ключи (fallback на основной)
ANTHROPIC_API_KEY_PAYROLL=
ANTHROPIC_API_KEY_STAFFING=
ANTHROPIC_API_KEY_NARRATIVE=
ANTHROPIC_API_KEY_REPUTATION=

# OpenAI (опционально — позволяет выбрать провайдер в UI)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# Модель Claude
CLAUDE_MODEL=claude-sonnet-4-20250514
```

### Nginx

Для `/api/ai-recommendations/` в `/etc/nginx/sites-available/aqniet.conf` стоит:

```nginx
location /api/ai-recommendations/ {
    proxy_pass http://localhost:8002;
    proxy_read_timeout 180s;
    proxy_send_timeout 180s;
    proxy_connect_timeout 30s;
}
```

Без `proxy_read_timeout 180s` дефолтный 60-секундный таймаут обрывал длинные анализы.

---

## 7. TODO — что нужно для полноценной работы

### 🔴 Критично для бизнес-ценности

#### 7.1 Включить `PayrollAnalysisAgent` и `StaffingAgent`

**Что не хватает**: данных о ФОТ и графиках смен.

**Варианты источника данных**:
- **Вариант A**: добавить в SalesForecast таблицы `shifts` (расписание) и `payroll_records` (выплаты), завести синхронизацию из iiko. iiko OLAP даёт `Department.Id, EmployeeName, OpenDate, Hours`.
- **Вариант B**: подключиться к hr-miniapp PostgreSQL (порт 5437) через второй SQLAlchemy session или psycopg2 connection pool — там уже есть payroll/shifts. Это «легче» по объёму работы, но создаёт coupling между двумя проектами.
- **Вариант C**: договориться с финансами о выгрузке ФОТ через 1С Exchange (5555) аналогично departments.

**Рекомендация**: Вариант B на короткой дистанции (быстрее, hr-miniapp уже работает), Вариант A на длинной дистанции (sales_forecast становится самодостаточным).

**Шаги после получения данных**:
1. В `app/services/ai/data_collector.py` заполнить секцию `payroll`:
   ```python
   def _get_payroll(db, department_id, date_start, date_end) -> list[dict]:
       # SELECT FROM payroll_records ... + JOIN shifts ...
       return [{
         "employee_name": ...,
         "shifts": [{"date": ..., "hours": ...}, ...],
         "payroll_total": ...,
       }, ...]
   ```
2. В `multi_agent_system.AGENTS` поменять `enabled=False → True` для `PayrollAnalysisAgent` и `StaffingAgent`.
3. Переразвернуть.

Промпты уже есть в `DEFAULT_PROMPTS` — оркестратор сам подхватит.

#### 7.2 Включить `ReputationAgent`

**Что не хватает**: источника отзывов.

В проекте на сервере есть `reviews-parser` на порту 8004 + `reviews-redis` (порт 6379). Скорее всего там лежат отзывы Yandex/2GIS/Google.

**Шаги**:
1. Договориться с командой `reviews-parser` об API контракте: `GET /reviews?department_id=&from=&to=` → JSON с `[{rating, text, author, source, date}]`.
2. В `data_collector.py` добавить `_get_reviews()` через httpx-клиент к 8004.
3. Поставить timeout 5-10с на этот вызов и graceful degradation: если reviews-parser недоступен → `reviews=None`, `ReputationAgent` попадёт в `skipped`.
4. `enabled=True` для `ReputationAgent`.

### 🟡 Качество промптов и результатов

#### 7.3 Промпты не оптимизированы

Сейчас в `DEFAULT_PROMPTS` лежат базовые шаблоны, портированные из hr-miniapp. Они работают, но:
- Не используют системную информацию о подразделении (бренд, сегмент, локация) для контекста — это есть в `compressed["department_info"]`, но в шаблонах не упомянуто.
- Нет явного запроса на структурированный вывод (markdown headings, bullet lists) — модель сама решает формат, и это даёт неровный UI.
- Нет few-shot примеров для конкретных проблем (низкий чек, длинный простой и т.д.).

**Действия**:
- Прогнать 5-10 реальных анализов на разных подразделениях (Plaza vs Аэропорт vs Колос — разные сегменты).
- Сравнить результаты, переписать промпты под единый формат «# Резюме / ## Что хорошо / ## Что плохо / ## Рекомендации».
- Добавить в шаблоны явное `Используй следующий формат: ...`.

#### 7.4 Нет валидации структуры ответа

LLM иногда возвращает неструктурированный текст. Идеально:
- Использовать `tool_use` API (Claude) или `response_format: json_schema` (OpenAI gpt-4o) для гарантии формата.
- Парсить ответ в `dict` со схемой `{summary: str, strengths: list[str], weaknesses: list[str], recommendations: list[str]}`.
- Сохранять в `agent_results` уже структурированный JSON, фронт рендерит его в типизированный layout.

Это большая переработка — пока приемлемо хранить plain text.

### 🟢 UX и операционные улучшения

#### 7.5 Прогресс-бар во время анализа

Сейчас при `POST /analyze` фронт ждёт 90-110с с прогресс-плашкой «Идёт анализ...» без реальных индикаторов. Варианты:
- **Polling**: добавить endpoint `GET /api/ai-recommendations/analyze-status/{id}` — читает `ai_prompt_logs` для `analysis_id` и возвращает `{completed_agents: [...], in_progress: <name>, total: 3}`. Фронт опрашивает каждые 2с.
- **SSE (Server-Sent Events)**: стримить per-agent статус. Сложнее, но без polling.
- **WebSocket**: оверкилл для одного запроса.

**Рекомендация**: polling. Нужно создать запись в `ai_recommendations` ДО запуска агентов (уже так и сделано), и тогда `analyze-status` просто читает `ai_prompt_logs WHERE analysis_id = X`.

#### 7.6 Background-запуск анализа

Сейчас `POST /analyze` синхронный — клиент держит соединение 90+ секунд. Если nginx таймаут или клиент отвалится — анализ теряется.

**Решение**:
- Запускать анализ как `asyncio.create_task()` или через APScheduler one-off.
- `POST /analyze` сразу возвращает `{analysis_id: N, status: "running"}` (~1с).
- Клиент опрашивает `analyze-status/{id}`.

Плюс: можно ставить много анализов в очередь, не блокируя webserver.

#### 7.7 Экспорт результатов

Endpoints, которых не хватает:
- `GET /api/ai-recommendations/{id}/export/markdown` — markdown с заголовками для копипаста в Notion/Slack.
- `GET /api/ai-recommendations/{id}/export/pdf` — для отправки управляющему по почте.

В hr-miniapp было — стоит портировать.

#### 7.8 Сравнение анализов

Сейчас можно посмотреть только один анализ. Полезно:
- Запустить анализ за апрель и за май одного и того же подразделения.
- В UI видеть две колонки рядом, подсветить что улучшилось / ухудшилось.

### 🔵 Тех-долг и рефакторинг

#### 7.9 Переименовать `mcp_response` → `input_data`

Колонка названа исторически, MCP убрали. Новый разработчик путается.

```sql
ALTER TABLE ai_recommendations RENAME COLUMN mcp_response TO input_data;
```

Параллельно обновить `app/models/ai.py`, `app/routers/ai_recommendations.py`. Не блокирующее, но сделать отдельным PR.

#### 7.10 Удалить мёртвый код для payroll/reviews в `compress_data_for_tokens`

Если решено что Variant A — постоянное состояние (хотя бы на полгода), убрать ветки `if payroll:` и `if reviews:` из `multi_agent_system.py:161-180`. Сейчас они лежат как «задел», но код не покрыт тестами.

После включения Payroll/Staffing/Reputation код вернётся, но к тому моменту, скорее всего, формат данных будет другой — лучше написать заново.

#### 7.11 Тесты

В `tests/` нет ни одного теста для AI-подсистемы. Минимально нужно:
- Unit-тест `compress_data_for_tokens()` с разными размерами входа.
- Unit-тест `render_prompt()` — корректная подстановка плейсхолдеров и graceful degradation если их нет.
- Unit-тест retry-логики `claude_engine._retry_delay()` для 529 vs 5xx.
- Integration-тест с моком `AsyncAnthropic` — проверить что `MultiAgentSystem.run_analysis()` правильно зовёт Phase 1 → Phase 2, что `ai_prompt_logs` пишется.

Без тестов рефакторинг рискован.

#### 7.12 Кеш отчётов

Один и тот же подразделение × период × provider — детерминированный (с точностью до timestamp в данных). Можно кешировать результат на 24 часа:
- При `POST /analyze` сначала `SELECT FROM ai_recommendations WHERE department_id=? AND date_start=? AND date_end=? AND provider=? AND created_at > NOW() - INTERVAL '24 hours'`.
- Если есть — вернуть существующий вместо нового вызова Claude.
- Параметр `force=true` в payload — пропустить кеш.

Экономия токенов и времени.

### 🟣 Расширение функциональности

#### 7.13 Сравнение нескольких подразделений

Сейчас анализ — для одного department_id. Полезно:
- `POST /analyze-batch` с `department_ids: list[uuid]` → запуск анализа для каждого + сводный `CrossDepartmentAgent` который найдёт паттерны (например, «у всех аэропортов проседает воскресенье»).

#### 7.14 Чат с результатом

После того как анализ готов, дать пользователю задавать вопросы LLM по этим данным:
- `POST /api/ai-recommendations/{id}/chat` с `{message: str}` — отправляет в Claude с system prompt «вот данные анализа X, отвечай на вопросы пользователя». История чата хранится отдельной таблицей.

Это превращает статичный отчёт в интерактивного консультанта.

#### 7.15 Автоматический запуск по расписанию

Добавить APScheduler-задачу: каждый понедельник 06:00 — запустить анализ за прошлую неделю для всех подразделений, отправить управляющим в Telegram/email.

В `app/services/scheduled_*.py` уже есть паттерн — добавить `scheduled_ai_recommendations.py`.

### ⚫ Безопасность и compliance

#### 7.16 Не логировать секреты в `full_prompt`

Сейчас весь user_prompt пишется в `ai_prompt_logs.full_prompt`. Если в данных подразделения окажется PII (полные имена сотрудников, телефоны) — это попадёт в plain text в БД.

**Действия**:
- Перед записью в лог — прогонять через regex-маскер (телефоны, email).
- Или добавить флаг `LOG_FULL_PROMPTS=False` в config — в проде писать только prompt_length, без текста.

#### 7.17 Rate limiting на `/analyze`

Один анализ = 15k токенов = ~$0.05 у Claude. 100 анализов в час от одного клиента = $5/час. Без rate limiting любой утёкший API_TOKEN сольёт деньги.

Проект уже имеет in-memory rate limiting (`app/auth.py`), но для AI endpoint можно поставить более строгий лимит — например, 10 анализов в час на ключ.

---

## 8. Контакты и ссылки

- **Источник миграции**: `/root/projects/hr-miniapp` (Node.js, исходные агенты)
- **Session log**: `SESSION_LOG_AI_RECOMMENDATIONS_MIGRATION_20260430_091808.md`
- **Migration plan**: `AI_RECOMMENDATIONS_MIGRATION_PLAN.md`
- **Commit**: `19406cc feat(ai): add multi-agent recommendations powered by Claude`
- **Live**: https://aqniet.space/ai-recommendations

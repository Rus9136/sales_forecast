# Session Log: React Frontend Migration

**Дата**: 2026-04-29, 13:43
**Задача**: Переписать фронтенд с Jinja2 HTML на React 19 SPA
**Статус**: Завершено

---

## Контекст

Текущий фронтенд — монолитный Jinja2-шаблон `app/templates/admin.html` (~3200 строк inline CSS/JS/HTML). Содержит 6 страниц: подразделения (CRUD + фильтры), продажи по дням/часам (таблицы + Chart.js), прогнозы (таблицы + графики), синхронизация (формы + прогресс-бар). Авторизация — Bearer-токен, инжектируемый Jinja2.

**Цель**: заменить на современный React SPA с функциональным паритетом 1:1.

---

## Выбранный стек

| Технология | Назначение |
|-----------|-----------|
| React 19 | UI-фреймворк |
| Vite 8 | Сборщик + dev-server |
| TypeScript 6 | Типизация |
| TanStack Query 5 | Серверное состояние, кеширование |
| shadcn/ui (Radix UI) | UI-компоненты |
| Tailwind CSS 4 | Стилизация |
| Recharts 3 | Графики (замена Chart.js) |
| React Router 7 | Клиентская маршрутизация |
| react-hook-form + zod | Формы + валидация |
| pnpm | Пакетный менеджер |

---

## Фазы выполнения

### Фаза 1 — Скаффолдинг и инфраструктура

1. Создан Vite-проект в `frontend/` через `pnpm create vite`
2. Установлены все зависимости (React, Radix, TanStack Query, Recharts, date-fns, и др.)
3. Настроен `vite.config.ts`:
   - Proxy `/api/*` и `/health` → `http://localhost:8002`
   - Build output → `dist/`
   - Alias `@/` → `./src/`
4. Настроен `tsconfig.json`:
   - TypeScript 6 — `paths` без `baseUrl` (deprecated в TS 6)
   - JSX: `react-jsx`, strict mode
5. Создан `index.css` с Tailwind CSS 4 theme (цветовая палитра, радиусы)
6. Создан `vite-env.d.ts` для CSS модулей и Vite client types

### Фаза 2 — Ядро приложения

**Типы** (`src/types/`):
- `department.ts` — Department, DepartmentCreate, DepartmentUpdate, SegmentType
- `sales.ts` — SalesSummary, SalesByHour, SyncResult
- `forecast.ts` — BatchForecast, ForecastComparison, ModelInfo
- `sync.ts` — AutoSyncLog, SyncStatistics, SyncStatusResponse

**Библиотеки** (`src/lib/`):
- `api-client.ts` — Typed fetch wrapper с Bearer auth (`window.__API_TOKEN__` || `VITE_API_TOKEN`)
- `formatters.ts` — formatCurrency (₸), formatDate, formatDateTime, formatPercent (ru-RU locale), SEGMENT_LABELS, TYPE_LABELS
- `utils.ts` — `cn()` утилита для shadcn/ui (clsx + tailwind-merge)

**Роутинг** (`App.tsx`):
- QueryClientProvider (staleTime: 30s, retry: 1)
- BrowserRouter с 6 маршрутами + redirect `/` → `/departments`
- AppLayout с Outlet

### Фаза 3 — Компоненты

**shadcn/ui примитивы** (`src/components/ui/` — 12 компонентов):
- button, card, input, label, table, badge, progress, dialog, alert, alert-dialog, select, separator, skeleton

**Layout** (`src/components/layout/`):
- `app-layout.tsx` — Sidebar + main content (flex layout)
- `sidebar.tsx` — 4 секции навигации с NavLink, тёмная тема (bg-sidebar)

**Shared** (`src/components/shared/` — 6 компонентов):
- `date-range-picker.tsx` — Два date input (от/до), используется на 5 страницах
- `department-select.tsx` — Select с подразделениями из useDepartments(), "Все подразделения"
- `loading-spinner.tsx` — Loader2 + текст "Загрузка данных..."
- `empty-state.tsx` — Inbox + текст "Нет данных для отображения"
- `error-alert.tsx` — Alert destructive с сообщением об ошибке
- `confirm-dialog.tsx` — AlertDialog для подтверждений (удаление, синхронизация)

**TanStack Query хуки** (`src/hooks/` — 4 файла):
- `use-departments.ts` — useDepartments, useCreateDepartment, useUpdateDepartment, useDeleteDepartment, useSyncDepartments
- `use-sales.ts` — useDailySales, useHourlySales
- `use-forecast.ts` — useBatchForecasts, useForecastComparison, useRetrainModel
- `use-sync.ts` — useAutoSyncStatus, useSyncSales, useTestAutoSync

### Фаза 4 — Страницы (все 6)

#### 1. Подразделения (`/departments`)
- Три фильтра: тип (DEPARTMENT/JURPERSON/CORPORATION/Все), компания, поиск по имени/коду/ID
- Таблица: Код, Название, Тип, Сегмент, ИНН, Сезон, Действия (Edit/Delete)
- Dialog создания/редактирования (react state, не react-hook-form — упростили)
- Условные поля сезона (только для сегмента "coffeehouse")
- Кнопки: Синхронизация (POST /api/departments/sync), Обновить, Добавить
- Счётчик "Найдено: N"
- ConfirmDialog для удаления

#### 2. Продажи по дням (`/sales/daily`)
- DateRangePicker (default: последние 30 дней)
- DepartmentSelect с "Все подразделения"
- Таблица: ID, Подразделение (имя из кеша departments), Дата, Сумма, Создано, Синхронизировано
- Форматирование: валюта (₸), даты (ru-RU)

#### 3. Продажи по часам (`/sales/hourly`)
- DateRangePicker (default: 7 дней) + DepartmentSelect + HourSelect (0-23)
- **Recharts BarChart**: 24-часовое распределение, агрегация по часам
  - Показывается только при выбранном подразделении
  - Tooltip с форматированием валюты
  - Y-axis: `{v/1000}k` формат
- Таблица: ID, Подразделение, Дата, Час, Сумма, Создано, Синхронизировано

#### 4. Прогноз по филиалам (`/forecast/branches`)
- DateRangePicker (default: сегодня + 7 дней вперёд)
- Таблица: Дата, Филиал, Прогноз продаж
- "Недостаточно данных" (italic, muted) когда predicted_sales === null

#### 5. Сравнение факт/прогноз (`/forecast/comparison`)
- DateRangePicker (default: -30 дней до вчера)
- **Карточка средней ошибки**: gradient background (purple), mean absolute error %
- **Recharts LineChart**: два dataset (Прогноз синий + Факт зелёный)
  - **Smart scaling**: percentile-based (p5/p95), auto-switch linear ↔ logarithmic при ratio > 3x
  - Max 30 точек на графике
  - Tooltip с formatCurrency, labelFormatter с formatDate
  - Показывается только при выбранном подразделении
- **Сортируемая таблица**: 6 колонок с toggle asc/desc при клике на заголовок
  - ArrowUpDown иконка + стрелка направления
  - Цвет ошибки: зелёный < 20%, красный >= 20%
  - Отклонение: зелёный положительное, красный отрицательное

#### 6. Синхронизация данных (`/sync`)
- **3 статус-карточки**: Расписание (02:00, предыдущий день), Статистика 30 дн. (успех/ошибки/rate), Быстрые действия (тест + обновить)
- **Latest sync info**: зелёная карточка успеха + жёлтая карточка ошибки
- **Форма ручной синхронизации**: DateRangePicker + DepartmentSelect + кнопка
  - Progress bar с анимацией (20% → 100%)
  - Alert результата: success (зелёный) или error (красный) с детальной разбивкой (записи, период, рекомендации)
- **Таблица истории**: дата, период, тип (Авто/Ручная badge), статус (Успех/Ошибка badge), записей, сообщение

### Фаза 5 — Интеграция с бэкендом

**`app/main.py`** — изменения:
1. Импорт `pathlib`, `StaticFiles`
2. `SPA_DIR = pathlib.Path(__file__).parent / "static" / "spa"`
3. Mount `/assets` → `StaticFiles(SPA_DIR / "assets")` (если директория существует)
4. `_serve_spa()` — читает `index.html`, инжектирует `<script>window.__API_TOKEN__="..."</script>`
5. GET `/` — вызывает `_serve_spa()`, fallback на Jinja2 `admin.html`
6. GET `/{full_path:path}` — catch-all для React Router, отдаёт index.html
7. CSP headers — убран `https://cdn.jsdelivr.net` из `script-src` (Chart.js CDN больше не нужен)

**`Dockerfile`** — 3-stage build:
1. `node:20-slim` — pnpm install + pnpm build
2. `python:3.11-slim` (builder) — pip install requirements
3. `python:3.11-slim` (final) — copy app + SPA build + favicon, non-root user, healthcheck

**`.gitignore`** — добавлено:
```
frontend/node_modules/
frontend/dist/
app/static/spa/
```

**`.dockerignore`** — убраны `dist` и `build` (мешали frontend), добавлены:
```
frontend/node_modules/
frontend/dist/
app/static/spa/
```

### Фаза 6 — Верификация

- TypeScript: **0 ошибок** (`npx tsc --noEmit`)
- Vite build: **success** (29KB CSS + 800KB JS, 242KB gzip)
- SPA задеплоен в `app/static/spa/`

---

## Файлы (созданные / изменённые)

### Новые файлы (41 файл в frontend/src/)
```
frontend/
├── index.html
├── package.json
├── pnpm-lock.yaml
├── tsconfig.json
├── vite.config.ts
├── .env.development
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    ├── vite-env.d.ts
    ├── lib/
    │   ├── api-client.ts
    │   ├── formatters.ts
    │   └── utils.ts
    ├── types/
    │   ├── department.ts
    │   ├── sales.ts
    │   ├── forecast.ts
    │   └── sync.ts
    ├── hooks/
    │   ├── use-departments.ts
    │   ├── use-sales.ts
    │   ├── use-forecast.ts
    │   └── use-sync.ts
    ├── components/
    │   ├── ui/ (12 файлов)
    │   │   ├── alert-dialog.tsx
    │   │   ├── alert.tsx
    │   │   ├── badge.tsx
    │   │   ├── button.tsx
    │   │   ├── card.tsx
    │   │   ├── dialog.tsx
    │   │   ├── input.tsx
    │   │   ├── label.tsx
    │   │   ├── progress.tsx
    │   │   ├── select.tsx
    │   │   ├── separator.tsx
    │   │   └── skeleton.tsx
    │   ├── layout/
    │   │   ├── app-layout.tsx
    │   │   └── sidebar.tsx
    │   └── shared/
    │       ├── confirm-dialog.tsx
    │       ├── date-range-picker.tsx
    │       ├── department-select.tsx
    │       ├── empty-state.tsx
    │       ├── error-alert.tsx
    │       └── loading-spinner.tsx
    └── pages/
        ├── departments-page.tsx
        ├── daily-sales-page.tsx
        ├── hourly-sales-page.tsx
        ├── forecast-branch-page.tsx
        ├── forecast-comparison-page.tsx
        └── sync-page.tsx
```

### Изменённые файлы
| Файл | Изменения |
|------|-----------|
| `app/main.py` | +pathlib, +StaticFiles, +SPA_DIR, +_serve_spa(), +catch-all route, CSP update |
| `Dockerfile` | 3-stage build (Node.js + Python + final) |
| `.gitignore` | +frontend/node_modules, +frontend/dist, +app/static/spa |
| `.dockerignore` | Убраны dist/build, +frontend exclusions |
| `CLAUDE.md` | Полное обновление: frontend стек, структура, команды, deployment |

---

## Решённые проблемы

### 1. TypeScript 6 — baseUrl deprecated (TS5101)
**Проблема**: `baseUrl` в tsconfig.json вызывает TS5101 error
**Решение**: Убрал `baseUrl`, оставил только `paths: {"@/*": ["./src/*"]}` — TS 6 поддерживает `paths` самостоятельно

### 2. window.__API_TOKEN__ типизация
**Проблема**: `(window as Record<string, unknown>).__API_TOKEN__` — TS ошибка overlapping types
**Решение**: Расширение Window interface через `declare global { interface Window { __API_TOKEN__?: string } }`

### 3. import.meta.env не типизирован
**Проблема**: `import.meta.env.VITE_API_TOKEN` — TS ошибка "Property 'env' does not exist"
**Решение**: Cast через `(import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_TOKEN`

### 4. CSS import side-effect (TS2882)
**Проблема**: `import './index.css'` — TS не распознаёт CSS модуль
**Решение**: `/// <reference types="vite/client" />` + `declare module '*.css'` в vite-env.d.ts

### 5. Recharts Tooltip formatter типизация
**Проблема**: `(value: number) => [string]` несовместим с Formatter generic type
**Решение**: `(value) => [formatCurrency(Number(value))]` — убрали explicit type annotation

### 6. .dockerignore блокировал frontend/dist
**Проблема**: Глобальные правила `dist` и `build` исключали frontend build output
**Решение**: Убрали глобальные `dist`/`build`, добавили точечные `frontend/dist/` и `app/static/spa/`

---

## Build Output

```
dist/index.html                   0.45 kB │ gzip:   0.29 kB
dist/assets/index-DGLZB3Cn.css   28.59 kB │ gzip:   5.88 kB
dist/assets/index-CY73thvz.js   799.16 kB │ gzip: 241.89 kB
```

~242KB gzip — включает React, Recharts, Radix UI, TanStack Query, React Router, date-fns.

---

## Архитектурные решения

1. **Нет Redux/Zustand** — TanStack Query для серверного состояния, useState для локальных фильтров
2. **Recharts вместо Chart.js** — декларативный React-native API, типизация
3. **shadcn/ui компоненты** — скопированы вручную в `components/ui/` (без CLI shadcn init)
4. **Fallback на admin.html** — если SPA не собран, FastAPI отдаёт старый Jinja2 шаблон
5. **Token injection** — сервер инжектирует `window.__API_TOKEN__` в HTML при каждом запросе
6. **Vite proxy** — dev-режим: все `/api/*` запросы проксируются на `:8002`, нет CORS проблем

---

## Следующие шаги

- [ ] Проверить SPA на production-сервере (aqniet.site)
- [ ] Удалить `app/templates/admin.html` после подтверждения работы
- [ ] Убрать `jinja2` из `requirements.txt` (если больше нигде не используется)
- [ ] Code-splitting (lazy routes) для уменьшения начального бандла
- [ ] Unit-тесты для hooks и компонентов

# Session Log: Bonus Scheme UI — Phase 2 (Visual Editor)

**Дата**: 2026-05-02, 10:39
**Задача**: Построить визуальный редактор схем расчёта бонусов поверх метаданных Phase 1. HR-менеджер должен создать или изменить схему **без знания JSON** — через формы с dropdown'ами, таблицами и подсказками.
**Статус**: Завершён, задеплоен на https://aqniet.site (коммит будет после этого лога)

---

## Контекст

В Phase 1 (см. `SESSION_LOG_Bonus_Scheme_UI_Editor_Phase1_2026-05-02_10-27.md`) бэкенд получил метаданные источников и моделей расчёта; фронт научился показывать конфиг как читабельные таблицы вместо `JSON.stringify`. Но кнопок «Создать» / «Редактировать» не было — все схемы создавались только seed-скриптом или прямым `POST /schemes` с JSON-телом.

Phase 2 закрывает редактор. Архитектурная идея: вместо хардкода под каждую из 5 моделей расчёта — **метаданные модели управляют рендером**. `CALCULATION_MODEL_METADATA[code].requires_kpis` → показать блок KPI; `grade_type` → flat-таблица (₸) или rate-таблица (%); `options[]` → пробежать и отрендерить Switch/RadioGroup/NumberInput с label/hint.

Это даёт два эффекта:
1. Добавление новой модели = только новая запись в metadata + Pydantic-схема, **никаких правок UI**
2. UI всегда соответствует тому, что бэкенд готов валидировать

---

## Архитектурные решения

| Решение | Обоснование |
|---|---|
| Один большой Dialog, не wizard со «Шаг 1 / 2 / 3» | KPI и грейды — не последовательные этапы, а параллельно редактируемые блоки одной формы. Wizard заставлял бы возвращаться. Просто scrollable Dialog с секциями |
| Автоконвертация ставок на ввод (4.5% UI ↔ 0.045 БД) | В KPI-документах указано «4.5%», но Pydantic ожидает Decimal-долю. Делать пользователя считать `4.5/100` = плохо. Конвертация в `onChange` |
| `value_type` фильтрует Select источников | KPI-блок принимает любые источники (revenue/kpi_percent/kpi_value), `revenue_source` — только revenue. Это ловит ошибку «выбрал manual_audit как revenue source» на UI, до отправки на бэкенд |
| Auto-fill при выборе KPI из definition | Пользователь выбирает «Аудит / стандарты», и source/direction/target подставляются из `bonus_kpi_definition`. Можно переопределить, но это редкий случай |
| Live-валидация через `/schemes/validate`, не на каждое изменение | Валидация идёт на сервер — нет смысла дёргать на каждый keystroke. Кнопка «Проверить» делает round-trip, а финальный «Сохранить» делает свою валидацию |
| Превращение существующей схемы в form state через `fromBaseScheme()` | Кнопка «Новая версия» предзаполняет всё из старой схемы; HR меняет одно поле и сохраняет. Включает грейды (определяет flat vs rate по наличию `value`/`rate` в первом элементе) и опции (всё что не в основном списке полей) |
| Auto-switch `target_kind` на смену модели | Если выбрана `team_revenue_by_kpi` — должен быть Select команды, а не должности. Хук `useEffect` на `modelMeta.code` это делает; пользователь не путается |

---

## Что сделано

### Новые UI-компоненты shadcn

**1. `frontend/src/components/ui/switch.tsx`** — Radix `Switch` (для `type=bool` опций).
**2. `frontend/src/components/ui/radio-group.tsx`** — `RadioGroup` + `RadioGroupItem` (для `type=enum`).
**3. `frontend/src/components/ui/select.tsx`** — добавлены `SelectLabel`, `SelectSeparator` (для группировки источников).
**4. NPM dependencies**: `@radix-ui/react-switch`, `@radix-ui/react-radio-group`.

### Подкомпоненты редактора

`frontend/src/components/bonus/editors/`:

**5. `revenue-source-select.tsx`** — `RevenueSourceSelect`:
- Группированный Select по `category` (iiko_personal → iiko_location → iiko_products → iiko_plan → manual → crm → hr → tco)
- Принимает `valueTypes` для фильтра (`['revenue']` или `['kpi_percent', 'kpi_value', 'revenue']` для KPI-блока)
- Под Select — описание выбранного источника
- Badge «заглушка» рядом с `is_stub=true` источниками

**6. `kpi-editor.tsx`** — `KpiEditor`:
- Inline-таблица: KPI / Источник / Направление / Цель / target_metric / × (удалить)
- При выборе KPI из dropdown — auto-fill `source/direction/target/target_metric` из `bonus_kpi_definition`
- Кнопка «+ Добавить KPI»

**7. `grades-editor.tsx`** — `GradesEditor`:
- Discriminated union по `type: 'flat' | 'rate'`
- Колонки: От % | До % | Сумма (₸) или Ставка (%) | Превью
- Live-валидация: непрерывность диапазонов, монотонность, пересечения — выводится в `Alert` ниже таблицы
- Для rate: input в процентах (4.5), хранение в долях (0.045) через `fractionToPercent` / `percentToFraction`
- Превью: `170 000 ₸` или `4.50%` справа от ввода

**8. `components-editor.tsx`** — `ComponentsEditor` (только для `combined_products`):
- Inline-таблица: Код / Название / Источник / Ставка (%)
- Использует `RevenueSourceSelect` с `valueTypes=['revenue']`

**9. `options-editor.tsx`** — `OptionsEditor`:
- Диспетчер по `option.type`:
  - `bool` → Switch с label/hint
  - `enum` → RadioGroup с `options[].label`
  - `money` → NumberInput с шагом 1000
- Каждая опция — карточка `border rounded-md`, label сверху, hint мелким шрифтом

### Главный диалог

**10. `frontend/src/components/bonus/scheme-editor-dialog.tsx`** — `SchemeEditorDialog`:
- `useState` хранит весь FormState (один объект); ленивая инициализация на `open` через `useEffect`
- Поддержка двух режимов:
  - `baseScheme=null` → пустая форма «Создать схему»
  - `baseScheme=BonusScheme` → предзаполнение через `fromBaseScheme()`, заголовок «Новая версия #N (vX → vX+1)»
- `useEffect` синхронизирует `target_kind` с `modelMeta.is_team_model`
- `useMemo(buildConfig)` — собирает финальный config из FormState через метаданные модели
- Две основных кнопки: **«Проверить»** (`/schemes/validate`) и **«Создать / Сохранить как новую версию»** (`/schemes`)
- Inline-фидбек: `validateOk` (зелёная Alert), `validateError` (красная), `submitError` (отдельная)

### Mutation hooks

**11. `frontend/src/hooks/use-bonus.ts`** — добавлено:
- `useValidateScheme()` — `POST /api/bonus/schemes/validate`, возвращает `{ok, normalized_config}`
- `useCreateScheme()` — `POST /api/bonus/schemes`; на success инвалидирует ключ `['bonus', 'schemes']` чтобы таблица обновилась
- Тип `SchemeCreatePayload`

### Интеграция

**12. `frontend/src/pages/bonus-schemes-page.tsx`**:
- Кнопка «**Создать схему**» в шапке (рядом с заголовком)
- Колонка «**Действия**» с кнопкой «**Новая версия**» (icon Copy) в каждой строке
- Состояние `editorOpen` + `editorBase` управляет диалогом
- `<SchemeEditorDialog>` рендерится один раз внизу страницы

---

## Проверка

| Проверка | Результат |
|---|---|
| `pnpm build` | OK, 2493 модуля, без TS-ошибок (новый bundle `Cw8w2Hvr.js`) |
| `docker-compose build sales-forecast-app` | OK (frontend 16.7s) |
| `docker-compose up -d` | recreated, db healthy, app started |
| `GET /health` (prod) | `{"status":"healthy"}` |
| Bundle hash на проде | `index-Cw8w2Hvr.js` совпадает с локальным |
| `POST /api/bonus/schemes/validate` (prod, существующая схема) | `{"ok":true,"normalized_config":{...}}` |
| Frontend ошибки | Нет в `docker logs sales-forecast-app` |

Реальное сохранение через UI на проде не тестировал (чтобы не намусорить дубликатами схем). Бэкенд эндпоинт работает идемпотентно: новая `effective_from` → старая закрывается, новая получает `version+1`.

---

## Изменённые файлы

**Frontend (10 файлов):**
- `frontend/package.json` (+2 dependency)
- `frontend/src/components/ui/switch.tsx` (новый)
- `frontend/src/components/ui/radio-group.tsx` (новый)
- `frontend/src/components/ui/select.tsx` (добавлен SelectLabel + SelectSeparator)
- `frontend/src/components/bonus/editors/revenue-source-select.tsx` (новый)
- `frontend/src/components/bonus/editors/kpi-editor.tsx` (новый)
- `frontend/src/components/bonus/editors/grades-editor.tsx` (новый)
- `frontend/src/components/bonus/editors/components-editor.tsx` (новый)
- `frontend/src/components/bonus/editors/options-editor.tsx` (новый)
- `frontend/src/components/bonus/scheme-editor-dialog.tsx` (новый)
- `frontend/src/hooks/use-bonus.ts` (`useValidateScheme`, `useCreateScheme`, тип `SchemeCreatePayload`)
- `frontend/src/pages/bonus-schemes-page.tsx` (кнопки + интеграция)

**Документация:**
- `docs/SESSION_LOG_Bonus_Scheme_UI_Editor_Phase2_2026-05-02_10-39.md` (этот файл)
- `docs/BONUS_SYSTEM_GUIDE.md` §12.6 (отметить Phase 2 done)

**Backend**: не трогали — работает без изменений.

---

## Что осталось (Phase 3, опционально)

- **Тестовый расчёт (sandbox)** — эндпоинт `POST /schemes/preview-calculation` + UI-форма «При KPI=__%, выручке=__₸ → бонус будет ХХХ ₸». Полезно для проверки до сохранения, особенно при создании новой версии с изменёнными ставками
- **Diff против активной версии** — таблица «Что меняется»: было/стало по каждому полю в финальном confirm-диалоге
- **Inline-редактор слотов KITCHEN** на странице `/bonus/teams/{id}` — сейчас веса слотов меняются только через SQL
- **История версий схемы** — timeline всех версий пары `(department, position)` с диффами
- **Деактивация схемы** — кнопка «Закрыть» (UPDATE `effective_to = today`); сейчас можно только заменять новой версией
- **Tooltip на длинных hint'ах** — сейчас используется HTML `title=""`. Когда будет shadcn `Tooltip`, заменить
- **Bundle splitting** — main.js уже 949 KB. Стоит вынести редактор в lazy-loaded chunk

---

## Известные ограничения

- Кнопка «Новая версия» в строке всегда копирует *эту* схему. Если для пары `(department, position)` есть несколько версий — пользователь должен сам выбрать нужную (обычно последнюю активную). Это не критично, потому что `effective_to=null` показывается badge «активна»
- При смене модели расчёта в форме — поля KPI/grades/components не сбрасываются, потому что разные модели могут переиспользовать одни и те же KPI. Но если новая модель не требует KPI (например, `revenue_direct`) — они просто не попадут в финальный config (`buildConfig` фильтрует по `requires_*`)
- Валидация на фронте дублирует часть логики Pydantic-схем (например, проверка непрерывности грейдов). Это сознательно — даёт мгновенный feedback. Финальная истина — на бэкенде через `/schemes/validate`

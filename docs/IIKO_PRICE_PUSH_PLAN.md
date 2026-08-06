# План: автоматическая выгрузка утверждённых цен в iiko (приказы)

**Дата:** 2026-08-06. **Статус:** план, к реализации.
**Проблема:** после `approved` в UI цену в iiko управляющий вбивает руками (XLSX → бэк-офис).
Ручной шаг ломает две вещи: (1) цена доезжает через часы-дни или не доезжает вовсе,
(2) `applied_at` детектится по каталогу «когда заметили», а не «когда решили» — эффект
меряется по смазанной дате.

**Цель:** утверждённые рекомендации по точке одним действием превращаются в **приказ об
изменении меню** в iiko (документ `menuChange`), с журналом, откатом и подтверждением
факта по каталогу.

---

## 1. Что даёт iiko API (проверено на нашем контуре 2026-08-06)

Документация: `docs/prikazy.pdf` («Работа с приказами», iiko 7.8), `docs/tseny-zadannye-prikazami (1).pdf`.

| Метод | Назначение |
|---|---|
| `GET /resto/api/v2/documents/menuChange?dateFrom&dateTo[&status]` | Список приказов |
| `GET /resto/api/v2/documents/menuChange/byId?id=` | Приказ по id |
| `GET /resto/api/v2/documents/menuChange/byNumber?documentNumber=` | Приказ по номеру |
| **`POST /resto/api/v2/documents/menuChange`** | **Создание (без `id`) / редактирование (с `id`)** |
| `GET /resto/api/v2/price` | Уже используем — витрина результата (`sku_catalog_price`) |

Тело `MenuChangeDocumentDto`: `dateIncoming` (дата вступления в силу), `documentNumber`,
`status` (`NEW`/`PROCESSED`/`DELETED`), `comment`, `deletePreviousMenu`, `dateTo`,
`items[]`. Позиция: `departmentId`, `productId`, `productSizeId`, `including`, `price`,
`dishOfDay`, `flyerProgram`, `pricesForCategories[]`, `includeForCategories[]`.

**Проверка на живом контуре (read-only, обе БД iiko):**
- `GET menuChange` отвечает 200 на обоих доменах нашими текущими credentials —
  Sandyq: 86 приказов за июль–август, Madlen: 198 (373 PROCESSED / 2 DELETED / 1 NEW).
- Реальный приказ на цену выглядит ровно как наш целевой payload:
  `{"including": true, "price": 555, "productSizeId": null, "pricesForCategories": [], "includeForCategories": []}`.
- Один приказ **может содержать позиции нескольких точек** (видели документ на 2 точки, 26 строк).
- `documentNumber` присваивается iiko (у нас в базе номера сквозные: 1421, 1422…).
- В наших данных `product_size_id` **везде NULL**, `price_type` **везде BASE**,
  ценовых категорий нет (`pricesForCategories` пустые во всех просмотренных приказах) —
  payload остаётся простым; но код должен переносить эти поля из текущего приказа, а не
  затирать их пустотой (см. §6, риск R3).

**Проверка записи (этап 0 выполнен 2026-08-06, Мадлен 18 мкр, «Вилка Одноразовая»,
цена 1 ₸ = текущей, статус `NEW`):**
- `POST menuChange` → **200 `result: SUCCESS`**. Право на создание приказов у учётки
  `IIKO_LOGIN` **есть**.
- `documentNumber` **присваивает iiko сама** (выдала `1424`, следующий за 1423) — в payload
  не передаём.
- `GET byId` вернул документ ровно в том виде, в каком отправлен (включая `comment` —
  значит маркер `SF#{order_id}` для восстановления после обрыва работает, §4.3).
- Отмена: `POST` с тем же `id` и `status='DELETED'` → 200, контрольное чтение показало
  `status: DELETED`. Проба убрана за собой.
- Ответ на создание содержит созданный документ целиком (`response`) — сохраняем его в
  `price_change_order.response_payload`.

**Осталось проверить перед боевым включением:** отмена приказа в статусе `PROCESSED`
с датой проведения «сегодня или позже» (по документации разрешена) — это боевая ветка
отката; сейчас проверена только отмена черновика.

## 2. Куда встраивается (текущий контур)

```
price_recommendation.status:
  new ──approve──▶ approved ──[СЕЙЧАС: ручной ввод в iiko]──▶ (каталог 03:20) applied ──14д──▶ outcome
                        └──[БУДЕТ: POST menuChange]──────────┘
```

Ключевое решение: **статусную машину не трогаем.** Новый шаг «отправлено в iiko» не
становится статусом рекомендации — он живёт в отдельной таблице приказов и в двух новых
полях `price_recommendation`. `applied` по-прежнему ставит `detect_applied` по факту
каталога (`GET /v2/price`) — это честная верификация «цена реально встала», а не «мы
думаем, что отправили». Отправка приказа лишь делает эту детекцию точной (см. §5.3).

Ещё одно решение: **один приказ на (точку × дату вступления в силу)**, все утверждённые
позиции точки — строками одного документа. Это совпадает с методикой замера
(`price_outcome_batch` — эффект пачки решений по `department_id × applied_at`) и
с тем, как приказы ведут вручную.

## 3. Схема данных (миграция 038)

```sql
CREATE TABLE price_change_order (
    id                  BIGSERIAL PRIMARY KEY,
    department_id       UUID NOT NULL REFERENCES departments(id),
    iiko_source_domain  TEXT NOT NULL,
    effective_date      DATE NOT NULL,          -- dateIncoming
    status              TEXT NOT NULL,          -- draft|sending|sent|failed|cancelled
    iiko_status         TEXT,                   -- NEW|PROCESSED|DELETED (как в iiko)
    iiko_document_id    UUID,
    iiko_document_number TEXT,
    n_items             INTEGER NOT NULL DEFAULT 0,
    request_payload     JSONB NOT NULL,
    response_payload    JSONB,
    error_message       TEXT,
    created_by          UUID,                   -- app_user.id
    created_at          TIMESTAMP NOT NULL DEFAULT now(),
    sent_at             TIMESTAMP,
    cancelled_at        TIMESTAMP
);
-- один живой приказ на точку и дату: повтор кнопки не плодит документы
CREATE UNIQUE INDEX uq_price_order_open ON price_change_order (department_id, effective_date)
    WHERE status IN ('draft','sending','sent');

CREATE TABLE price_change_order_item (
    id                BIGSERIAL PRIMARY KEY,
    order_id          BIGINT NOT NULL REFERENCES price_change_order(id) ON DELETE CASCADE,
    recommendation_id BIGINT NOT NULL REFERENCES price_recommendation(id),
    product_id        BIGINT NOT NULL,
    iiko_product_id   UUID NOT NULL,
    old_price         NUMERIC(14,2) NOT NULL,   -- для отката и сверки
    new_price         NUMERIC(14,2) NOT NULL,
    UNIQUE (recommendation_id)                  -- одну рекомендацию нельзя отправить дважды
);

ALTER TABLE price_recommendation
    ADD COLUMN order_id BIGINT REFERENCES price_change_order(id),
    ADD COLUMN pushed_at TIMESTAMP;
```

`price_change_order` — тоже append-only по смыслу: отмена не удаляет строку, а ставит
`status='cancelled'`. Все мутации — через `log_audit(entity_type='price_order')`.

## 4. Backend

### 4.1 `app/services/iiko_menu_change_writer.py` (новый, низкий уровень)
Только транспорт к iiko, без бизнес-логики:
- `create_order(base_url, payload) -> dict` — POST `menuChange`, разбор `{result, errors, response}`;
  `result != SUCCESS` → исключение с текстом `errors`.
- `get_order(base_url, doc_id)`, `list_orders(base_url, date_from, date_to)`.
- `update_order(base_url, payload_with_id)` — редактирование/отмена.
- Таймаут 120с, ретрай только на 5xx/сетевые (2 попытки, backoff), **никогда на таймаут
  POST** — повтор создал бы второй приказ; таймаут → `status='sending'` + сверка (§4.3).
- Токен — существующий `IikoAuthService` (кэш 55 мин).

### 4.2 `app/services/price_order_service.py` (новый, бизнес-логика)
- `build_order(department_id, effective_date, rec_ids=None) -> preview` — собирает
  предпросмотр: список позиций, старая/новая цена, Δ%, суммарный ожидаемый ΔGP, список
  предупреждений. Ничего не пишет. Это то, что видит менеджер в диалоге подтверждения.
- `send_order(...)` — транзакция:
  1. advisory-lock по точке (как в `review_recommendation`);
  2. выбрать `approved`-рекомендации точки, у которых `order_id IS NULL`, `FOR UPDATE`;
  3. **ревалидация каждой позиции** (переиспользуем логику `_revalidate_for_approve`):
     цена в каталоге = `current_price` ±0.01, рекомендация не истекла, не в стоп-листе,
     `product.iiko_source_domain` совпадает с доменом точки, `recommended_price > 0`,
     `|Δ%| ≤ max_step` правила. Невалидные — не в приказ, а в `warnings` ответа;
  4. guard-проверки (§6);
  5. INSERT `price_change_order` (`status='draft'`) + items → commit;
  6. POST в iiko (вне транзакции БД, чтобы не держать блокировку на сетевом вызове);
  7. успех → `status='sent'`, `iiko_document_id/number`, `sent_at`;
     проставить `price_recommendation.order_id/pushed_at`; `log_audit`;
     ошибка → `status='failed'`, `error_message`, рекомендации не помечаются.
- `cancel_order(order_id)`:
  - если `effective_date >= today` → POST с тем же `id` и `status='DELETED'`
    (в контуре такие документы есть — 2 шт.);
  - если приказ уже вступил в силу вчера или раньше → iiko разрешает менять только
    `dateTo` → **обратный приказ**: новый `menuChange` с `old_price` из наших items
    на завтрашнюю дату;
  - в обоих случаях `status='cancelled'`, рекомендации → `order_id=NULL, pushed_at=NULL`
    (чтобы не висели «отправленными»), запись в аудит.
- `sync_order_status(order_id)` — GET byId, обновить `iiko_status` (кто-то мог провести
  или удалить приказ руками в бэк-офисе).

Payload одной позиции (жёстко):
```python
{"departmentId": dept_uuid, "productId": iiko_product_id, "productSizeId": None,
 "including": True, "price": float(new_price),
 "dishOfDay": carried, "flyerProgram": carried,
 "pricesForCategories": carried, "includeForCategories": carried}
```
`carried` — атрибуты из текущего приказа этой позиции (`sku_catalog_price.document_id` →
`GET menuChange/byId` → items по productId), с фолбэком на пустые/false. Поля
`taxCategoryId`/`taxCategoryEnabled` **не отправляем вовсе** — по документации,
если их не задавать явно, значения в БД iiko не меняются и лицензия не проверяется.

Документ: `deletePreviousMenu = False` (**хардкод, не параметр** — `true` вычистит из меню
всё, чего нет в документе), `dateTo = "2500-01-01"`, `comment = "Sales Forecast: приказ №{order_id}, {n} позиций"`,
`status` — из настройки (§6).

### 4.3 Восстановление после обрыва
`status='sending'` (POST ушёл, ответ не дошёл) — приказ мог создаться. Джоб-сверка
(и ручная кнопка) делает `GET menuChange?dateFrom=effective_date&dateTo=effective_date`,
ищет документ с нашим `comment`-маркером `SF#{order_id}` → если найден, дописывает
`iiko_document_id` и переводит в `sent`; если нет — `failed`. Поэтому маркер в комментарии
обязателен и уникален.

### 4.4 Эндпоинты (`app/routers/pricing_engine.py`)
| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/pricing-engine/price-orders` | Список приказов (фильтры: точка, статус, период) |
| `GET` | `/api/pricing-engine/price-orders/{id}` | Приказ + позиции + payload/ответ iiko |
| `POST` | `/api/pricing-engine/price-orders/preview` | Предпросмотр (точка, дата, rec_ids?) |
| `POST` | `/api/pricing-engine/price-orders` | Создать и отправить приказ |
| `POST` | `/api/pricing-engine/price-orders/{id}/cancel` | Отмена / обратный приказ |
| `POST` | `/api/pricing-engine/price-orders/{id}/sync` | Сверка статуса с iiko |

Все мутирующие — `Depends(get_optional_user)` + `_require_section(user, "pricing.apply")`
+ актор в аудит (правило §12 гайда). Отправка приказа на >50 позиций — `?background=true`
через `JobRegistry` (nginx 60с).

### 4.5 Новая секция роли `pricing.apply`
Публикация цен в боевую кассу — право более сильное, чем «утвердить в нашем UI»,
поэтому отдельный ключ. Дописать в 6 местах (чек-лист CLAUDE.md): `app/auth_ui.py::AVAILABLE_SECTIONS`,
`DEFAULT_ROLES` (admin, manager), `frontend/src/types/auth.ts::SectionKey`, `roles-page.tsx`,
`home-redirect.tsx`, `sidebar.tsx`. Доменным pricing-ролям (несистемным) ключ добавить
ручным SQL: `commercial_director` — да, `restaurant_manager` — решение заказчика,
`pricing_analyst`/`finance_director` — нет.

## 5. Связка с существующим контуром

### 5.1 Детекция applied — станет точной
Сейчас `detect_applied` ищет совпадение цены ±0.01 в каталоге в окне 30 дней от
`reviewed_at`. Добавляем **первичное сопоставление по документу**: если у рекомендации есть
`order.iiko_document_id`, и в `sku_catalog_price` появилась строка с этим `document_id` —
это applied, `applied_at = date_from` интервала. Совпадение по цене остаётся фолбэком
(ручные правки в обход системы).

### 5.2 Замер эффекта
`applied_at` становится ровно датой вступления приказа в силу → окна before/after в
`evaluate_outcomes` и `price_outcome_batch` перестают «плыть». Дополнительно у батча
появляется естественный ключ — приказ (одна точка, одна дата), что ровно соответствует
методике «эффект пачки решений».

### 5.3 Планировщик
- Новый джоб **03:25** (сразу после синка цен 03:20): `sync_order_status` для всех
  `sent`-приказов последних 30 дней + добивка `sending` (§4.3). Пишет в `auto_sync_log`.
- Автоотправку по расписанию **не делаем** — приказ уходит только по действию человека.

## 6. Безопасность и предохранители

| Guard | Поведение |
|---|---|
| `IIKO_PRICE_PUSH_ENABLED` (env, деф. `False`) | Kill-switch. Выключен → эндпоинты 503 с внятным текстом |
| `IIKO_PRICE_PUSH_DEPARTMENTS` (env, CSV UUID) | Белый список точек. Пусто → разрешены все (включать только после пилота) |
| `IIKO_PRICE_ORDER_STATUS` (env, `NEW`\|`PROCESSED`, деф. `NEW`) | Этап 1: приказ создаётся черновиком, управляющий проводит его в бэк-офисе и видит, что мы прислали. Этап 2 (после недели чистых прогонов) → `PROCESSED` |
| `deletePreviousMenu` | Хардкод `False`. Не параметр, не поле в UI |
| Лимит позиций в приказе | Деф. 40; больше → 400 с требованием разбить |
| Лимит отклонения | Каждая позиция: `|Δ%| ≤ max_step` действующего правила; иначе позиция не идёт в приказ |
| Санити цены | `new_price > 0`, `new_price != current_price`, `new_price ≥ COGS × (1+min_margin)` |
| Ревалидация каталога | Цена в iiko должна совпадать с `current_price` рекомендации — иначе базис устарел, позиция исключается (тот же код, что на approve) |
| Домен | `product.iiko_source_domain == departments.iiko_source_domain`, иначе позиция исключается (защита от Madlen-товара в Sandyq-приказе) |
| Идемпотентность | `uq_price_order_open` + `UNIQUE(recommendation_id)` в items |
| Дата | `effective_date ∈ [today, today+14]`, деф. **завтра** (цена меняется на границе учётного дня — чище для замера) |
| Dry-run | `?dry_run=true` возвращает готовый payload и не ходит в iiko |

## 7. Frontend

- **`recommendations-page.tsx`**, вкладка «Утверждены»: кнопка **«Отправить в iiko»**
  (видна при `hasSection('pricing.apply')`). Диалог: точка, дата вступления в силу,
  таблица позиций (было → станет, Δ%, ΔGP/нед), суммарный ожидаемый эффект, список
  исключённых позиций с причиной, красная плашка про боевую кассу. Кнопка
  «Отправить приказ». XLSX-экспорт остаётся как запасной путь.
- **Новая вкладка «Приказы»** (`pricing/orders-page.tsx`) в `PRICING_TABS`: список
  приказов (дата, точка, № документа iiko, статус, позиций, суммарный ΔGP), карточка
  приказа с позициями и кнопками «Сверить с iiko» / «Отменить». Статус рекомендации в
  инбоксе получает бейдж «Отправлено в iiko №1421» между «Утверждена» и «Применена».
- Хуки в `hooks/use-pricing.ts`, типы в `types/pricing.ts`, лейблы в `lib/pricing-labels.ts`.
- Верстка — по `sales-forecast-design` (та же плотность/токены, что у остальных pricing-страниц).

## 8. Порядок работ

### 8.1 Этап 0 — разведка прав ✅ ВЫПОЛНЕНО 2026-08-06
Права на создание и отмену приказов подтверждены на боевом контуре, результаты — в §1.
Скрипт пробы: `scratchpad/iiko_smoke_stage0.py` (создаёт черновик и сам его удаляет).
Открытый хвост: отмена приказа в статусе `PROCESSED` (боевая ветка отката) — проверить
до включения `IIKO_PRICE_ORDER_STATUS=PROCESSED`.

### 8.2 Этап 1 — бэкенд ✅ ВЫПОЛНЕНО 2026-08-06
Миграция 038 + ORM → `iiko_menu_change_writer` → `price_order_service` (build/send/cancel/sync)
→ эндпоинты + секция `pricing.apply` → правка `detect_applied` (сопоставление по документу)
→ джоб 03:25.

### 8.3 Этап 2 — фронтенд ✅ ВЫПОЛНЕНО 2026-08-06
Диалог отправки + страница «Приказы» + бейджи + хуки/типы.

### 8.4 Этап 3 — тесты ✅ ЧАСТИЧНО (unit готовы, интеграционный smoke — за пилотом)
- Unit (`tests/unit/test_price_orders.py`): сборка payload (в т.ч. перенос
  `dishOfDay`/категорий), все guard'ы, исключение позиций с причинами, идемпотентность,
  выбор ветки отмены (удаление vs обратный приказ), разбор ответа iiko с `result=ERROR`.
- Транспорт мокать через `respx` (пин `>=0.23.1`, `with respx.mock() as router:`).
- Интеграционный smoke на тестовой точке: приказ из 2 позиций → `GET /v2/price` на
  следующий день показывает новую цену с нашим `document_id` → `detect_applied` ставит
  `applied` → через 14 дней есть outcome.

### 8.5 Этап 4 — пилотная эксплуатация (1–2 недели)
`IIKO_PRICE_ORDER_STATUS=NEW` + белый список = Мадлен 18 мкр. Управляющий проводит приказ
руками, сверяет позиции. После недели без расхождений — `PROCESSED` и расширение списка точек.

**Статус на 2026-08-06:** этапы 0–2 выполнены и задеплоены; из этапа 3 сделаны
unit-тесты (33 шт., `tests/unit/test_price_orders.py`), интеграционный прогон идёт
вместе с пилотом. Осталось: этап 4 (пилотная эксплуатация).

**Итого:** ~5–7 рабочих дней разработки + пилот.

## 12. Что задеплоено (2026-08-06)

* Миграция `039_price_change_orders.sql` применена: `price_change_order`,
  `price_change_order_item`, `price_recommendation.order_id/pushed_at`.
* Сервисы `iiko_menu_change_writer.py` (транспорт) + `price_order_service.py` (сборка,
  отправка, отмена, сверка); джоб сверки 03:25; `detect_applied` сперва сопоставляет по
  `document_id` приказа.
* Эндпоинты `/api/pricing-engine/price-orders*`, секция роли `pricing.apply`
  (admin + manager; доменным pricing-ролям — ручным SQL).
* UI: вкладка «Приказы в iiko» (журнал, сверка, отмена) + диалог «Отправить в iiko»
  на «Рекомендациях».
* Пилотная конфигурация в `.env.prod`: `IIKO_PRICE_PUSH_ENABLED=True`,
  белый список = Мадлен 18 мкр, `IIKO_PRICE_ORDER_STATUS=NEW` (приказ-черновик).
* Проверено на проде: kill-switch и белый список отсекают (503/403), предпросмотр
  собирается. На живых данных ревалидация сработала по делу — единственную approved-позицию
  («Бал куырдак», Sandyq Алматы) исключило: цена в iiko уже 8990 против базиса 7790,
  отправка вслепую понизила бы цену на 840 ₸.

## 9. Риски

| # | Риск | Митигация |
|---|---|---|
| R1 | У учётки нет прав на POST `menuChange` | Этап 0 первым; фолбэк — отдельная сервисная учётка iiko |
| R2 | `deletePreviousMenu=true` вычистит меню точки | Хардкод `False`, unit-тест на payload, отсутствует в API |
| R3 | Затирание атрибутов позиции (хит дня, флаерная программа, ценовые категории) | Перенос из текущего приказа по `document_id`; в наших данных категории пусты, но код не полагается на это |
| R4 | Двойная отправка при таймауте POST | Не ретраить POST; маркер `SF#{id}` в комментарии + сверка (§4.3) |
| R5 | Цена уехала в iiko руками между approve и отправкой | Ревалидация по каталогу на отправке; позиция исключается с причиной |
| R6 | Ошибка в цене доехала до кассы | Этап `NEW` + белый список + лимиты Δ%/маржи + откат одним действием |
| R7 | Размеры/ценовые категории появятся позже | Сейчас в данных их нет; при появлении `productSizeId IS NOT NULL` — позиция исключается с явной причиной, а не отправляется «как есть» |
| R8 | Приказ проведён, но `applied` не детектится (каталог отдаёт с задержкой) | Сопоставление по `document_id` + окно детекции 30 дней остаётся |

## 10. Что НЕ делаем в этой итерации

- Автоотправку по расписанию без человека.
- Приказы со снятием с продажи (`including=false`) и приказы по времени (`scheduleId`) —
  отдельная задача, если понадобится happy hours.
- Массовую отправку по нескольким точкам одним документом — приказ на точку понятнее
  для откатов и замера.
- Ценовые категории и налоговые категории в приказе (лицензионный модуль 21052802).

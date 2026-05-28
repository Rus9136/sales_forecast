# Menu, Receipts, Prices & Recipes — Architecture Plan

**Статус:** Phase 0–3 + Phase 5.1–5.3 выполнены (2026-05-25). Phase 4 удалена (не нужна). Phase 5.4 не начата.
**Контекст:** добавляем сбор и хранение чеков по позициям, номенклатуры, прайс-листов и техкарт из iiko для последующего пословного (per-SKU) прогноза продаж и анализа цен.
**Связано с:** `iiko_sales_integration_guide.md` (текущий OLAP по продажам), `LABOR_OPTIMIZATION_ARCHITECTURE.md` (общий принцип «версионировать справочники по времени»).

---

## 1. Цели

1. **Хранить чеки и позиции** (а не только дневные/почасовые агрегаты, как сейчас в `sales_summary`/`sales_by_hour`).
2. **Хранить полный справочник номенклатуры** iiko с группами и категориями, синхронизировать его как сейчас синхронизируется `employees`.
3. **Хранить цены, заданные приказами**, с версионированием `effective_from`/`effective_to` — для анализа ценовой эластичности.
4. **Хранить технологические карты** (рецепты с ингредиентами и нормами списания) с версионированием по дате — для расчёта себестоимости позиции чека на исторический период.
5. На фундаменте всех четырёх сущностей — построить **прогноз продаж по SKU** (отдельный LightGBM per top-N блюд + fallback на групповой уровень) и анализ ценообразования.

Не-цели: складские движения (Transactions OLAP), интеграция с поставщиками, инвентаризация — отдельный пласт, не входит в этот план.

---

## 2. Ключевые архитектурные решения

### 2.1 Разделение Сандык/Мадлен — через `iiko_source_domain`

**Проблема:** Сандык и Мадлен — два разных iiko-сервера (`sandy-co-co.iiko.it`, `madlen-group-so.iiko.it`) с **разными ассортиментами**. iiko на каждом сервере генерирует **свои UUID** для блюд/групп/рецептов. Если просто сольём в общую таблицу `product` — потеряем источник, не сможем корректно резолвить позиции чеков в SKU.

В `departments` сейчас:
- `company_id integer` — пустой у всех 91 строк, осталось от bonus-подсистемы → дропаем.
- `taxpayer_id_number` (БИН) — заполнен только у 5 DEPARTMENT из 91. Ненадёжно.

**Решение (Вариант A, принят 2026-05-25):**
- Добавить колонку `iiko_source_domain TEXT NOT NULL` в `departments` и заполнять её прямо в loader из контекста (`for domain in self.domains: ...`).
- Та же колонка появляется в `product`, `nomenclature_group`, `nomenclature_category`, `recipe`, `price_list_entry`.
- Natural unique включает домен:
  - `product UNIQUE (iiko_source_domain, iiko_product_id)`
  - `recipe UNIQUE (iiko_source_domain, iiko_assembly_chart_id, effective_from)`
- Резолв `DishId → product.id` в позициях чека делается по паре `(department.iiko_source_domain, DishId)` — гарантированно без коллизий.

**Маппинг URL → человеческое имя** живёт во фронте, в `frontend/src/lib/iiko-sources.ts`:
```ts
export const IIKO_SOURCES: Record<string, string> = {
  "sandy-co-co.iiko.it": "Сандык",
  "madlen-group-so.iiko.it": "Мадлен",
};
```

Если в будущем понадобится полноценный справочник «компания» (с настройками, логотипами, видимостью по ролям) — отдельная таблица `company (id UUID PK, name TEXT, iiko_source_domain TEXT UNIQUE)`, и `iiko_source_domain` заменяется на `company_id`. Сейчас не делаем.

### 2.2 Натуральные ключи vs внутренние BIGSERIAL

- **`product`, `nomenclature_group`, `nomenclature_category`** → PK = `BIGSERIAL id`, natural unique = `(iiko_source_domain, iiko_<entity>_id UUID)`. Это защищает от теоретических UUID-коллизий между доменами и облегчает FK с других таблиц (короткий BIGINT vs пара колонок).
- **`receipt`** → PK = `BIGSERIAL id`, natural unique = `(department_id, open_date, order_num)`. iiko OLAP не отдаёт `Order.Id` — `OrderNum` достаточно для идемпотентного upsert.
- **`recipe`** → PK = `BIGSERIAL`, natural unique = `(product_id, effective_from)` + EXCLUDE constraint на пересечение интервалов `[effective_from, effective_to)`.
- **`price_list_entry`** → то же самое: `BIGSERIAL` + EXCLUDE на пересечение `(product_id, department_id, [effective_from, effective_to))`.

### 2.3 Snapshot полей в позициях чека

`receipt_item.product_id` — **nullable**. Если OLAP отдал `DishId`, которого нет в `product` (новое блюдо, ещё не синкнули), пишем позицию с `product_id=NULL` + snapshot полей (`product_name_snapshot`, `product_code_snapshot`, `group_name_snapshot`, `category_name_snapshot`). Отдельная job — `menu_reconciliation` — позже резолвит NULL-ы.

Принцип: **не теряем данные, не блокируем sync** из-за рассинхрона справочников.

### 2.4 Партиционирование чеков

`receipt` и `receipt_item` партиционируются по `open_date` (range, месячные партиции), **сразу в первой миграции**. При объёме ~18 млн `receipt_item`/год ретроактивный переезд через `pg_partman` болезнен.

Партиции создаём заранее на 12 месяцев вперёд через cron-задачу в APScheduler (раз в неделю проверка «есть ли партиции на следующий месяц», создаём недостающие).

### 2.5 Batch upsert вместо построчного

Текущие лоадеры (`iiko_sales_loader`, `iiko_waiter_sales_loader`) делают построчный `query → update/insert` в цикле. Для receipts (50 тыс. строк/день) это неприемлемо. Переходим на:
- `INSERT ... ON CONFLICT (...) DO UPDATE SET ...` батчами по 1000 строк.
- Для receipt_item — `COPY` через `psycopg2.extras.execute_values` или `INSERT ... ON CONFLICT DO NOTHING` (delete-and-reinsert при перезагрузке чека).

### 2.6 Версионирование справочников через `effective_from`/`effective_to`

Тот же принцип, что в `bonus_scheme` (хоть bonus и удаляется, паттерн правильный):
- На каждый sync читаем актуальные значения за период.
- Если значение изменилось — закрываем предыдущую запись (`effective_to = new.effective_from`) и вставляем новую.
- Старые записи **не удаляем** — нужны для воспроизводимости исторических анализов.

Касается: `price_list_entry`, `recipe`.

---

## 3. Источники данных (iiko эндпоинты)

| Сущность | Эндпоинт | Формат | Частота |
|---|---|---|---|
| Номенклатура (блюда/товары/модификаторы) | `GET /resto/api/v2/entities/products/list?includeDeleted=true` | JSON | 1×/сутки + ручной триггер |
| Номенклатурные группы | `GET /resto/api/v2/entities/products/group/list` | JSON | 1×/сутки |
| Категории блюд | `GET /resto/api/v2/entities/products/category/list` | JSON | 1×/сутки |
| Прайс-лист (цены приказами) | `GET /resto/api/v2/reports/priceList?departmentId=...&date=YYYY-MM-DD` | JSON | по каждому подразделению на каждую дату изменения |
| Техкарта на дату | `GET /resto/api/v2/assemblyCharts/getPrepared?productId=...&date=...` | JSON | по факту изменения |
| Дерево техкарт (bulk) | `GET /resto/api/v2/assemblyCharts/getTree?departmentId=...&dateFrom=...&dateTo=...` | JSON | 1×/сутки (еженедельный полный) |
| Чеки + позиции | `POST /resto/api/v2/reports/olap`, `reportType=SALES`, расширенный `groupByRowFields` | JSON | 1×/сутки (вчера) + gap check |

**Расширенный OLAP-запрос для чеков:**
```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Department.Id", "OpenDate.Typed", "OrderNum", "CloseTime",
    "OrderType", "TableNum", "WaiterName",
    "DishId", "DishName", "DishGroup", "DishCategory", "DishCode",
    "PriceCategory", "PaymentTypes"
  ],
  "aggregateFields": [
    "DishAmountInt", "DishSumInt", "DishDiscountSumInt",
    "DishReturnSum", "GuestNum"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange", "periodType": "CUSTOM",
      "from": "YYYY-MM-DD", "to": "YYYY-MM-DD"
    },
    "OrderDeleted":         {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
    "DeletedWithWriteoff":  {"filterType": "IncludeValues", "values": ["NOT_DELETED"]}
  }
}
```

---

## 4. Этапы работы

### Фаза 0 — Подготовка: удаление bonus subsystem ✅ ВЫПОЛНЕНО (2026-05-25)

> **Commit:** `70168ef chore(bonus): remove unused bonus subsystem` — 123 файла, +818 / −13224.
> **Backup:** `backups/bonus_dump_20260525_084615.sql.gz` (221KB, gitignored, на диске сервера).

**Цель:** убрать неиспользуемый код, освободить FK `departments.company_id integer` под наш новый `iiko_source_domain`.

**Что удалить:**
- 12 таблиц bonus (`bonus_company`, `bonus_position`, `bonus_team`, `bonus_team_position`, `bonus_kpi_definition`, `bonus_monthly_plan`, `bonus_employee_assignment`, `bonus_scheme`, `bonus_manual_kpi`, `bonus_calculation`, `bonus_calculation_penalty`) — миграция `012_drop_bonus.sql`.
- Колонка `departments.company_id integer` — в той же миграции.
- Директория `app/bonus/`.
- Эндпоинты под `/api/bonus/` (включить роутер выгрести из `app/main.py`).
- Тесты `tests/bonus/`.
- APScheduler job «monthly bonus auto-calculation» (5го числа в 05:00).
- Frontend страницы `/bonus/calculations`, `/bonus/schemes`, `/bonus/manual-kpi`, `/bonus/monthly-plans` + хуки + типы + sidebar-секция «БОНУСЫ».
- Section keys `bonus.calculations`, `bonus.schemes`, `bonus.manual-kpi`, `bonus.monthly-plans` из `app/auth_ui.py::AVAILABLE_SECTIONS`, `frontend/src/types/auth.ts::SectionKey`, `frontend/src/components/layout/sidebar.tsx`.
- Системные роли — пересчитать `allowed_sections` (убрать bonus.* у `admin`, `accountant`).
- Документация: блок «Bonus Subsystem» из `CLAUDE.md`, `docs/BONUS_SYSTEM_GUIDE.md`, директория `bonus_service/`.

**Тесты:**
- `pytest` зелёный без bonus-тестов.
- Health check `/api/health` отвечает.
- В sidebar нет битых пунктов.
- В sidebar нет «АДМИНИСТРИРОВАНИЕ» → bonus.

**Definition of done:** ✅
- ✅ Миграция `012_drop_bonus.sql` применена на dev и prod (`UPDATE 2; DROP INDEX; ALTER TABLE; DROP TABLE × 11`).
- ✅ `app/bonus/`, `tests/bonus/`, `bonus_service/` отсутствуют.
- ✅ В `CLAUDE.md` блок про bonus отсутствует (51 ref → 0).
- ✅ `pytest`: 120 passed; `pnpm build`: успешен (887KB).
- ✅ Production контейнер пересобран и задеплоен; `/api/bonus/schemes` → 404; в логах нет «Bonus data sources registered».

**Риски:** учтены — backup-дамп всех 11 таблиц с данными сделан перед `DROP TABLE` (`bonus_calculation` имела 51 строку, `bonus_scheme` 56, и т.д.). Архив на сервере, gitignored.

---

### Фаза 1 — `iiko_source_domain` в `departments` ✅ ВЫПОЛНЕНО (2026-05-25)

> **Commit:** `d6adef6 feat(departments): tag departments by iiko_source_domain` — 11 файлов, +542 / −16.

**Цель:** на уровне БД и loader-а фиксировать, из какого iiko-сервера приехало подразделение.

**База:**
- Миграция `013_iiko_source_domain.sql`:
  - `ALTER TABLE departments ADD COLUMN iiko_source_domain TEXT;`
  - Backfill для существующих 91 строк: одноразовый Python-скрипт `scripts/backfill_iiko_source_domain.py` — для каждого domain из `IIKO_DOMAINS` дёргает `/resto/api/corporation/departments` и обновляет совпадающие по `id` записи.
  - После backfill: `ALTER TABLE departments ALTER COLUMN iiko_source_domain SET NOT NULL;`
  - Индекс: `CREATE INDEX idx_departments_iiko_source ON departments(iiko_source_domain);`

**Backend:**
- `app/services/iiko_department_loader.py`:
  - `fetch_departments_from_single_domain` возвращает `(domain, [departments])` или прокидывает domain в каждый dict.
  - `sync_departments` заполняет `iiko_source_domain` при insert/update.
- `app/routers/department.py::serialize_department` — добавить `iiko_source_domain` в response.

**Frontend:**
- `frontend/src/lib/iiko-sources.ts` — маппинг URL → имя.
- `frontend/src/types/department.ts` — добавить `iikoSourceDomain: string`.
- `frontend/src/pages/departments-page.tsx` — фильтр «Источник iiko» (селект Сандык/Мадлен/все) + колонка в таблице.

**Тесты:**
- Unit: `iiko_department_loader.sync_departments` пишет `iiko_source_domain` для записи из каждого домена (мок httpx через respx).
- Smoke: `curl /api/departments/` возвращает поле.

**Definition of done:** ✅
- ✅ В БД у всех 91 подразделений `iiko_source_domain` заполнен. Распределение: **Sandy 61 / Madlen 30**.
- ✅ Колонка переведена в `NOT NULL` после backfill.
- ✅ Свежий sync не сбрасывает поле в NULL (loader сохраняет на каждой записи и при INSERT, и при UPDATE).
- ✅ `GET /api/departments/?limit=N` возвращает `iiko_source_domain` для каждой записи.
- ✅ UI: добавлен селект «Источник iiko» (Сандык/Мадлен/все) и колонка «Источник» в таблице.
- ✅ Тесты: 8 новых unit-тестов (`tests/unit/test_iiko_department_source_domain.py`), полный прогон 128 passed.

**Фактические находки и решения по ходу:**
- В loader-е используется helper `_domain_host(url)` (`urlparse(...).hostname`), который хранит только **bare hostname** (`sandy-co-co.iiko.it`), без scheme/port/path — устойчиво к смене URL.
- На фронте `frontend/src/lib/iiko-sources.ts` держит маппинг host → label + порядок `KNOWN_IIKO_SOURCES`. Неизвестный host отображается как-есть (graceful degradation).
- Selectbox «Источник iiko» собирается динамически из реально присутствующих в выборке хостов + порядок задан `KNOWN_IIKO_SOURCES` — расширение для нового домена не требует трогать UI-код.
- Backfill-скрипт `scripts/backfill_iiko_source_domain.py` идемпотентен: повторный запуск переписывает значения и no-op на `SET NOT NULL` (уже NOT NULL).
- `scripts/` теперь копируется в Docker-образ (`Dockerfile` обновлён, `.dockerignore` исправлен) — будущие one-shot скрипты доступны через `docker exec sales-forecast-app python -m scripts.<name>`.
- В коммит включены не-мои уже-в-tree правки (`is_active` flag на основе `last_sale_date`) в `routers/department.py` + `pages/departments-page.tsx` + `types/department.ts` — оставлены, чтобы не плодить ortogonal-коммиты.

---

### Фаза 2 — Номенклатура (products + groups + categories) ✅ ВЫПОЛНЕНО (2026-05-25)

> **Commit:** `8b5798e feat(menu): sync iiko nomenclature catalog (products + groups + categories)` — 19 файлов, +1596 / −4.
> **Live sync:** 25,283 продуктов / 1,130 групп / 136 категорий за ~18 сек. Sandy 18,398 · Madlen 6,885.

**Definition of done (фактически):** ✅
- ✅ Миграция `014_nomenclature.sql` применена, 3 таблицы + индексы (`pg_trgm` GIN на `product.name`).
- ✅ Loader `iiko_nomenclature_loader.py` с batch upsert через `execute_values(fetch=True)`.
- ✅ APScheduler 01:00 (перед employees 01:30 и sales 02:00).
- ✅ API `/api/menu/categories|groups|groups/tree|products|products/{id}|sync` — все endpoint'ы 200.
- ✅ Страницы `/menu/products` (фильтры + поиск + пагинация) и `/menu/groups` (дерево).
- ✅ Sidebar секция «Меню», section keys `menu.products` + `menu.groups`.
- ✅ Тесты: 139 passed (+11 unit для `_domain_host` и `_to_decimal_str`).

**FK резолв в реальной БД:**
| Источник | DISH | GOODS | PREPARED | MODIFIER | SERVICE |
|---|---|---|---|---|---|
| Sandy | 100% | 95.9% | 99.8% | 100% | 98.8% |
| Madlen | 100% | 100% | 100% | 100% | 100% |

**Фактические находки и решения по ходу:**
- В `products/list` поле `parent` указывает на UUID **группы** (не на другой product), поэтому FK product→group через `nomenclature_group` корректен.
- **Критичный баг psycopg2:** `execute_values(...)` с `RETURNING` + `cur.fetchall()` отдаёт **только последнюю страницу** (default `page_size=100`). При 772 группах Sandy в `group_map` попадало ~72 записи, и 84% products теряли `group_id`. Фикс — передать `fetch=True` (тогда execute_values сам собирает все страницы и возвращает их как list).
- iiko-тип `OUTER` (83 записи Sandy) не имеет parent-группы — это «внешние» продукты вне основного каталога. Хранятся как есть, `group_id=NULL`.
- Категории Madlen (96) > Sandy (40) — у Мадлен более глубокая каталогизация.
- Группы в фронте — 97 root для Sandy и ~42 для Madlen после фильтра `is_deleted=false`.

**Дополнительные эндпоинты, найденные в payload и переехавшие в колонки:**
`defaultSalePrice`, `estimatedPurchasePrice`, `unitWeight`, `coldLossPercent`, `hotLossPercent`, `taxCategory`, `accountingCategory`, `defaultIncludedInMenu`. Всё остальное живёт в `iiko_payload JSONB`.

---

### Фаза 2 (план) — для истории, не менялся:

**Цель:** загрузить и хранить полный справочник iiko-номенклатуры. Это основа для резолва позиций чеков и для будущих рецептов/цен.

**База:** миграция `014_nomenclature.sql`
```sql
CREATE TABLE nomenclature_group (
  id BIGSERIAL PRIMARY KEY,
  iiko_source_domain TEXT NOT NULL,
  iiko_group_id UUID NOT NULL,
  parent_id BIGINT REFERENCES nomenclature_group(id),
  name TEXT NOT NULL,
  num TEXT,
  is_deleted BOOLEAN NOT NULL DEFAULT false,
  synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (iiko_source_domain, iiko_group_id)
);
CREATE INDEX idx_nomenclature_group_parent ON nomenclature_group(parent_id);

CREATE TABLE nomenclature_category (
  id BIGSERIAL PRIMARY KEY,
  iiko_source_domain TEXT NOT NULL,
  iiko_category_id UUID NOT NULL,
  name TEXT NOT NULL,
  is_deleted BOOLEAN NOT NULL DEFAULT false,
  synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (iiko_source_domain, iiko_category_id)
);

CREATE TABLE product (
  id BIGSERIAL PRIMARY KEY,
  iiko_source_domain TEXT NOT NULL,
  iiko_product_id UUID NOT NULL,
  num TEXT,
  code TEXT,
  name TEXT NOT NULL,
  type TEXT NOT NULL,  -- DISH | GOODS | MODIFIER | PREPARED | SERVICE
  group_id BIGINT REFERENCES nomenclature_group(id),
  category_id BIGINT REFERENCES nomenclature_category(id),
  measure_unit TEXT,
  default_sale_price NUMERIC(14,2),
  cost_price NUMERIC(14,4),
  tax_category_id UUID,
  weight_kg NUMERIC(10,4),
  is_deleted BOOLEAN NOT NULL DEFAULT false,
  is_included_in_menu BOOLEAN NOT NULL DEFAULT true,
  iiko_payload JSONB,
  synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (iiko_source_domain, iiko_product_id)
);
CREATE INDEX idx_product_group ON product(group_id);
CREATE INDEX idx_product_type ON product(type);
CREATE INDEX idx_product_name_trgm ON product USING gin (name gin_trgm_ops);
-- требует CREATE EXTENSION pg_trgm; в миграцию
```

**Backend:**
- `app/models/menu.py` — модели `Product`, `NomenclatureGroup`, `NomenclatureCategory`. Re-export из `app/models/__init__.py`.
- `app/services/iiko_nomenclature_loader.py`:
  - `fetch_groups_from_single_domain(domain)` → GET `/resto/api/v2/entities/products/group/list`
  - `fetch_categories_from_single_domain(domain)` → GET `/resto/api/v2/entities/products/category/list`
  - `fetch_products_from_single_domain(domain)` → GET `/resto/api/v2/entities/products/list?includeDeleted=true`
  - `sync()` — последовательно: categories → groups (с резолвом `parent_id` через iiko_group_id → BIGINT id) → products (с резолвом group/category).
  - Batch upsert через `INSERT ... ON CONFLICT (iiko_source_domain, iiko_<entity>_id) DO UPDATE`.
- `app/routers/menu.py` (новый):
  - `GET /api/menu/products` — фильтры: `search`, `group_id`, `category_id`, `type`, `iiko_source_domain`, `is_deleted`, пагинация.
  - `GET /api/menu/products/{id}` — детально, JOIN на group и category.
  - `GET /api/menu/groups` — иерархия (tree response).
  - `GET /api/menu/categories`.
  - `POST /api/menu/sync` — ручной триггер (admin only).
- `app/schemas/menu.py` — Pydantic схемы.
- `app/main.py` — register router.

**Scheduler:**
- 01:00 ежедневно — `iiko_nomenclature_loader.sync()`.

**Frontend:**
- `frontend/src/types/menu.ts` — `Product`, `NomenclatureGroup`, `NomenclatureCategory`.
- `frontend/src/hooks/use-menu.ts` — TanStack Query хуки.
- `frontend/src/pages/menu/products-page.tsx` — таблица с фильтрами, поиск, селект источника, селект группы.
- `frontend/src/pages/menu/groups-page.tsx` — дерево групп (можно отложить, MVP — список).
- Sidebar: новая секция «МЕНЮ» с пунктами `/menu/products`, `/menu/groups`.
- Section keys: `menu.products`, `menu.groups` — в `auth_ui.py::AVAILABLE_SECTIONS` + `frontend/src/types/auth.ts::SectionKey`.

**Тесты:**
- `tests/services/test_iiko_nomenclature_loader.py` — moc httpx через respx, проверка корректного резолва group → BIGINT id.
- `tests/routers/test_menu.py` — фильтры, пагинация.

**Definition of done:**
- В БД: ~3-10 тыс. SKU × 2 домена = 6-20 тыс. строк в `product`.
- UI `/menu/products` — поиск по названию работает.
- `POST /api/menu/sync` отрабатывает за < 60 секунд.

**Что критично проверить перед началом:**
- Curl на оба домена: `curl "https://sandy-co-co.iiko.it/resto/api/v2/entities/products/list?key=$TOKEN"` — отдаёт ли учётка `IIKO_LOGIN` нужный набор. На некоторых iiko-серверах для `/entities/*` нужна отдельная роль API-пользователя. Если 403 — запросить роль у владельца iiko.
- Размер ответа `products/list` — если > 50 МБ, поднять таймаут httpx до 180с.

---

### Фаза 3 — Чеки + позиции ✅ ВЫПОЛНЕНО (2026-05-25)

> **Commit:** `8cd869f feat(receipts): Phase 3 — partitioned receipt/receipt_item tables with iiko OLAP sync` — 21 файл, +1848 / −6.
> **Live sync (1 день, 2026-05-24):** Sandy 2,503 чеков / 12,425 позиций + Madlen 1,789 / 5,102 = **4,292 чека, 17,527 позиций**, 100% product resolution.

**Definition of done (фактически):** ✅
- ✅ Миграция `015_receipts.sql` применена: партиционированные `receipt` + `receipt_item` (36 месячных партиций 2025-01..2027-12), 5 индексов.
- ✅ Loader `iiko_receipts_loader.py`: расширенный OLAP с `DishId`/`DishName`/`DishCode`/`DishGroup`/`DishCategory`, batch upsert через `execute_values(fetch=True)`, resolve DishId→product.id и WaiterName→employee.id.
- ✅ APScheduler: daily sync 02:15, gap check 11:30.
- ✅ API: `GET /api/receipts` (фильтры + пагинация), `GET /api/receipts/{id}?open_date=` (позиции), `GET /api/receipts/stats/by-product` (топ блюд), `POST /api/receipts/sync`.
- ✅ Frontend: журнал чеков `/receipts` (фильтры + диалог деталей) и продажи по блюдам `/receipts/stats` (KPI + таблица).
- ✅ Sidebar секция «Чеки», section keys `receipts.list` + `receipts.stats`.
- ✅ Nginx: `proxy_read_timeout 300s` для `/api/receipts/sync`.
- ✅ Тесты: 10 unit-тестов (парсинг OLAP, группировка, дробные qty, _to_float, _domain_host).
- ✅ Partition pruning подтверждён через `EXPLAIN`: запрос по 1 дню сканирует только `receipt_2026_05`.
- ✅ Идемпотентность: повторный sync не дублирует записи (upsert ON CONFLICT работает).

**Фактические находки и решения по ходу:**

- **`DishAmountInt` — НЕ int!** Madlen: сотни дробных значений (0.24, 1.168, 1.674 — весовые позиции). Sandy: 16 из 12k. Тип `qty` → `NUMERIC(12,3)`, не INTEGER.
- **`DishSumInt` — в тенге** (целых), итого за позицию (price × qty). `price_per_unit` вычисляется как `dish_sum / qty` при вставке.
- **Поле оплаты — `PayTypes`** (не `PaymentTypes`). НЕ включено в groupBy основного запроса — иначе позиции дублируются при split-платежах. Оставлено на Phase 5+.
- **`PriceCategory`** из плана — не включено, избыточно для MVP.
- **Employees без `iiko_source_domain`**: таблица `employees` не имеет колонки домена (мерж по UUID между доменами). Lookup по имени делается без фильтра по домену.
- **FK receipt_item → receipt** опущен в пользу application-level consistency. Причина: composite FK `(receipt_id, open_date) REFERENCES receipt(id, open_date)` через партиционированные таблицы создаёт overhead при bulk DELETE+INSERT items.
- **FK receipt.department_id, receipt.waiter_employee_id, receipt_item.product_id** — указаны в DDL миграции, но не в SQLAlchemy model (partitioned tables + SQLAlchemy ORM = лишние проблемы с mapper). Constraint enforcement — на уровне PostgreSQL.
- **`menu_reconciliation.py`** из плана — не реализован. При 100% product resolution (все DishId совпали с product.iiko_product_id) — reconciliation job не нужен. Если в будущем появятся NULL product_id — добавить.
- **`scripts/create_receipt_partitions.py`** — создаёт партиции на 6 месяцев вперёд, идемпотентен. Пока НЕ подключён к APScheduler (достаточно 36 партиций до 2027-12). Подключить при необходимости.
- **Объём OLAP-ответа**: Sandy 6.4 МБ + Madlen 2.8 МБ за 1 день — httpx timeout 180s достаточен. Чанкинг по подразделениям не нужен.

**Фактическая схема (отличия от плана):**

```sql
-- receipt: убраны open_time, payment_types, total_sum_with_discount, is_deleted
-- (OLAP не отдаёт эти поля; is_deleted фильтруется на уровне запроса)
-- Добавлены: items_count (кол-во позиций в чеке)
CREATE TABLE receipt (
  id BIGSERIAL,
  department_id UUID NOT NULL REFERENCES departments(id),
  open_date DATE NOT NULL,
  order_num INTEGER NOT NULL,
  close_time TIMESTAMP NOT NULL,
  order_type TEXT,
  table_num TEXT,
  waiter_name TEXT,
  waiter_employee_id UUID REFERENCES employees(id),
  guest_num INTEGER,
  total_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
  discount_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
  return_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
  items_count INTEGER NOT NULL DEFAULT 0,
  synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (id, open_date),
  UNIQUE (department_id, open_date, order_num)
) PARTITION BY RANGE (open_date);

-- receipt_item: snapshot-поля переименованы в dish_name/dish_code/dish_group/dish_category
-- (напрямую из OLAP, без prefix product_*_snapshot)
-- Добавлен iiko_dish_id UUID для re-resolve при необходимости
CREATE TABLE receipt_item (
  id BIGSERIAL,
  receipt_id BIGINT NOT NULL,
  open_date DATE NOT NULL,
  product_id BIGINT REFERENCES product(id),
  iiko_dish_id UUID,
  dish_name TEXT NOT NULL,
  dish_code TEXT,
  dish_group TEXT,
  dish_category TEXT,
  qty NUMERIC(12,3) NOT NULL,
  price_per_unit NUMERIC(14,2),
  dish_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
  discount_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
  return_sum NUMERIC(14,2) NOT NULL DEFAULT 0,
  PRIMARY KEY (id, open_date)
) PARTITION BY RANGE (open_date);
```

**Реальные метрики:**
| Домен | Чеков/день | Позиций/день | Уник. блюд | OLAP размер | Sync время |
|---|---|---|---|---|---|
| Sandy | 2,503 | 12,425 | 579 | 6.4 МБ | ~12с |
| Madlen | 1,789 | 5,102 | 575 | 2.8 МБ | ~8с |
| **Итого** | **4,292** | **17,527** | **1,154** | **9.2 МБ** | **~20с** |

**Эндпоинты не реализованные из плана (отложены):**
- `GET /api/receipts/stats/by-hour-product` — heatmap блюдо×час (Phase 5, per-SKU forecasting)
- `GET /api/receipts/auto-sync/status` — статус авто-загрузок (добавить по необходимости)

---

### Фаза 4 — Цены приказами ✅ ВЫПОЛНЕНО (2026-05-28, через правильный эндпоинт)

> **ВАЖНОЕ ИСПРАВЛЕНИЕ (2026-05-28):** ранее Фаза 4 была удалена с выводом «цен в API нет, эндпоинт `/resto/api/v2/reports/priceList` → 404». **Это была ошибка — тестировался неправильный URL.** Рабочий эндпоинт — **`GET /resto/api/v2/price`** (iiko 7.8). Он отдаёт настоящие цены из меню с интервалами `[dateFrom, dateTo]` и `documentId` приказа.
>
> **Реализация:** миграция `024_sku_catalog_price.sql`, модель `SkuCatalogPrice`, загрузчик `app/services/iiko_price_loader.py`, scheduler Sunday 03:20.
>
> **Live sync:** Sandy 34,449 + Madlen 128,984 = **163,433 ценовых интервала, 100% резолв** продуктов. 33,300 пар имеют реальную вариацию цены (≥2 цены).
>
> **Зачем это критично:** до этого `sku_price_history` и эластичность строились на производной цене `выручка/количество`, загрязнённой миксом модификаторов и весовыми позициями (~49% высокооборотных SKU имели дневную волатильность цены >5% без реальных изменений в меню). Это давало attenuation bias в эластичности. Каталожная цена — чистый источник, см. [`PRICING_SYSTEM_ROADMAP.md`](PRICING_SYSTEM_ROADMAP.md) B2.
>
> **Связанные эндпоинты iiko 7.8** (документация в `docs/*.pdf`): `GET /resto/api/v2/documents/menuChange` (сами приказы — кто/когда/зачем менял цену), `GET /resto/api/v2/entities/periodSchedules` (расписания для SCHEDULED-цен по времени). Пока загружаем только BASE-цены; SCHEDULED (бизнес-ланч и т.п.) — отложено.

---

### Фаза 5 — Техкарты + cost-аналитика + прогноз по SKU

**Цель:** хранить состав и нормы списания блюд, считать себестоимость позиций чека на дату, начать прогнозировать продажи на уровне SKU.

#### 5.1 Техкарты ✅ ВЫПОЛНЕНО (2026-05-25)

> **Commit:** `50211cb feat(recipes): Phase 5.1 — assembly charts (tech cards) sync + API + UI` — 11 файлов, +721 / −3.
> **Live sync:** Sandy 27,431 рецептов / 154,309 ингредиентов + Madlen 3,722 / 16,844 = **31,153 рецепта, 171,153 ингредиентов**.

**Definition of done (фактически):** ✅
- ✅ Миграция `016_recipes.sql` (не 017 — Фаза 4 пропущена): `recipe` + `recipe_ingredient` с FK на `product`, индексы.
- ✅ Loader `iiko_recipe_loader.py`: bulk fetch через `assemblyCharts/getAll` (Sandy 39 МБ, Madlen 5 МБ), batch upsert `execute_values(fetch=True)`, resolve assembledProductId→product.id (99.9% Sandy, 100% Madlen), delete+insert ингредиентов.
- ✅ APScheduler: weekly Sun 03:30.
- ✅ API: `GET /api/menu/products/{id}/recipe` (ингредиенты с резолвом имён), `GET /api/menu/recipes` (список), `POST /api/menu/recipes/sync`.
- ✅ UI: кнопка «Техкарта» (ChefHat) на каждой строке номенклатуры → диалог с таблицей ингредиентов (брутто / после х/о / нетто).

**Фактическая схема (отличия от плана):**
- Natural key = `(iiko_source_domain, iiko_assembly_chart_id)` вместо `(product_id, effective_from)` + EXCLUDE. Причина: iiko отдаёт `id` карты как стабильный UUID, версионирование через `dateFrom`/`dateTo` уже в данных. EXCLUDE constraint не нужен — iiko гарантирует неперекрытие.
- `amount_in` / `amount_middle` / `amount_out` вместо `norm_qty` + `cold_loss_pct` / `hot_loss_pct`. iiko отдаёт три стадии обработки напрямую (до обработки / после х/о / после т/о), не процент потерь.
- Модель в `app/models/recipe.py` (отдельный файл), не в `menu.py`.
- `iiko_payload JSONB` хранит полную карту без массива `items` (ингредиенты в отдельной таблице).

**Фактические находки:**
- `preparedCharts` и `deletedAssemblyChartIds` пусты на обоих доменах (все данные в `assemblyCharts`).
- 934 из 10,130 Sandy-карт без ингредиентов (пустые заготовки).
- Sandy: 567 закрытых карт (dateTo != null), 9,563 открытых. Madlen: 373 / 2,308.
- Ответ `getAll` не зависит от `dateFrom` параметра (отдаёт все карты за всю историю). `dateFrom=2020-01-01` используется формально.
- 8 из 9,563 Sandy assembledProductId не нашлись в product (удалённые продукты с `includeDeleted=false` при sync номенклатуры? — не критично).

#### 5.2 Cost-аналитика ✅ ВЫПОЛНЕНО (2026-05-25)

> **Commit:** `a08e571 feat(cost): Phase 5.2 — cost price and margin from iiko OLAP ProductCostBase` — 8 файлов, +92 / −13.
> **Данные за 1 день (2026-05-24):** выручка 37,123,814 ₸ / себестоимость 12,057,184 ₸ / маржа 25,066,631 ₸ (67.5%). Себестоимость доступна для 86.5% позиций (15,164 из 17,527).

**Реализация (отличается от плана):**

Вместо рекурсивного расчёта через рецепты (`cost_calculator.py`) используются готовые агрегаты из iiko OLAP:
- `ProductCostBase.ProductCost` — себестоимость позиции (iiko считает её на своей стороне по рецептам + закупочным ценам)
- `ProductCostBase.Percent` — food cost % (себестоимость / выручка)

Эти поля добавлены в OLAP-запрос чеков и сохраняются в `receipt_item.cost_price` / `receipt_item.food_cost_percent` (миграция `017_receipt_item_cost.sql`).

**Definition of done:** ✅
- ✅ `GET /api/receipts/{id}` отдаёт `cost_price`, `food_cost_percent`, `margin` per позицию.
- ✅ `GET /api/receipts/stats/by-product` отдаёт `total_cost`, `margin`, `avg_food_cost_pct` per блюдо + `total_cost`, `total_margin` в итогах.
- ✅ UI: диалог деталей чека — колонки Себест./Маржа/FC%. Страница «Продажи по блюдам» — KPI-карточки Выручка/Себестоимость/Маржа + колонки в таблице.
- ✅ Покрытие данных: 86.5% позиций имеют себестоимость (13.5% без данных — модификаторы, комплименты, позиции с нулевой суммой).

**Почему не `cost_calculator.py` из плана:** iiko уже считает себестоимость по рецептам + закупочным ценам на своей стороне и отдаёт готовый результат через OLAP. Рекурсивный расчёт через наши таблицы `recipe` / `recipe_ingredient` дал бы тот же результат, но потребовал бы закупочные цены ингредиентов (`estimated_purchase_price`), которые заполнены только у 6 из 18,581 продуктов. OLAP-подход надёжнее и проще.

#### 5.3 Прогноз по SKU ✅ ВЫПОЛНЕНО (2026-05-25)

> **Архитектура**: один глобальный LightGBM (не per-SKU) с ~74 признаками. Target: SUM(qty) per (department, product, date). Только type IN ('DISH', 'GOODS').

**Data layer:**
- Миграция `018_sku_daily_sales.sql`: таблицы `sku_daily_sales` (агрегат из receipt_item) + `sku_forecasts` (хранение прогнозов).
- `app/services/sku_daily_aggregation_service.py`: INSERT ... ON CONFLICT из receipt_item, вызывается автоматически после каждого receipt sync.
- `app/models/sku_forecast.py`: SQLAlchemy модели SkuDailySales, SkuForecast.

**ML pipeline:**
- `app/services/sku_training_service.py`: ~74 фичи (23 time + 18 dept + 11 operational + 8 SKU static + 11 SKU rolling + 4 cross). Zero-expansion для активных SKU (sold in last 30 days). Переиспользует TrainingDataService для time/dept/operational фичей.
- `app/agents/sku_forecaster_agent.py`: LightGBM (600 trees, lr=0.03, depth=7, log1p target). Singleton. train_model + forecast_department_skus (batch predict all active SKUs).

**API:**
- `app/routers/forecast/sku.py`:
  - `POST /api/forecast/sku/retrain` — обучение модели
  - `GET /api/forecast/sku/model/info` — метаданные
  - `GET /api/forecast/sku/batch?department_id=&from_date=&to_date=&top_n=50` — прогноз
  - `GET /api/forecast/sku/top-n` — топ SKU по выручке
  - `GET /api/forecast/sku/comparison` — факт vs прогноз
  - `GET /api/forecast/sku/export/csv` — CSV экспорт
  - `POST /api/forecast/sku/aggregate/backfill` — backfill агрегации

**Frontend:**
- Страница `/forecast/sku` с фильтрами, KPI-карточками, BarChart top-10, сортируемой таблицей, блоком модели (admin).
- Section key `forecast.sku`, sidebar entry, protected route.

**Scheduler:** Sunday 03:45 — weekly SKU model retraining.

**Prerequisite:** перед первым обучением нужна история чеков за 6+ месяцев (POST /api/receipts/sync) + backfill агрегации (POST /api/forecast/sku/aggregate/backfill).

#### 5.4 Анализ ценовой эластичности

- Сервис `app/services/price_elasticity_service.py`:
  - На исторических парах (cena, qty) для одного SKU × подразделение — оценка коэффициента эластичности (log-log regression).
  - `GET /api/menu/products/{id}/price-elasticity?department_id=&from=&to=`.
- UI — на странице SKU detail вкладка «Эластичность»: scatter plot + кривая + рекомендация по оптимальной цене.

**Definition of done (вся Фаза 5):**
- ✅ В БД: 31,153 техкарты, 171,153 ингредиентов (Phase 5.1).
- ✅ На странице блюда — кнопка «Техкарта» → диалог с ингредиентами (Phase 5.1).
- ✅ `GET /api/receipts/{id}` отдаёт cost_price и margin per позицию (Phase 5.2).
- ✅ `GET /api/receipts/stats/by-product` отдаёт маржинальность per SKU (Phase 5.2).
- ✅ LightGBM SKU-модель: глобальная модель с ~74 признаками, страница /forecast/sku, API endpoints (Phase 5.3). MAPE — определится после загрузки 6+ мес. истории чеков.
- ⬜ Эластичность для топ-50 SKU рассчитана (Phase 5.4).

---

## 5. Сводное расписание APScheduler (после всех фаз)

| Время | Задача | Источник |
|---|---|---|
| 01:00 | Sync nomenclature (products + groups + categories) | Фаза 2 ✅ |
| 01:30 | Sync employees (как сейчас) | существующее |
| 02:00 | Sync `sales_summary` (как сейчас) | существующее |
| 02:15 | Sync receipts за вчера | Фаза 3 |
| 02:30 | Sync waiter sales (как сейчас) | существующее |
| 03:00 (Sun) | Weekly model retraining (как сейчас) | существующее |
| 03:30 (Sun) | Sync recipes (full tree) | Фаза 5.1 |
| 03:45 (Sun) | Weekly SKU model retraining | Фаза 5.3 ✅ |
| 04:00 | Daily performance metrics (как сейчас) | существующее |
| 04:00 (Sun) | Create next-month partitions for receipt/receipt_item | Фаза 3 |
| 10:00 | Daily sales gap check (как сейчас) | существующее |
| 11:00 | Daily waiter sales gap check (как сейчас) | существующее |
| 11:30 | Receipts gap check (7 дней) | Фаза 3 |

---

## 6. Объём данных (ориентировочно)

Для 50 подразделений × 200 чеков/день × 5 позиций/чек × 2 домена:
- `receipt`: ~20 тыс./день, ~7.3 млн/год.
- `receipt_item`: ~100 тыс./день, ~36 млн/год.
- `product`: 18,581 строк (два домена, статика).
- `recipe`: 31,153 строк × ~5.5 ингредиентов = 171,153 строк в `recipe_ingredient`.

PostgreSQL 15 + партиционирование по месяцам справится. Индексы выше дают partition pruning по `open_date`.

---

## 7. Открытые вопросы

| # | Вопрос | Статус |
|---|---|---|
| 1 | bonus subsystem не используется и удаление безопасно | ✅ Подтверждено и удалено (Phase 0, 2026-05-25) |
| 2 | Учётка `IIKO_LOGIN` имеет доступ к `/resto/api/v2/entities/products/*` | ✅ 200 на обоих доменах (Sandy 18398 SKU / 32MB, Madlen 16MB) |
| 3 | Учётка имеет доступ к `/resto/api/v2/assemblyCharts/*` | ✅ 200 на обоих доменах; **bulk-эндпоинт `getAll?dateFrom=...` доступен** (Sandy 36MB с `dateFrom/dateTo` версионированием) |
| 4 | `/resto/api/v2/reports/priceList` доступен | ❌ 404 на обоих доменах. **Фаза 4 удалена.** Себестоимость берётся из OLAP `ProductCostBase.*` (Phase 5.2). |
| 5 | Себестоимость доступна через API | ✅ OLAP SALES отдаёт `ProductCostBase.ProductCost` (себестоимость) и `ProductCostBase.Percent` (food cost %). Покрытие 86.5% позиций чеков. Фаза 4 не нужна. |
| 6 | В iiko OLAP `DishAmountInt` — int или float? | ✅ Float! Madlen: сотни дробных значений (весовые позиции). Sandy: 16 из 12k. Тип `receipt_item.qty` = `NUMERIC(12,3)`. |
| 7 | Нужен ли split видимости по компаниям на уровне ролей (Сандык-юзер не видит Мадлен) | ⚠ Опционально, не блокирует. |

### 7.1 Бонусные находки из products/list

`GET /resto/api/v2/entities/products/list` отдаёт значительно больше полезных полей, чем ожидалось — это **снимает необходимость в отдельных Фазах 4 (priceList) и упрощает Фазу 5 (recipes)** в части базовой себестоимости:

| Поле | Назначение | Где использовать |
|---|---|---|
| `defaultSalePrice` | Цена по умолчанию | Источник цены без отдельного priceList-эндпоинта (Фаза 4) |
| `estimatedPurchasePrice` | Расчётная закупочная себестоимость | Быстрый margin-расчёт без раскрытия рецепта (Фаза 5.2 lite) |
| `coldLossPercent`, `hotLossPercent` | Потери при обработке | Точный расчёт нетто-себестоимости (Фаза 5.2) |
| `unitWeight` | Вес порции в кг | Для нормирования и cost-per-gram |
| `parent` | Иерархия групп | Внешний ключ на `nomenclature_group` |
| `category` | Категория блюда | Внешний ключ на `nomenclature_category` |
| `accountingCategory` | Категория учёта | Опционально, можно сохранить в `iiko_payload` |
| `modifiers` | Список модификаторов | Для будущей детализации позиций чека |
| `taxCategory` | Категория НДС | Для финансовой отчётности |
| `defaultIncludedInMenu` | Видимость в меню | Фильтр «активного» меню |
| `barcodes` | Штрих-коды | Опционально |

### 7.2 Bulk-загрузка техкарт (важно для Фазы 5)

`GET /resto/api/v2/assemblyCharts/getAll?dateFrom=YYYY-MM-DD` отдаёт **все** рецепты одним запросом (Sandy 36MB, Madlen 4MB). Каждый assemblyChart содержит `dateFrom`, `dateTo`, `assembledProductId`, `items[]` — это покрывает версионирование, нужное для Фазы 5.1, без 18к отдельных запросов.

Также доступны per-product варианты:
- `getPrepared?productId=&date=&departmentId=` — раскрытая карта (preparedCharts)
- `getTree?productId=&date=&departmentId=` — дерево исходных рецептов (assemblyCharts)
для точечной донагрузки конкретного блюда.

---

## 8. Принципы доработки (правила, как не сломать)

**❌ НЕЛЬЗЯ:**
- Загружать продукты/рецепты/прайсы без `iiko_source_domain` — это сломает резолв позиций чеков.
- Использовать построчный upsert для `receipt_item` (50k строк/день) — только batch через `execute_values`.
- Удалять старые `price_list_entry` / `recipe` записи — версионировать через `effective_to`.
- Резолвить `DishId → product` без учёта `iiko_source_domain` — может вернуть продукт из другой компании при коллизии UUID.
- Создавать партиции `receipt`/`receipt_item` руками вручную — только через `scripts/create_receipt_partitions.py`.
- Делать `SELECT * FROM receipt_item WHERE product_id = ...` без `receipt_open_date BETWEEN ...` — без partition pruning запрос сканирует всю таблицу.

**✅ ОБЯЗАТЕЛЬНО:**
- Все запросы к `receipt`/`receipt_item` — с фильтром по `open_date` / `receipt_open_date`.
- При резолве `DishId` в позиции чека всегда передавать `domain = receipt.department.iiko_source_domain`.
- При изменении прайса — закрывать предыдущую запись (`effective_to`), не апдейтить in-place.
- Снапшоты `product_name_snapshot`, `group_name_snapshot` сохранять при INSERT receipt_item — они должны переживать переименование SKU.
- Лоадеры читают `IIKO_DOMAINS` из settings, никаких хардкоженных URL.

---

## 9. Откат / rollback

Каждая миграция имеет соответствующий `<NNN>_*_down.sql` (или Alembic downgrade). Для Фазы 0 (drop bonus) — перед применением сделать `pg_dump bonus_* > backups/bonus_dump_YYYYMMDD.sql.gz`, чтобы при необходимости можно было восстановить.

---

## 10. Ссылки

- `docs/iiko_sales_integration_guide.md` — основа для OLAP-запросов.
- `docs/iiko_departments_integration_guide.md` — основа для departments.
- `CLAUDE.md` § «iiko API Integration» — текущее состояние интеграции.
- `app/services/iiko_waiter_sales_loader.py` — эталон паттерна multi-domain + name resolution.
- `app/services/iiko_employee_loader.py` — эталон XML-парсинга + merge по UUID.

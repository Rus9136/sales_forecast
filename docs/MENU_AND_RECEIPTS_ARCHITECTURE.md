# Menu, Receipts, Prices & Recipes — Architecture Plan

**Статус:** Phase 0 + Phase 1 + Phase 2 выполнены (2026-05-25), Phase 3 не начата
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

### Фаза 3 — Чеки + позиции

**Цель:** хранить полные чеки с позициями (блюдо/qty/price/discount), идемпотентно синхронизировать.

**База:** миграция `015_receipts.sql`
```sql
CREATE TABLE receipt (
  id BIGSERIAL,
  department_id UUID NOT NULL REFERENCES departments(id),
  order_num INTEGER NOT NULL,
  open_date DATE NOT NULL,
  open_time TIMESTAMP,
  close_time TIMESTAMP NOT NULL,
  order_type TEXT,
  table_num TEXT,
  waiter_name TEXT,
  waiter_employee_id UUID REFERENCES employees(id),
  guest_num INTEGER,
  payment_types TEXT[],
  total_sum NUMERIC(14,2) NOT NULL,
  total_sum_with_discount NUMERIC(14,2),
  discount_sum NUMERIC(14,2),
  return_sum NUMERIC(14,2),
  is_deleted BOOLEAN NOT NULL DEFAULT false,
  synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (id, open_date),
  UNIQUE (department_id, open_date, order_num)
) PARTITION BY RANGE (open_date);

-- Партиции по месяцам — создаются скриптом, см. ниже
CREATE TABLE receipt_2026_05 PARTITION OF receipt FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
-- ... 2026_06, 2026_07, ... на 12 месяцев вперёд

CREATE INDEX idx_receipt_dept_close ON receipt(department_id, close_time);
CREATE INDEX idx_receipt_open_date ON receipt(open_date);

CREATE TABLE receipt_item (
  id BIGSERIAL,
  receipt_id BIGINT NOT NULL,
  receipt_open_date DATE NOT NULL,  -- для партиционирования
  product_id BIGINT REFERENCES product(id),
  product_name_snapshot TEXT NOT NULL,
  product_code_snapshot TEXT,
  group_name_snapshot TEXT,
  category_name_snapshot TEXT,
  qty NUMERIC(12,3) NOT NULL,
  price_per_unit NUMERIC(14,2) NOT NULL,
  sum_no_discount NUMERIC(14,2) NOT NULL,
  sum_with_discount NUMERIC(14,2) NOT NULL,
  discount_sum NUMERIC(14,2),
  return_sum NUMERIC(14,2),
  PRIMARY KEY (id, receipt_open_date),
  FOREIGN KEY (receipt_id, receipt_open_date) REFERENCES receipt(id, open_date) ON DELETE CASCADE
) PARTITION BY RANGE (receipt_open_date);

CREATE TABLE receipt_item_2026_05 PARTITION OF receipt_item FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
-- ... аналогично

CREATE INDEX idx_receipt_item_product ON receipt_item(product_id, receipt_open_date);
CREATE INDEX idx_receipt_item_receipt ON receipt_item(receipt_id, receipt_open_date);
```

**Backend:**
- `app/models/receipts.py` — `Receipt`, `ReceiptItem`.
- `app/services/iiko_receipts_loader.py`:
  - `fetch_from_single_domain(domain, from_date, to_date)` → POST OLAP с расширенным groupBy.
  - `aggregate(raw_rows)` — pandas group по `(Department.Id, OpenDate, OrderNum)` → шапка чека + список позиций.
  - `resolve_products(items, domain)` — batch lookup `product` по `(iiko_source_domain, iiko_product_id)`, проставляем `product_id` или NULL.
  - `resolve_waiters(receipts, domain)` — то же, что в `iiko_waiter_sales_loader._build_name_to_employee_map`.
  - `upsert(receipts, items)` — batch upsert через `execute_values`:
    - `INSERT INTO receipt ... ON CONFLICT (department_id, open_date, order_num) DO UPDATE`.
    - Для items: `DELETE WHERE receipt_id IN (...) AND receipt_open_date IN (...)` + `INSERT` (проще, чем upsert по неестественному ключу).
  - Таймаут httpx: 180с (большой OLAP).
- `app/services/scheduled_receipts_loader.py` — обёртка для APScheduler + gap check (по аналогии с `scheduled_sales_loader`).
- `app/services/menu_reconciliation.py` — отдельный job, который раз в сутки проходит по `receipt_item WHERE product_id IS NULL` и пытается резолвнуть по snapshot имени + `iiko_source_domain` через `department`.
- `scripts/create_receipt_partitions.py` — раз в неделю проверяет, есть ли партиции на следующий месяц, создаёт недостающие.
- `app/routers/receipts.py`:
  - `GET /api/receipts` — фильтры: `department_id`, `from_date`, `to_date`, `waiter_employee_id`, `min_sum`, пагинация.
  - `GET /api/receipts/{id}?open_date=YYYY-MM-DD` — шапка + позиции (open_date обязателен для partition pruning).
  - `GET /api/receipts/stats/by-product` — топ-N блюд по выручке/qty за период.
  - `GET /api/receipts/stats/by-hour-product` — heatmap blue×hour для прогноза.
  - `POST /api/receipts/sync?from_date=&to_date=&department_id=` — ручной триггер.
  - `GET /api/receipts/auto-sync/status`.

**Scheduler:**
- 02:15 ежедневно — `iiko_receipts_loader.sync` за вчера.
- 11:30 ежедневно — gap check за последние 7 дней.
- Воскресенье 04:00 — `scripts/create_receipt_partitions.py`.

**Frontend:**
- `frontend/src/types/receipts.ts`.
- `frontend/src/hooks/use-receipts.ts`.
- `frontend/src/pages/receipts/receipts-page.tsx` — таблица чеков с фильтрами.
- `frontend/src/pages/receipts/receipt-detail-page.tsx` — модалка/страница с позициями.
- `frontend/src/pages/receipts/stats-by-product-page.tsx` — топ-блюд BarChart.
- Sidebar: секция «ЧЕКИ» (`/receipts`, `/receipts/stats/by-product`).
- Section keys: `receipts.list`, `receipts.stats`.

**Nginx:**
- `aqniet.conf` — для `/api/receipts/sync` поднять `proxy_read_timeout` до 300s (большие OLAP-выгрузки).

**Тесты:**
- `tests/services/test_iiko_receipts_loader.py` — fixture с типичным OLAP-ответом, проверка корректной агрегации в шапку + позиции, корректный резолв `product_id`.
- `tests/services/test_receipt_partitions.py` — скрипт создаёт партицию на следующий месяц, повторный запуск идемпотентен.

**Definition of done:**
- За тестовый день (1 день × все 30+ активных подразделений × 2 домена) загружено N чеков, M позиций.
- `EXPLAIN ANALYZE` на `GET /api/receipts` с фильтром `open_date BETWEEN ... AND ...` показывает partition pruning.
- Реальный sync за 1 день укладывается в < 5 минут.

**Что критично проверить перед началом:**
- Проверить, что расширенный OLAP с `DishId` отдаёт UUID, который реально совпадает с `product.iiko_product_id` (curl + grep).
- Оценить размер ответа OLAP на 1 день × 1 домен × 30 подразделений (если > 100 МБ — нужна пагинация/чанкинг по подразделениям).
- В iiko OLAP `DishAmountInt` — реально int, или float? (От этого зависит тип `qty`).

---

### Фаза 4 — Цены приказами

**Цель:** хранить историю цен SKU × подразделение с версионированием.

**База:** миграция `016_price_list.sql`
```sql
CREATE TABLE price_list_entry (
  id BIGSERIAL PRIMARY KEY,
  iiko_source_domain TEXT NOT NULL,
  product_id BIGINT NOT NULL REFERENCES product(id),
  department_id UUID NOT NULL REFERENCES departments(id),
  price NUMERIC(14,2) NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE,  -- NULL = открытая запись
  source_order_id UUID,
  source_order_num TEXT,
  is_included BOOLEAN NOT NULL DEFAULT true,
  synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
  EXCLUDE USING gist (
    product_id WITH =,
    department_id WITH =,
    daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
  )
);
CREATE INDEX idx_price_list_product_dept ON price_list_entry(product_id, department_id, effective_from DESC);
-- требует CREATE EXTENSION btree_gist;
```

**Backend:**
- `app/models/menu.py` (расширить) — `PriceListEntry`.
- `app/services/iiko_price_list_loader.py`:
  - `fetch(domain, department_id, date)` → GET `/resto/api/v2/reports/priceList?departmentId=...&date=...`
  - `sync_for_period(from_date, to_date)` — обходит все активные подразделения × каждую дату.
  - Логика версионирования: для каждой (product, department) сравнить новую цену с актуальной открытой записью. Если цена изменилась — `UPDATE existing SET effective_to = new.effective_from` + `INSERT new`. Если не изменилась — пропустить.
- `app/routers/menu.py` (расширить):
  - `GET /api/menu/products/{id}/price-history?department_id=&from=&to=` — список `price_list_entry`.
  - `GET /api/menu/products/{id}/current-price?department_id=&date=` — текущая открытая цена на дату.
  - `POST /api/menu/price-list/sync?from_date=&to_date=&department_id=` — ручной триггер.

**Scheduler:**
- 01:15 ежедневно — sync прайс-листов за вчера для всех активных подразделений.

**Frontend:**
- `frontend/src/pages/menu/price-history-page.tsx` — для выбранного SKU + подразделения LineChart с историей цены.
- На странице SKU detail — блок «Текущая цена» по каждому подразделению (таблица).

**Тесты:**
- `tests/services/test_iiko_price_list_loader.py` — fixture, проверка корректного закрытия предыдущей записи при изменении цены, идемпотентность при том же значении.
- `tests/services/test_price_list_overlap.py` — EXCLUDE constraint не даёт вставить пересекающиеся периоды.

**Definition of done:**
- В БД для топ-100 SKU × 30 подразделений × 30 дней — корректная история без пересечений.
- UI показывает LineChart истории цены.

**Что критично проверить перед началом:**
- Что отдаёт `/resto/api/v2/reports/priceList` — JSON или XML? Какие поля? (Если эндпоинт недоступен или возвращает другую структуру — план придётся скорректировать. Curl до старта.)
- На некоторых iiko-серверах прайс-листы задаются не «приказами», а напрямую через карточку блюда. Узнать у заказчика, как у Сандык/Мадлен (от этого зависит, нужен ли вообще этот эндпоинт или достаточно `product.default_sale_price`).

---

### Фаза 5 — Техкарты + cost-аналитика + прогноз по SKU

**Цель:** хранить состав и нормы списания блюд, считать себестоимость позиций чека на дату, начать прогнозировать продажи на уровне SKU.

#### 5.1 Техкарты

**База:** миграция `017_recipes.sql`
```sql
CREATE TABLE recipe (
  id BIGSERIAL PRIMARY KEY,
  iiko_source_domain TEXT NOT NULL,
  product_id BIGINT NOT NULL REFERENCES product(id),
  effective_from DATE NOT NULL,
  effective_to DATE,
  output_qty NUMERIC(12,4) NOT NULL,
  output_unit TEXT,
  cost_price NUMERIC(14,4),
  iiko_assembly_chart_id UUID,
  iiko_payload JSONB,
  synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (product_id, effective_from),
  EXCLUDE USING gist (
    product_id WITH =,
    daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
  )
);

CREATE TABLE recipe_ingredient (
  id BIGSERIAL PRIMARY KEY,
  recipe_id BIGINT NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
  ingredient_product_id BIGINT NOT NULL REFERENCES product(id),
  norm_qty NUMERIC(14,6) NOT NULL,
  norm_unit TEXT,
  cold_loss_pct NUMERIC(7,4),
  hot_loss_pct NUMERIC(7,4)
);
CREATE INDEX idx_recipe_ingredient_recipe ON recipe_ingredient(recipe_id);
CREATE INDEX idx_recipe_ingredient_product ON recipe_ingredient(ingredient_product_id);
```

**Backend:**
- `app/models/menu.py` — `Recipe`, `RecipeIngredient`.
- `app/services/iiko_recipe_loader.py`:
  - `fetch_tree(domain, department_id, from_date, to_date)` → GET `/resto/api/v2/assemblyCharts/getTree`.
  - `fetch_prepared(domain, product_id, date)` → GET `/resto/api/v2/assemblyCharts/getPrepared` (для точечной донагрузки).
  - `sync_full()` — раз в неделю проходит по всем активным подразделениям, получает дерево и upsert-ит.
- `app/routers/menu.py` (расширить):
  - `GET /api/menu/products/{id}/recipe?date=YYYY-MM-DD` — карта актуальная на дату + список ингредиентов с резолвом названий.
  - `POST /api/menu/recipes/sync` — ручной триггер.

**Scheduler:**
- Воскресенье 03:30 — `iiko_recipe_loader.sync_full()`.

**Frontend:**
- На странице SKU detail — вкладка «Техкарта»: список ингредиентов, нормы, потери, расчётная себестоимость.

#### 5.2 Cost-аналитика

- Сервис `app/services/cost_calculator.py`:
  - `calculate_receipt_item_cost(item, date)` — найти recipe для `item.product_id` актуальный на `item.receipt_open_date`, посчитать суммарную себестоимость ингредиентов (рекурсивно для полуфабрикатов).
- Расширить `GET /api/receipts/{id}` — отдавать вместе с позициями расчётный `cost_price` и `margin`.
- Дашборд «Маржинальность по SKU» — `GET /api/receipts/stats/margin-by-product?from=&to=&department_id=`.

#### 5.3 Прогноз по SKU

- Расширить `app/services/training_service.py`:
  - Подготовка фичей на уровне `(department_id, product_id, date)` — продажи в qty, день недели, история цены, наличие в прайсе, segment_type, weekend features.
  - Top-N SKU (по выручке) обучаются индивидуально, остальные — fallback на групповой LightGBM (per `group_id`).
- `app/agents/sku_forecaster_agent.py` — обёртка над LightGBM-моделью.
- `app/routers/forecast/sku.py`:
  - `GET /api/forecast/sku/batch?from_date=&to_date=&department_id=&product_id=`
  - `POST /api/forecast/sku/retrain`
  - `GET /api/forecast/sku/comparison`

#### 5.4 Анализ ценовой эластичности

- Сервис `app/services/price_elasticity_service.py`:
  - На исторических парах (cena, qty) для одного SKU × подразделение — оценка коэффициента эластичности (log-log regression).
  - `GET /api/menu/products/{id}/price-elasticity?department_id=&from=&to=`.
- UI — на странице SKU detail вкладка «Эластичность»: scatter plot + кривая + рекомендация по оптимальной цене.

**Definition of done (вся Фаза 5):**
- В БД: техкарты для топ-500 SKU.
- На странице блюда показана техкарта.
- `GET /api/receipts/{id}` отдаёт margin per позицию.
- LightGBM SKU-модель обучена, MAPE на top-10 SKU < 25%.
- Эластичность для топ-50 SKU рассчитана.

---

## 5. Сводное расписание APScheduler (после всех фаз)

| Время | Задача | Источник |
|---|---|---|
| 01:00 | Sync nomenclature (products + groups + categories) | Фаза 2 |
| 01:15 | Sync price-list за вчера для всех активных подразделений | Фаза 4 |
| 01:30 | Sync employees (как сейчас) | существующее |
| 02:00 | Sync `sales_summary` (как сейчас) | существующее |
| 02:15 | Sync receipts за вчера | Фаза 3 |
| 02:30 | Sync waiter sales (как сейчас) | существующее |
| 03:00 (Sun) | Weekly model retraining (как сейчас) | существующее |
| 03:30 (Sun) | Sync recipes (full tree) | Фаза 5 |
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
- `product`: 6-20 тыс. строк (статика).
- `price_list_entry`: ~10-30 тыс./месяц (только при изменении цен).
- `recipe`: ~3-10 тыс. строк × ~5 ингредиентов = 15-50 тыс. строк в `recipe_ingredient`.

PostgreSQL 15 + партиционирование по месяцам справится. Индексы выше дают partition pruning по `open_date`.

---

## 7. Открытые вопросы

| # | Вопрос | Статус |
|---|---|---|
| 1 | bonus subsystem не используется и удаление безопасно | ✅ Подтверждено и удалено (Phase 0, 2026-05-25) |
| 2 | Учётка `IIKO_LOGIN` имеет доступ к `/resto/api/v2/entities/products/*` | ✅ 200 на обоих доменах (Sandy 18398 SKU / 32MB, Madlen 16MB) |
| 3 | Учётка имеет доступ к `/resto/api/v2/assemblyCharts/*` | ✅ 200 на обоих доменах; **bulk-эндпоинт `getAll?dateFrom=...` доступен** (Sandy 36MB с `dateFrom/dateTo` версионированием) |
| 4 | `/resto/api/v2/reports/priceList` доступен | ❌ 404 на обоих доменах. В v1 и альтернативных путях тоже нет. **Используем `defaultSalePrice` из карточки `products/list`** (см. ниже). |
| 5 | Цены в Сандык/Мадлен задаются приказами или из карточки блюда | ⚠ Требует уточнения у заказчика. `defaultSalePrice` в карточке = 0 для некоторых блюд (`Баурсаки комплимент` — возможно действительно 0). Если приказами не задаются — Фаза 4 = просто tracking изменений `defaultSalePrice` между sync'ами; если задаются — нужно искать другой эндпоинт. |
| 6 | В iiko OLAP `DishAmountInt` — int или float? (Влияет на тип `receipt_item.qty`.) | ⚠ Не проверено — отложено до Фазы 3 (один тестовый OLAP-запрос с реальным `DishId`). |
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

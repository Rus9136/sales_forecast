# API: Продажи блюд в разрезе SKU (фактические продажи из чеков)

**Сервис:** Sales Forecast API
**Base URL:** `https://aqniet.space`
**Версия документа:** 2026-06-29
**Источник данных:** чеки iiko (OLAP), позиции каждого чека → таблицы `receipt` / `receipt_item`.

Документ для интеграции из стороннего сервиса. Описывает, как получить фактические продажи **по каждому блюду (SKU)**: количество, выручку, себестоимость, маржу, food cost.

> Это **факт** (что реально продано), а не прогноз. Прогноз продаж по SKU — отдельный контур (`/api/forecast/sku/*`), здесь не описан.

---

## 1. Авторизация

Все эндпоинты требуют Bearer-токен (общий `API_TOKEN` сервиса).

```
Authorization: Bearer <API_TOKEN>
```

Токен запрашивается у команды Sales Forecast. Без него — `401 Unauthorized`.

---

## 2. Главный эндпоинт: агрегированный отчёт по блюдам

### `GET /api/receipts/stats/by-product`

Топ блюд по выручке за период с агрегатами по каждому SKU. **Это основной отчёт «продажи блюд в разрезе SKU».**

#### Query-параметры

| Параметр | Тип | Обяз. | По умолчанию | Описание |
|---|---|---|---|---|
| `from_date` | date (`YYYY-MM-DD`) | да | — | Начало периода (включительно), по учётному дню |
| `to_date` | date (`YYYY-MM-DD`) | да | — | Конец периода (включительно) |
| `department_id` | UUID | нет | все | Фильтр по подразделению |
| `iiko_source_domain` | string | нет | все | Фильтр по сети: `sandy-co-co.iiko.it` (Сандык) или `madlen-group-so.iiko.it` (Мадлен) |
| `limit` | int | нет | 50 | Сколько SKU вернуть (макс. 200), сортировка по выручке убыв. |

#### Пример запроса

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.space/api/receipts/stats/by-product?from_date=2026-06-01&to_date=2026-06-28&limit=100"

# По одному подразделению:
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.space/api/receipts/stats/by-product?from_date=2026-06-01&to_date=2026-06-28&department_id=<uuid>"
```

#### Ответ (`200 OK`)

```json
{
  "period_start": "2026-06-01",
  "period_end": "2026-06-28",
  "department_id": null,
  "items": [
    {
      "product_id": 1423,
      "iiko_dish_id": "a1b2c3d4-0000-0000-0000-000000000000",
      "dish_name": "Плов казахский",
      "dish_group": "Горячие блюда",
      "dish_category": "Кухня",
      "total_qty": 1240.0,
      "total_sum": 3100000.0,
      "total_discount": 45000.0,
      "total_cost": 1085000.0,
      "receipts_count": 1180,
      "avg_price": 2500.0,
      "avg_cost": 875.0,
      "avg_food_cost_pct": 35.0,
      "margin": 2015000.0
    }
  ],
  "total_revenue": 18450000.0,
  "total_cost": 6900000.0,
  "total_margin": 11550000.0,
  "total_items_sold": 9820.0
}
```

#### Поля одного SKU (`items[]`)

| Поле | Тип | Описание |
|---|---|---|
| `product_id` | int \| null | Внутренний ID блюда в номенклатуре. `null`, если позиция ещё не зарезолвлена в справочник |
| `iiko_dish_id` | string \| null | UUID блюда в iiko (стабильный ключ SKU в рамках одной сети) |
| `dish_name` | string | Название блюда |
| `dish_group` | string \| null | Группа номенклатуры iiko |
| `dish_category` | string \| null | Категория номенклатуры iiko (используется как «цех/станция» на стороне потребителя) |
| `total_qty` | float | Суммарно продано единиц за период |
| `total_sum` | float | Выручка по блюду (₸), сумма продаж позиций |
| `total_discount` | float | Сумма скидок (₸) |
| `total_cost` | float \| null | Себестоимость суммарно (₸); `null`, если нет техкарт |
| `receipts_count` | int | В скольких чеках встречалось блюдо |
| `avg_price` | float \| null | Средняя цена за единицу = `total_sum / total_qty` |
| `avg_cost` | float \| null | Средняя себестоимость за единицу |
| `avg_food_cost_pct` | float \| null | Food cost, % = `total_cost / total_sum * 100` |
| `margin` | float \| null | Валовая прибыль (₸) = `total_sum − total_cost` |

#### Итоги по периоду (корень ответа)

| Поле | Описание |
|---|---|
| `total_revenue` | Суммарная выручка по возвращённым SKU |
| `total_cost` | Суммарная себестоимость |
| `total_margin` | `total_revenue − total_cost` |
| `total_items_sold` | Всего продано единиц |

> ⚠️ Итоги считаются **по строкам, попавшим в выдачу** (с учётом `limit`). Чтобы получить полные итоги периода — поднимите `limit` до 200 или запрашивайте без агрессивной отсечки.

---

## 3. Сырьё: список чеков и позиции

Если нужны не агрегаты, а построчные данные (каждая позиция каждого чека).

### `GET /api/receipts` — список чеков

| Параметр | Тип | Обяз. | Описание |
|---|---|---|---|
| `from_date` | date | да | Начало периода |
| `to_date` | date | да | Конец периода |
| `department_id` | UUID | нет | Фильтр по подразделению |
| `iiko_source_domain` | string | нет | Фильтр по сети |
| `waiter_name` | string | нет | Поиск по официанту (ilike) |
| `min_sum` | float | нет | Минимальная сумма чека |
| `limit` | int | нет | По умолч. 100, макс. 500 |
| `offset` | int | нет | Пагинация |

Возвращает массив чеков (без позиций): `id`, `department_id`, `department_name`, `open_date`, `order_num`, `close_time`, `order_type`, `table_num`, `waiter_name`, `guest_num`, `total_sum`, `discount_sum`, `return_sum`, `items_count`, `synced_at`.

### `GET /api/receipts/{receipt_id}` — чек с позициями

| Параметр | Тип | Обяз. | Описание |
|---|---|---|---|
| `open_date` | date | **да** | Учётный день чека — обязателен для partition pruning |

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.space/api/receipts/12345?open_date=2026-06-15"
```

Возвращает поля чека + массив `items[]`, каждая позиция (SKU в чеке):

| Поле | Описание |
|---|---|
| `product_id`, `iiko_dish_id` | Идентификаторы SKU |
| `dish_name`, `dish_code`, `dish_group`, `dish_category` | Описание блюда |
| `qty` | Количество в позиции |
| `price_per_unit` | Цена за единицу |
| `dish_sum` | Сумма позиции (₸) |
| `discount_sum`, `return_sum` | Скидка / возврат |
| `cost_price` | Себестоимость позиции |
| `food_cost_percent` | Food cost позиции, % |
| `margin` | `dish_sum − cost_price` |

---

## 4. Идентификация SKU (важно для интеграции)

- Стабильный ключ блюда — **`iiko_dish_id` (UUID)**, но он уникален только **в рамках одной сети** (Сандык и Мадлен — два разных iiko-сервера, генерируют свои UUID). Для глобальной уникальности используйте пару **`(iiko_source_domain, iiko_dish_id)`** либо внутренний **`product_id`**.
- `product_id` может быть `null`, если позиция чека ещё не зарезолвлена в справочник номенклатуры (новое блюдо до синка). В этом случае опирайтесь на `iiko_dish_id` + snapshot-поля (`dish_name`, `dish_group`, `dish_category`).
- Сети различаются параметром `iiko_source_domain`:
  - `sandy-co-co.iiko.it` → **Сандык**
  - `madlen-group-so.iiko.it` → **Мадлен**

---

## 5. Свежесть данных

Чеки синхронизируются автоматически раз в сутки (~02:15 по серверу) + ежедневная проверка пропусков (~11:30). То есть данные за «вчера» доступны утром. Поле `synced_at` показывает время последней загрузки конкретного чека.

---

## 6. Коды ошибок

| Код | Причина |
|---|---|
| `401` | Нет/неверный Bearer-токен |
| `404` | Чек не найден (неверный `receipt_id` или `open_date`) |
| `422` | Неверные параметры (формат даты, тип UUID и т.п.) |

---

## 7. Шпаргалка

```bash
# Топ-100 блюд по выручке за июнь, вся сеть
GET /api/receipts/stats/by-product?from_date=2026-06-01&to_date=2026-06-28&limit=100

# Топ блюд по одному подразделению
GET /api/receipts/stats/by-product?from_date=2026-06-01&to_date=2026-06-28&department_id=<uuid>

# Только Сандык
GET /api/receipts/stats/by-product?from_date=2026-06-01&to_date=2026-06-28&iiko_source_domain=sandy-co-co.iiko.it

# Список чеков подразделения
GET /api/receipts?from_date=2026-06-01&to_date=2026-06-28&department_id=<uuid>&limit=200

# Детали чека с позициями
GET /api/receipts/{receipt_id}?open_date=2026-06-15
```

Все запросы — с заголовком `Authorization: Bearer <API_TOKEN>`.

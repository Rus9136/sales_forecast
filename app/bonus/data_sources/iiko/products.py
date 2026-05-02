"""Per-employee product-category revenue (ready vs prepared products).

Currently we don't have a category breakdown in the DB, so these adapters
return 0 — schemes that depend on them (combined_products for бариста) will
need either:
  (a) extension of the iiko OLAP loader to fetch DishCategory.Name and
      aggregate per category, or
  (b) manual import.

The adapters are wired so seeds and schemes work without breaking; once the
real data lands in a new table (e.g. sales_by_waiter_category), update the
SQL inside fetch().
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ..base import BonusDataSource, DataSourceParams


class IikoPersonalReadyProducts(BonusDataSource):
    code = "iiko_personal_ready_products_with_discount"
    name = "Личная выручка по готовой продукции"
    description = (
        "Категория 'Готовая' (DishCategory.Name) по конкретному сотруднику. "
        "ЗАГЛУШКА: возвращает 0 — нужно расширить iiko OLAP loader для группировки "
        "sales_by_waiter по категориям блюд."
    )
    value_type = "revenue"
    unit = "KZT"
    category = "iiko_products"
    is_stub = True

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        # TODO: read from sales_by_waiter_category once the loader is extended
        return Decimal(0)


class IikoPersonalPreparedProducts(BonusDataSource):
    code = "iiko_personal_prepared_products_with_discount"
    name = "Личная выручка по приготовленной продукции"
    description = (
        "Категория 'Приготовленная' по конкретному сотруднику. "
        "ЗАГЛУШКА: возвращает 0 (см. iiko_personal_ready_products_with_discount)."
    )
    value_type = "revenue"
    unit = "KZT"
    category = "iiko_products"
    is_stub = True

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        # TODO: read from sales_by_waiter_category once the loader is extended
        return Decimal(0)

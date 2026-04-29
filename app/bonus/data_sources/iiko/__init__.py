"""iiko-based data sources reading from the existing sales_summary / sales_by_waiter tables."""

from .revenue import (  # noqa: F401
    IikoLocationRevenueWithDiscount,
    IikoLocationRevenueDishSum,
    IikoPersonalRevenueWithDiscount,
    IikoPersonalRevenueDishSum,
    IikoSalesPlanLocation,
    IikoSalesPlanPersonal,
)
from .products import (  # noqa: F401
    IikoPersonalReadyProducts,
    IikoPersonalPreparedProducts,
)


def register_iiko_sources() -> None:
    from ..registry import DataSourceRegistry
    DataSourceRegistry.register(IikoLocationRevenueWithDiscount())
    DataSourceRegistry.register(IikoLocationRevenueDishSum())
    DataSourceRegistry.register(IikoPersonalRevenueWithDiscount())
    DataSourceRegistry.register(IikoPersonalRevenueDishSum())
    DataSourceRegistry.register(IikoSalesPlanLocation())
    DataSourceRegistry.register(IikoSalesPlanPersonal())
    DataSourceRegistry.register(IikoPersonalReadyProducts())
    DataSourceRegistry.register(IikoPersonalPreparedProducts())

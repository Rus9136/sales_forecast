"""Sources that read from bonus_manual_kpi (audit, reviews, staffing, profitability)."""

from .manual_kpi import (  # noqa: F401
    ManualAudit,
    ManualKitchenAudit,
    ManualProfitability,
    HrStaffingPercent,
    CrmNegativeReviewsShare,
    CrmIndividualNegativeReviews,
    CrmKitchenReviews,
    CrmRestaurantRating,
    IikoApcGrowth,
    IikoMarginShare,
)


def register_manual_sources() -> None:
    from ..registry import DataSourceRegistry
    DataSourceRegistry.register(ManualAudit())
    DataSourceRegistry.register(ManualKitchenAudit())
    DataSourceRegistry.register(ManualProfitability())
    DataSourceRegistry.register(HrStaffingPercent())
    DataSourceRegistry.register(CrmNegativeReviewsShare())
    DataSourceRegistry.register(CrmIndividualNegativeReviews())
    DataSourceRegistry.register(CrmKitchenReviews())
    DataSourceRegistry.register(CrmRestaurantRating())
    DataSourceRegistry.register(IikoApcGrowth())
    DataSourceRegistry.register(IikoMarginShare())

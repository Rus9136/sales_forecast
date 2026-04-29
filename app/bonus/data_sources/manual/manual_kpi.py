"""Generic adapter that reads a single KPI value from bonus_manual_kpi.

We register multiple adapters under different `code` strings (one per KPI
shape used in scheme configs). Each one looks up bonus_manual_kpi by its
specific kpi_code. This way scheme configs reference logical names like
'manual_audit' or 'crm_negative_reviews_share' rather than internal IDs.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ...models.kpi import BonusManualKpi
from ...utils.decimal_utils import to_decimal
from ..base import BonusDataSource, DataSourceParams


class _ManualKpiBase(BonusDataSource):
    """Reads bonus_manual_kpi by self.kpi_code."""
    kpi_code: str = ""

    def fetch(self, db: Session, params: DataSourceParams) -> Decimal:
        if not params.department_id or not self.kpi_code:
            return Decimal(0)
        row = (
            db.query(BonusManualKpi.fact_value)
            .filter(
                BonusManualKpi.department_id == params.department_id,
                BonusManualKpi.kpi_code == self.kpi_code,
                BonusManualKpi.period_year == params.period.year,
                BonusManualKpi.period_month == params.period.month,
            )
            .scalar()
        )
        return to_decimal(row) if row is not None else Decimal(0)


class ManualAudit(_ManualKpiBase):
    code = "manual_audit"
    kpi_code = "manual_audit"


class ManualKitchenAudit(_ManualKpiBase):
    code = "manual_kitchen_audit"
    kpi_code = "manual_kitchen_audit"


class ManualProfitability(_ManualKpiBase):
    code = "manual_profitability"
    kpi_code = "manual_profitability"


class HrStaffingPercent(_ManualKpiBase):
    code = "hr_staffing_percent"
    kpi_code = "hr_staffing_percent"


class CrmNegativeReviewsShare(_ManualKpiBase):
    code = "crm_negative_reviews_share"
    kpi_code = "crm_negative_reviews_share"


class CrmIndividualNegativeReviews(_ManualKpiBase):
    code = "crm_individual_negative_reviews"
    kpi_code = "crm_individual_negative_reviews"


class CrmKitchenReviews(_ManualKpiBase):
    code = "crm_kitchen_reviews"
    kpi_code = "crm_kitchen_reviews"


class CrmRestaurantRating(_ManualKpiBase):
    code = "crm_restaurant_rating"
    kpi_code = "crm_restaurant_rating"


class IikoApcGrowth(_ManualKpiBase):
    """APC growth — currently entered manually until the iiko adapter computes it."""
    code = "iiko_apc_growth"
    kpi_code = "iiko_apc_growth"


class IikoMarginShare(_ManualKpiBase):
    """Margin share — manual until product-category data is available."""
    code = "iiko_margin_share"
    kpi_code = "iiko_margin_share"

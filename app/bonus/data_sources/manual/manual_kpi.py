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
    name = "Аудит / стандарты"
    description = "% соответствия стандартам обслуживания. Вводится HR через /bonus/manual-kpi."
    value_type = "kpi_percent"
    unit = "%"
    category = "manual"


class ManualKitchenAudit(_ManualKpiBase):
    code = "manual_kitchen_audit"
    kpi_code = "manual_kitchen_audit"
    name = "Аудит кухни"
    description = "% соответствия стандартам кухни (используется для KITCHEN-команд)."
    value_type = "kpi_percent"
    unit = "%"
    category = "manual"


class ManualProfitability(_ManualKpiBase):
    code = "manual_profitability"
    kpi_code = "manual_profitability"
    name = "Рентабельность (факт)"
    description = "Факт рентабельности за период. KPI-движок сравнивает с target из плана."
    value_type = "kpi_percent"
    unit = "%"
    category = "manual"


class HrStaffingPercent(_ManualKpiBase):
    code = "hr_staffing_percent"
    kpi_code = "hr_staffing_percent"
    name = "Укомплектованность штата"
    description = "% от целевого количества сотрудников. Заглушка до интеграции с HR/1С:ЗУП."
    value_type = "kpi_percent"
    unit = "%"
    category = "hr"
    is_stub = True


class CrmNegativeReviewsShare(_ManualKpiBase):
    code = "crm_negative_reviews_share"
    kpi_code = "crm_negative_reviews_share"
    name = "Доля негативных отзывов (точка)"
    description = "% негативных отзывов от общего числа. Заглушка до интеграции с CRM."
    value_type = "kpi_percent"
    unit = "%"
    category = "crm"
    is_stub = True


class CrmIndividualNegativeReviews(_ManualKpiBase):
    code = "crm_individual_negative_reviews"
    kpi_code = "crm_individual_negative_reviews"
    name = "Личные негативные отзывы"
    description = "Кол-во негативных отзывов по конкретному сотруднику. Заглушка до CRM."
    value_type = "kpi_value"
    unit = "count"
    category = "crm"
    is_stub = True


class CrmKitchenReviews(_ManualKpiBase):
    code = "crm_kitchen_reviews"
    kpi_code = "crm_kitchen_reviews"
    name = "Негативные отзывы по кухне"
    description = "Кол-во негативных отзывов о кухне за период. Заглушка до CRM."
    value_type = "kpi_value"
    unit = "count"
    category = "crm"
    is_stub = True


class CrmRestaurantRating(_ManualKpiBase):
    code = "crm_restaurant_rating"
    kpi_code = "crm_restaurant_rating"
    name = "Рейтинг ресторана"
    description = "Средний рейтинг 1-5. Используется как binary KPI (target=5 → 100%, иначе 0%)."
    value_type = "kpi_value"
    unit = "stars"
    category = "crm"
    is_stub = True


class IikoApcGrowth(_ManualKpiBase):
    """APC growth — currently entered manually until the iiko adapter computes it."""
    code = "iiko_apc_growth"
    kpi_code = "iiko_apc_growth"
    name = "Рост среднего чека (APC)"
    description = "% роста среднего чека (Average Per Check) к прошлому периоду. Сейчас вручную."
    value_type = "kpi_percent"
    unit = "%"
    category = "manual"
    is_stub = True


class IikoMarginShare(_ManualKpiBase):
    """Margin share — manual until product-category data is available."""
    code = "iiko_margin_share"
    kpi_code = "iiko_margin_share"
    name = "Доля маржинальных позиций"
    description = "% маржинальных блюд в чеках. Сейчас вручную (нет категорий в OLAP)."
    value_type = "kpi_percent"
    unit = "%"
    category = "manual"
    is_stub = True

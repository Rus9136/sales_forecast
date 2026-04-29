"""Pydantic schemas validating bonus_scheme.config per calculation model."""

from .common import KpiConfig, FlatGrade, RateGrade  # noqa: F401
from .flat_by_kpi import FlatByKpiConfig  # noqa: F401
from .revenue_percent_by_kpi import RevenuePercentByKpiConfig  # noqa: F401
from .revenue_direct import RevenueDirectConfig  # noqa: F401
from .combined_products import CombinedProductsConfig, ProductComponent  # noqa: F401
from .team_revenue_by_kpi import TeamRevenueByKpiConfig  # noqa: F401

CONFIG_VALIDATORS = {
    "flat_by_kpi": FlatByKpiConfig,
    "revenue_percent_by_kpi": RevenuePercentByKpiConfig,
    "revenue_direct": RevenueDirectConfig,
    "combined_products": CombinedProductsConfig,
    "team_revenue_by_kpi": TeamRevenueByKpiConfig,
}


def validate_config(model_code: str, config: dict) -> dict:
    """Validate a config dict against the appropriate Pydantic schema.

    Returns the parsed config (with default values filled in).
    Raises ValueError if `model_code` is unknown or the config is invalid.
    """
    if model_code not in CONFIG_VALIDATORS:
        raise ValueError(
            f"Unknown calculation model: {model_code!r}. "
            f"Known: {sorted(CONFIG_VALIDATORS)}"
        )
    validator = CONFIG_VALIDATORS[model_code]
    return validator.model_validate(config).model_dump(mode="json", by_alias=True)

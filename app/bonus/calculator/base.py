from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .context import CalculationContext
from .result import BonusResult


class BaseBonusModel(ABC):
    """Base interface for all bonus calculation models.

    Subclasses are registered via @register_model('<code>'). The runner
    fetches the model by `scheme.calculation_model` and calls calculate().
    """

    code: str = ""

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """Raise ValueError if config dict is malformed for this model."""

    @abstractmethod
    def calculate(self, config: dict[str, Any], context: CalculationContext) -> BonusResult:
        """Compute the bonus given a validated config and a pre-loaded context."""

    # ------------------------------------------------------------------ #
    # Hooks for the preloader to know which sources to fetch.            #
    # Default implementations cover most models; team_revenue overrides. #
    # ------------------------------------------------------------------ #

    def get_required_kpi_codes(self, config: dict[str, Any]) -> list[str]:
        return [k["code"] for k in config.get("kpis", [])]

    def get_required_revenue_sources(self, config: dict[str, Any]) -> list[str]:
        sources: list[str] = []
        if "revenue_source" in config:
            sources.append(config["revenue_source"])
        for component in config.get("components", []):
            sources.append(component["source"])
        return sources

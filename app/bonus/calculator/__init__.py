"""Calculator engine: pure logic (no DB), plugin registry of 5 models."""

from .registry import CALCULATION_MODELS, register_model, get_model  # noqa: F401
from .base import BaseBonusModel  # noqa: F401
from .context import CalculationContext, KpiFact, ShiftStats  # noqa: F401
from .result import BonusResult, BonusBreakdown  # noqa: F401

# Importing the models package triggers @register_model decorators
from . import models as _models  # noqa: F401

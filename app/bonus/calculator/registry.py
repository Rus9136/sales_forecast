from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseBonusModel


CALCULATION_MODELS: dict[str, type["BaseBonusModel"]] = {}


def register_model(code: str):
    """Decorator that registers a calculation model class under `code`."""
    def decorator(cls):
        if code in CALCULATION_MODELS:
            raise ValueError(f"Calculation model '{code}' is already registered")
        cls.code = code
        CALCULATION_MODELS[code] = cls
        return cls
    return decorator


def get_model(code: str) -> "BaseBonusModel":
    if code not in CALCULATION_MODELS:
        raise ValueError(
            f"Unknown calculation model: {code!r}. "
            f"Registered: {sorted(CALCULATION_MODELS)}"
        )
    return CALCULATION_MODELS[code]()

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProductComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    source: str
    rate: Decimal


class CombinedProductsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "combined_products"
    components: list[ProductComponent]
    apply_shifts_proration: bool = False
    require_no_violations: bool = False

"""Pydantic schemas for /api/menu/*."""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NomenclatureCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iiko_source_domain: str
    iiko_category_id: UUID
    name: str
    is_deleted: bool


class NomenclatureGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iiko_source_domain: str
    iiko_group_id: UUID
    parent_id: Optional[int]
    name: str
    num: Optional[str]
    code: Optional[str]
    position: Optional[int]
    is_deleted: bool


class NomenclatureGroupTreeNode(BaseModel):
    """Group with nested children — used by GET /groups/tree."""
    id: int
    iiko_group_id: UUID
    name: str
    code: Optional[str]
    position: Optional[int]
    is_deleted: bool
    children: List["NomenclatureGroupTreeNode"] = []


NomenclatureGroupTreeNode.model_rebuild()


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iiko_source_domain: str
    iiko_product_id: UUID
    num: Optional[str]
    code: Optional[str]
    name: str
    description: Optional[str]
    type: str
    group_id: Optional[int]
    category_id: Optional[int]
    default_sale_price: Optional[Decimal]
    estimated_purchase_price: Optional[Decimal]
    weight_kg: Optional[Decimal]
    cold_loss_percent: Optional[Decimal]
    hot_loss_percent: Optional[Decimal]
    is_deleted: bool
    is_included_in_menu: bool


class ProductDetailResponse(ProductResponse):
    """Adds resolved group/category names for the detail view."""
    group_name: Optional[str] = None
    category_name: Optional[str] = None


class NomenclatureSyncResponse(BaseModel):
    status: str
    total_categories: int
    total_groups: int
    total_products: int
    per_domain: List[dict]
    errors: List[str]

"""GET / list / sync endpoints for the iiko nomenclature catalog.

See `docs/MENU_AND_RECEIPTS_ARCHITECTURE.md` § Фаза 2.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_api_key_or_bypass, ApiKey
from ..db import get_db
from ..models.menu import NomenclatureCategory, NomenclatureGroup, Product
from ..schemas.menu import (
    NomenclatureCategoryResponse,
    NomenclatureGroupResponse,
    NomenclatureGroupTreeNode,
    NomenclatureSyncResponse,
    ProductDetailResponse,
    ProductResponse,
)
from ..services.iiko_nomenclature_loader import IikoNomenclatureLoaderService

router = APIRouter(prefix="/menu", tags=["menu"])


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=List[NomenclatureCategoryResponse])
def list_categories(
    iiko_source_domain: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> List[NomenclatureCategoryResponse]:
    q = db.query(NomenclatureCategory)
    if iiko_source_domain:
        q = q.filter(NomenclatureCategory.iiko_source_domain == iiko_source_domain)
    if not include_deleted:
        q = q.filter(NomenclatureCategory.is_deleted.is_(False))
    return q.order_by(NomenclatureCategory.name).all()


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@router.get("/groups", response_model=List[NomenclatureGroupResponse])
def list_groups(
    iiko_source_domain: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> List[NomenclatureGroupResponse]:
    q = db.query(NomenclatureGroup)
    if iiko_source_domain:
        q = q.filter(NomenclatureGroup.iiko_source_domain == iiko_source_domain)
    if not include_deleted:
        q = q.filter(NomenclatureGroup.is_deleted.is_(False))
    return q.order_by(NomenclatureGroup.position, NomenclatureGroup.name).all()


@router.get("/groups/tree", response_model=List[NomenclatureGroupTreeNode])
def list_groups_tree(
    iiko_source_domain: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> List[NomenclatureGroupTreeNode]:
    """Return groups as nested tree (parent → children)."""
    q = db.query(NomenclatureGroup)
    if iiko_source_domain:
        q = q.filter(NomenclatureGroup.iiko_source_domain == iiko_source_domain)
    if not include_deleted:
        q = q.filter(NomenclatureGroup.is_deleted.is_(False))
    rows = q.order_by(NomenclatureGroup.position, NomenclatureGroup.name).all()

    nodes: dict[int, NomenclatureGroupTreeNode] = {
        g.id: NomenclatureGroupTreeNode(
            id=g.id,
            iiko_group_id=g.iiko_group_id,
            name=g.name,
            code=g.code,
            position=g.position,
            is_deleted=g.is_deleted,
            children=[],
        )
        for g in rows
    }
    roots: List[NomenclatureGroupTreeNode] = []
    for g in rows:
        node = nodes[g.id]
        if g.parent_id and g.parent_id in nodes:
            nodes[g.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@router.get("/products", response_model=List[ProductResponse])
def list_products(
    search: Optional[str] = Query(None, description="ILIKE on product.name"),
    iiko_source_domain: Optional[str] = Query(None),
    group_id: Optional[int] = Query(None),
    category_id: Optional[int] = Query(None),
    type: Optional[str] = Query(
        None,
        description="DISH | GOODS | MODIFIER | PREPARED | SERVICE",
    ),
    include_deleted: bool = Query(False),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> List[ProductResponse]:
    q = db.query(Product)
    if search:
        q = q.filter(Product.name.ilike(f"%{search}%"))
    if iiko_source_domain:
        q = q.filter(Product.iiko_source_domain == iiko_source_domain)
    if group_id is not None:
        q = q.filter(Product.group_id == group_id)
    if category_id is not None:
        q = q.filter(Product.category_id == category_id)
    if type:
        q = q.filter(Product.type == type)
    if not include_deleted:
        q = q.filter(Product.is_deleted.is_(False))
    return q.order_by(Product.name).offset(offset).limit(limit).all()


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> ProductDetailResponse:
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    group_name = (
        db.query(NomenclatureGroup.name)
        .filter(NomenclatureGroup.id == p.group_id)
        .scalar()
        if p.group_id else None
    )
    category_name = (
        db.query(NomenclatureCategory.name)
        .filter(NomenclatureCategory.id == p.category_id)
        .scalar()
        if p.category_id else None
    )
    return ProductDetailResponse(
        **{c.name: getattr(p, c.name) for c in Product.__table__.columns
           if c.name in ProductResponse.model_fields},
        group_name=group_name,
        category_name=category_name,
    )


# ---------------------------------------------------------------------------
# Sync (manual trigger)
# ---------------------------------------------------------------------------

@router.post("/sync", response_model=NomenclatureSyncResponse)
async def sync_nomenclature(
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> NomenclatureSyncResponse:
    service = IikoNomenclatureLoaderService(db)
    result = await service.sync()
    return NomenclatureSyncResponse(**result)

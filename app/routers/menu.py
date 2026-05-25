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
from ..models.recipe import Recipe, RecipeIngredient
from ..schemas.menu import (
    NomenclatureCategoryResponse,
    NomenclatureGroupResponse,
    NomenclatureGroupTreeNode,
    NomenclatureSyncResponse,
    ProductDetailResponse,
    ProductResponse,
    RecipeDetailResponse,
    RecipeIngredientResponse,
    RecipeResponse,
    RecipeSyncResponse,
)
from ..services.iiko_nomenclature_loader import IikoNomenclatureLoaderService
from ..services.iiko_recipe_loader import IikoRecipeLoaderService

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


# ---------------------------------------------------------------------------
# Recipes (tech cards)
# ---------------------------------------------------------------------------

@router.get("/products/{product_id}/recipe", response_model=Optional[RecipeDetailResponse])
def get_product_recipe(
    product_id: int,
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
):
    """Current (open-ended) recipe for a product, with resolved ingredient names."""
    recipe = (
        db.query(Recipe)
        .filter(Recipe.product_id == product_id, Recipe.date_to.is_(None))
        .first()
    )
    if not recipe:
        return None

    ingredients = (
        db.query(RecipeIngredient)
        .filter(RecipeIngredient.recipe_id == recipe.id)
        .order_by(RecipeIngredient.sort_weight)
        .all()
    )

    # Batch-resolve ingredient names
    ing_pids = [i.ingredient_product_id for i in ingredients if i.ingredient_product_id]
    name_map: dict[int, tuple] = {}
    if ing_pids:
        rows = (
            db.query(Product.id, Product.name, Product.code, Product.type)
            .filter(Product.id.in_(ing_pids))
            .all()
        )
        name_map = {r.id: (r.name, r.code, r.type) for r in rows}

    product_name = db.query(Product.name).filter(Product.id == product_id).scalar()

    return RecipeDetailResponse(
        id=recipe.id,
        iiko_source_domain=recipe.iiko_source_domain,
        product_id=recipe.product_id,
        product_name=product_name,
        date_from=str(recipe.date_from),
        date_to=str(recipe.date_to) if recipe.date_to else None,
        assembled_amount=float(recipe.assembled_amount),
        description=recipe.description,
        technology_description=recipe.technology_description,
        ingredients_count=len(ingredients),
        ingredients=[
            RecipeIngredientResponse(
                id=i.id,
                ingredient_product_id=i.ingredient_product_id,
                ingredient_name=name_map.get(i.ingredient_product_id, (None,))[0] if i.ingredient_product_id else None,
                ingredient_code=name_map.get(i.ingredient_product_id, (None, None))[1] if i.ingredient_product_id else None,
                ingredient_type=name_map.get(i.ingredient_product_id, (None, None, None))[2] if i.ingredient_product_id else None,
                sort_weight=float(i.sort_weight) if i.sort_weight else None,
                amount_in=float(i.amount_in),
                amount_middle=float(i.amount_middle) if i.amount_middle else None,
                amount_out=float(i.amount_out) if i.amount_out else None,
            )
            for i in ingredients
        ],
    )


@router.get("/recipes", response_model=List[RecipeResponse])
def list_recipes(
    iiko_source_domain: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    active_only: bool = Query(True, description="Only open-ended recipes (date_to IS NULL)"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> List[RecipeResponse]:
    q = db.query(Recipe, Product.name).join(Product, Recipe.product_id == Product.id)
    if iiko_source_domain:
        q = q.filter(Recipe.iiko_source_domain == iiko_source_domain)
    if product_id is not None:
        q = q.filter(Recipe.product_id == product_id)
    if active_only:
        q = q.filter(Recipe.date_to.is_(None))
    q = q.order_by(Product.name).offset(offset).limit(limit)

    result = []
    for r, pname in q.all():
        ing_count = (
            db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id == r.id)
            .count()
        )
        result.append(RecipeResponse(
            id=r.id,
            iiko_source_domain=r.iiko_source_domain,
            product_id=r.product_id,
            product_name=pname,
            date_from=str(r.date_from),
            date_to=str(r.date_to) if r.date_to else None,
            assembled_amount=float(r.assembled_amount),
            description=r.description,
            technology_description=r.technology_description,
            ingredients_count=ing_count,
        ))
    return result


@router.post("/recipes/sync", response_model=RecipeSyncResponse)
async def sync_recipes(
    db: Session = Depends(get_db),
    _auth: ApiKey = Depends(get_api_key_or_bypass),
) -> RecipeSyncResponse:
    service = IikoRecipeLoaderService(db)
    result = await service.sync()
    return RecipeSyncResponse(**result)

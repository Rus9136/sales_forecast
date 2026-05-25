"""Recipe (assembly chart) and RecipeIngredient models."""

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, ForeignKey, Numeric, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from ..db import Base


class Recipe(Base):
    __tablename__ = "recipe"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    iiko_source_domain = Column(Text, nullable=False, index=True)
    iiko_assembly_chart_id = Column(UUID(as_uuid=True), nullable=False)
    product_id = Column(BigInteger, nullable=False, index=True)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date)
    assembled_amount = Column(Numeric(12, 4), nullable=False, default=1)
    description = Column(Text)
    technology_description = Column(Text)
    iiko_payload = Column(JSONB)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())

    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan", lazy="select")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredient"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    recipe_id = Column(BigInteger, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False, index=True)
    iiko_item_id = Column(UUID(as_uuid=True))
    ingredient_product_id = Column(BigInteger, index=True)
    iiko_ingredient_product_id = Column(UUID(as_uuid=True))
    sort_weight = Column(Numeric(8, 2), default=0)
    amount_in = Column(Numeric(14, 6), nullable=False)
    amount_middle = Column(Numeric(14, 6))
    amount_out = Column(Numeric(14, 6))
    synced_at = Column(DateTime, nullable=False, server_default=func.now())

    recipe = relationship("Recipe", back_populates="ingredients")

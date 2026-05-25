"""Nomenclature models (iiko products + groups + categories).

Schema is established by `migrations/014_nomenclature.sql`. See
`docs/MENU_AND_RECEIPTS_ARCHITECTURE.md` § Фаза 2 for context.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from ..db import Base


class NomenclatureCategory(Base):
    __tablename__ = "nomenclature_category"

    id = Column(BigInteger, primary_key=True, index=True)
    iiko_source_domain = Column(Text, nullable=False, index=True)
    iiko_category_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(Text, nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "iiko_source_domain", "iiko_category_id",
            name="nomenclature_category_iiko_source_domain_iiko_category_id_key",
        ),
    )


class NomenclatureGroup(Base):
    __tablename__ = "nomenclature_group"

    id = Column(BigInteger, primary_key=True, index=True)
    iiko_source_domain = Column(Text, nullable=False, index=True)
    iiko_group_id = Column(UUID(as_uuid=True), nullable=False)
    parent_id = Column(
        BigInteger, ForeignKey("nomenclature_group.id"), nullable=True, index=True
    )
    name = Column(Text, nullable=False)
    num = Column(Text, nullable=True)
    code = Column(Text, nullable=True)
    position = Column(Integer, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    iiko_payload = Column(JSONB, nullable=True)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    parent = relationship("NomenclatureGroup", remote_side=[id], back_populates="children")
    children = relationship("NomenclatureGroup", back_populates="parent")

    __table_args__ = (
        UniqueConstraint(
            "iiko_source_domain", "iiko_group_id",
            name="nomenclature_group_iiko_source_domain_iiko_group_id_key",
        ),
    )


class Product(Base):
    __tablename__ = "product"

    id = Column(BigInteger, primary_key=True, index=True)
    iiko_source_domain = Column(Text, nullable=False, index=True)
    iiko_product_id = Column(UUID(as_uuid=True), nullable=False)
    num = Column(Text, nullable=True)
    code = Column(Text, nullable=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Text, nullable=False, index=True)
    group_id = Column(
        BigInteger, ForeignKey("nomenclature_group.id"), nullable=True, index=True
    )
    category_id = Column(
        BigInteger, ForeignKey("nomenclature_category.id"), nullable=True, index=True
    )
    measure_unit_id = Column(UUID(as_uuid=True), nullable=True)
    default_sale_price = Column(Numeric(14, 2), nullable=True)
    estimated_purchase_price = Column(Numeric(14, 2), nullable=True)
    weight_kg = Column(Numeric(10, 4), nullable=True)
    cold_loss_percent = Column(Numeric(7, 4), nullable=True)
    hot_loss_percent = Column(Numeric(7, 4), nullable=True)
    tax_category_id = Column(UUID(as_uuid=True), nullable=True)
    accounting_category_id = Column(UUID(as_uuid=True), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    is_included_in_menu = Column(Boolean, nullable=False, default=True)
    iiko_payload = Column(JSONB, nullable=True)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    group = relationship("NomenclatureGroup", foreign_keys=[group_id])
    category = relationship("NomenclatureCategory", foreign_keys=[category_id])

    __table_args__ = (
        UniqueConstraint(
            "iiko_source_domain", "iiko_product_id",
            name="product_iiko_source_domain_iiko_product_id_key",
        ),
    )

"""Складской контур iiko: справочники, акты списания, приходные накладные.

Семантика, о которой легко споткнуться (миграция 035):
  * ``WriteoffItem.cost`` — себестоимость ВСЕЙ строки, не за единицу.
  * У акта списания склад лежит в шапке (``WriteoffDocument.store_id``),
    у накладной — в позиции (``IncomingInvoiceItem.store_id``), потому что
    одна накладная может раскладываться на несколько складов.
  * ``status`` обязателен в фильтрах отчётов: DELETED-документов в сети
    примерно четверть.
"""

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric,
    Text, func,
)
from sqlalchemy.dialects.postgresql import UUID

from ..db import Base


# --------------------------------------------------------------- справочники

class Store(Base):
    __tablename__ = "store"

    id = Column(UUID(as_uuid=True), primary_key=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), index=True)
    code = Column(Text)
    name = Column(Text, nullable=False)
    iiko_source_domain = Column(Text, nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class IikoAccount(Base):
    """План счетов. Для списаний account_id — это причина списания."""

    __tablename__ = "iiko_account"

    id = Column(UUID(as_uuid=True), primary_key=True)
    code = Column(Text)
    name = Column(Text, nullable=False)
    account_type = Column(Text)
    parent_id = Column(UUID(as_uuid=True))
    iiko_source_domain = Column(Text, nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class Supplier(Base):
    __tablename__ = "supplier"

    id = Column(UUID(as_uuid=True), primary_key=True)
    code = Column(Text)
    name = Column(Text, nullable=False)
    taxpayer_id_number = Column(Text)
    iiko_source_domain = Column(Text, nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class MeasureUnit(Base):
    __tablename__ = "measure_unit"

    id = Column(UUID(as_uuid=True), primary_key=True)
    code = Column(Text)
    name = Column(Text, nullable=False)
    iiko_source_domain = Column(Text, nullable=False)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


# ------------------------------------------------------------ акты списания

class WriteoffDocument(Base):
    __tablename__ = "writeoff_document"

    id = Column(UUID(as_uuid=True), primary_key=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"))
    store_id = Column(UUID(as_uuid=True))
    account_id = Column(UUID(as_uuid=True))
    document_number = Column(Text)
    date_incoming = Column(DateTime, nullable=False)
    doc_date = Column(Date, nullable=False)
    status = Column(Text, nullable=False)
    conception_id = Column(UUID(as_uuid=True))
    comment = Column(Text)
    items_count = Column(Integer, nullable=False, default=0)
    total_cost = Column(Numeric(16, 4), nullable=False, default=0)
    iiko_source_domain = Column(Text, nullable=False)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class WriteoffItem(Base):
    __tablename__ = "writeoff_item"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("writeoff_document.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(UUID(as_uuid=True))
    store_id = Column(UUID(as_uuid=True))
    doc_date = Column(Date, nullable=False)
    num = Column(Integer)
    iiko_product_id = Column(UUID(as_uuid=True), nullable=False)
    product_id = Column(BigInteger, ForeignKey("product.id"))
    product_size_id = Column(UUID(as_uuid=True))
    amount = Column(Numeric(16, 6), nullable=False)
    amount_factor = Column(Numeric(16, 6))
    measure_unit_id = Column(UUID(as_uuid=True))
    container_id = Column(UUID(as_uuid=True))
    cost = Column(Numeric(16, 4))  # себестоимость всей строки, не за единицу


# ------------------------------------------------------ приходные накладные

class IncomingInvoice(Base):
    __tablename__ = "incoming_invoice"

    id = Column(UUID(as_uuid=True), primary_key=True)
    supplier_id = Column(UUID(as_uuid=True))
    default_store_id = Column(UUID(as_uuid=True))
    document_number = Column(Text)
    incoming_document_number = Column(Text)
    incoming_date = Column(Date)
    date_incoming = Column(DateTime)
    doc_date = Column(Date, nullable=False)
    status = Column(Text, nullable=False)
    conception_id = Column(UUID(as_uuid=True))
    comment = Column(Text)
    linked_outgoing_invoice_id = Column(UUID(as_uuid=True))
    items_count = Column(Integer, nullable=False, default=0)
    total_sum = Column(Numeric(16, 4), nullable=False, default=0)
    iiko_source_domain = Column(Text, nullable=False)
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class IncomingInvoiceItem(Base):
    __tablename__ = "incoming_invoice_item"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("incoming_invoice.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(UUID(as_uuid=True))
    store_id = Column(UUID(as_uuid=True))
    doc_date = Column(Date, nullable=False)
    num = Column(Integer)
    iiko_product_id = Column(UUID(as_uuid=True))
    product_id = Column(BigInteger, ForeignKey("product.id"))
    product_article = Column(Text)
    amount = Column(Numeric(16, 6))
    actual_amount = Column(Numeric(16, 6))
    price = Column(Numeric(16, 4))
    price_without_vat = Column(Numeric(16, 4))
    line_sum = Column(Numeric(16, 4))
    vat_percent = Column(Numeric(9, 4))
    vat_sum = Column(Numeric(16, 4))
    discount_sum = Column(Numeric(16, 4))
    amount_unit_id = Column(UUID(as_uuid=True))
    is_additional_expense = Column(Boolean, nullable=False, default=False)


class SkuStockBalance(Base):
    """Остаток товара на складе на конец учётного дня.

    iiko отдаёт только срез на момент времени, истории нет — снимок делается
    ежедневно. Нулевые позиции сервер не присылает: отсутствие строки за
    загруженный день означает нулевой остаток.
    """

    __tablename__ = "sku_stock_balance"

    balance_date = Column(Date, primary_key=True)
    store_id = Column(UUID(as_uuid=True), ForeignKey("store.id"), primary_key=True)
    product_id = Column(BigInteger, ForeignKey("product.id"), primary_key=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"))
    amount = Column(Numeric(16, 3), nullable=False)
    cost_sum = Column(Numeric(16, 2))
    synced_at = Column(DateTime, nullable=False, server_default=func.now())


class InventorySyncLog(Base):
    __tablename__ = "inventory_sync_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sync_type = Column(Text, nullable=False)
    department_id = Column(UUID(as_uuid=True))
    from_date = Column(Date)
    to_date = Column(Date)
    documents = Column(Integer, nullable=False, default=0)
    items = Column(Integer, nullable=False, default=0)
    unresolved = Column(Integer, nullable=False, default=0)
    status = Column(Text, nullable=False)
    error_message = Column(Text)
    duration_sec = Column(Numeric(10, 2))
    created_at = Column(DateTime, nullable=False, server_default=func.now())

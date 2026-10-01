"""Tables this pack adds. TenantScoped gives each one tenant_id and an RLS policy."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from factory.db import Base, TenantScoped, now
from factory.models import uid

Money = Numeric(12, 2)


class Supplier(TenantScoped, Base):
    __tablename__ = "rp_suppliers"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str]
    email: Mapped[str]
    min_order: Mapped[float] = mapped_column(Money, default=0)
    delivery_days: Mapped[list[str]] = mapped_column(JSON, default=list)


class Item(TenantScoped, Base):
    __tablename__ = "rp_items"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str]
    unit: Mapped[str] = mapped_column(default="each")
    category: Mapped[str] = mapped_column(default="general")
    par_level: Mapped[float] = mapped_column(default=0)
    on_hand: Mapped[float] = mapped_column(default=0)
    counted_at: Mapped[datetime | None]


class SupplierPrice(TenantScoped, Base):
    __tablename__ = "rp_supplier_prices"
    __table_args__ = (UniqueConstraint("tenant_id", "supplier_id", "item_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_suppliers.id"))
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_items.id"))
    pack_size: Mapped[float]  # units per pack (case)
    pack_price: Mapped[float] = mapped_column(Money)
    updated_at: Mapped[datetime] = mapped_column(default=now)
    supplier: Mapped[Supplier] = relationship(lazy="joined")
    item: Mapped[Item] = relationship(lazy="joined")

    @property
    def unit_price(self) -> float:
        return float(self.pack_price) / self.pack_size


class PurchaseOrder(TenantScoped, Base):
    __tablename__ = "rp_purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    number: Mapped[str]
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_suppliers.id"))
    status: Mapped[str] = mapped_column(default="draft")  # draft|superseded|sent|invoiced
    total: Mapped[float] = mapped_column(Money)
    savings_vs_primary: Mapped[float] = mapped_column(Money, default=0)
    below_minimum: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=now)
    sent_at: Mapped[datetime | None]
    supplier: Mapped[Supplier] = relationship(lazy="joined")
    lines: Mapped[list["POLine"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class POLine(TenantScoped, Base):
    __tablename__ = "rp_po_lines"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_purchase_orders.id"))
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_items.id"))
    packs: Mapped[int]
    pack_size: Mapped[float]
    pack_price: Mapped[float] = mapped_column(Money)
    item: Mapped[Item] = relationship(lazy="joined")

    @property
    def line_total(self) -> float:
        return round(self.packs * float(self.pack_price), 2)


class Invoice(TenantScoped, Base):
    __tablename__ = "rp_invoices"
    __table_args__ = (UniqueConstraint("tenant_id", "supplier_id", "number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    number: Mapped[str]
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_suppliers.id"))
    po_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rp_purchase_orders.id"))
    total: Mapped[float] = mapped_column(Money)
    status: Mapped[str]  # matched|disputed|credit_requested
    dispute_amount: Mapped[float] = mapped_column(Money, default=0)
    received_at: Mapped[datetime] = mapped_column(default=now)
    supplier: Mapped[Supplier] = relationship(lazy="joined")
    issues: Mapped[list["InvoiceIssue"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class InvoiceIssue(TenantScoped, Base):
    __tablename__ = "rp_invoice_issues"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rp_invoices.id"))
    item: Mapped[str]
    kind: Mapped[str]  # price_over|quantity_over|not_ordered|no_po
    expected: Mapped[str]
    actual: Mapped[str]
    amount: Mapped[float] = mapped_column(Money)

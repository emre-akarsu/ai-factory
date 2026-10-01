"""Purchasing Manager tools: the light code behind employee.yaml. Each tool gets ctx
(tenant, user, config, db, email) and typed arguments; roles, approvals, audit and
metering are applied by the platform."""
from __future__ import annotations

import math
import uuid
from collections import defaultdict

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from factory.db import now
from factory.runtime import Ctx, tool

from .config import ParLevel, PriceList, SupplierIn
from .models import Invoice, InvoiceIssue, Item, POLine, PurchaseOrder, Supplier, SupplierPrice


# --- helpers ---------------------------------------------------------------------------

def _supplier(ctx: Ctx, name: str) -> Supplier:
    s = ctx.db.scalar(select(Supplier).where(func.lower(Supplier.name) == name.strip().lower()))
    if s is None:
        raise LookupError(f"unknown supplier {name!r}")
    return s


def _item(ctx: Ctx, name: str, create: dict | None = None) -> Item | None:
    it = ctx.db.scalar(select(Item).where(func.lower(Item.name) == name.strip().lower()))
    if it is None and create is not None:
        it = Item(tenant_id=ctx.tenant_id, name=name.strip(), **create)
        ctx.db.add(it)
        ctx.db.flush()
    return it


def _money(x: float) -> float:
    return round(float(x) + 1e-9, 2)


# --- setup (used by the onboarding wizard too) -------------------------------------------

@tool
def import_suppliers(ctx: Ctx, suppliers: list[SupplierIn]) -> dict:
    """Add or update suppliers (distributors) with their order email and minimum order."""
    for s in suppliers:
        row = ctx.db.scalar(select(Supplier).where(func.lower(Supplier.name) == s.name.lower()))
        if row is None:
            ctx.db.add(Supplier(tenant_id=ctx.tenant_id, **s.model_dump()))
        else:
            row.email, row.min_order, row.delivery_days = s.email, s.min_order, s.delivery_days
    return {"suppliers": len(suppliers)}


@tool
def import_price_lists(ctx: Ctx, price_lists: list[PriceList]) -> dict:
    """Load each supplier's price list (order guide). Records price changes."""
    changes = []
    for pl in price_lists:
        sup = _supplier(ctx, pl.supplier)
        for line in pl.lines:
            item = _item(ctx, line.item, create={"unit": line.unit, "category": line.category})
            price = ctx.db.scalar(select(SupplierPrice).where(SupplierPrice.supplier_id == sup.id,
                                                              SupplierPrice.item_id == item.id))
            if price is None:
                ctx.db.add(SupplierPrice(tenant_id=ctx.tenant_id, supplier_id=sup.id, item_id=item.id,
                                         pack_size=line.pack_size, pack_price=line.pack_price))
            elif float(price.pack_price) != line.pack_price or price.pack_size != line.pack_size:
                changes.append({"supplier": sup.name, "item": item.name, "old": float(price.pack_price),
                                "new": line.pack_price})
                price.pack_size, price.pack_price, price.updated_at = line.pack_size, line.pack_price, now()
    return {"lines": sum(len(pl.lines) for pl in price_lists), "price_changes": changes}


@tool
def set_par_levels(ctx: Ctx, items: list[ParLevel]) -> dict:
    """Set the par level (stock to have after delivery) for items, optionally with on-hand counts."""
    for p in items:
        it = _item(ctx, p.item)
        if it is None:
            raise LookupError(f"unknown item {p.item!r}; import a price list that carries it first")
        it.par_level = p.par_level
        if p.on_hand is not None:
            it.on_hand, it.counted_at = p.on_hand, now()
    return {"items": len(items)}


# --- daily work ------------------------------------------------------------------------

class Count(BaseModel):
    item: str
    on_hand: float = Field(ge=0)


@tool
def record_count(ctx: Ctx, counts: list[Count]) -> dict:
    """Record an inventory count (what is on the shelf now)."""
    unknown = []
    for c in counts:
        it = _item(ctx, c.item)
        if it is None:
            unknown.append(c.item)
            continue
        it.on_hand, it.counted_at = c.on_hand, now()
    return {"counted": len(counts) - len(unknown), "unknown_items": unknown}


@tool
def compare_prices(ctx: Ctx, item: str) -> dict:
    """Compare every supplier's current price for one item, cheapest per unit first."""
    it = _item(ctx, item)
    if it is None:
        raise LookupError(f"unknown item {item!r}")
    prices = ctx.db.scalars(select(SupplierPrice).where(SupplierPrice.item_id == it.id)).all()
    rows = sorted(({"supplier": p.supplier.name, "pack_size": p.pack_size, "pack_price": float(p.pack_price),
                    "unit_price": round(p.unit_price, 4)} for p in prices), key=lambda r: r["unit_price"])
    return {"item": it.name, "unit": it.unit, "prices": rows}


def _next_number(ctx: Ctx) -> int:
    return (ctx.db.scalar(select(func.count()).select_from(PurchaseOrder)) or 0) + 1


@tool
def build_order(ctx: Ctx) -> dict:
    """Draft purchase orders for everything below par, choosing the cheapest supplier per
    item and consolidating lines so each supplier's minimum order is met."""
    for old in ctx.db.scalars(select(PurchaseOrder).where(PurchaseOrder.status == "draft")):
        old.status = "superseded"

    needs: dict[uuid.UUID, tuple[Item, float, list[SupplierPrice]]] = {}
    no_supplier = []
    for it in ctx.db.scalars(select(Item).where(Item.par_level > Item.on_hand)).all():
        prices = sorted(ctx.db.scalars(select(SupplierPrice).where(SupplierPrice.item_id == it.id)).all(),
                        key=lambda p: p.unit_price)
        if not prices:
            no_supplier.append(it.name)
            continue
        needs[it.id] = (it, it.par_level - it.on_hand, prices)

    def cost(p: SupplierPrice, qty: float) -> float:
        return math.ceil(qty / p.pack_size - 1e-9) * float(p.pack_price)

    choice = {iid: prices[0] for iid, (_, _, prices) in needs.items()}

    # Move lines off suppliers whose subtotal misses their minimum, to the next cheapest
    # supplier already in the order. Repeat until nothing moves.
    for _ in range(len(needs) + 1):
        totals: dict[uuid.UUID, float] = defaultdict(float)
        for iid, p in choice.items():
            totals[p.supplier_id] += cost(p, needs[iid][1])
        short = {sid for sid, t in totals.items() if t < float(ctx.db.get(Supplier, sid).min_order)}
        moved = False
        for iid, p in list(choice.items()):
            if p.supplier_id in short:
                alt = next((q for q in needs[iid][2] if q.supplier_id in totals and q.supplier_id not in short), None)
                if alt is not None:
                    choice[iid], moved = alt, True
        if not moved:
            break

    primary = ctx.config.primary_supplier
    by_supplier: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for iid, p in choice.items():
        by_supplier[p.supplier_id].append(iid)

    seq = _next_number(ctx)
    stamp = now().strftime("%Y%m%d")
    orders = []
    for sid, iids in sorted(by_supplier.items(), key=lambda kv: ctx.db.get(Supplier, kv[0]).name):
        sup = ctx.db.get(Supplier, sid)
        po = PurchaseOrder(tenant_id=ctx.tenant_id, number=f"PO-{stamp}-{seq:04d}", supplier_id=sid, total=0)
        seq += 1
        savings = 0.0
        for iid in sorted(iids, key=lambda i: needs[i][0].name):
            it, qty, prices = needs[iid]
            p = choice[iid]
            packs = math.ceil(qty / p.pack_size - 1e-9)
            po.lines.append(POLine(tenant_id=ctx.tenant_id, item_id=iid, packs=packs, pack_size=p.pack_size,
                                   pack_price=p.pack_price))
            prim = next((q for q in prices if primary and q.supplier.name.lower() == primary.lower()), None)
            if prim is not None:
                savings += cost(prim, qty) - cost(p, qty)
        po.total = _money(sum(line.line_total for line in po.lines))
        po.savings_vs_primary = _money(savings)
        po.below_minimum = po.total < float(sup.min_order)
        ctx.db.add(po)
        ctx.db.flush()
        orders.append({
            "id": str(po.id), "number": po.number, "supplier": sup.name, "total": po.total,
            "below_minimum": po.below_minimum, "savings_vs_primary": po.savings_vs_primary,
            "lines": [{"item": needs[l.item_id][0].name, "packs": l.packs, "pack_size": l.pack_size,
                       "pack_price": float(l.pack_price), "line_total": l.line_total} for l in po.lines],
        })
    return {
        "po_ids": [o["id"] for o in orders],
        "orders": orders,
        "total": _money(sum(o["total"] for o in orders)),
        "savings_vs_primary": _money(sum(o["savings_vs_primary"] for o in orders)),
        "items_without_supplier": no_supplier,
    }


def _draft_pos(ctx: Ctx, po_ids: list[str]) -> list[PurchaseOrder]:
    try:
        pos = [ctx.db.get(PurchaseOrder, uuid.UUID(i)) for i in po_ids]
    except ValueError:
        pos = [None]
    if any(p is None for p in pos):
        raise LookupError("unknown purchase order")
    return pos


def _po_amount(ctx: Ctx, po_ids: list[str]) -> float:
    return sum(float(p.total) for p in _draft_pos(ctx, po_ids))


@tool(amount=_po_amount)
def send_purchase_orders(ctx: Ctx, po_ids: list[str]) -> dict:
    """Email draft purchase orders to their suppliers."""
    sent = []
    for po in _draft_pos(ctx, po_ids):
        if po.status != "draft":
            raise ValueError(f"{po.number} is {po.status}, not draft")
        lines = "\n".join(f"- {l.item.name}: {l.packs} x {l.pack_size:g} {l.item.unit} @ ${float(l.pack_price):,.2f}"
                          f" = ${l.line_total:,.2f}" for l in po.lines)
        body = (f"Hello {po.supplier.name},\n\nPlease supply the following for {ctx.config.restaurant_name}.\n\n"
                f"Purchase order {po.number}\n{lines}\n\nTotal: ${float(po.total):,.2f}\n\n{ctx.config.delivery_note}\n")
        ctx.email.send(po.supplier.email, f"Purchase order {po.number} from {ctx.config.restaurant_name}", body)
        po.status, po.sent_at = "sent", now()
        ctx.meter("po_sent")
        ctx.emit("purchase_order.sent", {"number": po.number, "supplier": po.supplier.name, "total": float(po.total)})
        sent.append({"number": po.number, "supplier": po.supplier.name, "to": po.supplier.email,
                     "total": float(po.total)})
    return {"sent": sent}


class InvoiceLine(BaseModel):
    item: str
    packs: int = Field(ge=0)
    pack_price: float = Field(ge=0)


@tool
def check_invoice(ctx: Ctx, supplier: str, invoice_number: str, po_number: str | None,
                  lines: list[InvoiceLine]) -> dict:
    """Match a supplier invoice against its purchase order: flag price increases beyond the
    tolerance, quantities over what was ordered, and items that were never ordered."""
    sup = _supplier(ctx, supplier)
    po = ctx.db.scalar(select(PurchaseOrder).where(PurchaseOrder.number == po_number)) if po_number else None
    tol = ctx.config.price_variance_tolerance_pct / 100
    issues: list[InvoiceIssue] = []

    def issue(item, kind, expected, actual, amount):
        issues.append(InvoiceIssue(tenant_id=ctx.tenant_id, item=item, kind=kind, expected=str(expected),
                                   actual=str(actual), amount=_money(amount)))

    if po is None or po.supplier_id != sup.id:
        issue("-", "no_po", po_number or "a purchase order", "none found", 0)
        ordered = {}
    else:
        ordered = {l.item.name.lower(): l for l in po.lines}
    for line in lines:
        pl = ordered.get(line.item.lower())
        if po is not None and pl is None:
            issue(line.item, "not_ordered", 0, line.packs, line.packs * line.pack_price)
            continue
        if pl is None:
            continue
        agreed = float(pl.pack_price)
        if line.pack_price > agreed * (1 + tol):
            issue(line.item, "price_over", agreed, line.pack_price, (line.pack_price - agreed) * min(line.packs, pl.packs))
        if line.packs > pl.packs:
            issue(line.item, "quantity_over", pl.packs, line.packs, (line.packs - pl.packs) * line.pack_price)

    total = _money(sum(l.packs * l.pack_price for l in lines))
    dispute = _money(sum(float(i.amount) for i in issues))
    inv = Invoice(tenant_id=ctx.tenant_id, number=invoice_number, supplier_id=sup.id, po_id=po.id if po else None,
                  total=total, status="disputed" if issues else "matched", dispute_amount=dispute)
    inv.issues.extend(issues)
    ctx.db.add(inv)
    if po is not None:
        po.status = "invoiced"
    ctx.meter("invoice_checked")
    ctx.emit("invoice.disputed" if issues else "invoice.matched",
             {"invoice_number": invoice_number, "supplier": sup.name, "issues": len(issues), "amount": dispute})
    return {
        "invoice_number": invoice_number, "supplier": sup.name, "status": inv.status, "total": total,
        "dispute_amount": dispute,
        "issues": [{"item": i.item, "kind": i.kind, "expected": i.expected, "actual": i.actual,
                    "amount": float(i.amount)} for i in issues],
    }


@tool
def send_credit_request(ctx: Ctx, supplier: str, invoice_number: str) -> dict:
    """Email the supplier a credit request listing every disputed line on an invoice."""
    sup = _supplier(ctx, supplier)
    inv = ctx.db.scalar(select(Invoice).where(Invoice.number == invoice_number, Invoice.supplier_id == sup.id))
    if inv is None or inv.status != "disputed":
        raise ValueError(f"invoice {invoice_number} has nothing to dispute")
    labels = {"price_over": "billed above the agreed price", "quantity_over": "billed more than ordered",
              "not_ordered": "not on our purchase order", "no_po": "no matching purchase order"}
    lines = "\n".join(f"- {i.item}: {labels[i.kind]} (expected {i.expected}, billed {i.actual}), ${float(i.amount):,.2f}"
                      for i in inv.issues)
    body = (f"Hello {sup.name},\n\nWe found these problems on invoice {inv.number}:\n{lines}\n\n"
            f"Please issue a credit of ${float(inv.dispute_amount):,.2f}.\n\nThanks,\n{ctx.config.restaurant_name}\n")
    ctx.email.send(sup.email, f"Credit request for invoice {inv.number}", body)
    inv.status = "credit_requested"
    return {"invoice_number": inv.number, "credit_requested": float(inv.dispute_amount), "to": sup.email}

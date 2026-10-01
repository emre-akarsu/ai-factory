"""Store component: the public product page, Stripe checkout and order fulfilment.

The product page is config: each pack's store.yaml (validated here) plus its
marketing/ folder. Paying creates the customer's workspace and a subscription;
installing a paid employee requires an active one.

STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET switch on real Stripe (test or live keys).
Without them the store runs in sandbox mode: checkout goes to a local page that
completes the order without taking money."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import JSON, select
from sqlalchemy.orm import Mapped, mapped_column

from factory.components.workspace import create_workspace
from factory.db import Base, TenantScoped, now, tenant_session
from factory.models import Event, Listing, uid
from factory.runtime import NotAllowed, get_pack


# --- store.yaml ------------------------------------------------------------------------

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Stat(_Strict):
    value: str
    label: str
    source: str | None = None


class Step(_Strict):
    title: str
    body: str


class Feature(_Strict):
    icon: str
    title: str
    body: str


class Plan(_Strict):
    id: str
    name: str
    price_monthly_usd: int
    trial_days: int = 0
    includes: list[str]


class Faq(_Strict):
    q: str
    a: str


class KitItem(_Strict):
    title: str
    file: str
    kind: str  # video|pdf|image|text


class Media(_Strict):
    hero_video: str | None = None  # MP4 (H.264)
    hero_video_webm: str | None = None  # VP9, for browsers without H.264
    hero_poster: str | None = None
    social_video: str | None = None
    one_pager: str | None = None
    images: list[str] = []
    kit: list[KitItem] = []


class StoreSpec(_Strict):
    headline: str
    subheadline: str
    cta: str = "Start free trial"
    problem: list[Stat]
    steps: list[Step]
    features: list[Feature]
    demo: dict[str, Any]  # sample run shown on the page, labelled as a demo
    roi: dict[str, float]  # assumptions for the savings calculator
    plans: list[Plan]
    faq: list[Faq]
    trust: list[str]
    media: Media


def store_spec(employee_id: str) -> StoreSpec:
    pack = get_pack(employee_id)
    if not pack.manifest.store:
        raise LookupError(f"{employee_id} has no store page")
    return StoreSpec.model_validate(yaml.safe_load((pack.path / pack.manifest.store).read_text()))


def asset_path(employee_id: str, name: str) -> Path:
    root = (get_pack(employee_id).path / "marketing").resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        raise LookupError("no such asset")
    return path


def product(employee_id: str) -> dict[str, Any]:
    from factory.components.marketplace import listing_view

    with tenant_session(None) as db:
        listing = db.get(Listing, employee_id)
        if listing is None:
            raise LookupError(f"{employee_id} is not published")
        view = listing_view(listing)
    spec = store_spec(employee_id)
    return {**{k: view[k] for k in ("employee_id", "name", "version", "industry", "tagline", "description",
                                    "category", "highlights", "permissions", "suggested_prompts")},
            "store": spec.model_dump(), "sandbox": not stripe_enabled()}


# --- orders and subscriptions ------------------------------------------------------------

class Order(Base):
    """Created at checkout, before the buyer has a workspace. Read only by the service."""
    __tablename__ = "store_orders"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    employee_id: Mapped[str]
    plan_id: Mapped[str]
    email: Mapped[str]
    business_name: Mapped[str]
    amount_usd: Mapped[int]
    status: Mapped[str] = mapped_column(default="pending")  # pending|paid
    stripe_session_id: Mapped[str | None]
    # Not named tenant_id: orders exist before the workspace and must not get an RLS policy.
    workspace_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(default=now)
    paid_at: Mapped[datetime | None]


class Subscription(TenantScoped, Base):
    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    employee_id: Mapped[str]
    plan_id: Mapped[str]
    status: Mapped[str]  # trialing|active|canceled
    provider: Mapped[str]  # stripe|sandbox
    provider_customer: Mapped[str | None]
    provider_subscription: Mapped[str | None] = mapped_column(index=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(default=now)


def stripe_enabled() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def web_url() -> str:
    return os.environ.get("FACTORY_WEB_URL", "http://localhost:3000")


class CheckoutRequest(BaseModel):
    employee_id: str
    plan_id: str
    email: EmailStr
    business_name: str = Field(min_length=1, max_length=120)


def start_checkout(req: CheckoutRequest) -> dict[str, str]:
    plan = next((p for p in store_spec(req.employee_id).plans if p.id == req.plan_id), None)
    if plan is None:
        raise LookupError(f"unknown plan {req.plan_id}")
    name = get_pack(req.employee_id).manifest.name
    with tenant_session(None) as db:
        order = Order(employee_id=req.employee_id, plan_id=plan.id, email=str(req.email),
                      business_name=req.business_name, amount_usd=plan.price_monthly_usd)
        db.add(order)
        db.flush()
        if not stripe_enabled():
            return {"order_id": str(order.id), "url": f"{web_url()}/checkout/sandbox?order={order.id}"}
        import stripe

        stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=str(req.email),
            client_reference_id=str(order.id),
            line_items=[{"quantity": 1, "price_data": {
                "currency": "usd", "unit_amount": plan.price_monthly_usd * 100, "recurring": {"interval": "month"},
                "product_data": {"name": f"{name} ({plan.name})"}}}],
            subscription_data={"trial_period_days": plan.trial_days} if plan.trial_days else None,
            metadata={"order_id": str(order.id), "employee_id": req.employee_id, "plan_id": plan.id},
            success_url=f"{web_url()}/checkout/success?order={order.id}",
            cancel_url=f"{web_url()}/employees/{req.employee_id}?canceled=1",
        )
        order.stripe_session_id = session.id
        return {"order_id": str(order.id), "url": session.url}


def fulfil(order_id: uuid.UUID, provider: str, customer: str | None, subscription: str | None) -> Order:
    """Idempotent: a repeated webhook returns the same order and workspace."""
    with tenant_session(None) as db:
        order = db.get(Order, order_id, with_for_update=True)
        if order is None:
            raise LookupError("unknown order")
        if order.status == "paid":
            return order
        plan = next(p for p in store_spec(order.employee_id).plans if p.id == order.plan_id)
        # The buyer signs in later with this email (Supabase Auth); until then the owner is keyed by email.
        tenant_id = create_workspace(order.business_name, f"email:{order.email}", order.email)
        with tenant_session(tenant_id) as tdb:
            tdb.add(Subscription(tenant_id=tenant_id, employee_id=order.employee_id, plan_id=plan.id,
                                 status="trialing" if plan.trial_days else "active", provider=provider,
                                 provider_customer=customer, provider_subscription=subscription))
            tdb.add(Event(tenant_id=tenant_id, type="subscription.started",
                          payload={"employee_id": order.employee_id, "plan_id": plan.id}))
        order.status, order.paid_at, order.workspace_id = "paid", now(), tenant_id
        return order


def complete_sandbox(order_id: uuid.UUID) -> Order:
    if stripe_enabled():
        raise NotAllowed("sandbox checkout is off when Stripe is configured")
    return fulfil(order_id, "sandbox", None, f"sandbox_{uuid.uuid4().hex[:12]}")


def handle_stripe_webhook(payload: bytes, signature: str) -> str:
    import stripe

    event = stripe.Webhook.construct_event(payload, signature, os.environ["STRIPE_WEBHOOK_SECRET"]).to_dict()
    obj = event["data"]["object"]
    if event["type"] == "checkout.session.completed":
        fulfil(uuid.UUID(obj["client_reference_id"]), "stripe", obj.get("customer"), obj.get("subscription"))
    elif event["type"] == "customer.subscription.deleted":
        with tenant_session(None) as db:
            tenants = db.scalars(select(Order.workspace_id).where(Order.workspace_id.is_not(None))).all()
        for tid in tenants:  # RLS: look in each workspace the store created
            with tenant_session(tid) as tdb:
                for sub in tdb.scalars(select(Subscription).where(Subscription.provider_subscription == obj["id"])):
                    sub.status = "canceled"
    return event["type"]


def order_status(order_id: uuid.UUID) -> dict[str, Any]:
    with tenant_session(None) as db:
        order = db.get(Order, order_id)
        if order is None:
            raise LookupError("unknown order")
        return {"order_id": str(order.id), "status": order.status, "employee_id": order.employee_id,
                "plan_id": order.plan_id, "business_name": order.business_name, "email": order.email,
                "workspace_id": str(order.workspace_id) if order.workspace_id else None}


def has_subscription(db, employee_id: str) -> bool:
    return db.scalar(select(Subscription.id).where(Subscription.employee_id == employee_id,
                                                   Subscription.status.in_(("trialing", "active")))) is not None

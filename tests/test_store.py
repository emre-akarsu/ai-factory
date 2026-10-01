import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from factory.api import app
from factory.components import marketplace
from factory.components.workspace import create_workspace
from factory.manifest import load_manifest
from factory.runtime import NotAllowed

api = TestClient(app)
BODY = {"employee_id": "restaurant-purchasing", "plan_id": "single", "email": "chef@bistro.example",
        "business_name": "Bistro Uno"}


def test_product_page_data_comes_from_store_yaml():
    p = api.get("/v1/store/products/restaurant-purchasing").json()
    assert p["store"]["plans"][0] == {
        "id": "single", "name": "Single location", "price_monthly_usd": 149, "trial_days": 14,
        "includes": p["store"]["plans"][0]["includes"]}
    assert p["sandbox"] is True and len(p["store"]["faq"]) == 6
    video = p["store"]["media"]["hero_video"]
    r = api.get(f"/v1/store/assets/restaurant-purchasing/{video}", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and r.headers["content-type"] == "video/mp4"


def test_assets_cannot_escape_the_marketing_folder():
    assert api.get("/v1/store/assets/restaurant-purchasing/../employee.yaml").status_code == 404
    assert api.get("/v1/store/assets/restaurant-purchasing/%2e%2e/employee.yaml").status_code == 404


def test_checkout_validates_input():
    assert api.post("/v1/store/checkout", json={**BODY, "email": "not-an-email"}).status_code == 422
    assert api.post("/v1/store/checkout", json={**BODY, "plan_id": "gold"}).status_code == 422


def test_sandbox_purchase_creates_workspace_once():
    order = api.post("/v1/store/checkout", json=BODY).json()
    assert order["url"].endswith(f"/checkout/sandbox?order={order['order_id']}")
    assert api.get(f"/v1/store/orders/{order['order_id']}").json()["status"] == "pending"
    first = api.post(f"/v1/store/sandbox/{order['order_id']}/complete").json()
    again = api.post(f"/v1/store/sandbox/{order['order_id']}/complete").json()
    assert first["status"] == "paid" and first["workspace_id"] == again["workspace_id"]


def test_paid_employee_needs_a_subscription_to_install():
    m = load_manifest("employees/restaurant_purchasing")
    tid = create_workspace("No Sub Diner", "owner-nosub", "o@example.test")
    with pytest.raises(NotAllowed, match="needs a subscription"):
        marketplace.install(tid, "owner-nosub", m.id, m.permissions, {"restaurant_name": "x"})


def _sign(payload: bytes, secret: str) -> str:
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def test_stripe_checkout_and_signed_webhook(monkeypatch):
    import stripe

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    created = {}

    def fake_create(**kwargs):
        created.update(kwargs)
        return SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)
    order = api.post("/v1/store/checkout", json=BODY).json()
    assert order["url"].startswith("https://checkout.stripe.com/")
    item = created["line_items"][0]["price_data"]
    assert item["unit_amount"] == 14900 and item["recurring"] == {"interval": "month"}
    assert created["subscription_data"] == {"trial_period_days": 14}
    assert api.post(f"/v1/store/sandbox/{order['order_id']}/complete").status_code == 403

    event = {"id": "evt_1", "object": "event", "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_test_123", "object": "checkout.session", "client_reference_id": order["order_id"],
        "customer": "cus_1", "subscription": "sub_1"}}}
    payload = json.dumps(event).encode()
    bad = api.post("/v1/store/stripe/webhook", content=payload, headers={"Stripe-Signature": _sign(payload, "wrong")})
    assert bad.status_code == 400
    ok = api.post("/v1/store/stripe/webhook", content=payload, headers={"Stripe-Signature": _sign(payload, "whsec_test")})
    assert ok.json() == {"received": "checkout.session.completed"}
    status = api.get(f"/v1/store/orders/{order['order_id']}").json()
    assert status["status"] == "paid" and status["workspace_id"]

    # The new owner can now install the employee they paid for.
    m = load_manifest("employees/restaurant_purchasing")
    inst = marketplace.install(uuid.UUID(status["workspace_id"]), "email:chef@bistro.example", m.id, m.permissions,
                               {"restaurant_name": "Bistro Uno"})
    assert inst.employee_id == "restaurant-purchasing"

    cancel = {"id": "evt_2", "object": "event", "type": "customer.subscription.deleted",
              "data": {"object": {"id": "sub_1", "object": "subscription"}}}
    payload = json.dumps(cancel).encode()
    api.post("/v1/store/stripe/webhook", content=payload, headers={"Stripe-Signature": _sign(payload, "whsec_test")})
    from sqlalchemy import select

    from factory.components.store import Subscription
    from factory.db import tenant_session

    with tenant_session(uuid.UUID(status["workspace_id"])) as db:
        assert db.scalar(select(Subscription.status)) == "canceled"

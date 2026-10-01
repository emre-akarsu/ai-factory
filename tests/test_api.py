import uuid

import yaml
from fastapi.testclient import TestClient

from factory.api import app
from factory.components.workspace import add_member, create_workspace

FIXTURE = yaml.safe_load(open("employees/restaurant_purchasing/evals/fixtures/harbor_bistro.yaml"))


def client_for(tenant, user):
    c = TestClient(app)
    c.headers.update({"X-Tenant-Id": str(tenant), "X-User-Id": user})
    return c


def test_marketplace_lists_purchasing_manager_first():
    listings = TestClient(app).get("/v1/marketplace").json()
    first = listings[0]
    assert first["rank"] == 1 and first["employee_id"] == "restaurant-purchasing" and first["featured"]
    assert first["permissions"]["connectors"][0]["scopes"] == ["send"]
    assert [w["id"] for w in first["wizard"]] == ["suppliers", "price_lists", "par_levels"]
    assert "approval_threshold" in first["config_schema"]["properties"]


def test_install_order_approve_invoice_report():
    owner, manager = f"owner-{uuid.uuid4().hex[:6]}", f"mgr-{uuid.uuid4().hex[:6]}"
    tid = create_workspace("Harbor Bistro", owner, "owner@harbor.example")
    add_member(tid, manager, "mgr@harbor.example", "manager")
    c, m = client_for(tid, owner), client_for(tid, manager)
    listing = c.get("/v1/marketplace").json()[0]

    body = {"accepted_permissions": {"components": ["crm"], "connectors": []},
            "config": {**FIXTURE["config"], "approval_threshold": 800}, "wizard": FIXTURE["wizard"]}
    assert c.post("/v1/marketplace/restaurant-purchasing/install", json=body).status_code == 403
    assert m.post("/v1/marketplace/restaurant-purchasing/install",
                  json={**body, "accepted_permissions": listing["permissions"]}).status_code == 403  # not owner
    r = c.post("/v1/marketplace/restaurant-purchasing/install", json={**body, "accepted_permissions": listing["permissions"]})
    assert r.status_code == 201, r.text

    prices = m.post("/v1/employees/restaurant-purchasing/tools/compare_prices", json={"item": "Romaine"}).json()
    assert prices["prices"][0]["supplier"] == "Local Produce Co"

    run = m.post("/v1/employees/restaurant-purchasing/workflows/reorder/runs").json()
    assert run["status"] == "waiting_approval"
    approvals = c.get("/v1/approvals").json()
    assert len(approvals) == 1 and approvals[0]["amount"] == 1015.0 and approvals[0]["role"] == "owner"
    assert m.post(f"/v1/approvals/{approvals[0]['id']}/decide", json={"approve": True}).status_code == 403
    assert c.post(f"/v1/approvals/{approvals[0]['id']}/decide", json={"approve": True}).json()["status"] == "approved"
    run = c.get(f"/v1/runs/{run['id']}").json()
    assert run["status"] == "completed"
    orders = run["result"]["build_order"]["orders"]
    assert {o["to"] for o in run["result"]["send_purchase_orders"]["sent"]} == {
        "orders@usfoods.example", "hello@localproduce.example"}

    # A manual send of an already-sent PO is refused, and the refusal is audited.
    r = m.post("/v1/employees/restaurant-purchasing/tools/send_purchase_orders", json={"po_ids": [orders[0]["id"]]})
    assert r.status_code == 422

    invoice = {"sender": "billing@usfoods.example", "kind": "invoice", "data": {
        "supplier": "US Foods", "invoice_number": "INV-9", "po_number": orders[1]["number"],
        "lines": [{"item": "Chicken thighs", "packs": 3, "pack_price": 118}]}}
    assert c.post("/v1/inbound", json=invoice).status_code == 202
    pending = c.get("/v1/approvals").json()
    assert [a["tool"] for a in pending] == ["send_credit_request"]
    m.post(f"/v1/approvals/{pending[0]['id']}/decide", json={"approve": True})

    outbox = c.get("/v1/outbox").json()
    assert [o["subject"].split(" ")[0] for o in outbox].count("Purchase") == 2
    assert outbox[-1]["subject"] == "Credit request for invoice INV-9" and "$24.00" in outbox[-1]["body"]

    spend = c.get("/v1/reports/restaurant-purchasing/spend_by_supplier").json()
    assert {r["supplier"]: r["spend"] for r in spend["rows"]} == {"US Foods": 877.0, "Local Produce Co": 138.0}
    issues = c.get("/v1/reports/restaurant-purchasing/invoice_issues").json()
    assert issues["rows"] == [{"kind": "price_over", "issues": 1, "amount": 24.0}]

    events = {n["event"] for n in c.get("/v1/notifications").json()}
    assert {"approval.requested", "purchase_order.sent", "invoice.disputed"} <= events
    audit = c.get("/v1/audit").json()
    assert ("send_purchase_orders", "error") in {(a["action"], a["outcome"]) for a in audit}
    assert any(a["actor"] == "agent:restaurant-purchasing" and a["action"] == "send_purchase_orders"
               and a["outcome"] == "ok" for a in audit)


def test_outsider_is_refused():
    tid = create_workspace("Other", "someone", "s@example.test")
    r = client_for(tid, "intruder").get("/v1/approvals")
    assert r.status_code == 403

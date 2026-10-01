"""Versioned REST API (/v1). Auth is the user's Supabase JWT plus an X-Tenant-Id header;
FACTORY_DEV_AUTH=1 also accepts X-User-Id for local runs and tests."""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from factory import jobs
from factory.components import marketplace, reports, store
from factory.components.workflows import runs_waiting_on
from factory.db import tenant_session
from factory.models import Approval, AuditEntry, Member, Notification, OutboundMessage, Run
from factory.runtime import ApprovalRejected, ApprovalRequired, NotAllowed, call_tool, decide_approval, load_all_packs, make_ctx

@asynccontextmanager
async def lifespan(_: FastAPI):
    load_all_packs()
    yield


app = FastAPI(title="AI Factory", version="1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("FACTORY_CORS", "http://localhost:3000").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@dataclass
class Principal:
    tenant_id: uuid.UUID
    user_id: str


def principal(x_tenant_id: uuid.UUID = Header(), authorization: str | None = Header(None),
              x_user_id: str | None = Header(None)) -> Principal:
    if authorization and authorization.startswith("Bearer "):
        try:
            claims = jwt.decode(authorization[7:], os.environ["SUPABASE_JWT_SECRET"], algorithms=["HS256"],
                                audience="authenticated")
        except (jwt.PyJWTError, KeyError) as e:
            raise HTTPException(401, "invalid token") from e
        user_id = claims["sub"]
    elif x_user_id and os.environ.get("FACTORY_DEV_AUTH") == "1":
        user_id = x_user_id
    else:
        raise HTTPException(401, "missing credentials")
    with tenant_session(x_tenant_id) as db:
        if db.scalar(select(Member.id).where(Member.user_id == user_id)) is None:
            raise HTTPException(403, "not a member of this workspace")
    return Principal(x_tenant_id, user_id)


@contextmanager
def domain_errors():
    try:
        yield
    except ApprovalRequired as e:
        raise HTTPException(202, {"status": "waiting_for_approval", "approval_id": str(e.approval.id)})
    except (NotAllowed, ApprovalRejected) as e:
        raise HTTPException(403, str(e))
    except (ValueError, LookupError) as e:
        raise HTTPException(422, str(e))


# --- marketplace ---------------------------------------------------------------------

@app.get("/v1/marketplace")
def list_marketplace() -> list[dict[str, Any]]:
    return marketplace.catalog()


class InstallBody(BaseModel):
    accepted_permissions: dict[str, Any]
    config: dict[str, Any] = {}
    wizard: dict[str, Any] = {}


@app.post("/v1/marketplace/{employee_id}/install", status_code=201)
def install(employee_id: str, body: InstallBody, p: Principal = Depends(principal)) -> dict[str, Any]:
    with domain_errors():
        inst = marketplace.install(p.tenant_id, p.user_id, employee_id, body.accepted_permissions,
                                   body.config, body.wizard)
    jobs.defer("dispatch_events", tenant_id=str(p.tenant_id))
    return {"installation_id": str(inst.id), "employee_id": employee_id, "version": inst.version}


# --- store (public) -------------------------------------------------------------------

@app.get("/v1/store/products/{employee_id}")
def store_product(employee_id: str) -> dict[str, Any]:
    with domain_errors():
        return store.product(employee_id)


@app.get("/v1/store/assets/{employee_id}/{name:path}")
def store_asset(employee_id: str, name: str) -> FileResponse:
    try:
        return FileResponse(store.asset_path(employee_id, name))
    except (LookupError, KeyError):
        raise HTTPException(404)


@app.post("/v1/store/checkout")
def store_checkout(body: store.CheckoutRequest) -> dict[str, str]:
    with domain_errors():
        return store.start_checkout(body)


@app.post("/v1/store/sandbox/{order_id}/complete")
def store_sandbox_complete(order_id: uuid.UUID) -> dict[str, Any]:
    with domain_errors():
        store.complete_sandbox(order_id)
        return store.order_status(order_id)


@app.get("/v1/store/orders/{order_id}")
def store_order(order_id: uuid.UUID) -> dict[str, Any]:
    with domain_errors():
        return store.order_status(order_id)


@app.post("/v1/store/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header()) -> dict[str, str]:
    payload = await request.body()
    try:
        kind = store.handle_stripe_webhook(payload, stripe_signature)
    except Exception as e:  # bad signature or payload
        if type(e).__name__ in ("SignatureVerificationError", "ValueError"):
            raise HTTPException(400, "invalid webhook") from e
        raise
    return {"received": kind}


# --- tools, runs, approvals ------------------------------------------------------------

@app.post("/v1/employees/{employee_id}/tools/{tool}")
def run_tool(employee_id: str, tool: str, args: dict[str, Any], p: Principal = Depends(principal)) -> Any:
    error = None
    with tenant_session(p.tenant_id) as db:
        try:
            with domain_errors():
                ctx = make_ctx(db, p.tenant_id, p.user_id, employee_id)
                result = call_tool(ctx, tool, args)
        except HTTPException as e:
            error = e  # commit the audit row and any approval request, then raise
    jobs.defer("dispatch_events", tenant_id=str(p.tenant_id))
    if error:
        raise error
    return result


@app.post("/v1/employees/{employee_id}/workflows/{workflow}/runs", status_code=202)
def start_workflow(employee_id: str, workflow: str, p: Principal = Depends(principal)) -> dict[str, Any]:
    with tenant_session(p.tenant_id) as db, domain_errors():
        make_ctx(db, p.tenant_id, p.user_id, employee_id).pack.manifest.workflows[workflow]
        run = Run(tenant_id=p.tenant_id, employee_id=employee_id, workflow=workflow, started_by=p.user_id,
                  status="queued")
        db.add(run)
    jobs.defer("start_run", tenant_id=str(p.tenant_id), user_id=p.user_id, employee_id=employee_id,
               workflow=workflow, run_id=str(run.id))
    with tenant_session(p.tenant_id) as db:
        return run_view(db.get(Run, run.id))


@app.get("/v1/runs/{run_id}")
def get_run(run_id: uuid.UUID, p: Principal = Depends(principal)) -> dict[str, Any]:
    with tenant_session(p.tenant_id) as db:
        run = db.get(Run, run_id)
        if run is None:
            raise HTTPException(404)
        return run_view(run)


def run_view(run: Run) -> dict[str, Any]:
    return {"id": str(run.id), "workflow": run.workflow, "status": run.status, "result": run.result}


@app.get("/v1/approvals")
def list_approvals(p: Principal = Depends(principal)) -> list[dict[str, Any]]:
    with tenant_session(p.tenant_id) as db:
        rows = db.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.created_at)).all()
        return [{"id": str(a.id), "employee_id": a.employee_id, "tool": a.tool, "args": a.args,
                 "amount": a.amount, "role": a.role, "run_id": str(a.run_id) if a.run_id else None} for a in rows]


class Decision(BaseModel):
    approve: bool


@app.post("/v1/approvals/{approval_id}/decide")
def decide(approval_id: uuid.UUID, body: Decision, p: Principal = Depends(principal)) -> dict[str, Any]:
    with tenant_session(p.tenant_id) as db, domain_errors():
        approval = decide_approval(db, approval_id, p.user_id, body.approve)
        status, run_id = approval.status, runs_waiting_on(db, approval_id)
    if run_id:
        jobs.defer("resume_run", tenant_id=str(p.tenant_id), run_id=str(run_id))
    jobs.defer("dispatch_events", tenant_id=str(p.tenant_id))
    return {"id": str(approval_id), "status": status, "run_id": str(run_id) if run_id else None}


# --- inbound, reports, audit, notifications ----------------------------------------------

class InboundMessage(BaseModel):
    channel: str = "email"
    sender: str
    subject: str = ""
    kind: str  # set by the connector's parser: invoice, confirmation, other
    data: dict[str, Any] = {}


@app.post("/v1/inbound", status_code=202)
def inbound(msg: InboundMessage, p: Principal = Depends(principal)) -> dict[str, str]:
    """Connector webhook: a parsed supplier email arrives as event message.received."""
    from factory.models import Event

    with tenant_session(p.tenant_id) as db:
        db.add(Event(tenant_id=p.tenant_id, type="message.received", payload=msg.model_dump()))
    jobs.defer("dispatch_events", tenant_id=str(p.tenant_id))
    return {"status": "accepted"}


@app.get("/v1/reports/{employee_id}/{report_id}")
def report(employee_id: str, report_id: str, p: Principal = Depends(principal)) -> dict[str, Any]:
    with domain_errors():
        return reports.run_report(p.tenant_id, employee_id, report_id)


@app.get("/v1/audit")
def audit_log(p: Principal = Depends(principal)) -> list[dict[str, Any]]:
    with tenant_session(p.tenant_id) as db:
        rows = db.scalars(select(AuditEntry).order_by(AuditEntry.at)).all()
        return [{"actor": r.actor, "action": r.action, "outcome": r.outcome, "at": r.at.isoformat()} for r in rows]


@app.get("/v1/notifications")
def notifications(p: Principal = Depends(principal)) -> list[dict[str, Any]]:
    with tenant_session(p.tenant_id) as db:
        rows = db.scalars(select(Notification).order_by(Notification.at)).all()
        return [{"role": n.role, "event": n.event_type, "message": n.message} for n in rows]


@app.get("/v1/outbox")
def outbox(p: Principal = Depends(principal)) -> list[dict[str, Any]]:
    with tenant_session(p.tenant_id) as db:
        rows = db.scalars(select(OutboundMessage).order_by(OutboundMessage.at)).all()
        return [{"to": m.to, "subject": m.subject, "body": m.body, "status": m.status} for m in rows]

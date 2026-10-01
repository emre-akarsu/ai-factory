"""Pack loading, the tool decorator and the ctx every tool receives.

A tool is a typed function `fn(ctx, **args)`. The runner, not the tool, enforces
roles, approvals, audit and metering, so pack code cannot forget them."""
from __future__ import annotations

import inspect
import typing
import uuid
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import select
from sqlalchemy.orm import Session

from factory.db import now
from factory.manifest import Component, EmployeeManifest, import_ref, load_manifest
from factory.models import Approval, AuditEntry, Event, Installation, Member, Notification, Usage

# Components this platform build implements. A pack that declares another fails `factory build`.
AVAILABLE_COMPONENTS = {
    Component.workspace, Component.onboarding_wizard, Component.approvals, Component.connectors,
    Component.workflows, Component.agent_chat, Component.reports, Component.notifications,
    Component.metering, Component.audit,
}


class ApprovalRequired(Exception):
    def __init__(self, approval: Approval):
        super().__init__(f"{approval.tool} needs approval by {approval.role}")
        self.approval = approval


class ApprovalRejected(Exception):
    pass


class NotAllowed(Exception):
    pass


# --- the decorator -------------------------------------------------------------------

def tool(fn: Callable | None = None, *, amount: Callable | None = None):
    """Mark a pack function as a tool. `amount(ctx, **args)` returns the money at stake,
    compared with the manifest's approval.over_config."""

    def wrap(f: Callable) -> Callable:
        f.__factory_tool__ = True
        f.__factory_amount__ = amount
        f.__factory_args__ = args_model(f)
        return f

    return wrap(fn) if fn else wrap


def args_model(f: Callable) -> type[BaseModel]:
    hints = typing.get_type_hints(f)
    fields: dict[str, Any] = {}
    for name, p in list(inspect.signature(f).parameters.items())[1:]:  # skip ctx
        default = ... if p.default is inspect.Parameter.empty else p.default
        fields[name] = (hints.get(name, Any), default)
    return create_model(f"{f.__name__}_args", __config__=ConfigDict(extra="forbid"), **fields)


# --- packs ---------------------------------------------------------------------------

@dataclass
class Pack:
    manifest: EmployeeManifest
    path: Path

    @cached_property
    def config_model(self) -> type[BaseModel]:
        return import_ref(self.manifest.config_model)

    @cached_property
    def tools(self) -> dict[str, Callable]:
        out = {}
        for spec in self.manifest.tools:
            fn = import_ref(spec.entry)
            if not getattr(fn, "__factory_tool__", False):
                raise TypeError(f"{spec.entry} is not decorated with @tool")
            out[spec.name] = fn
        return out

    @cached_property
    def wizard_models(self) -> dict[str, type[BaseModel]]:
        return {s.id: import_ref(s.model) for s in self.manifest.wizard}

    def load_models(self) -> None:
        import_ref(self.manifest.data_models)


_PACKS: dict[str, Pack] = {}


def packs_root() -> Path:
    return Path(__file__).resolve().parents[2] / "employees"


def load_pack(path: str | Path) -> Pack:
    pack = Pack(load_manifest(path), Path(path))
    pack.load_models()
    _PACKS[pack.manifest.id] = pack
    return pack


def load_all_packs(root: Path | None = None) -> dict[str, Pack]:
    for d in sorted((root or packs_root()).iterdir()):
        if (d / "employee.yaml").exists():
            load_pack(d)
    return _PACKS


def get_pack(employee_id: str) -> Pack:
    if not _PACKS:
        load_all_packs()
    return _PACKS[employee_id]


# --- ctx -----------------------------------------------------------------------------

@dataclass
class Ctx:
    tenant_id: uuid.UUID
    user_id: str
    role: str
    pack: Pack
    db: Session
    config: BaseModel
    run_id: uuid.UUID | None = None
    step_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def employee_id(self) -> str:
        return self.pack.manifest.id

    @property
    def actor(self) -> str:
        return f"agent:{self.employee_id}" if self.run_id else self.user_id

    def emit(self, type: str, payload: dict[str, Any]) -> None:
        self.db.add(Event(tenant_id=self.tenant_id, type=type, payload={"employee_id": self.employee_id, **payload}))

    def meter(self, unit: str, quantity: int = 1) -> None:
        if unit not in self.pack.manifest.meters:
            raise NotAllowed(f"meter {unit} is not declared in the manifest")
        self.db.add(Usage(tenant_id=self.tenant_id, employee_id=self.employee_id, unit=unit, quantity=quantity))

    def notify(self, role: str, message: str, event_type: str = "custom", channel: str = "in_app") -> None:
        self.db.add(Notification(tenant_id=self.tenant_id, role=role, channel=channel, event_type=event_type, message=message))

    @property
    def email(self):
        from factory.components.connectors import email_client

        if "email" not in {c.name for c in self.pack.manifest.connectors}:
            raise NotAllowed("this employee did not declare the email connector")
        return email_client(self)


def make_ctx(db: Session, tenant_id: uuid.UUID, user_id: str, employee_id: str, *,
             role: str | None = None, run_id: uuid.UUID | None = None) -> Ctx:
    pack = get_pack(employee_id)
    inst = db.scalar(select(Installation).where(Installation.employee_id == employee_id))
    if inst is None:
        raise NotAllowed(f"{employee_id} is not installed in this workspace")
    if role is None:
        role = db.scalar(select(Member.role).where(Member.user_id == user_id))
        if role is None:
            raise NotAllowed("user is not a member of this workspace")
    return Ctx(tenant_id, user_id, role, pack, db, pack.config_model.model_validate(inst.config), run_id)


# --- the runner ----------------------------------------------------------------------

def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def audit(ctx: Ctx, action: str, args: dict, outcome: str, detail: dict | None = None) -> None:
    ctx.db.add(AuditEntry(tenant_id=ctx.tenant_id, actor=ctx.actor, employee_id=ctx.employee_id,
                          action=action, args=_jsonable(args), outcome=outcome, detail=_jsonable(detail)))


def _approval_gate(ctx: Ctx, name: str, fn: Callable, kwargs: dict, approval_id: uuid.UUID | None) -> Approval | None:
    spec = ctx.pack.manifest.tool(name).approval
    if spec is None:
        return None
    amount = float(fn.__factory_amount__(ctx, **kwargs)) if fn.__factory_amount__ else None
    if spec.over_config is not None:
        threshold = getattr(ctx.config, spec.over_config)
        if amount is not None and amount <= threshold:
            return None

    q = select(Approval).where(Approval.tool == name)
    if approval_id:
        q = q.where(Approval.id == approval_id)
    elif ctx.step_key:
        q = q.where(Approval.step_key == ctx.step_key)
    else:
        q = None
    existing = ctx.db.scalar(q.order_by(Approval.created_at.desc())) if q is not None else None
    if existing is not None:
        if existing.args != _jsonable(kwargs):
            raise NotAllowed("approval was given for different arguments")
        if existing.status == "approved":
            return existing
        if existing.status == "rejected":
            raise ApprovalRejected(f"{name} was rejected by {existing.decided_by}")
        if existing.status == "pending":
            raise ApprovalRequired(existing)
        raise NotAllowed("approval already used")

    approval = Approval(tenant_id=ctx.tenant_id, employee_id=ctx.employee_id, tool=name, args=_jsonable(kwargs),
                        amount=amount, role=spec.role, run_id=ctx.run_id, step_key=ctx.step_key,
                        requested_by=ctx.actor)
    ctx.db.add(approval)
    ctx.db.flush()
    ctx.emit("approval.requested", {"approval_id": str(approval.id), "tool": name, "amount": amount})
    ctx.notify(spec.role, f"{ctx.pack.manifest.name} needs approval to run {name}"
               + (f" for ${amount:,.2f}" if amount is not None else ""), "approval.requested")
    audit(ctx, name, kwargs, "approval_requested", {"approval_id": approval.id, "amount": amount})
    raise ApprovalRequired(approval)


def call_tool(ctx: Ctx, name: str, args: dict[str, Any] | None = None, *, approval_id: uuid.UUID | None = None) -> Any:
    spec = ctx.pack.manifest.tool(name)
    fn = ctx.pack.tools[name]
    args = args or {}
    if ctx.role not in spec.roles and not ctx.run_id:
        audit(ctx, name, args, "denied", {"role": ctx.role})
        raise NotAllowed(f"role {ctx.role} cannot run {name}")
    kwargs = dict(fn.__factory_args__.model_validate(args))

    approval = _approval_gate(ctx, name, fn, kwargs, approval_id)
    try:
        with ctx.db.begin_nested():  # a failing tool rolls back its own writes, the audit row stays
            result = _jsonable(fn(ctx, **kwargs))
    except Exception as e:
        audit(ctx, name, kwargs, "error", {"error": str(e)})
        raise
    if approval is not None:
        approval.status = "used"
    audit(ctx, name, kwargs, "ok", {"approval_id": approval.id} if approval else None)
    return result


def decide_approval(db: Session, approval_id: uuid.UUID, user_id: str, approve: bool) -> Approval:
    approval = db.get(Approval, approval_id)
    if approval is None or approval.status != "pending":
        raise NotAllowed("no pending approval with that id")
    role = db.scalar(select(Member.role).where(Member.user_id == user_id))
    if role not in (approval.role, "owner"):
        raise NotAllowed(f"approval needs role {approval.role}")
    approval.status = "approved" if approve else "rejected"
    approval.decided_by = user_id
    approval.decided_at = now()
    db.add(Event(tenant_id=approval.tenant_id, type="approval.decided",
                 payload={"approval_id": str(approval.id), "status": approval.status, "employee_id": approval.employee_id}))
    db.add(AuditEntry(tenant_id=approval.tenant_id, actor=user_id, employee_id=approval.employee_id,
                      action="approval.decide", args={"approval_id": str(approval.id)}, outcome=approval.status, detail=None))
    return approval

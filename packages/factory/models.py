"""Tables owned by the shared components. Packs add their own tables next to these."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from factory.db import Base, TenantScoped, now


def uid() -> uuid.UUID:
    return uuid.uuid4()


# --- global tables (no tenant data) -------------------------------------------------

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str]
    plan: Mapped[str] = mapped_column(default="starter")
    created_at: Mapped[datetime] = mapped_column(default=now)


class PackBuild(Base):
    """Result of `factory build`: a pack can only be published from a passing build."""
    __tablename__ = "pack_builds"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    employee_id: Mapped[str] = mapped_column(index=True)
    version: Mapped[str]
    passed: Mapped[bool]
    report: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Listing(Base):
    """Marketplace catalog entry, generated from the manifest."""
    __tablename__ = "marketplace_listings"
    employee_id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[str]
    rank: Mapped[int]
    name: Mapped[str]
    industry: Mapped[str]
    tagline: Mapped[str]
    description: Mapped[str]
    category: Mapped[str]
    price_monthly_usd: Mapped[int]
    featured: Mapped[bool]
    highlights: Mapped[list[str]] = mapped_column(JSON)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON)
    build_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pack_builds.id"))
    published_at: Mapped[datetime] = mapped_column(default=now)


# --- tenant tables (RLS) -------------------------------------------------------------

class Member(TenantScoped, Base):
    __tablename__ = "members"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str]
    role: Mapped[str]


class Installation(TenantScoped, Base):
    __tablename__ = "installations"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    employee_id: Mapped[str]
    version: Mapped[str]
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    accepted_permissions: Mapped[dict[str, Any]] = mapped_column(JSON)
    installed_by: Mapped[str]
    installed_at: Mapped[datetime] = mapped_column(default=now)


class AuditEntry(TenantScoped, Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    actor: Mapped[str]  # user id, or "agent:<employee>"
    employee_id: Mapped[str]
    action: Mapped[str]
    args: Mapped[dict[str, Any]] = mapped_column(JSON)
    outcome: Mapped[str]
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(default=now)


class Approval(TenantScoped, Base):
    __tablename__ = "approvals"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    employee_id: Mapped[str]
    tool: Mapped[str]
    args: Mapped[dict[str, Any]] = mapped_column(JSON)
    amount: Mapped[float | None]
    role: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")  # pending|approved|rejected|used
    run_id: Mapped[uuid.UUID | None]
    step_key: Mapped[str | None] = mapped_column(index=True)
    requested_by: Mapped[str]
    decided_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=now)
    decided_at: Mapped[datetime | None]


class Event(TenantScoped, Base):
    """Outbox: written in the same transaction as the change, delivered by the worker."""
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    type: Mapped[str] = mapped_column(index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    delivered: Mapped[bool] = mapped_column(default=False)
    at: Mapped[datetime] = mapped_column(default=now)


class Usage(TenantScoped, Base):
    __tablename__ = "usage"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    employee_id: Mapped[str]
    unit: Mapped[str]
    quantity: Mapped[int] = mapped_column(default=1)
    at: Mapped[datetime] = mapped_column(default=now)


class Run(TenantScoped, Base):
    __tablename__ = "runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    employee_id: Mapped[str]
    workflow: Mapped[str]
    status: Mapped[str] = mapped_column(default="running")  # running|waiting_approval|completed|failed|rejected
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_by: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(default=now)
    finished_at: Mapped[datetime | None]


class Notification(TenantScoped, Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    role: Mapped[str]
    channel: Mapped[str]
    event_type: Mapped[str]
    message: Mapped[str]
    read: Mapped[bool] = mapped_column(default=False)
    at: Mapped[datetime] = mapped_column(default=now)


class OutboundMessage(TenantScoped, Base):
    """Every email an agent sends, whichever connector delivered it."""
    __tablename__ = "outbound_messages"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    connector: Mapped[str]
    to: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str]
    status: Mapped[str] = mapped_column(default="sent")
    at: Mapped[datetime] = mapped_column(default=now)

"""Workspace and roles component."""
from __future__ import annotations

import uuid

from factory.db import tenant_session
from factory.models import Member, Tenant


def create_workspace(name: str, owner_user_id: str, owner_email: str) -> uuid.UUID:
    with tenant_session(None) as db:
        tenant = Tenant(name=name)
        db.add(tenant)
    with tenant_session(tenant.id) as db:
        db.add(Member(tenant_id=tenant.id, user_id=owner_user_id, email=owner_email, role="owner"))
    return tenant.id


def add_member(tenant_id: uuid.UUID, user_id: str, email: str, role: str) -> None:
    with tenant_session(tenant_id) as db:
        db.add(Member(tenant_id=tenant_id, user_id=user_id, email=email, role=role))

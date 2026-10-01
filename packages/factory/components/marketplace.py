"""Marketplace component: listings come from passing builds; installing an employee
records consent to its permissions, validates its config and applies the wizard."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from factory.db import tenant_session
from factory.models import Installation, Listing, Member, PackBuild
from factory.runtime import NotAllowed, call_tool, get_pack, make_ctx


def publish(employee_id: str) -> Listing:
    m = get_pack(employee_id).manifest
    with tenant_session(None) as db:
        build = db.scalar(select(PackBuild).where(PackBuild.employee_id == m.id, PackBuild.version == m.version)
                          .order_by(PackBuild.created_at.desc()))
        if build is None or not build.passed:
            raise NotAllowed(f"{m.id} {m.version} has no passing build; run `factory build` first")
        listing = db.get(Listing, m.id)
        rank = listing.rank if listing else (db.scalar(select(func.count()).select_from(Listing)) or 0) + 1
        values = dict(version=m.version, rank=rank, name=m.name, industry=m.industry, tagline=m.tagline,
                      description=m.description, category=m.listing.category,
                      price_monthly_usd=m.listing.price_monthly_usd, featured=m.listing.featured,
                      highlights=m.listing.highlights, permissions=m.permissions, build_id=build.id)
        if listing is None:
            listing = Listing(employee_id=m.id, **values)
            db.add(listing)
        else:
            for k, v in values.items():
                setattr(listing, k, v)
        return listing


def catalog() -> list[dict[str, Any]]:
    with tenant_session(None) as db:
        rows = db.scalars(select(Listing).order_by(Listing.rank)).all()
        return [listing_view(r) for r in rows]


def listing_view(r: Listing) -> dict[str, Any]:
    pack = get_pack(r.employee_id)
    return {
        "employee_id": r.employee_id, "rank": r.rank, "name": r.name, "version": r.version,
        "industry": r.industry, "tagline": r.tagline, "description": r.description, "category": r.category,
        "price_monthly_usd": r.price_monthly_usd, "featured": r.featured, "highlights": r.highlights,
        "permissions": r.permissions, "suggested_prompts": pack.manifest.suggested_prompts,
        "config_schema": pack.config_model.model_json_schema(),
        "wizard": [{"id": s.id, "title": s.title, "schema": pack.wizard_models[s.id].model_json_schema()}
                   for s in pack.manifest.wizard],
    }


def install(tenant_id: uuid.UUID, user_id: str, employee_id: str, accepted_permissions: dict[str, Any],
            config: dict[str, Any], wizard: dict[str, Any] | None = None, *,
            require_listing: bool = True) -> Installation:
    """require_listing=False is only for `factory build` evals, which run before publishing."""
    pack = get_pack(employee_id)
    m = pack.manifest
    with tenant_session(None) as db:
        if require_listing and db.get(Listing, employee_id) is None:
            raise NotAllowed(f"{employee_id} is not published in the marketplace")
    if accepted_permissions != m.permissions:
        raise NotAllowed("installer must accept exactly the permissions the employee asks for")
    cfg = pack.config_model.model_validate(config)
    with tenant_session(tenant_id) as db:
        role = db.scalar(select(Member.role).where(Member.user_id == user_id))
        if role != "owner":
            raise NotAllowed("only a workspace owner can install employees")
        inst = Installation(tenant_id=tenant_id, employee_id=m.id, version=m.version,
                            config=cfg.model_dump(mode="json"), accepted_permissions=accepted_permissions,
                            installed_by=user_id)
        db.add(inst)
        db.flush()
        ctx = make_ctx(db, tenant_id, user_id, employee_id)
        for step in m.wizard:
            data = (wizard or {}).get(step.id)
            if data is None:
                continue
            validated = pack.wizard_models[step.id].model_validate(data)
            if step.apply_tool:
                call_tool(ctx, step.apply_tool, validated.model_dump(mode="json"))
        ctx.emit("employee.installed", {"version": m.version})
        return inst

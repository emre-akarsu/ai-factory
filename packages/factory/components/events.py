"""Events component: deliver outbox events to notification rules and to workflows whose
trigger names the event. Packs never call each other; they react to events."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from factory.models import Event, Installation, Notification
from factory.db import tenant_session
from factory.runtime import get_pack
from factory import jobs


def _matches(match: dict, payload: dict) -> bool:
    return all(payload.get(k) == v for k, v in match.items())


def dispatch_events(tenant_id: uuid.UUID) -> int:
    """Called by the worker after writes; returns how many events were delivered."""
    starts = []
    with tenant_session(tenant_id) as db:
        events = db.scalars(select(Event).where(Event.delivered.is_(False)).order_by(Event.at)
                            .with_for_update(skip_locked=True)).all()
        installed = db.scalars(select(Installation)).all()
        for ev in events:
            for inst in installed:
                m = get_pack(inst.employee_id).manifest
                if ev.payload.get("employee_id") == m.id or ev.type.startswith("message."):
                    for rule in m.notifications:
                        if rule.event == ev.type:
                            db.add(Notification(tenant_id=tenant_id, role=rule.role, channel=rule.channel,
                                                event_type=ev.type, message=_describe(ev)))
                for wf_id, wf in m.workflows.items():
                    if wf.trigger and wf.trigger.event == ev.type and _matches(wf.trigger.match, ev.payload):
                        starts.append((m.id, wf_id, ev.payload))
            ev.delivered = True
    for employee_id, wf_id, payload in starts:
        jobs.defer("start_run", tenant_id=str(tenant_id), user_id="system", employee_id=employee_id,
                   workflow=wf_id, event=payload)
    return len(events)


def _describe(ev: Event) -> str:
    p = ev.payload
    if ev.type == "invoice.disputed":
        return f"Invoice {p.get('invoice_number')} from {p.get('supplier')} has {p.get('issues')} issue(s) worth ${p.get('amount', 0):,.2f}"
    if ev.type == "purchase_order.sent":
        return f"PO {p.get('number')} sent to {p.get('supplier')} for ${p.get('total', 0):,.2f}"
    return f"{ev.type}: {p}"

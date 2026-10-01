"""Render background worker: `procrastinate --app=factory.worker.app worker`.
Cron triggers in manifests become periodic tasks that start a run in every workspace
that installed the employee."""
from __future__ import annotations

import uuid
from typing import Any

import procrastinate
from sqlalchemy import select

from factory.db import app_url, libpq, tenant_session
from factory.models import Installation, Tenant
from factory.runtime import load_all_packs

app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=libpq(app_url())))


@app.task(name="factory.start_run", retry=3)
def start_run(tenant_id: str, user_id: str, employee_id: str, workflow: str,
              event: dict[str, Any] | None = None, run_id: str | None = None) -> None:
    from factory.components.workflows import start_run as run

    run(uuid.UUID(tenant_id), user_id, employee_id, workflow, event, uuid.UUID(run_id) if run_id else None)
    dispatch_events.func(tenant_id=tenant_id)


@app.task(name="factory.resume_run", retry=3)
def resume_run(tenant_id: str, run_id: str) -> None:
    from factory.components.workflows import resume_run as resume

    resume(uuid.UUID(tenant_id), uuid.UUID(run_id))
    dispatch_events.func(tenant_id=tenant_id)


@app.task(name="factory.dispatch_events")
def dispatch_events(tenant_id: str) -> None:
    from factory.components.events import dispatch_events as dispatch

    dispatch(uuid.UUID(tenant_id))


def scheduled(employee_id: str, workflow: str) -> int:
    """Start a run for every workspace with this employee installed."""
    with tenant_session(None) as db:
        tenants = db.scalars(select(Tenant.id)).all()
    started = 0
    for tid in tenants:
        with tenant_session(tid) as db:
            installed = db.scalar(select(Installation.id).where(Installation.employee_id == employee_id))
        if installed:
            start_run.func(tenant_id=str(tid), user_id="schedule", employee_id=employee_id, workflow=workflow)
            started += 1
    return started


_registered: list[str] = []


def register_schedules() -> list[str]:
    ids = _registered
    for pack in load_all_packs().values():
        for wf_id, wf in pack.manifest.workflows.items():
            if wf.trigger and wf.trigger.cron:
                pid = f"{pack.manifest.id}.{wf_id}"
                if pid in ids:
                    continue

                def task(timestamp: int, _e=pack.manifest.id, _w=wf_id) -> None:
                    scheduled(_e, _w)

                task.__name__ = pid.replace("-", "_").replace(".", "__")
                app.periodic(cron=wf.trigger.cron, periodic_id=pid)(app.task(name=f"schedule.{pid}")(task))
                ids.append(pid)
    return ids


register_schedules()

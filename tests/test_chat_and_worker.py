import uuid

from sqlalchemy import select

import yaml
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from factory.components import marketplace
from factory.components.agent_chat import build_agent
from factory.components.workspace import create_workspace
from factory.db import tenant_session
from factory.manifest import load_manifest
from factory.runtime import make_ctx

FIXTURE = yaml.safe_load(open("employees/restaurant_purchasing/evals/fixtures/harbor_bistro.yaml"))


class ToolCallingFake(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        self.__dict__["bound"] = [t.name for t in tools]
        return self


def installed_workspace():
    owner = f"owner-{uuid.uuid4().hex[:6]}"
    tid = create_workspace("Chat Bistro", owner, "o@example.test")
    m = load_manifest("employees/restaurant_purchasing")
    marketplace.install(tid, owner, m.id, m.permissions, FIXTURE["config"], FIXTURE["wizard"], require_listing=False)
    return tid, owner


def test_chat_agent_uses_tools_through_the_runner():
    tid, owner = installed_workspace()
    model = ToolCallingFake(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "build_order", "args": {}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "send_purchase_orders", "args": {"po_ids": ["PLACEHOLDER"]}, "id": "2"}]),
        AIMessage(content="Drafted two orders totalling $1,015."),
    ]))
    with tenant_session(tid) as db:
        ctx = make_ctx(db, tid, owner, "restaurant-purchasing")
        agent = build_agent(ctx, model)
        out = agent.invoke({"messages": [("user", "What do we need for Thursday?")]})
    assert "build_order" in model.__dict__["bound"]
    tool_msgs = [m for m in out["messages"] if m.type == "tool"]
    assert '"total": 1015.0' in tool_msgs[0].content
    assert "unknown purchase order" in tool_msgs[1].content or "Error" in tool_msgs[1].content
    assert out["messages"][-1].content.startswith("Drafted")


def test_staff_chat_only_gets_staff_tools():
    tid, owner = installed_workspace()
    with tenant_session(tid) as db:
        ctx = make_ctx(db, tid, owner, "restaurant-purchasing", role="staff")
        from factory.components.agent_chat import lc_tools

        assert sorted(t.name for t in lc_tools(ctx)) == ["compare_prices", "record_count"]


def test_worker_registers_manifest_schedule_and_runs_jobs():
    from procrastinate import testing

    from factory import worker

    assert "restaurant-purchasing.reorder" in worker.register_schedules()
    tid, owner = installed_workspace()
    connector = testing.InMemoryConnector()
    with worker.app.replace_connector(connector) as app:
        app.configure_task("factory.start_run").defer(
            tenant_id=str(tid), user_id=owner, employee_id="restaurant-purchasing", workflow="reorder")
        app.run_worker(wait=False, install_signal_handlers=False, listen_notify=False)
    assert [j["status"] for j in connector.jobs.values()] == ["succeeded"]
    from sqlalchemy import select

    from factory.models import OutboundMessage, Run

    with tenant_session(tid) as db:
        assert db.scalar(select(Run.status)) == "completed"  # $1,015 is under the $1,500 default limit
        assert len(db.scalars(select(OutboundMessage)).all()) == 2


def test_worker_job_can_enqueue_follow_up_jobs(monkeypatch):
    """An inbound invoice is dispatched inside a worker job, which must enqueue the
    invoice-check run on the real Postgres queue (not run it inline)."""
    import os
    import subprocess
    import sys

    import psycopg

    from factory import worker
    from factory.db import app_url, libpq
    from factory.models import Event

    monkeypatch.setenv("FACTORY_JOBS", "procrastinate")
    tid, _ = installed_workspace()
    with tenant_session(tid) as db:
        db.add(Event(tenant_id=tid, type="message.received", payload={"kind": "invoice", "data": {}}))
    with worker.app.open():
        worker.app.configure_task("factory.dispatch_events").defer(tenant_id=str(tid))
    # the real worker CLI, as on Render: a fresh process whose app is opened async
    subprocess.run([sys.executable, "-m", "procrastinate", "--app=factory.worker.app", "worker", "--one-shot"],
                   check=True, timeout=60, env={**os.environ, "FACTORY_JOBS": "procrastinate"}, capture_output=True)

    with psycopg.connect(libpq(app_url())) as conn:
        rows = conn.execute("select task_name, status from procrastinate_jobs where args->>'tenant_id' = %s",
                            (str(tid),)).fetchall()
    tasks = {name: status for name, status in rows}
    assert tasks["factory.dispatch_events"] == "succeeded"
    assert "factory.start_run" in tasks
    with tenant_session(tid) as db:
        assert db.scalar(select(Event.delivered).where(Event.type == "message.received")) is True

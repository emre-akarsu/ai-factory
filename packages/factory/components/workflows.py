"""Workflows component: each manifest workflow becomes a LangGraph graph with one node
per step. A step whose tool needs approval pauses the run with interrupt(); the Postgres
checkpointer keeps it paused until someone decides, then the run resumes in place."""
from __future__ import annotations

import operator
import uuid
from functools import lru_cache
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from factory.db import app_url, libpq, now, owner_url, tenant_session
from factory.manifest import Step
from factory.models import Approval, Event, Run
from factory.runtime import ApprovalRejected, ApprovalRequired, call_tool, get_pack, make_ctx


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class RunState(TypedDict, total=False):
    tenant_id: str
    user_id: str
    run_id: str
    event: dict[str, Any]
    results: Annotated[dict[str, Any], _merge]
    halted: Annotated[bool, operator.or_]


def resolve(value: Any, state: RunState) -> Any:
    """'$build_order.po_ids' -> state results; '$event.invoice' -> trigger payload."""
    if isinstance(value, str) and value.startswith("$"):
        head, *path = value[1:].split(".")
        cur: Any = state.get("event", {}) if head == "event" else state.get("results", {}).get(head)
        for key in path:
            cur = cur.get(key) if isinstance(cur, dict) else None
        return cur
    if isinstance(value, dict):
        return {k: resolve(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, state) for v in value]
    return value


def _node(employee_id: str, index: int, step: Step):
    def run_step(state: RunState) -> dict:
        if state.get("halted"):
            return {}
        if step.skip_if_empty and not resolve(f"${step.skip_if_empty}", state):
            return {"results": {step.tool: {"skipped": True}}}
        args = resolve(step.args, state)
        tenant_id, run_id = uuid.UUID(state["tenant_id"]), uuid.UUID(state["run_id"])
        pending = None
        with tenant_session(tenant_id) as db:
            ctx = make_ctx(db, tenant_id, state["user_id"], employee_id, role="agent", run_id=run_id)
            ctx.step_key = f"{run_id}:{index}"
            try:
                return {"results": {step.tool: call_tool(ctx, step.tool, args)}}
            except ApprovalRequired as e:
                pending = str(e.approval.id)  # committed when the session closes
            except ApprovalRejected as e:
                return {"results": {step.tool: {"rejected": str(e)}}, "halted": True}
        interrupt({"approval_id": pending, "tool": step.tool})
        return {}  # not reached: on resume the node starts again and finds the decision

    return run_step


def compile_workflow(employee_id: str, workflow: str, checkpointer=None):
    spec = get_pack(employee_id).manifest.workflows[workflow]
    g = StateGraph(RunState)
    names = []
    for i, step in enumerate(spec.steps):
        name = f"{i}_{step.tool}"
        g.add_node(name, _node(employee_id, i, step))
        names.append(name)
    g.add_edge(START, names[0])
    for a, b in zip(names, names[1:]):
        g.add_edge(a, b)
    g.add_edge(names[-1], END)
    return g.compile(checkpointer=checkpointer)


@lru_cache
def _pool() -> ConnectionPool:
    return ConnectionPool(libpq(app_url()), kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                          open=True, max_size=5)


def checkpointer():
    from langgraph.checkpoint.postgres import PostgresSaver

    return PostgresSaver(_pool())


def setup_checkpointer() -> None:
    """Run once by `factory migrate`, as the owner role."""
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver

    with psycopg.connect(libpq(owner_url()), autocommit=True, row_factory=dict_row) as conn:
        PostgresSaver(conn).setup()


def _finish(run_id: uuid.UUID, tenant_id: uuid.UUID, graph, config) -> Run:
    snapshot = graph.get_state(config)
    values = snapshot.values
    with tenant_session(tenant_id) as db:
        run = db.get(Run, run_id)
        run.result = values.get("results", {})
        if snapshot.next:
            run.status = "waiting_approval"
        else:
            run.status = "rejected" if values.get("halted") else "completed"
            run.finished_at = now()
            db.add(Event(tenant_id=tenant_id, type="run.completed",
                         payload={"run_id": str(run_id), "employee_id": run.employee_id,
                                  "workflow": run.workflow, "status": run.status}))
        return run


def start_run(tenant_id: uuid.UUID, user_id: str, employee_id: str, workflow: str,
              event: dict[str, Any] | None = None, run_id: uuid.UUID | None = None) -> Run:
    with tenant_session(tenant_id) as db:
        run = db.get(Run, run_id) if run_id else None
        if run is None:
            run = Run(tenant_id=tenant_id, employee_id=employee_id, workflow=workflow, started_by=user_id)
            db.add(run)
        run.status = "running"
    graph = compile_workflow(employee_id, workflow, checkpointer())
    config = {"configurable": {"thread_id": str(run.id)}}
    try:
        graph.invoke({"tenant_id": str(tenant_id), "user_id": user_id, "run_id": str(run.id),
                      "event": event or {}, "results": {}}, config)
    except Exception as e:
        _fail(run.id, tenant_id, e)
        raise
    return _finish(run.id, tenant_id, graph, config)


def resume_run(tenant_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    with tenant_session(tenant_id) as db:
        run = db.get(Run, run_id)
        if run is None or run.status not in ("waiting_approval", "queued"):
            return run
        employee_id, workflow = run.employee_id, run.workflow
    graph = compile_workflow(employee_id, workflow, checkpointer())
    config = {"configurable": {"thread_id": str(run_id)}}
    try:
        graph.invoke(Command(resume=True), config)
    except Exception as e:
        _fail(run_id, tenant_id, e)
        raise
    return _finish(run_id, tenant_id, graph, config)


def _fail(run_id: uuid.UUID, tenant_id: uuid.UUID, error: Exception) -> None:
    with tenant_session(tenant_id) as db:
        run = db.get(Run, run_id)
        run.status, run.result, run.finished_at = "failed", {"error": str(error)}, now()


def runs_waiting_on(db, approval_id: uuid.UUID) -> uuid.UUID | None:
    a = db.get(Approval, approval_id)
    return a.run_id if a else None

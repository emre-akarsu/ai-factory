"""`factory build <pack>`: the gate every employee passes before it can be published.
It validates the manifest, checks that every reference resolves, compiles the workflows,
dry-runs the reports, and runs the pack's eval scenarios against a scratch workspace."""
from __future__ import annotations

import json
import os
import traceback
import uuid
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from sqlalchemy import select, text

from factory.components import marketplace
from factory.components.events import dispatch_events
from factory.components.workflows import compile_workflow, resume_run, start_run
from factory.components.workspace import add_member, create_workspace
from factory.db import Base, tenant_session
from factory.manifest import manifest_json_schema
from factory.models import Approval, Event, PackBuild, Run, Tenant
from factory.runtime import AVAILABLE_COMPONENTS, Pack, call_tool, decide_approval, load_pack, make_ctx


class Check(BaseModel):
    name: str
    passed: bool
    detail: str = ""


def _check(checks: list[Check], name: str, fn) -> Any:
    try:
        out = fn()
        checks.append(Check(name=name, passed=True, detail=str(out or "")))
        return out
    except Exception as e:  # a failed check is recorded, not raised
        checks.append(Check(name=name, passed=False, detail=f"{type(e).__name__}: {e}"))
        return None


def static_checks(pack: Pack, checks: list[Check]) -> None:
    m = pack.manifest

    def components():
        missing = sorted(c.value for c in m.uses if c not in AVAILABLE_COMPONENTS)
        if missing:
            raise ValueError(f"components not available on this platform yet: {missing}")
        return f"{len(m.uses)} components"

    def tools():
        return f"{len(pack.tools)} tools"

    def config():
        fields = pack.config_model.model_fields
        for t in m.tools:
            if t.approval and t.approval.over_config and t.approval.over_config not in fields:
                raise ValueError(f"{t.name} approval names missing config field {t.approval.over_config}")
        return pack.config_model.__name__

    def wizard():
        for step in m.wizard:
            model = pack.wizard_models[step.id]
            if step.apply_tool:
                tool_fields = set(pack.tools[step.apply_tool].__factory_args__.model_fields)
                if set(model.model_fields) != tool_fields:
                    raise ValueError(f"wizard step {step.id} fields {sorted(model.model_fields)} "
                                     f"do not match {step.apply_tool} args {sorted(tool_fields)}")
        return f"{len(m.wizard)} steps"

    def workflows():
        for wf in m.workflows:
            compile_workflow(m.id, wf)
        return f"{len(m.workflows)} workflows"

    def reports():
        with tenant_session(uuid.uuid4()) as db:
            for r in m.reports:
                db.execute(text(f"explain {r.sql}"))
        return f"{len(m.reports)} reports"

    def store():
        if not m.store:
            return "no store page"
        from factory.components.store import asset_path, store_spec

        spec = store_spec(m.id)
        media = spec.media
        files = [f for f in [media.hero_video, media.hero_video_webm, media.hero_poster, media.social_video, media.one_pager, *media.images,
                             *(k.file for k in media.kit)] if f]
        for f in files:
            asset_path(m.id, f)
        return f"{len(spec.plans)} plans, {len(files)} media files"

    for name, fn in [("components", components), ("tools import", tools), ("config", config),
                     ("wizard", wizard), ("workflows compile", workflows), ("reports", reports), ("store page", store)]:
        _check(checks, name, fn)


# --- evals ---------------------------------------------------------------------------

def get_path(data: Any, path: str) -> Any:
    for key in path.split("."):
        if isinstance(data, list):
            data = data[int(key)]
        elif isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data


def assert_expect(result: Any, expect: dict[str, Any]) -> None:
    for path, want in expect.items():
        got = get_path(result, path)
        if isinstance(want, dict) and len(want) == 1 and next(iter(want)) in {"len", "gte", "lte", "contains", "approx"}:
            op, val = next(iter(want.items()))
            ok = {"len": lambda: len(got) == val, "gte": lambda: got >= val, "lte": lambda: got <= val,
                  "contains": lambda: val in got, "approx": lambda: abs(float(got) - val) < 0.01}[op]()
        else:
            ok = got == want
        if not ok:
            raise AssertionError(f"{path}: expected {want!r}, got {got!r}")


def _resolve(value: Any, results: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        head, _, rest = value[1:].partition(".")
        return get_path(results[head], rest) if rest else results[head]
    if isinstance(value, dict):
        return {k: _resolve(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, results) for v in value]
    return value


def run_scenario(pack: Pack, scenario: dict[str, Any]) -> None:
    m = pack.manifest
    users = {r: f"eval-{r}-{uuid.uuid4().hex[:8]}" for r in m.roles}
    owner = users["owner"]
    tid = create_workspace(f"eval: {m.id} {scenario['name']}", owner, "owner@example.test")
    for role, user in users.items():
        if role != "owner":
            add_member(tid, user, f"{role}@example.test", role)
    try:
        marketplace.install(tid, owner, m.id, m.permissions, scenario.get("config", {}), scenario.get("wizard"),
                            require_listing=False)
        dispatch_events(tid)
        results: dict[str, Any] = {}
        for i, step in enumerate(scenario["steps"]):
            label = step.get("as") or step.get("tool") or step.get("workflow") or step.get("event") or f"step{i}"
            user = users[step.get("user", "owner")]
            try:
                out = _run_step(pack, tid, user, step, results)
            except Exception as e:
                if "raises" not in step:
                    raise
                out = {"error": type(e).__name__, "message": str(e)}
            results[label] = out
            if "expect" in step:
                try:
                    assert_expect(out, step["expect"])
                except AssertionError as e:
                    raise AssertionError(f"step {i} ({label}): {e}") from None
    finally:
        _drop_tenant(tid)


def _run_step(pack: Pack, tid: uuid.UUID, user: str, step: dict[str, Any], results: dict[str, Any]) -> Any:
    m = pack.manifest
    if "tool" in step:
        with tenant_session(tid) as db:
            ctx = make_ctx(db, tid, user, m.id)
            out = call_tool(ctx, step["tool"], _resolve(step.get("args", {}), results))
    elif "workflow" in step:
        run = start_run(tid, user, m.id, step["workflow"])
        dispatch_events(tid)
        out = {"status": run.status, "result": run.result, "id": str(run.id)}
    elif "event" in step:
        with tenant_session(tid) as db:
            db.add(Event(tenant_id=tid, type=step["event"], payload=_resolve(step.get("payload", {}), results)))
        dispatch_events(tid)
        with tenant_session(tid) as db:
            run = db.scalar(select(Run).order_by(Run.started_at.desc()))
            out = {"status": run.status, "result": run.result, "id": str(run.id)} if run else {}
    elif "decide" in step:
        approve = step["decide"] == "approve"
        with tenant_session(tid) as db:
            pending = db.scalars(select(Approval).where(Approval.status == "pending")).all()
            decided = [decide_approval(db, a.id, user, approve) for a in pending]
            run_ids = {a.run_id for a in decided if a.run_id}
        out = {"decided": len(decided)}
        for rid in run_ids:
            run = resume_run(tid, rid)
            out = {"decided": len(decided), "status": run.status, "result": run.result}
        dispatch_events(tid)
    elif "query" in step:
        with tenant_session(tid) as db:
            rows = db.execute(text(step["query"])).mappings().all()
            out = [{k: (float(v) if hasattr(v, "is_finite") else v) for k, v in r.items()} for r in rows]
    else:
        raise ValueError(f"unknown step {step}")
    return out


def _drop_tenant(tid: uuid.UUID) -> None:
    with tenant_session(tid) as db:
        for table in reversed(Base.metadata.sorted_tables):
            if "tenant_id" in table.c:
                db.execute(table.delete())
    with tenant_session(None) as db:
        db.execute(Tenant.__table__.delete().where(Tenant.id == tid))


def eval_checks(pack: Pack, checks: list[Check]) -> None:
    if not pack.manifest.evals:
        checks.append(Check(name="evals", passed=False, detail="every pack ships evals"))
        return
    previous = os.environ.get("FACTORY_JOBS")
    os.environ["FACTORY_JOBS"] = "inline"
    try:
        for path in sorted((pack.path / pack.manifest.evals).glob("*.yaml")):
            scenario = yaml.safe_load(path.read_text())
            if "fixture" in scenario:
                base = yaml.safe_load((path.parent / scenario["fixture"]).read_text())
                scenario["config"] = {**base.get("config", {}), **scenario.get("config", {})}
                scenario["wizard"] = {**base.get("wizard", {}), **scenario.get("wizard", {})}
            name = f"eval: {scenario['name']}"
            try:
                run_scenario(pack, scenario)
                checks.append(Check(name=name, passed=True))
            except Exception as e:
                checks.append(Check(name=name, passed=False, detail=f"{type(e).__name__}: {e}\n"
                                    + "".join(traceback.format_exception(e)[-3:])))
    finally:
        if previous is None:
            os.environ.pop("FACTORY_JOBS", None)
        else:
            os.environ["FACTORY_JOBS"] = previous


def build(pack_dir: str | Path, dist: Path = Path("dist")) -> dict[str, Any]:
    checks: list[Check] = []
    pack = _check(checks, "manifest", lambda: load_pack(pack_dir))
    if pack is not None:
        checks[-1].detail = f"{pack.manifest.id} {pack.manifest.version}"
        static_checks(pack, checks)
        if all(c.passed for c in checks):
            eval_checks(pack, checks)
    passed = all(c.passed for c in checks)
    report = {"pack": str(pack_dir), "passed": passed, "checks": [c.model_dump() for c in checks]}
    if pack is not None:
        m = pack.manifest
        with tenant_session(None) as db:
            db.add(PackBuild(employee_id=m.id, version=m.version, passed=passed, report=report))
        dist.mkdir(exist_ok=True)
        (dist / "employee.schema.json").write_text(json.dumps(manifest_json_schema(), indent=2))
        (dist / f"{m.id}-{m.version}.build.json").write_text(json.dumps(report, indent=2))
        (dist / f"{m.id}-{m.version}.config.schema.json").write_text(
            json.dumps({"config": pack.config_model.model_json_schema(),
                        "wizard": {k: v.model_json_schema() for k, v in pack.wizard_models.items()}}, indent=2))
    return report

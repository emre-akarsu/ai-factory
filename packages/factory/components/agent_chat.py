"""Agent chat component: a LangGraph ReAct agent over the employee's tools, with the
manifest's role prompt and model. CopilotKit's AG-UI endpoint talks to this graph.
Tools go through call_tool, so chat gets the same roles, approvals and audit."""
from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

from factory.runtime import ApprovalRequired, Ctx, NotAllowed, call_tool


def chat_model(name: str) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=name, max_tokens=4096)


def lc_tools(ctx: Ctx) -> list[StructuredTool]:
    out = []
    for spec in ctx.pack.manifest.tools:
        if ctx.role not in spec.roles:
            continue
        fn = ctx.pack.tools[spec.name]

        def run(_name=spec.name, **kwargs) -> str:
            try:
                return json.dumps(call_tool(ctx, _name, kwargs), default=str)
            except ApprovalRequired as e:
                return json.dumps({"status": "waiting_for_approval", "approval_id": str(e.approval.id),
                                   "message": str(e)})
            except NotAllowed as e:
                return json.dumps({"status": "not_allowed", "message": str(e)})
            except (ValueError, LookupError) as e:
                return json.dumps({"status": "error", "message": str(e)})

        out.append(StructuredTool.from_function(
            func=run, name=spec.name, args_schema=fn.__factory_args__,
            description=spec.description or (fn.__doc__ or spec.name).strip()))
    return out


def build_agent(ctx: Ctx, model: BaseChatModel | None = None):
    m = ctx.pack.manifest
    prompt = f"{m.role_prompt}\n\nWorkspace settings: {ctx.config.model_dump_json()}"
    return create_react_agent(model or chat_model(m.model), lc_tools(ctx), prompt=prompt)

"""The employee manifest: one typed file (employee.yaml) that the platform wires into
tools, workflows, approvals, screens, reports and a marketplace listing."""
from __future__ import annotations

import importlib
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Component(str, Enum):
    """The 15 shared marketplace components from the stack doc."""

    workspace = "workspace"
    crm = "crm"
    inbox = "inbox"
    calendar = "calendar"
    files = "files"
    knowledge = "knowledge"
    onboarding_wizard = "onboarding_wizard"
    approvals = "approvals"
    connectors = "connectors"
    workflows = "workflows"
    agent_chat = "agent_chat"
    reports = "reports"
    notifications = "notifications"
    metering = "metering"
    audit = "audit"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectorSpec(Strict):
    name: str
    scopes: list[str] = []
    purpose: str


class ApprovalRule(Strict):
    role: str = "owner"
    # Approval is needed when the tool's amount is above this config value.
    # Omit it to require approval every time.
    over_config: str | None = None


class ToolSpec(Strict):
    name: str
    entry: str  # "module:function"
    description: str | None = None
    roles: list[str] = ["owner", "manager"]
    approval: ApprovalRule | None = None


class Trigger(Strict):
    cron: str | None = None
    event: str | None = None
    match: dict[str, Any] = {}

    @model_validator(mode="after")
    def one_kind(self) -> "Trigger":
        if bool(self.cron) == bool(self.event):
            raise ValueError("a trigger needs exactly one of cron or event")
        return self


class Step(Strict):
    tool: str
    # Values may reference earlier results: "$build_order.po_ids", "$event.invoice".
    # A bare string reference spreads a dict into the tool's arguments.
    args: dict[str, Any] | str = {}
    skip_if_empty: str | None = None


class WorkflowSpec(Strict):
    title: str
    trigger: Trigger | None = None
    steps: list[Step]


class WizardStep(Strict):
    id: str
    title: str
    model: str  # "module:PydanticModel"
    apply_tool: str | None = None


class ReportSpec(Strict):
    id: str
    title: str
    sql: str  # runs under the tenant's RLS session


class NotificationRule(Strict):
    event: str
    role: str = "owner"
    channel: str = "in_app"


class Listing(Strict):
    category: str
    price_monthly_usd: int
    featured: bool = False
    highlights: list[str] = []


class EmployeeManifest(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    industry: str
    tagline: str
    description: str
    role_prompt: str
    model: str
    roles: list[str]
    uses: list[Component]
    connectors: list[ConnectorSpec] = []
    config_model: str
    data_models: str
    tools: list[ToolSpec]
    workflows: dict[str, WorkflowSpec] = {}
    wizard: list[WizardStep] = []
    reports: list[ReportSpec] = []
    notifications: list[NotificationRule] = []
    meters: list[str] = []
    suggested_prompts: list[str] = []
    evals: str | None = None
    listing: Listing

    @model_validator(mode="after")
    def references_resolve(self) -> "EmployeeManifest":
        tool_names = {t.name for t in self.tools}
        for wf_id, wf in self.workflows.items():
            for step in wf.steps:
                if step.tool not in tool_names:
                    raise ValueError(f"workflow {wf_id} uses unknown tool {step.tool}")
        for step in self.wizard:
            if step.apply_tool and step.apply_tool not in tool_names:
                raise ValueError(f"wizard step {step.id} uses unknown tool {step.apply_tool}")
        used = set(self.uses)
        needs = {
            Component.workflows: bool(self.workflows),
            Component.onboarding_wizard: bool(self.wizard),
            Component.reports: bool(self.reports),
            Component.notifications: bool(self.notifications),
            Component.metering: bool(self.meters),
            Component.connectors: bool(self.connectors),
            Component.approvals: any(t.approval for t in self.tools),
        }
        missing = [c.value for c, needed in needs.items() if needed and c not in used]
        if missing:
            raise ValueError(f"manifest configures but does not declare uses: {missing}")
        for t in self.tools:
            for r in t.roles + ([t.approval.role] if t.approval else []):
                if r not in self.roles:
                    raise ValueError(f"tool {t.name} names unknown role {r}")
        return self

    def tool(self, name: str) -> ToolSpec:
        for t in self.tools:
            if t.name == name:
                return t
        raise KeyError(name)

    @property
    def permissions(self) -> dict[str, Any]:
        """What the install consent screen shows, like a Shopify app's scopes."""
        return {
            "components": sorted(c.value for c in self.uses),
            "connectors": [c.model_dump() for c in self.connectors],
        }


def import_ref(ref: str) -> Any:
    module, _, attr = ref.partition(":")
    return getattr(importlib.import_module(module), attr) if attr else importlib.import_module(module)


def load_manifest(pack_dir: str | Path) -> EmployeeManifest:
    path = Path(pack_dir) / "employee.yaml"
    return EmployeeManifest.model_validate(yaml.safe_load(path.read_text()))


def manifest_json_schema() -> dict[str, Any]:
    """Published so editors autocomplete employee.yaml."""
    return EmployeeManifest.model_json_schema()

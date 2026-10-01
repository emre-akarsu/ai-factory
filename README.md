# AI Factory

One shared platform for AI employees. Each employee is a config pack under `employees/`;
the platform under `packages/factory/` turns its `employee.yaml` into tools, approvals,
LangGraph workflows, reports, an onboarding wizard and a marketplace listing.

First employee: **Purchasing Manager for restaurants** (`employees/restaurant_purchasing`).

## Run it

```bash
uv sync
export MIGRATE_DATABASE_URL=postgresql+psycopg://factory:factory@localhost/factory   # owner role
export DATABASE_URL=postgresql+psycopg://factory_app:factory_app@localhost/factory   # app role, RLS applies
uv run factory migrate                                   # tables, RLS, LangGraph checkpointer, job queue
uv run factory build employees/restaurant_purchasing     # validate, compile, run evals
uv run factory publish restaurant-purchasing             # only works after a passing build
uv run pytest
uv run uvicorn factory.api:app                           # API (Render web service)
FACTORY_JOBS=procrastinate uv run procrastinate --app=factory.worker.app worker   # Render worker
```

`FACTORY_DEV_AUTH=1` lets local calls use `X-User-Id`; otherwise the API expects a Supabase JWT
(`SUPABASE_JWT_SECRET`) plus `X-Tenant-Id`. `FACTORY_EMAIL_TRANSPORT=gmail` sends real email;
the default `sandbox` only records it in `outbound_messages`.

## Add an employee

1. `employees/<name>/employee.yaml` (schema in `dist/employee.schema.json` after a build)
2. `config.py` (settings + wizard steps as Pydantic models), `models.py` (tables with `TenantScoped`)
3. `tools.py`: typed functions decorated with `@tool`; roles, approvals, audit and metering are applied by the platform
4. `evals/*.yaml`: scenarios that `factory build` runs against a scratch workspace
5. An Alembic revision for the new tables (`alembic revision --autogenerate`)

## Platform components in this build

workspace, onboarding wizard, connectors (email), approvals, workflows (LangGraph + Postgres
checkpointer, cron and event triggers, Procrastinate worker), agent chat (LangGraph ReAct over the
pack's tools), reports (SQL under RLS), notifications, metering, audit, marketplace.
Not built yet: crm, inbox, calendar, files, knowledge; a pack that declares them fails `factory build`.
The Next.js + CopilotKit UI is not built yet; the API and JSON Schemas it needs are.

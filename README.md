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

## Storefront (apps/web)

Next.js 16 + Tailwind, shadcn-style components. The marketplace (`/`) and the product page
(`/employees/<id>`) render any employee from its `store.yaml` and `marketing/` folder; no page
code is per employee. Checkout goes to Stripe when the API has `STRIPE_SECRET_KEY` and
`STRIPE_WEBHOOK_SECRET` (point the webhook at `/v1/store/stripe/webhook`); without them the store
runs in sandbox mode and no card is charged. Paying creates the buyer's workspace and subscription;
a paid employee cannot be installed without one.

```bash
cd apps/web && pnpm install
FACTORY_API_URL=http://localhost:8000 pnpm dev        # http://localhost:3000
pnpm test:e2e                                         # browser test: find, try, buy
pnpm render:marketing video <html> <out.mp4> 1920 1080 30   # re-render a pack's videos
```

Marketing sources live in `employees/<pack>/marketing/source/` (HTML scenes driven by
`timeline.js`); rendered videos, the one-pager PDF, social images and launch copy sit next to them.

## Add an employee

1. `employees/<name>/employee.yaml` (schema in `dist/employee.schema.json` after a build)
2. `config.py` (settings + wizard steps as Pydantic models), `models.py` (tables with `TenantScoped`)
3. `tools.py`: typed functions decorated with `@tool`; roles, approvals, audit and metering are applied by the platform
4. `evals/*.yaml`: scenarios that `factory build` runs against a scratch workspace
5. `store.yaml` and `marketing/` for its product page
6. An Alembic revision for the new tables (`alembic revision --autogenerate`)

## Platform components in this build

workspace, onboarding wizard, connectors (email), approvals, workflows (LangGraph + Postgres
checkpointer, cron and event triggers, Procrastinate worker), agent chat (LangGraph ReAct over the
pack's tools), reports (SQL under RLS), notifications, metering, audit, marketplace, store (Stripe checkout, subscriptions).
Not built yet: crm, inbox, calendar, files, knowledge; a pack that declares them fails `factory build`.
The storefront is built; the signed-in app (CopilotKit chat, setup wizard, approvals) is not yet.

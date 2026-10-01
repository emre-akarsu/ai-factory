"""Database plumbing: one SQLAlchemy Base, a tenant_id mixin, and Row Level Security
generated for every tenant table so isolation is enforced by Postgres, not by code."""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Iterator

from sqlalchemy import DateTime, create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


class TenantScoped:
    """Mix into any table that holds customer data. RLS is added for it automatically."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)


def app_url() -> str:
    # The API and worker connect as a role that does not own the tables, so RLS applies.
    return os.environ.get("DATABASE_URL", "postgresql+psycopg://factory_app:factory_app@localhost/factory")


def owner_url() -> str:
    # Migrations run as the owner role.
    return os.environ.get("MIGRATE_DATABASE_URL", "postgresql+psycopg://factory:factory@localhost/factory")


def libpq(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def engine(url: str | None = None) -> Engine:
    return create_engine(url or app_url(), pool_pre_ping=True)


_Session = sessionmaker(expire_on_commit=False)


@event.listens_for(_Session, "after_begin")
def _set_tenant(session: Session, transaction, connection: Connection) -> None:
    tenant_id = session.info.get("tenant_id")
    # Supabase sets request.jwt.claims; the policy helper below reads either.
    connection.execute(
        text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id) if tenant_id else ""}
    )


@contextmanager
def tenant_session(tenant_id: uuid.UUID | None) -> Iterator[Session]:
    """A session whose every transaction is pinned to one tenant by RLS.
    tenant_id=None is for global tables only (tenants, marketplace)."""
    session = _Session(bind=engine())
    session.info["tenant_id"] = tenant_id
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def tenant_tables() -> list[str]:
    return sorted(t.name for t in Base.metadata.sorted_tables if "tenant_id" in t.c)


RLS_FUNCTION = """
create or replace function app_current_tenant() returns uuid language sql stable as $$
  select coalesce(
    nullif(current_setting('app.tenant_id', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')::json->>'tenant_id'
  )::uuid
$$;
"""


def apply_rls(conn: Connection, app_role: str = "factory_app") -> None:
    """The shared Alembic helper: RLS policy + grants for every TenantScoped table."""
    conn.execute(text(RLS_FUNCTION))
    for name in tenant_tables():
        conn.execute(text(f'alter table "{name}" enable row level security'))
        conn.execute(text(f'alter table "{name}" force row level security'))
        conn.execute(text(f'drop policy if exists tenant_isolation on "{name}"'))
        conn.execute(
            text(
                f'create policy tenant_isolation on "{name}" '
                "using (tenant_id = app_current_tenant()) with check (tenant_id = app_current_tenant())"
            )
        )
    conn.execute(text(f"grant select, insert, update, delete on all tables in schema public to {app_role}"))
    conn.execute(text(f"grant usage, select on all sequences in schema public to {app_role}"))
    conn.execute(text(f"grant execute on function app_current_tenant() to {app_role}"))


def ensure_app_role(conn: Connection, role: str = "factory_app", password: str = "factory_app") -> None:
    exists = conn.execute(text("select 1 from pg_roles where rolname = :r"), {"r": role}).scalar()
    if not exists:
        conn.execute(text(f"create role {role} login password '{password}' nosuperuser nobypassrls"))

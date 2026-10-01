"""Platform components and the restaurant-purchasing pack.

Revision ID: 0001
"""
from alembic import op

from factory.db import Base, apply_rls, ensure_app_role

revision = "0001"
down_revision = None


def upgrade() -> None:
    bind = op.get_bind()
    ensure_app_role(bind)
    Base.metadata.create_all(bind)
    apply_rls(bind)  # every later revision ends with this too (see script.py.mako)


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())

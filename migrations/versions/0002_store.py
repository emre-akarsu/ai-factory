"""Store: orders and subscriptions.

Revision ID: 0002
"""
from alembic import op

import factory.components.store  # noqa: F401
from factory.db import Base, apply_rls

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind, tables=[Base.metadata.tables["store_orders"], Base.metadata.tables["subscriptions"]])
    apply_rls(bind)


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("store_orders")

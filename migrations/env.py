"""Alembic runs as the owner role. Loading every pack registers its tables on Base, so
`alembic revision --autogenerate` sees platform and pack tables together."""
from alembic import context
from sqlalchemy import create_engine

from factory.db import Base, owner_url
from factory.runtime import load_all_packs

load_all_packs()
target_metadata = Base.metadata

with create_engine(owner_url()).connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from employees.restaurant_purchasing.models import Supplier
from factory.components.workspace import create_workspace
from factory.db import tenant_session


def test_rls_hides_other_workspaces():
    a = create_workspace("A", "user-a", "a@example.test")
    b = create_workspace("B", "user-b", "b@example.test")
    with tenant_session(a) as db:
        db.add(Supplier(tenant_id=a, name="Sysco", email="a@sysco.example"))
    with tenant_session(b) as db:
        assert db.scalars(select(Supplier)).all() == []
        assert db.execute(text("select count(*) from rp_suppliers where tenant_id = :a"), {"a": str(a)}).scalar() == 0
    with tenant_session(a) as db:
        assert [s.name for s in db.scalars(select(Supplier))] == ["Sysco"]


def test_rls_blocks_writes_into_another_workspace():
    a = create_workspace("A2", "user-a2", "a@example.test")
    b = create_workspace("B2", "user-b2", "b@example.test")
    with pytest.raises(ProgrammingError, match="row-level security"):
        with tenant_session(b) as db:
            db.add(Supplier(tenant_id=a, name="Sneaky", email="x@example.test"))

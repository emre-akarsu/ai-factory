"""Reports component: each report is a SQL query in the manifest, run under the
tenant's RLS session so it can only see that workspace's rows."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from factory.db import tenant_session
from factory.runtime import get_pack


def run_report(tenant_id: uuid.UUID, employee_id: str, report_id: str) -> dict[str, Any]:
    spec = next(r for r in get_pack(employee_id).manifest.reports if r.id == report_id)
    with tenant_session(tenant_id) as db:
        result = db.execute(text(spec.sql))
        cols = list(result.keys())
        rows = [dict(zip(cols, [float(v) if hasattr(v, "is_finite") else v for v in row])) for row in result]
    return {"id": spec.id, "title": spec.title, "columns": cols, "rows": rows}

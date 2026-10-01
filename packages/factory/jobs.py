"""Background jobs. FACTORY_JOBS=procrastinate puts them on the Postgres queue for the
Render worker; the default `inline` runs them in-process (tests, local dev)."""
from __future__ import annotations

import os
from typing import Any

_deferrer = None


def queued() -> bool:
    return os.environ.get("FACTORY_JOBS", "inline") == "procrastinate"


def defer(task: str, **kwargs: Any) -> None:
    if queued():
        import procrastinate

        from factory.db import app_url, libpq

        global _deferrer
        if _deferrer is None:  # a defer-only app with a sync connector, usable in the API and inside worker jobs
            _deferrer = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=libpq(app_url())))
            _deferrer.open()
        _deferrer.configure_task(f"factory.{task}").defer(**kwargs)
        return
    from factory import worker

    getattr(worker, task).func(**kwargs)

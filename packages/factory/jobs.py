"""Background jobs. FACTORY_JOBS=procrastinate puts them on the Postgres queue for the
Render worker; the default `inline` runs them in-process (tests, local dev)."""
from __future__ import annotations

import os
from typing import Any

_opened = False


def defer(task: str, **kwargs: Any) -> None:
    if os.environ.get("FACTORY_JOBS", "inline") == "procrastinate":
        from factory.worker import app

        global _opened
        if not _opened:  # the API process keeps one open connector for deferring
            app.open()
            _opened = True
        app.configure_task(f"factory.{task}").defer(**kwargs)
        return
    from factory import worker

    getattr(worker, task).func(**kwargs)

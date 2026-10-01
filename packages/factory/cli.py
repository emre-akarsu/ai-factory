"""factory migrate | build <pack_dir> | publish <employee_id> | catalog"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factory")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply migrations, RLS, workflow checkpointer and job queue schema")
    b = sub.add_parser("build", help="validate, compile and eval a pack")
    b.add_argument("pack_dir")
    pub = sub.add_parser("publish", help="list a pack with a passing build in the marketplace")
    pub.add_argument("employee_id")
    sub.add_parser("catalog", help="print the marketplace")
    args = p.parse_args(argv)

    if args.cmd == "migrate":
        from alembic import command
        from alembic.config import Config

        from factory.components.workflows import setup_checkpointer
        from factory.db import apply_rls, owner_url
        from sqlalchemy import create_engine

        command.upgrade(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")), "head")
        setup_checkpointer()
        with create_engine(owner_url()).begin() as conn:
            apply_rls(conn)  # grants on the checkpointer tables too
        _procrastinate_schema()
        print("migrated")
    elif args.cmd == "build":
        from factory.build import build

        report = build(args.pack_dir)
        for c in report["checks"]:
            print(f"{'PASS' if c['passed'] else 'FAIL'}  {c['name']}  {c['detail'].splitlines()[0] if c['detail'] else ''}")
            if not c["passed"] and c["detail"]:
                print("      " + c["detail"].replace("\n", "\n      "))
        print("BUILD PASSED" if report["passed"] else "BUILD FAILED")
        return 0 if report["passed"] else 1
    elif args.cmd == "publish":
        from factory.components.marketplace import publish

        listing = publish(args.employee_id)
        print(f"published {listing.employee_id} {listing.version} as marketplace listing #{listing.rank}")
    elif args.cmd == "catalog":
        from factory.components.marketplace import catalog

        json.dump([{k: v for k, v in l.items() if k not in ("config_schema", "wizard")} for l in catalog()],
                  sys.stdout, indent=2)
        print()
    return 0


def _procrastinate_schema() -> None:
    import psycopg

    from factory.db import libpq, owner_url

    with psycopg.connect(libpq(owner_url()), autocommit=True) as conn:
        if conn.execute("select to_regclass('procrastinate_jobs')").fetchone()[0] is None:
            from procrastinate import App, PsycopgConnector

            app = App(connector=PsycopgConnector(conninfo=libpq(owner_url())))
            with app.open():
                app.schema_manager.apply_schema()
        conn.execute("grant all on all tables in schema public to factory_app")
        conn.execute("grant all on all sequences in schema public to factory_app")
        conn.execute("grant execute on all functions in schema public to factory_app")


if __name__ == "__main__":
    raise SystemExit(main())

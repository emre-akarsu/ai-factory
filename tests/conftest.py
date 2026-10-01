import os

os.environ.setdefault("FACTORY_DEV_AUTH", "1")
os.environ["FACTORY_JOBS"] = "inline"

import pytest  # noqa: E402

from factory.runtime import load_all_packs  # noqa: E402

PACK = "employees/restaurant_purchasing"


@pytest.fixture(scope="session", autouse=True)
def platform():
    """Migrate, build and publish once: the same path a release takes."""
    from factory.build import build
    from factory.cli import main
    from factory.components.marketplace import publish

    assert main(["migrate"]) == 0
    load_all_packs()
    report = build(PACK)
    assert report["passed"], report
    publish("restaurant-purchasing")

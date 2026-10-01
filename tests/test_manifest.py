import copy

import pytest
import yaml
from pydantic import ValidationError

from factory.manifest import EmployeeManifest

BASE = yaml.safe_load(open("employees/restaurant_purchasing/employee.yaml"))


def test_pack_manifest_is_valid():
    m = EmployeeManifest.model_validate(BASE)
    assert m.permissions["connectors"][0]["name"] == "email"


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["workflows"]["reorder"]["steps"].append({"tool": "wire_money"}), "unknown tool wire_money"),
    (lambda d: d["uses"].remove("approvals"), "does not declare uses"),
    (lambda d: d["tools"][0].update(roles=["chef"]), "unknown role chef"),
    (lambda d: d.update(surprise=1), "Extra inputs"),
    (lambda d: d["workflows"]["reorder"].update(trigger={}), "exactly one of cron or event"),
])
def test_bad_manifests_are_rejected(mutate, message):
    d = copy.deepcopy(BASE)
    mutate(d)
    with pytest.raises(ValidationError, match=message):
        EmployeeManifest.model_validate(d)

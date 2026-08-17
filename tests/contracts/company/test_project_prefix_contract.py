"""Project display-prefix contract evidence for ticket display keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
_PROJECT_SCHEMA = ROOT / "contracts/components/project.schema.json"
_PROJECT_PACKS = ROOT / "packs/components/projects"
_APPROVED_PREFIXES = {"CTW", "MNB", "BHL"}


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def test_project_component_requires_a_unique_uppercase_display_prefix() -> None:
    schema = _load(_PROJECT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    required = cast(list[str], schema["required"])
    properties = cast(dict[str, object], schema["properties"])
    assert "prefix" in required
    assert cast(dict[str, object], properties["prefix"])["pattern"] == "^[A-Z]{2,5}$"

    prefixes: list[str] = []
    for path in sorted(_PROJECT_PACKS.glob("*/v1.yaml")):
        payload = cast(dict[str, object], YAML(typ="safe", pure=True).load(path.read_text()))
        prefixes.append(cast(str, payload["prefix"]))
        assert payload["prefix"] in _APPROVED_PREFIXES
    assert len(prefixes) == len(set(prefixes))
    assert set(prefixes) == _APPROVED_PREFIXES


def test_project_prefix_contract_admits_only_two_to_five_uppercase_letters() -> None:
    """The authored contract alone decides the prefix alphabet; refusal rules live in Catalog.

    The CompanyBundle refusals for duplicate and reserved prefixes are proven against the
    real validator in `tests/modules/catalog/test_policy.py`.
    """

    validator = Draft202012Validator(_load(_PROJECT_SCHEMA))
    base = {
        "schema": "ctower.project/v1",
        "key": "example.project",
        "display_name": "Example",
        "repository_ref": "repository:github/example/project",
        "goal_refs": ["company.goal@1"],
        "prefix": "CTW",
    }
    assert not list(validator.iter_errors(base))
    for refused in ("ctw", "R", "CTOWER", "CT-1", "", "C1W"):
        assert list(validator.iter_errors({**base, "prefix": refused})), refused
    assert list(
        validator.iter_errors({key: value for key, value in base.items() if key != "prefix"})
    )

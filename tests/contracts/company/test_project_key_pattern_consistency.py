"""Contract consistency: the authored project key pattern equals the consumer pattern (T-020).

`getBoard` and every other consumer refuse dotted project keys with 422 while the authored
`ctower.project/v1` schema admitted them — authoring accepted an identifier the system
cannot serve. This test pins the authored pattern to the consumer pattern so the two sides
cannot drift again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ruamel.yaml import YAML

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
_PROJECT_SCHEMA = ROOT / "contracts/components/project.schema.json"
_OPENAPI = ROOT / "contracts/http/openapi.yaml"
_BUNDLE = ROOT / "company/company.bundle.yaml"
_CONSUMER_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
_EXPECTED_PROJECT_RESOURCES = 3


def _project_key_pattern() -> str:
    schema = cast(dict[str, object], json.loads(_PROJECT_SCHEMA.read_text(encoding="utf-8")))
    properties = cast(dict[str, object], schema["properties"])
    key = cast(dict[str, object], properties["key"])
    return cast(str, key["pattern"])


def _openapi_project_query_pattern() -> str:
    spec = cast(
        dict[str, object], YAML(typ="safe", pure=True).load(_OPENAPI.read_text(encoding="utf-8"))
    )
    components = cast(dict[str, object], spec["components"])
    parameters = cast(dict[str, object], components["parameters"])
    project_query = cast(dict[str, object], parameters["ProjectQuery"])
    schema = cast(dict[str, object], project_query["schema"])
    return cast(str, schema["pattern"])


def test_authored_project_key_pattern_equals_the_consumer_pattern() -> None:
    assert _project_key_pattern() == _CONSUMER_PATTERN


def test_authored_project_key_pattern_matches_openapi_project_query() -> None:
    assert _project_key_pattern() == _openapi_project_query_pattern()


def test_every_bundle_project_payload_and_component_key_satisfies_the_consumer_pattern() -> None:
    bundle = YAML(typ="safe", pure=True).load(_BUNDLE.read_text(encoding="utf-8"))
    project_resources = [
        resource for resource in bundle["resources"] if resource["component"]["kind"] == "project"
    ]
    assert len(project_resources) == _EXPECTED_PROJECT_RESOURCES

    offenders = sorted(
        f"{resource['component']['key']}"
        for resource in project_resources
        if "." in resource["component"]["key"] or "." in resource["payload"]["key"]
    )
    assert offenders == [], (
        "dotted project keys are legal to author but getBoard refuses them (T-020): "
        + ", ".join(offenders)
    )


def test_no_pack_project_directory_or_manifest_entry_carries_a_dotted_project_key() -> None:
    packs = ROOT / "packs/components/projects"
    dotted_dirs = sorted(path.name for path in packs.iterdir() if "." in path.name)
    assert dotted_dirs == []

    manifest = YAML(typ="safe", pure=True).load(
        (ROOT / "packs/manifests/core-v1.yaml").read_text(encoding="utf-8")
    )
    dotted_entries = sorted(
        entry["key"]
        for entry in manifest["components"]
        if entry["kind"] == "project" and "." in entry["key"]
    )
    assert dotted_entries == []

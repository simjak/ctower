from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).parents[3]
COMPONENTS = ROOT / "contracts/components"
_MINIMAL_RESOURCE_COUNT = 18
_PAYLOAD_FILES = {
    "ctower.agent-profile/v1": "agent-profile.schema.json",
    "ctower.capability/v1": "capability.schema.json",
    "ctower.environment/v1": "environment.schema.json",
    "ctower.goal/v1": "goal.schema.json",
    "ctower.harness/v1": "harness.schema.json",
    "ctower.image/v1": "image.schema.json",
    "ctower.integration/v1": "integration.schema.json",
    "ctower.notification/v1": "notification.schema.json",
    "ctower.persona/v1": "persona.schema.json",
    "ctower.project/v1": "project.schema.json",
    "ctower.skill/v1": "skill.schema.json",
    "ctower.supervisor/v1": "supervisor.schema.json",
    "ctower.target/v1": "target.schema.json",
    "ctower.telemetry/v1": "telemetry.schema.json",
    "ctower.tool/v1": "tool.schema.json",
    "ctower.workspace/v1": "workspace.schema.json",
}
_KINDS = {
    "adapter",
    "agent_profile",
    "cadence_policy",
    "capability",
    "environment",
    "evidence_policy",
    "execution_policy",
    "extension",
    "gate_policy",
    "goal",
    "harness",
    "image",
    "integration",
    "notification",
    "persona",
    "placement_policy",
    "project",
    "skill",
    "supervisor",
    "target",
    "telemetry",
    "tool",
    "workflow",
    "workspace",
}


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _validator() -> Draft202012Validator:
    bundle = _load(ROOT / "contracts/company/company-bundle.schema.json")
    component = _load(COMPONENTS / "versioned-component.schema.json")
    resource = Resource.from_contents(component)
    registry = Registry().with_resource(cast(str, component["$id"]), resource)
    return Draft202012Validator(bundle, registry=registry)


def _bundle() -> dict[str, object]:
    digest = "sha256:" + "1" * 64
    return {
        "schema": "ctower.company-bundle/v1",
        "company": {"key": "example-company", "display_name": "Example Company"},
        "resources": [
            {
                "component": {
                    "schema": "ctower.versioned-component/v1",
                    "kind": "goal",
                    "key": "company.goal",
                    "scope": {"tenant": "example-company", "project": None},
                    "revision": 1,
                    "content_digest": digest,
                    "schema_ref": "ctower.goal/v1",
                    "lifecycle": "published",
                    "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
                    "provenance": [
                        {
                            "kind": "authored",
                            "source": "company/company.bundle.yaml",
                            "digest": digest,
                        }
                    ],
                    "payload_ref": "object:" + digest,
                },
                "payload": {
                    "schema": "ctower.goal/v1",
                    "key": "company.goal",
                    "display_name": "Company goal",
                    "outcome": "Protected work is attributable.",
                    "success_criteria": ["One exact bundle is active."],
                },
            }
        ],
        "assignments": [],
        "secret_binding_refs": [
            {"name": "SOURCE_CONTROL_TOKEN", "reference_class": "runtime-binding"}
        ],
    }


def test_portable_bundle_envelope_is_closed_and_resource_bearing() -> None:
    validator = _validator()
    bundle = _bundle()

    assert not list(validator.iter_errors(bundle))
    legacy = {**bundle, "component_refs": []}
    assert list(validator.iter_errors(legacy))
    secret = {**bundle, "secret_binding_refs": [{"name": "TOKEN", "value": "forbidden"}]}
    assert list(validator.iter_errors(secret))


def test_universal_component_kind_inventory_is_exact() -> None:
    schema = _load(COMPONENTS / "versioned-component.schema.json")
    properties = cast(dict[str, object], schema["properties"])
    kind = cast(dict[str, object], properties["kind"])

    assert set(cast(list[str], kind["enum"])) == _KINDS


def test_minimal_bundle_is_portable_strict_and_content_addressed() -> None:
    bundle = cast(
        dict[str, object],
        yaml.safe_load((ROOT / "company/company.bundle.yaml").read_text(encoding="utf-8")),
    )
    resources = cast(list[dict[str, object]], bundle["resources"])
    schema_paths = _schema_paths()

    assert not list(_validator().iter_errors(bundle))
    assert len(resources) == _MINIMAL_RESOURCE_COUNT
    assert {cast(dict[str, object], resource["component"])["kind"] for resource in resources} >= {
        "agent_profile",
        "environment",
        "evidence_policy",
        "execution_policy",
        "gate_policy",
        "goal",
        "harness",
        "image",
        "project",
        "supervisor",
        "target",
        "telemetry",
        "workflow",
        "workspace",
    }
    for resource in resources:
        component = cast(dict[str, object], resource["component"])
        payload = cast(dict[str, object], resource["payload"])
        canonical = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        provenance = cast(list[dict[str, object]], component["provenance"])
        source = ROOT / cast(str, provenance[0]["source"])

        assert component["content_digest"] == digest
        assert component["payload_ref"] == "object:" + digest
        assert provenance[0]["digest"] == digest
        assert json.loads(source.read_text(encoding="utf-8")) == payload
        schema = _load(schema_paths[cast(str, component["schema_ref"])])
        assert not list(Draft202012Validator(schema).iter_errors(payload))


@pytest.mark.parametrize(("schema_id", "filename"), sorted(_PAYLOAD_FILES.items()))
def test_payload_contract_is_strict_and_schema_identified(schema_id: str, filename: str) -> None:
    schema = _load(COMPONENTS / filename)
    properties = cast(dict[str, object], schema["properties"])
    schema_field = cast(dict[str, object], properties["schema"])

    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema_field["const"] == schema_id


def _schema_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for path in (ROOT / "contracts").rglob("*.schema.json"):
        schema = _load(path)
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        schema_property = properties.get("schema")
        if isinstance(schema_property, dict) and isinstance(schema_property.get("const"), str):
            paths[cast(str, schema_property["const"])] = path
    return paths

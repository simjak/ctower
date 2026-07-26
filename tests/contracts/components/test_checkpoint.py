"""Generic checkpoint components publish the frozen ctower hierarchy atomically."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
import rfc8785
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
COMPONENTS = ROOT / "contracts/components"
COMPANY_SCHEMA = ROOT / "contracts/company/company-bundle.schema.json"
VECTOR_PATH = ROOT / "contracts/domain/project-delivery/project-delivery-vectors.json"
EXPECTED_CHECKPOINT_COUNT = 14


def _checkpoint(checkpoint_key: str) -> dict[str, object]:
    key = checkpoint_key.casefold().replace(".", "-")
    criteria = [
        {
            "key": "declared-outcome",
            "description": f"Current proof establishes {checkpoint_key} outcome",
            "required": True,
            "evidence_policy_refs": [],
        }
    ]
    if checkpoint_key == "I1.7":
        vectors = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
        criteria = [
            {
                "key": criterion,
                "description": f"Current proof for {criterion}",
                "required": True,
                "evidence_policy_refs": [],
            }
            for criterion in vectors["i1_7_criteria"]
        ]
    return {
        "schema": "ctower.checkpoint/v1",
        "key": f"ctower.{key}",
        "checkpoint_key": checkpoint_key,
        "display_name": f"ctower checkpoint {checkpoint_key}",
        "outcome": f"ctower establishes the declared {checkpoint_key} outcome",
        "accountable_owner": "ctower-operator",
        "criteria": criteria,
        "dependency_refs": [],
    }


def _resource(payload: dict[str, object]) -> dict[str, object]:
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(cast(Any, payload))).hexdigest()
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": "checkpoint",
            "key": payload["key"],
            "scope": {"tenant": "ctower", "project": "ctower"},
            "revision": 1,
            "content_digest": digest,
            "schema_ref": "ctower.checkpoint/v1",
            "lifecycle": "published",
            "compatibility": {"ctower": "development", "requires": []},
            "provenance": [
                {
                    "kind": "reviewed-contract",
                    "source": "SPEC#project-delivery-projection",
                    "digest": digest,
                }
            ],
            "payload_ref": f"object:{digest}",
        },
        "payload": payload,
    }


def test_generic_checkpoint_schema_is_strict_and_has_no_status_field() -> None:
    validator = _checkpoint_validator()
    payload = _checkpoint("I1.7")

    validator.validate(payload)
    criteria = cast(list[dict[str, object]], payload["criteria"])
    assert [item["key"] for item in criteria] == [
        "source-conservation",
        "development-single-writer",
        "api-cli-dogfood",
        "project-delivery-rebuild",
        "i1-evidence-archive",
        "disaster-safe-authority",
    ]
    with pytest.raises(ValidationError):
        validator.validate({**payload, "status": "done"})
    with pytest.raises(ValidationError):
        validator.validate({**payload, "checkpoint_key": "ctower-I1.7"})


def test_one_company_bundle_can_publish_all_14_checkpoint_components() -> None:
    vectors = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    resources = [_resource(_checkpoint(key)) for key in vectors["checkpoint_keys"]]
    bundle = {
        "schema": "ctower.company-bundle/v1",
        "company": {"key": "ctower", "display_name": "ctower"},
        "resources": resources,
        "assignments": [],
        "secret_binding_refs": [],
    }

    _company_validator().validate(bundle)
    for resource in resources:
        _checkpoint_validator().validate(resource["payload"])
    components = cast(
        list[dict[str, object]],
        [resource["component"] for resource in resources],
    )
    assert len(components) == EXPECTED_CHECKPOINT_COUNT
    assert len({item["key"] for item in components}) == EXPECTED_CHECKPOINT_COUNT
    assert {item["kind"] for item in components} == {"checkpoint"}
    assert all(item["scope"] == {"tenant": "ctower", "project": "ctower"} for item in components)


def test_checkpoint_publication_vector_rejects_partial_or_duplicate_sets() -> None:
    expected = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))["checkpoint_keys"]

    assert _is_atomic_checkpoint_set(expected)
    assert not _is_atomic_checkpoint_set(expected[:-1])
    assert not _is_atomic_checkpoint_set([*expected[:-1], expected[0]])


def _is_atomic_checkpoint_set(keys: list[str]) -> bool:
    expected = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))["checkpoint_keys"]
    return keys == expected and len(keys) == len(set(keys))


def _checkpoint_validator() -> Draft202012Validator:
    schema = json.loads((COMPONENTS / "checkpoint.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _company_validator() -> Draft202012Validator:
    company = json.loads(COMPANY_SCHEMA.read_text(encoding="utf-8"))
    versioned = json.loads(
        (COMPONENTS / "versioned-component.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resources(
        [
            (company["$id"], Resource.from_contents(company)),
            (versioned["$id"], Resource.from_contents(versioned)),
        ]
    )
    return Draft202012Validator(company, registry=registry)

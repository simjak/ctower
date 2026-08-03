"""Generic checkpoint components accept configured cross-domain hierarchies."""

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


def _checkpoint(
    checkpoint_key: str,
    *,
    reference: str,
) -> dict[str, object]:
    return {
        "schema": "ctower.checkpoint/v1",
        "key": reference,
        "checkpoint_key": checkpoint_key,
        "display_name": f"Configured checkpoint {checkpoint_key}",
        "outcome": f"The declared {checkpoint_key} outcome is established",
        "accountable_owner": "controller",
        "criteria": [
            {
                "key": "declared-outcome",
                "description": f"Current proof establishes {checkpoint_key} outcome",
                "required": True,
                "evidence_policy_refs": [],
            }
        ],
        "dependency_refs": [],
    }


def _resource(payload: dict[str, object]) -> dict[str, object]:
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(cast(Any, payload))).hexdigest()
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": "checkpoint",
            "key": payload["key"],
            "scope": {"tenant": "ledger-co", "project": "quarterly-close"},
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


def test_generic_checkpoint_schema_accepts_configured_keys_without_status() -> None:
    validator = _checkpoint_validator()
    payload = _checkpoint("Q3-close.2", reference="ledger.q3-close.2")

    validator.validate(payload)
    validator.validate(_checkpoint("audit-ready", reference="ledger.audit-ready"))
    with pytest.raises(ValidationError):
        validator.validate({**payload, "status": "done"})
    for invalid in ("", "quarter close", "quarter/close", "-quarter-close"):
        with pytest.raises(ValidationError):
            validator.validate({**payload, "checkpoint_key": invalid})


def test_checkpoint_slot_can_pin_proof_link_and_assigned_seat_catalog_revision() -> None:
    validator = _checkpoint_validator()
    payload = _checkpoint("Q3-close.2", reference="ledger.q3-close.2")
    criterion = cast(list[dict[str, object]], payload["criteria"])[0]
    criterion["proof_link"] = {
        "ticket_id": "019fae21-910f-7b58-a7c8-13322b2ae81c",
        "criterion_key": "ledger-posted",
    }
    criterion["assigned_seat"] = {
        "seat_key": "reviewer-a",
        "catalog_key": "ledger.delivery-seats",
        "catalog_revision": 4,
        "catalog_digest": "sha256:" + "a" * 64,
    }

    validator.validate(payload)
    with pytest.raises(ValidationError):
        validator.validate(
            {
                **payload,
                "criteria": [{**criterion, "proof_link": {"criterion_key": "ledger-posted"}}],
            }
        )


def test_non_ctower_company_bundle_publishes_configured_checkpoints() -> None:
    resources = [
        _resource(_checkpoint("Q3-close.2", reference="ledger.q3-close.2")),
        _resource(_checkpoint("audit-ready", reference="ledger.audit-ready")),
    ]
    bundle = {
        "schema": "ctower.company-bundle/v1",
        "company": {"key": "ledger-co", "display_name": "Ledger Company"},
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
    assert {item["key"] for item in components} == {
        "ledger.q3-close.2",
        "ledger.audit-ready",
    }
    assert {item["kind"] for item in components} == {"checkpoint"}
    assert all(
        item["scope"] == {"tenant": "ledger-co", "project": "quarterly-close"}
        for item in components
    )


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

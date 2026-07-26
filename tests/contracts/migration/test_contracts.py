"""Strict I1.7B migration schemas reject drift and preserve development truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
CONTRACTS = ROOT / "contracts/domain/migration"
VECTOR = json.loads((CONTRACTS / "migration-vectors.json").read_text(encoding="utf-8"))
ZERO_DIGEST = "sha256:" + ("0" * 64)
FORBIDDEN_CLASSES = [
    "non_ctower_scope",
    "bulk_crew_log",
    "raw_session_or_transcript",
    "prompt_or_model_context",
    "secret_or_authentication_value",
    "pii_or_client_data",
    "accounting_payment_tax_invoice",
    "production_approval_effect_or_incident",
    "large_binary",
    "irreplaceable_or_expensive_sole_copy",
    "derived_board_markdown",
    "unreferenced_coordination",
]


def _review() -> dict[str, object]:
    return {
        "reviewer_principal_id": str(uuid4()),
        "reviewed_at": "2026-07-25T12:00:00Z",
        "decision": "approved",
    }


def _signature() -> dict[str, object]:
    fixture = VECTOR["canonical_signature"]
    return {
        "algorithm": "Ed25519",
        "signed_digest": fixture["signed_digest"],
        "key_ref": "signing-key-ref:synthetic/i1-7b",
        "key_version": 1,
        "public_key_digest": fixture["public_key_digest"],
        "signature": fixture["signature"],
    }


def _source_identity() -> dict[str, object]:
    return {
        "namespace": "mission-control:request",
        "immutable_source_id": "R325",
        "source_version": "line:1",
        "source_digest": ZERO_DIGEST,
    }


def _source_inventories() -> list[dict[str, object]]:
    keys = (
        "mission_control_requests",
        "mission_control_tasks",
        "mission_control_project",
        "mission_control_decisions",
        "mission_control_coordination",
        "git_ctower",
        "github_ctower",
        "ctower_target",
    )
    return [
        {
            "source_key": key,
            "authority_class": (
                "target_inventory" if key == "ctower_target" else "migration_provenance"
            ),
            "path": None if key in {"github_ctower", "ctower_target"} else f"source/{key}.jsonl",
            "whole_source_digest": ZERO_DIGEST,
            "whole_source_bytes": 0,
            "whole_source_rows": 0,
            "selected_logical_items": 0,
            "selected_physical_items": 0,
            "expected_zero": key in {"mission_control_tasks", "ctower_target"},
            "watermark": "sealed:synthetic",
        }
        for key in keys
    ]


def _selection_payload() -> dict[str, object]:
    source = VECTOR["sealed_source"]
    return {
        "schema": "ctower.ctower-project-source-selection/v1",
        "selection_id": str(uuid4()),
        "revision": 1,
        "cutover_scope": {
            "tenant_key": "ctower",
            "company_key": "ctower",
            "project_key": "ctower",
            "repository": "github.com/simjak/ctower",
        },
        "canonicalization": "RFC8785",
        "created_at": "2026-07-25T12:00:00Z",
        "stable_item_ids": source["stable_ticket_ids"],
        "checkpoint_keys": source["checkpoint_keys"],
        "selected_request_ids": source["mission_control_request_ids"],
        "selected_task_ids": [],
        "explicit_exclusions": [
            {"source_id": "R546", "reason_code": "reviewed_false_positive"},
            {"source_id": "R669+", "reason_code": "outside_signed_baseline"},
        ],
        "source_inventories": _source_inventories(),
        "forbidden_classes": FORBIDDEN_CLASSES,
        "review": _review(),
        "manifest_digest": ZERO_DIGEST,
        "signature": _signature(),
    }


def _health_base() -> dict[str, object]:
    return {
        "schema": "ctower.ctower-project-cutover-health/v1",
        "cutover_id": None,
        "authority_mode": "legacy_writable",
        "phase": "not_started",
        "writes_enabled": False,
        "durability_claim": "CP3_D_NOT_PROVEN",
        "recovery_claim": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
        "data_class": "RECONSTRUCTIBLE_ONLY",
        "legacy_writer_fence": "not_armed",
        "split_brain": "clear",
        "projection_completeness": "current",
        "source_watermark": 0,
        "projection_watermark": 0,
        "import_run_id": None,
        "migration_digests": {
            "source_selection": None,
            "export_equality": None,
            "alias_map": None,
            "reconciliation": None,
            "fence_registry": None,
            "fence_observation": None,
        },
        "banner": "DEVELOPMENT DOGFOOD — not disaster-safe",
    }


def test_every_migration_schema_is_valid_and_closes_every_object_shape() -> None:
    for path in sorted(CONTRACTS.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        for node in _objects(schema):
            assert node.get("additionalProperties") is False, path.name


def test_cutover_health_preserves_degraded_truth_and_fail_closed_fence() -> None:
    validator = _validator("ctower-project-cutover-health.schema.json")
    base = _health_base()
    validator.validate(base)
    validator.validate(
        {
            **base,
            "cutover_id": str(uuid4()),
            "authority_mode": "development_single_writer",
            "phase": "development_epoch_committed",
            "writes_enabled": True,
            "legacy_writer_fence": "enforced",
        }
    )
    contradictions = (
        {**base, "phase": "reconciled", "writes_enabled": True},
        {**base, "durability_claim": "CP3_D_PROVEN"},
        {
            **base,
            "split_brain": "unknown",
            "projection_completeness": "current",
        },
        {**base, "unexpected": "green"},
    )
    for payload in contradictions:
        with pytest.raises(ValidationError):
            validator.validate(payload)


def test_source_selection_freezes_exact_scope_counts_and_safe_paths() -> None:
    validator = _validator("ctower-project-source-selection.schema.json")
    source = VECTOR["sealed_source"]
    inventories = _source_inventories()
    payload = _selection_payload()
    scope = dict(cast(dict[str, object], payload["cutover_scope"]))
    validator.validate(payload)
    invalid = (
        {**payload, "cutover_scope": {**scope, "project_key": "other"}},
        {**payload, "selected_task_ids": ["T1"]},
        {**payload, "selected_request_ids": source["mission_control_request_ids"][:-1]},
        {
            **payload,
            "source_inventories": [
                {**inventories[0], "path": "../private/source"},
                *inventories[1:],
            ],
        },
    )
    for candidate in invalid:
        with pytest.raises(ValidationError):
            validator.validate(candidate)


def test_import_batch_is_a_closed_64_item_union_without_proof_authority() -> None:
    validator = _validator("ctower-project-import-batch.schema.json")
    identity = {
        "namespace": "mission-control:request",
        "immutable_source_id": "R325",
        "source_version_or_digest": "line:1",
        "operation_kind": "ticket_seed",
        "planned_target_ref": "new_ticket",
        "command_id": str(uuid4()),
    }
    seed = {
        "operation": "ticket_seed",
        "identity": identity,
        "project_key": "ctower",
        "priority": "P2",
        "title": "Synthetic red vector",
        "source": _source_identity(),
        "initial_commander_custodian_id": str(uuid4()),
    }
    payload = {
        "schema": "ctower.ctower-project-import-batch/v1",
        "run_id": str(uuid4()),
        "cutover_id": str(uuid4()),
        "batch_index": 0,
        "batch_digest": ZERO_DIGEST,
        "operations": [seed],
    }
    validator.validate(payload)
    invalid_operations = (
        {**seed, "priority": "P0"},
        {**seed, "project_key": "other"},
        {**seed, "proof": {"verdict": "passed"}},
        {**seed, "operation": "workflow_transition"},
    )
    for operation in invalid_operations:
        with pytest.raises(ValidationError):
            validator.validate({**payload, "operations": [operation]})
    with pytest.raises(ValidationError):
        validator.validate({**payload, "operations": [seed] * 65})


def test_corrections_are_append_only_and_scope_bound() -> None:
    correction = {
        "schema": "ctower.ctower-project-import-correction/v1",
        "correction_id": str(uuid4()),
        "run_id": str(uuid4()),
        "cutover_id": str(uuid4()),
        "tenant_key": "ctower",
        "project_key": "ctower",
        "correction_kind": "alias",
        "superseded_revision": {"object_id": str(uuid4()), "revision": 1},
        "expected_current_digest": ZERO_DIGEST,
        "replacement": {
            "kind": "alias",
            "identity": _source_identity(),
            "target_ticket_id": str(uuid4()),
            "disposition": "alias_linked_existing",
        },
        "reason": "Correct reviewed target",
        "reviewer": _review(),
        "operator_id": str(uuid4()),
    }
    _validator("ctower-project-import-correction.schema.json").validate(correction)
    with pytest.raises(ValidationError):
        _validator("ctower-project-import-correction.schema.json").validate(
            {**correction, "project_key": "other"}
        )


def test_fence_observations_can_degrade_but_never_enable_writes() -> None:
    observation = {
        "schema": "ctower.ctower-project-fence-observation/v1",
        "observation_id": str(uuid4()),
        "run_id": str(uuid4()),
        "cutover_id": str(uuid4()),
        "tenant_key": "ctower",
        "project_key": "ctower",
        "registry_id": str(uuid4()),
        "registry_revision": 1,
        "registry_digest": ZERO_DIGEST,
        "sequence": 1,
        "previous_observation_digest": None,
        "observed_at": "2026-07-25T12:00:00Z",
        "from_offset": 0,
        "to_offset": 0,
        "file_identity": {"device": 1, "inode": 1, "scoped_rows_digest": ZERO_DIGEST},
        "status": "unknown",
        "reason_code": "classifier_unknown",
        "observation_digest": ZERO_DIGEST,
        "disables_writes": True,
        "may_enable_writes": False,
    }
    fence = _validator("ctower-project-fence-observation.schema.json")
    fence.validate(observation)
    with pytest.raises(ValidationError):
        fence.validate({**observation, "disables_writes": False})
    with pytest.raises(ValidationError):
        fence.validate({**observation, "may_enable_writes": True})


def _validator(name: str) -> Draft202012Validator:
    schemas = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CONTRACTS.glob("*.schema.json"))
    ]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema = next(item for item in schemas if item["$id"].endswith(f"/{name}"))
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def _objects(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [node for item in value for node in _objects(item)]
    if not isinstance(value, dict):
        return []
    nested = [node for item in value.values() for node in _objects(item)]
    return ([value] if value.get("type") == "object" else []) + nested

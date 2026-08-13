"""Closed authored contracts for the Request-maintenance proposal queue."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()

_OPERATIONS = {
    "appendRequestMaintenanceProposal",
    "confirmRequestMaintenanceProposal",
    "getRequestMaintenanceReview",
    "listRequestMaintenanceProposals",
    "rejectRequestMaintenanceProposal",
}
_SCHEMAS = {
    "append.schema.json",
    "decision.schema.json",
    "evidence.schema.json",
    "list.schema.json",
    "proposal.schema.json",
    "review.schema.json",
    "summary.schema.json",
}


def test_request_proposal_contracts_are_authored_and_strict() -> None:
    contract_root = ROOT / "contracts/domain/request-proposals"

    assert {path.name for path in contract_root.glob("*.json")} == _SCHEMAS
    for path in contract_root.glob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_append_contract_accepts_exact_vectors_and_refuses_omission_tamper_and_extras() -> None:
    validator = _validator("append.schema.json")
    valid = _append_vector()
    validator.validate(valid)
    duplicate = {
        **valid,
        "basis": "similarity",
        "kind": "duplicate",
        "related_expected_version": 1,
        "related_request_id": "00000000-0000-7000-8000-000000000003",
        "related_text": "Second exact Request.",
    }
    validator.validate(duplicate)

    invalid = []
    for missing in ("evidence", "source_record_position", "target_text"):
        payload = deepcopy(valid)
        payload.pop(missing)
        invalid.append(payload)
    invalid.extend(
        (
            {**valid, "unexpected": True},
            {**valid, "related_request_id": "00000000-0000-7000-8000-000000000003"},
            {**duplicate, "kind": "supersession"},
        )
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            validator.validate(payload)


def test_evidence_and_proposal_rows_are_closed_exact_shapes() -> None:
    evidence = _event_evidence()
    _validator("evidence.schema.json").validate(evidence)
    hybrid = {
        **evidence,
        "artifact_digest": "sha256:" + "b" * 64,
        "evidence_id": "00000000-0000-7000-8000-000000000010",
        "proof_id": "00000000-0000-7000-8000-000000000011",
        "ticket_id": "00000000-0000-7000-8000-000000000012",
    }
    with pytest.raises(ValidationError):
        _validator("evidence.schema.json").validate(hybrid)

    proposal = {
        "ambiguity_reason": None,
        "basis": "recorded-evidence",
        "created_at": "2026-08-13T06:00:00+00:00",
        "decision": None,
        "evidence": [evidence],
        "kind": "keep",
        "project_key": "ctower",
        "proposal_id": "00000000-0000-7000-8000-000000000020",
        "proposal_version": 1,
        "proposer_principal_id": "00000000-0000-7000-8000-000000000021",
        "related_expected_version": None,
        "related_request_id": None,
        "related_text": None,
        "seat_credential_id": None,
        "source_record_position": 12,
        "state": "OPEN",
        "target_expected_version": 1,
        "target_request_id": "00000000-0000-7000-8000-000000000002",
        "target_text": "Exact Request text.",
    }
    validator = _validator("proposal.schema.json")
    validator.validate(proposal)
    for missing in ("decision", "seat_credential_id", "related_request_id"):
        invalid = deepcopy(proposal)
        invalid.pop(missing)
        with pytest.raises(ValidationError):
            validator.validate(invalid)


def test_decision_contract_preserves_terminal_outcome_coherence() -> None:
    validator = _validator("decision.schema.json")
    accepted = _decision_vector()
    validator.validate(accepted)
    rejected = {
        **accepted,
        "operation": "rejected",
        "reason": "Evidence was incomplete.",
        "target_command_id": None,
        "target_outcome": None,
        "target_request_version": None,
    }
    validator.validate(rejected)
    for invalid in (
        {**accepted, "target_problem_code": "unexpected"},
        {**accepted, "operation": "rejected"},
        {key: value for key, value in accepted.items() if key != "target_outcome"},
    ):
        with pytest.raises(ValidationError):
            validator.validate(invalid)


def test_request_proposal_http_surface_has_five_real_cli_operations() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    operations = {
        cast(str, operation["operationId"]): operation
        for path in cast(dict[str, dict[str, object]], document["paths"]).values()
        for method, operation in path.items()
        if method in {"get", "post"} and isinstance(operation, dict)
    }

    assert operations.keys() >= _OPERATIONS
    assert {cast(str, operations[name]["x-ctower-cli"]) for name in _OPERATIONS} == {
        "request proposal append",
        "request proposal confirm",
        "request proposal list",
        "request proposal reject",
        "request proposal review",
    }


def test_request_proposal_storage_is_append_only_and_separate() -> None:
    migration = (
        ROOT / "packages/ctower-kernel/migrations/0067_request_maintenance_proposals.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "request_maintenance_proposals",
        "request_maintenance_proposal_evidence",
        "request_maintenance_proposal_decisions",
    ):
        assert f"CREATE TABLE {table}" in migration
        assert f"CREATE TRIGGER {table}_immutable" in migration
    assert "ALTER TABLE requests" not in migration


def _validator(name: str) -> Draft202012Validator:
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "contracts/domain/request-proposals").glob("*.json")
    }
    registry = Registry().with_resources(
        (
            cast(str, schema["$id"]),
            Resource.from_contents(schema),
        )
        for schema in schemas.values()
    )
    return Draft202012Validator(schemas[name], registry=registry, format_checker=FormatChecker())


def _event_evidence() -> dict[str, object]:
    return {
        "event_digest": "sha256:" + "a" * 64,
        "event_id": "00000000-0000-7000-8000-000000000001",
        "event_kind": "request.changed",
        "kind": "record-event",
    }


def _append_vector() -> dict[str, object]:
    return {
        "basis": "recorded-evidence",
        "evidence": [_event_evidence()],
        "kind": "keep",
        "project_key": "ctower",
        "source_record_position": 12,
        "target_expected_version": 1,
        "target_request_id": "00000000-0000-7000-8000-000000000002",
        "target_text": "Exact Request text.",
    }


def _decision_vector() -> dict[str, object]:
    return {
        "accepted_position": 13,
        "command_id": "00000000-0000-7000-8000-000000000030",
        "decided_at": "2026-08-13T06:00:00+00:00",
        "decided_by": "00000000-0000-7000-8000-000000000031",
        "decision_id": "00000000-0000-7000-8000-000000000032",
        "durability_state": "accepted",
        "event_ids": ["00000000-0000-7000-8000-000000000033"],
        "expected_proposal_version": 1,
        "operation": "confirmed",
        "proposal_id": "00000000-0000-7000-8000-000000000020",
        "reason": None,
        "target_command_id": "00000000-0000-7000-8000-000000000034",
        "target_outcome": "accepted",
        "target_problem_code": None,
        "target_request_version": 2,
    }

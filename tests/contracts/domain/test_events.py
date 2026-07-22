"""Canonical event-envelope and hash-chain contract vectors."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).parents[3]
VECTOR_COUNT = 6


def test_event_envelope_is_strict_and_hash_vectors_are_canonical() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/events/event-envelope.schema.json").read_text(encoding="utf-8")
    )
    document = json.loads(
        (ROOT / "contracts/domain/events/canonical-vectors.json").read_text(encoding="utf-8")
    )
    vectors = cast(list[dict[str, object]], document["vectors"])

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert schema["additionalProperties"] is False
    assert len(vectors) == VECTOR_COUNT
    previous_hashes: dict[str, str] = {}
    for vector in vectors:
        event = cast(dict[str, object], vector["event"])
        stream_id = str(event["stream_id"])
        previous_hash = previous_hashes.get(stream_id, f"sha256:{'0' * 64}")
        canonical = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        event_hash = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
        validator.validate(event)
        assert event["prev_hash"] == previous_hash
        assert vector["canonical_json"] == canonical
        assert vector["event_hash"] == event_hash
        previous_hashes[stream_id] = event_hash


def test_ticket_event_payload_contract_covers_the_typed_work_slice() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/tickets/ticket-event.schema.json").read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["kind"]["enum"]) == {
        "ticket.created",
        "ticket.custody_transferred",
        "work.changed",
    }


def test_work_proof_and_workflow_event_variants_are_strict_and_typed() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/events/event-envelope.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    work = _aggregate_event("work.changed", "ticket")
    work["payload"] = {
        "data": {
            "authority": "commander",
            "from_priority": "P2",
            "policy_ref": "ctower.priority-authority@1",
            "reason": "Customer impact",
            "to_priority": "P1",
            "urgent_evidence_ref": None,
        },
        "operation": "priority_changed",
        "ticket_id": "00000000-0000-4000-8000-000000000008",
        "work_version": 2,
    }
    proof = _aggregate_event("proof.changed", "proof")
    proof["payload"] = {
        "candidate_digest": "sha256:" + "a" * 64,
        "invalidated_evidence_ids": [],
        "invalidated_verdict_ids": [],
        "operation": "freeze_criteria",
        "proof_version": 1,
        "ticket_id": "00000000-0000-4000-8000-000000000008",
    }
    workflow = _aggregate_event("workflow.changed", "workflow")
    workflow["payload"] = {
        "lifecycle_facts": ["resolved", "closed"],
        "operation": "resolve_close",
        "stage": "terminal",
        "ticket_id": "00000000-0000-4000-8000-000000000008",
        "workflow_ref": "fixture.generic@1",
        "workflow_version": 3,
    }

    validator.validate(work)
    validator.validate(proof)
    validator.validate(workflow)
    corrupt = deepcopy(workflow)
    cast(dict[str, object], corrupt["payload"])["lifecycle_facts"] = ["closed", "resolved"]
    with pytest.raises(ValidationError):
        validator.validate(corrupt)


def _aggregate_event(kind: str, stream: str) -> dict[str, object]:
    aggregate_id = "00000000-0000-4000-8000-000000000007"
    return {
        "actor_principal_id": "00000000-0000-4000-8000-000000000001",
        "aggregate_id": aggregate_id,
        "causation_id": None,
        "client_command_id": "00000000-0000-4000-8000-000000000002",
        "correlation_id": "00000000-0000-4000-8000-000000000003",
        "event_id": "00000000-0000-4000-8000-000000000004",
        "kind": kind,
        "origin": "api",
        "payload": {},
        "prev_hash": "sha256:" + "0" * 64,
        "request_sha256": "sha256:" + "1" * 64,
        "schema_version": 1,
        "sequence": 1,
        "server_time": "2026-07-20T12:00:00Z",
        "stream_id": f"{stream}:{aggregate_id}",
        "tenant_id": "00000000-0000-4000-8000-000000000005",
    }

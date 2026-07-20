"""Canonical event-envelope and hash-chain contract vectors."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
VECTOR_COUNT = 3


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


def test_ticket_event_payload_contract_covers_only_the_slice_vocabulary() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/tickets/ticket-event.schema.json").read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["kind"]["enum"]) == {
        "ticket.created",
        "ticket.custody_transferred",
    }

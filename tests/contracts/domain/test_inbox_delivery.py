"""Strict authored contracts for append-only inbox delivery and read facts."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).parents[3]


def test_inbox_v2_contract_carries_strict_delivery_and_read_facts() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/inbox/inbox-v2.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    document = _inbox_document()

    Draft202012Validator.check_schema(schema)
    validator.validate(document)
    assert schema["properties"]["schema"]["const"] == "ctower.inbox/v2"

    corrupt = deepcopy(document)
    fact = cast(dict[str, object], cast(list[object], corrupt["delivery_facts"])[0])
    fact["caller_claimed_delivery"] = True
    with pytest.raises(ValidationError):
        validator.validate(corrupt)


def test_inbox_message_requires_closed_severity_contract() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/inbox/inbox-v2.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    document = _inbox_document()
    message = cast(dict[str, object], cast(list[object], document["messages"])[0])
    message["severity"] = "P0"

    validator.validate(document)

    for invalid in ("P2", "p0", ""):
        message["severity"] = invalid
        with pytest.raises(ValidationError):
            validator.validate(document)


def test_event_envelope_has_distinct_strict_delivered_and_read_branches() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/events/event-envelope.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    delivered = _delivery_event("message.delivered", sequence=3)
    read = _delivery_event("message.read", sequence=4)

    validator.validate(delivered)
    validator.validate(read)
    corrupt = deepcopy(read)
    payload = cast(dict[str, object], corrupt["payload"])
    recipient = cast(dict[str, object], payload["recipient"])
    recipient["seat_key"] = "INVALID SEAT"
    with pytest.raises(ValidationError):
        validator.validate(corrupt)


def _inbox_document() -> dict[str, object]:
    recipient = {
        "principal_id": "018f0d5e-7b9a-7c01-8000-000000000004",
        "seat_key": "qa-agent",
    }
    sender = {
        "principal_id": "018f0d5e-7b9a-7c01-8000-000000000003",
        "seat_key": "ctower-commander",
    }
    message_id = "018f0d5e-7b9a-7c01-8000-000000000602"
    thread_id = "018f0d5e-7b9a-7c01-8000-000000000600"
    return {
        "schema": "ctower.inbox/v2",
        "thread": {
            "thread_id": thread_id,
            "tenant_id": "018f0d5e-7b9a-7c01-8000-000000000001",
            "participants": [sender, recipient],
            "version": 4,
        },
        "messages": [
            {
                "message_id": message_id,
                "thread_id": thread_id,
                "position": 1,
                "sender": sender,
                "recipient": recipient,
                "text": "Acknowledge this message.",
                "severity": "info",
            }
        ],
        "delivery_facts": [
            {
                "event_id": "018f0d5e-7b9a-7c01-8000-000000000603",
                "message_id": message_id,
                "thread_id": thread_id,
                "recipient": recipient,
                "state": "delivered",
                "recorded_at": "2026-08-07T18:50:00Z",
            },
            {
                "event_id": "018f0d5e-7b9a-7c01-8000-000000000604",
                "message_id": message_id,
                "thread_id": thread_id,
                "recipient": recipient,
                "state": "read",
                "recorded_at": "2026-08-07T18:51:00Z",
            },
        ],
        "promotion": None,
    }


def _delivery_event(kind: str, *, sequence: int) -> dict[str, object]:
    thread_id = "018f0d5e-7b9a-7c01-8000-000000000600"
    return {
        "actor_principal_id": "018f0d5e-7b9a-7c01-8000-000000000004",
        "aggregate_id": thread_id,
        "causation_id": None,
        "client_command_id": "018f0d5e-7b9a-7c01-8000-000000000603",
        "correlation_id": "018f0d5e-7b9a-7c01-8000-000000000603",
        "event_id": f"018f0d5e-7b9a-7c01-8000-00000000060{sequence}",
        "kind": kind,
        "origin": "api",
        "payload": {
            "message_id": "018f0d5e-7b9a-7c01-8000-000000000602",
            "recipient": {
                "principal_id": "018f0d5e-7b9a-7c01-8000-000000000004",
                "seat_key": "qa-agent",
            },
            "thread_id": thread_id,
        },
        "prev_hash": "sha256:" + "0" * 64,
        "request_sha256": "sha256:" + "1" * 64,
        "schema_version": 1,
        "sequence": sequence,
        "server_time": "2026-08-07T18:50:00Z",
        "stream_id": f"inbox-thread:{thread_id}",
        "tenant_id": "018f0d5e-7b9a-7c01-8000-000000000001",
    }

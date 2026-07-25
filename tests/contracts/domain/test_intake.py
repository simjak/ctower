"""Strict durable inbound-thread aggregate contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).parents[3]
SCHEMA = json.loads(
    (ROOT / "contracts/domain/intake/thread-intake.schema.json").read_text(encoding="utf-8")
)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def test_discussion_contract_has_stable_source_and_no_ticket_link() -> None:
    thread_id, event_id, tenant_id = uuid4(), uuid4(), uuid4()
    payload = {
        "schema": "ctower.thread-intake/v1",
        "thread": {
            "thread_id": str(thread_id),
            "tenant_id": str(tenant_id),
            "project_key": "ctower",
            "version": 1,
        },
        "inbound_event": {
            "inbound_event_id": str(event_id),
            "thread_id": str(thread_id),
            "position": 1,
            "source": {"kind": "chat", "ref": "chat:message:1"},
            "content_digest": "sha256:" + "0" * 64,
            "taint": "authenticated",
            "initial_intent": "discussion",
            "initial_outcome": "discussion",
        },
        "ticket_link": None,
        "quarantine": None,
    }

    VALIDATOR.validate(payload)
    inbound_event = cast(dict[str, object], payload["inbound_event"])
    with pytest.raises(ValidationError):
        VALIDATOR.validate(
            {
                **payload,
                "inbound_event": {
                    **inbound_event,
                    "classifier_guess": "ticket",
                },
            }
        )

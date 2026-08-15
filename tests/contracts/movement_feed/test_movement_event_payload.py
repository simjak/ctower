"""AC-MOVE-01: the enriched `workflow.changed` payload contract.

Proves the transition event carries exact from/to stage plus a stable
transition-evaluation/evidence-manifest pointer, is linked to the Ticket, and
never embeds an exhaustive Ticket snapshot.  These are schema-level contract
vectors — no live Postgres.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
ENVELOPE = ROOT / "contracts/domain/events/event-envelope.schema.json"


def _schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(ENVELOPE.read_text(encoding="utf-8")))


def _workflow_changed() -> dict[str, Any]:
    return cast(dict[str, Any], _schema()["$defs"]["workflowChanged"])


def test_transition_payload_requires_from_stage_and_evaluation_ref() -> None:
    workflow = _workflow_changed()
    required = set(cast(list[str], workflow["required"]))
    properties = cast(dict[str, Any], workflow["properties"])

    # Every new workflow.changed event names both fields (empty only when a
    # pre-enrichment or non-transition operation has no prior stage or pointer).
    assert "source_stage" in required
    assert "evaluation_ref" in required
    assert "ticket_id" in required
    assert set(properties) >= {
        "evaluation_ref",
        "lifecycle_facts",
        "operation",
        "source_stage",
        "stage",
        "ticket_id",
        "workflow_ref",
        "workflow_version",
    }
    # Empty string is honest for start/resolve_close; a non-empty value is a
    # stable stage key.
    assert properties["source_stage"]["pattern"] == "^$|^[a-z][a-z0-9._-]*$"
    assert properties["evaluation_ref"]["type"] == "string"


def test_transition_operation_conditionally_forbids_missing_pointer() -> None:
    workflow = _workflow_changed()
    all_of = cast(list[Any], workflow.get("allOf", []))
    transition_rules = [
        item
        for item in all_of
        if item.get("if", {}).get("properties", {}).get("operation", {}).get("const")
        == "transition"
    ]
    assert transition_rules, "transition operation must conditionally require the fields"
    required = set(cast(list[str], transition_rules[0]["then"]["required"]))
    assert {"evaluation_ref", "source_stage"} <= required


def test_payload_never_carries_ticket_content_fields() -> None:
    properties = cast(dict[str, Any], _workflow_changed()["properties"])
    assert "title" not in properties
    assert "text" not in properties
    assert "summary" not in properties
    assert "body" not in properties


def test_transition_payload_has_a_stable_evaluation_pointer_shape() -> None:
    # The evaluation pointer is a stable reference (workflow_transition_facts id),
    # typed as a string so the read path can tolerate an empty default for
    # pre-enrichment rows while write-path ids remain non-empty.
    assert _workflow_changed()["properties"]["evaluation_ref"]["type"] == "string"

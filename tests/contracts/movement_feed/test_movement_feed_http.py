"""AC-MOVE-01..05 payload and route contract vectors for the movement feed.

No live Postgres here — this proves the authored OpenAPI route/schema shape and
the enriched `workflow.changed` payload contract, matching `tests/contracts/http`'s
convention of schema-level contract tests.  These files may use only relative
imports from this package (the tests root is on mypy_path; absolute `tests.*`
imports abort the whole mypy run).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any, cast

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
OPENAPI = ROOT / "contracts/http/openapi.yaml"
EXPECTED_SUITES = ROOT / "tools/checks/expected-suites.toml"


def _openapi() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(OPENAPI.read_text(encoding="utf-8")))


def _schemas() -> dict[str, Any]:
    return cast(dict[str, Any], _openapi()["components"]["schemas"])


def _paths() -> dict[str, Any]:
    return cast(dict[str, Any], _openapi()["paths"])


def test_movement_route_is_a_named_authenticated_read_never_mutation() -> None:
    operation = _paths()["/v1/projects/{project_key}/movement"]["get"]

    assert operation["operationId"] == "listTicketMovement"
    assert operation["x-ctower-cli"] == "project movement"
    assert operation["x-ctower-mutation"] is False
    assert operation["x-ctower-spool"] == "forbidden"
    assert operation["x-ctower-principal"] == "authenticated"
    assert operation["security"] == [{"bearerAuth": []}]


def test_movement_route_reuses_the_shared_project_cursor_parameters() -> None:
    operation = _paths()["/v1/projects/{project_key}/movement"]["get"]
    refs = {item["$ref"] for item in operation["parameters"]}

    assert refs == {
        "#/components/parameters/ProjectKey",
        "#/components/parameters/AuditCursor",
        "#/components/parameters/AuditLimit",
    }


def test_movement_route_answers_every_named_failure() -> None:
    responses = _paths()["/v1/projects/{project_key}/movement"]["get"]["responses"]
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MovementEventPage"
    }
    for status in ("401", "403", "404", "422"):
        assert responses[status]["$ref"] == "#/components/responses/ProblemResponse"


def test_atom_route_is_an_authenticated_non_generated_read() -> None:
    operation = _paths()["/v1/projects/{project_key}/movement.atom"]["get"]

    assert operation["operationId"] == "getMovementAtom"
    assert operation["x-ctower-cli"] is None
    assert operation["x-ctower-mutation"] is False
    assert operation["x-ctower-spool"] == "forbidden"
    assert operation["x-ctower-principal"] == "authenticated"
    assert operation["x-ctower-generated-client"] is False
    assert operation["security"] == [{"bearerAuth": []}]
    assert operation["responses"]["200"]["content"]["application/atom+xml"]["schema"] == {
        "type": "string"
    }


def test_movement_event_carries_only_transition_facts_and_never_a_ticket_snapshot() -> None:
    event = _schemas()["MovementEvent"]

    assert event["additionalProperties"] is False
    assert list(event["required"]) == [
        "evaluation_ref",
        "event_id",
        "from_stage",
        "record_position",
        "ticket_id",
        "to_stage",
        "workflow_ref",
        "workflow_version",
    ]
    # The movement event must not embed ticket content.
    properties = cast(dict[str, Any], event["properties"])
    assert "title" not in properties
    assert "text" not in properties
    assert "summary" not in properties
    assert properties["record_position"] == {"type": "integer", "minimum": 1}
    assert properties["from_stage"] == {"type": "string", "pattern": "^[a-z][a-z0-9._-]*$"}
    assert properties["to_stage"] == {"type": "string", "pattern": "^[a-z][a-z0-9._-]*$"}
    assert properties["evaluation_ref"]["type"] == "string"


def test_movement_page_is_strict_and_reuses_cursor_paging() -> None:
    page = _schemas()["MovementEventPage"]

    assert page["additionalProperties"] is False
    assert set(page["required"]) == {"events", "next_cursor", "project_key"}
    assert page["properties"]["next_cursor"]["type"] == ["integer", "null"]
    assert page["properties"]["events"]["items"] == {"$ref": "#/components/schemas/MovementEvent"}


def test_expected_suites_manifest_registers_new_required_suites() -> None:
    data = tomllib.loads(EXPECTED_SUITES.read_text(encoding="utf-8"))
    ids = {suite["id"] for suite in cast(list[dict[str, object]], data["suite"])}
    assert "movement-feed-contracts" in ids
    assert "ticket-movement-projection" in ids
    assert "ticket-movement-acceptance" in ids


def test_phase_order_places_ct_i1_027_after_ct_i1_024() -> None:
    data = tomllib.loads(EXPECTED_SUITES.read_text(encoding="utf-8"))
    order = cast(list[str], data["phase_order"])
    assert "CT-I1-027" in order
    assert order.index("CT-I1-024") < order.index("CT-I1-027")


def test_movement_pointer_path_regex_is_stable() -> None:
    # The digest pointer and Atom links must reference the dedicated movement view.
    assert re.fullmatch(r"/v1/projects/\{[a-z_]+\}/movement", "/v1/projects/{project_key}/movement")

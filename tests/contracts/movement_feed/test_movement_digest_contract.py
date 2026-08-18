"""AC-MOVE-03: the movement digest summary contract.

The morning digest carries deterministic prior-civil-day movement counts grouped
by Project and exact from/to stage, an authorization-preserving pointer to the
MOVEMENT VIEW (never the raw events feed), and a source watermark.  It embeds no
movement event row, Ticket identity, or Ticket text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
OPENAPI = ROOT / "contracts/http/openapi.yaml"


def _openapi() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(OPENAPI.read_text(encoding="utf-8")))


def _schemas() -> dict[str, Any]:
    return cast(dict[str, Any], _openapi()["components"]["schemas"])


def test_digest_carries_a_movement_summary_with_pointer_and_watermark() -> None:
    digest = _schemas()["MorningDigest"]

    properties = cast(dict[str, Any], digest["properties"])
    assert "movement" in properties
    assert "movement_watermark" in properties
    assert properties["movement"]["$ref"] == "#/components/schemas/MovementDigestSummary"
    assert properties["movement_watermark"]["type"] == ["integer", "null"]


def test_movement_summary_counts_by_project_and_stage_with_movement_view_pointer() -> None:
    summary = _schemas()["MovementDigestSummary"]
    properties = cast(dict[str, Any], summary["properties"])

    assert summary["additionalProperties"] is False
    # Counts grouped by (project, from_stage, to_stage); each row is strict and
    # carries its deterministic count.
    count_schema = _schemas()["MovementDigestCount"]
    assert cast(list[str], count_schema["required"]) == [
        "count",
        "from_stage",
        "project_key",
        "to_stage",
    ]
    assert count_schema["properties"]["count"] == {"type": "integer", "minimum": 1}
    assert count_schema["properties"]["project_key"] == {
        "type": "string",
        "pattern": "^[a-z][a-z0-9-]{2,63}$",
    }
    assert properties["counts"]["items"]["$ref"] == "#/components/schemas/MovementDigestCount"
    assert properties["watermark"] == {"type": ["integer", "null"], "minimum": 0}
    # Pointer targets the movement view endpoint (never raw events).
    assert properties["pointer"]["const"] == "/v1/projects/{project_key}/movement"


def test_movement_summary_embeds_no_event_row_identity_or_text() -> None:
    summary = _schemas()["MovementDigestSummary"]
    properties = cast(dict[str, Any], summary["properties"])

    for forbidden in ("event_id", "record_position", "server_time", "ticket_id", "text", "title"):
        assert forbidden not in properties, f"MovementDigestSummary leaks {forbidden}"
    encoded = json.dumps(summary)
    assert "ticket_id" not in encoded
    assert "event_id" not in encoded


def test_movement_digest_route_reuses_the_morning_digest_operation() -> None:
    paths = cast(dict[str, Any], _openapi()["paths"])
    operation = cast(dict[str, Any], paths["/v1/digests/morning"]["get"])

    assert operation["operationId"] == "getMorningDigest"
    assert operation["x-ctower-cli"] == "digest morning"

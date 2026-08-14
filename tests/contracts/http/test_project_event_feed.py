"""Static contract for CT-I1-012's project-scoped typed event feed (#186, INV-78).

No live Postgres here — this proves the authored OpenAPI route/schema shape, matching
`tests/contracts/http`'s convention of schema-level contract tests. `contract-tests` may
not depend on `control-cli` or reach into another owner's private modules, so codegen
inventory coverage is proven by `just check`'s own `codegen-check` step (which runs
`tools.codegen`'s exact-set equality gate against this same contract) and CLI inventory
coverage lives in `tests/modules/ctowerctl`, control-cli's own owner. Live behavioral
proof (three-project replay, reconnect/gap, project-separation refusal, prohibited-field
scan) lives in `tests/acceptance/increment-1/test_portfolio_board.py`, the file the canonical
specification's CT-I1-012 row names as the designated acceptance suite.
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


def test_the_route_is_a_named_authenticated_read_never_mutation_or_spool() -> None:
    operation = _openapi()["paths"]["/v1/projects/{project_key}/events"]["get"]

    assert operation["operationId"] == "listProjectEvents"
    assert operation["x-ctower-cli"] == "project events"
    assert operation["x-ctower-mutation"] is False
    assert operation["x-ctower-spool"] == "forbidden"
    assert operation["x-ctower-principal"] == "authenticated"
    assert operation["security"] == [{"bearerAuth": []}]


def test_the_route_reuses_the_shared_project_key_and_cursor_parameters() -> None:
    operation = _openapi()["paths"]["/v1/projects/{project_key}/events"]["get"]
    refs = {item["$ref"] for item in operation["parameters"]}

    assert refs == {
        "#/components/parameters/ProjectKey",
        "#/components/parameters/AuditCursor",
        "#/components/parameters/AuditLimit",
    }


def test_the_route_answers_every_named_refusal_the_grant_boundary_can_produce() -> None:
    responses = _openapi()["paths"]["/v1/projects/{project_key}/events"]["get"]["responses"]

    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectEventPage"
    }
    for status in ("401", "403", "404", "422"):
        assert responses[status]["$ref"] == "#/components/responses/ProblemResponse"


def test_project_event_page_is_strict_and_carries_no_project_encoded_cursor() -> None:
    """The cursor is a plain record-position integer, matching `ProjectSessionPage`/`AuditPage` —
    never a `v1:<project>:...` opaque string that would need its own parse/validate path."""

    page = _schemas()["ProjectEventPage"]

    assert page["additionalProperties"] is False
    assert set(page["required"]) == {"events", "next_cursor", "project_key"}
    assert page["properties"]["next_cursor"] == {"type": ["integer", "null"], "minimum": 1}
    assert page["properties"]["project_key"] == {
        "type": "string",
        "pattern": "^[a-z][a-z0-9-]{2,63}$",
    }
    assert page["properties"]["events"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/ProjectEvent"},
    }


def test_project_event_is_a_named_union_with_no_anonymous_branch() -> None:
    schemas = _schemas()
    branches = schemas["ProjectEvent"]["oneOf"]

    assert all(set(branch) == {"$ref"} for branch in branches)
    for branch in branches:
        name = branch["$ref"].rsplit("/", 1)[-1]
        assert name in schemas
        assert schemas[name]["additionalProperties"] is False

"""AC-MOVE-05: cross-surface movement inventory remains one read boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
OPENAPI = ROOT / "contracts/http/openapi.yaml"
SPEC = ROOT / "docs/internal/SPEC.md"
_PRIMARY_SURFACE_COUNT = 5
_PRIMARY_SURFACE_HEADER = (
    "| Primary screenshot surface | Included concepts from the research "
    "inventory | Never a primary destination |"
)
_PRIMARY_SURFACE_END = (
    "Members, invites, identities/access, secret bindings, execution environments, "
    "image lifecycle, provider"
)


def _openapi() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(OPENAPI.read_text(encoding="utf-8")))


def test_json_and_atom_surfaces_share_project_cursor_inputs() -> None:
    paths = cast(dict[str, Any], _openapi()["paths"])
    json_operation = paths["/v1/projects/{project_key}/movement"]["get"]
    atom_operation = paths["/v1/projects/{project_key}/movement.atom"]["get"]

    json_refs = {parameter["$ref"] for parameter in json_operation["parameters"]}
    atom_refs = {parameter["$ref"] for parameter in atom_operation["parameters"]}
    assert (
        json_refs
        == atom_refs
        == {
            "#/components/parameters/ProjectKey",
            "#/components/parameters/AuditCursor",
            "#/components/parameters/AuditLimit",
        }
    )
    assert json_operation["x-ctower-cli"] == "project movement"
    assert atom_operation["x-ctower-cli"] is None


def test_movement_is_contextual_read_surface_without_a_new_principal_or_feed_token() -> None:
    paths = cast(dict[str, Any], _openapi()["paths"])
    movement_paths = tuple(path for path in paths if "/movement" in path)

    assert movement_paths == (
        "/v1/projects/{project_key}/movement",
        "/v1/projects/{project_key}/movement.atom",
    )
    for path in movement_paths:
        operation = paths[path]["get"]
        assert operation["security"] == [{"bearerAuth": []}]
        assert operation["x-ctower-principal"] == "authenticated"
        assert "token" not in {parameter.get("name") for parameter in operation["parameters"]}
        assert "feed_token" not in json.dumps(operation)


def test_movement_page_and_digest_pointer_name_the_same_view() -> None:
    paths = cast(dict[str, Any], _openapi()["paths"])
    schemas = cast(dict[str, Any], _openapi()["components"]["schemas"])

    movement_schema = schemas["MovementDigestSummary"]
    assert (
        movement_schema["properties"]["pointer"]["const"] == "/v1/projects/{project_key}/movement"
    )
    assert (
        paths["/v1/projects/{project_key}/movement"]["get"]["operationId"] == "listTicketMovement"
    )


def test_movement_stays_contextual_inside_the_exactly_five_primary_surfaces() -> None:
    lines = SPEC.read_text(encoding="utf-8").splitlines()
    start = lines.index(_PRIMARY_SURFACE_HEADER)
    end = next(
        index
        for index, line in enumerate(lines[start:], start)
        if line.startswith(_PRIMARY_SURFACE_END)
    )
    surfaces = tuple(
        line.split("|", maxsplit=2)[1].strip()
        for line in lines[start + 2 : end]
        if line.startswith("| **")
    )

    assert surfaces == (
        "**Home / Needs You**",
        "**Board**",
        "**Ticket detail**",
        "**Fleet**",
        "**Analytics**",
    )
    assert len(surfaces) == _PRIMARY_SURFACE_COUNT
    assert all("movement" not in surface.lower() for surface in surfaces)


def test_record_interface_owns_movement_read_types_without_importing_sql() -> None:
    interface = (ROOT / "packages/ctower-kernel/src/ctower_kernel/record/interface.py").read_text(
        encoding="utf-8"
    )

    assert "_movement_event_sql" not in interface

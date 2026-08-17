"""HTTP contract vectors for ticket display keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]


def _document() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8")),
    )


def test_ticket_and_board_resources_expose_the_server_assigned_display_key() -> None:
    document = _document()
    components = cast(dict[str, object], document["components"])
    schemas = cast(dict[str, object], components["schemas"])
    for name in ("TicketResource", "BoardCard"):
        schema = cast(dict[str, object], schemas[name])
        properties = cast(dict[str, object], schema["properties"])
        assert "display_key" in properties
        assert (
            cast(dict[str, object], properties["display_key"])["pattern"]
            == "^[A-Z]{2,5}-[1-9][0-9]*$"
        )


def test_ticket_path_accepts_uuid_or_server_assigned_display_key() -> None:
    document = _document()
    parameters = cast(
        dict[str, object], cast(dict[str, object], document["components"])["parameters"]
    )
    ticket_id = cast(dict[str, object], parameters["TicketId"])
    schema = cast(dict[str, object], ticket_id["schema"])
    assert schema["format"] == "ticket-ref"
    assert schema["pattern"] == (
        "^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
        "[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|[A-Z]{2,5}-[1-9][0-9]*)$"
    )

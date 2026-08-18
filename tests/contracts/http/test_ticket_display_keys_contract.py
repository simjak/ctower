"""HTTP contract vectors for ticket display keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from ._generated_client_runtime import python_client

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
RECORD_UUID_VERSION = 7
# Record mints ticket identity with `record/identifiers.py:uuid7`, so the canonical
# ticket UUID is version 7; the path parameter carries whatever version it is given.
CANONICAL_TICKET_ID = UUID("01a010ca-79a0-706d-b5ee-8e96afa4a574")


def _document() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8")),
    )


def _ticket_body() -> str:
    return json.dumps(
        {
            "created_at": "2026-08-17T17:35:00Z",
            "custodian_id": "018f7a40-1234-7abc-8def-1234567890ab",
            "display_key": "CTW-4",
            "durability_state": "accepted",
            "priority": "P2",
            "source": {"kind": "test", "ref": "contract:ticket-display-keys"},
            "ticket_id": str(CANONICAL_TICKET_ID),
            "title": "Ticket resource",
            "version": 1,
        }
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
        "^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[A-Z]{2,5}-[1-9][0-9]*)$"
    )


def test_generated_client_takes_the_canonical_uuid_version_the_record_mints() -> None:
    """Record issues UUIDv7, so the ticket path must accept it in both transport forms."""

    assert CANONICAL_TICKET_ID.version == RECORD_UUID_VERSION
    references: tuple[UUID | str, ...] = (
        CANONICAL_TICKET_ID,
        str(CANONICAL_TICKET_ID),
        str(CANONICAL_TICKET_ID).upper(),
        "9a5c1a6e-8097-4bb2-b3d7-07e0dd7aaaaa",
        "CTW-4",
    )
    for reference in references:
        client = python_client(_ticket_body(), status=200)
        try:
            assert client.get_ticket(reference, project_key="ctower").display_key == "CTW-4"
        finally:
            client.close()


@pytest.mark.parametrize(
    "reference",
    (
        "CTW-0",
        "CTW-04",
        "ctw-4",
        "CTOWER-4",
        "01a010ca-79a0-706d-b5ee-8e96afa4a57",
        "01a010ca79a0706db5ee8e96afa4a574",
        "not-a-ticket-reference",
    ),
)
def test_generated_client_refuses_references_outside_the_authored_contract(
    reference: str,
) -> None:
    client = python_client(_ticket_body(), status=200)
    try:
        with pytest.raises(ValidationError):
            client.get_ticket(reference, project_key="ctower")
    finally:
        client.close()

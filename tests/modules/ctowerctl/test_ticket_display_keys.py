"""CLI ticket references accept UUIDs and server-assigned display keys."""

from __future__ import annotations

from ctowerctl._parser import parse_arguments

__all__: tuple[str, ...] = ()


def test_ticket_query_accepts_a_display_key_where_a_ticket_id_is_expected() -> None:
    arguments = parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "ticket",
            "query",
            "CTW-311",
            "--project-key",
            "ctower",
        ]
    )
    assert arguments.ticket_id == "CTW-311"

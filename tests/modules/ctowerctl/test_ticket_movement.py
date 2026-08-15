"""Protected CLI coverage for the generated project movement read."""

from __future__ import annotations

from argparse import Namespace
from typing import cast

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import MovementEventPage
from ctowerctl._migration_commands import execute_query, query_command_names
from ctowerctl._parser import authored_command_names, parse_arguments

__all__: tuple[str, ...] = ()

_CURSOR = 7
_LIMIT = 2


class _Client:
    def __init__(self) -> None:
        self.received: tuple[str, int | None, int | None] | None = None

    def list_ticket_movement(
        self,
        project_key: str,
        *,
        cursor: int | None = None,
        limit: int | None = None,
    ) -> MovementEventPage:
        self.received = (project_key, cursor, limit)
        return MovementEventPage(project_key=project_key, events=(), next_cursor=None)


def test_project_movement_is_a_real_authored_cursor_command() -> None:
    arguments = parse_arguments(
        ["project", "movement", "ctower", "--cursor", str(_CURSOR), "--limit", str(_LIMIT)]
    )

    assert arguments.cli_name == "project movement"
    assert arguments.project_key == "ctower"
    assert arguments.cursor == _CURSOR
    assert arguments.limit == _LIMIT
    assert "project movement" in authored_command_names()
    assert "project movement" in query_command_names()


def test_project_movement_dispatches_to_the_generated_client() -> None:
    client = _Client()
    arguments = Namespace(
        cli_name="project movement",
        project_key="ctower",
        cursor=_CURSOR,
        limit=_LIMIT,
    )

    result = execute_query(arguments, cast(CtowerClient, client))

    assert isinstance(result, BaseModel)
    assert client.received == ("ctower", _CURSOR, _LIMIT)

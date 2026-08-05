"""The Board project-source watermark must derive from the fold dispatch, not a second list."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest

from ctower_kernel.projections import _board_sql
from ctower_kernel.record.events import EventKind

__all__: tuple[str, ...] = ()

_TODAYS_BOARD_SOURCE_KINDS = frozenset(
    {
        EventKind.TICKET_CREATED,
        EventKind.CUSTODY_TRANSFERRED,
        EventKind.WORK_CHANGED,
        EventKind.WORKFLOW_CHANGED,
    }
)


def test_project_source_event_kinds_match_the_fold_dispatch_exactly() -> None:
    assert set(_board_sql._FOLD_DISPATCH) == _TODAYS_BOARD_SOURCE_KINDS
    assert set(_board_sql._board_source_event_kinds()) == _TODAYS_BOARD_SOURCE_KINDS


def test_project_source_event_kinds_follow_the_fold_dispatch_when_it_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trimmed = {EventKind.TICKET_CREATED: _board_sql._FOLD_DISPATCH[EventKind.TICKET_CREATED]}
    monkeypatch.setattr(_board_sql, "_FOLD_DISPATCH", trimmed)

    assert _board_sql._board_source_event_kinds() == (EventKind.TICKET_CREATED,)


def test_apply_message_is_a_no_op_for_a_kind_the_fold_does_not_dispatch() -> None:
    assert EventKind.TICKET_COMMENT_ADDED not in _board_sql._FOLD_DISPATCH

    _board_sql.apply_message(
        cast(Any, _ExplodingConnection()),
        uuid4(),
        {"kind": EventKind.TICKET_COMMENT_ADDED.value},
    )


class _ExplodingConnection:
    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("apply_message touched the connection for an undispatched kind")

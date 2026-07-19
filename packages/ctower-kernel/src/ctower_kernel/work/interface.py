"""Deep Work Module for ticket policy and authoritative commands."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    Record,
    RecordProblem,
    TicketCommand,
    TicketCommandResult,
)

__all__ = ["Work"]

PRIORITIES = frozenset({"P0", "P1", "P2"})


class Work:
    """Own ticket command policy while Record owns atomic persistence."""

    def __init__(
        self,
        record: Record,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._record = record
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_ticket(
        self, actor: Actor, command: TicketCommand
    ) -> TicketCommandResult | RecordProblem:
        """Enforce priority policy before appending a ticket."""

        if command.priority not in PRIORITIES:
            return _refusal(command, "Ticket priority is outside P0/P1/P2.")
        if command.priority == "P0" and actor.kind is not PrincipalKind.OPERATOR:
            return _refusal(command, "Only an operator may create a P0 ticket.")
        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        return self._record.create_ticket(
            actor,
            command,
            request_digest=request_digest,
            now=self._clock(),
        )


def _refusal(command: TicketCommand, detail: str) -> RecordProblem:
    return RecordProblem(
        code="unauthorized",
        detail=detail,
        status=403,
        title="Ticket command refused",
        command_id=command.client_command_id,
    )


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

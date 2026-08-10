"""Work-owned policy and PostgreSQL facade for the Agreements ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import Actor, RecordProblem, credential_scope_refusal
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext
from ctower_kernel.work._ruling_sql import append_ruling, get_ruling, list_rulings
from ctower_kernel.work._ruling_types import (
    RulingAppend,
    RulingAppendResult,
    RulingList,
    RulingRow,
)

__all__ = [
    "PostgresRulings",
    "RulingAppend",
    "RulingAppendResult",
    "RulingList",
    "RulingRow",
    "Rulings",
]

_MAX_VERBATIM_BYTES = 65536


class _RulingStore(Protocol):
    def append(
        self,
        actor: Actor,
        command: RulingAppend,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RulingAppendResult | RecordProblem: ...

    def list(
        self, actor: Actor, *, project_key: str | None, now: datetime
    ) -> RulingList | RecordProblem: ...

    def get(self, actor: Actor, ruling_id: UUID) -> RulingRow | RecordProblem: ...


class Rulings:
    """Validate one append and delegate authority/read choreography to the store."""

    def __init__(
        self,
        store: _RulingStore,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def append(
        self, actor: Actor, command: RulingAppend, *, telemetry: TelemetryContext
    ) -> RulingAppendResult | RecordProblem:
        refusal = credential_scope_refusal(
            actor, CredentialScope.TRANSITION, command_id=command.client_command_id
        )
        if refusal is None:
            refusal = prohibited_data_refusal(
                (command.verbatim,), command_id=command.client_command_id
            )
        if refusal is None:
            verbatim = command.verbatim.encode("utf-8")
            if not 1 <= len(verbatim) <= _MAX_VERBATIM_BYTES or "\x00" in command.verbatim:
                refusal = RecordProblem(
                    "invalid-ruling",
                    "Ruling verbatim bytes are outside the authored contract.",
                    422,
                    "Invalid Ruling",
                    command.client_command_id,
                )
        if refusal is not None:
            return refusal
        outcome = self._store.append(
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("work.ruling.append", telemetry, outcome)
        return outcome

    def list(
        self,
        actor: Actor,
        *,
        project_key: str | None = None,
        telemetry: TelemetryContext,
    ) -> RulingList | RecordProblem:
        outcome = self._store.list(actor, project_key=project_key, now=self._clock())
        self._emit("work.ruling.list", telemetry, outcome)
        return outcome

    def get(
        self, actor: Actor, ruling_id: UUID, *, telemetry: TelemetryContext
    ) -> RulingRow | RecordProblem:
        outcome = self._store.get(actor, ruling_id)
        self._emit("work.ruling.get", telemetry, outcome)
        return outcome

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: RulingAppendResult | RulingList | RulingRow | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


class PostgresRulings:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def append(
        self,
        actor: Actor,
        command: RulingAppend,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RulingAppendResult | RecordProblem:
        return recover_ambiguous_commit(
            lambda: append_ruling(
                self._dsn,
                actor,
                command,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            )
        )

    def list(
        self, actor: Actor, *, project_key: str | None, now: datetime
    ) -> RulingList | RecordProblem:
        return list_rulings(self._dsn, actor, project_key=project_key, now=now)

    def get(self, actor: Actor, ruling_id: UUID) -> RulingRow | RecordProblem:
        return get_ruling(self._dsn, actor, ruling_id)


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()

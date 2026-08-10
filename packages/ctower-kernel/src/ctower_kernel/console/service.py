"""Console Phase-1 orchestration across authority, Adapter, custody, and SSE bounds."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from ctower_kernel.console.cipher import AesGcmConsoleCipher
from ctower_kernel.console.models import (
    ConsoleBackendObservation,
    ConsoleGlobalSwitchCommand,
    ConsoleGrantIdentifiers,
    ConsoleOutputBatch,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleStreamLease,
    ConsoleViewGrant,
    StoredConsoleOutput,
)
from ctower_kernel.console.output_store import PostgresConsoleOutputStore
from ctower_kernel.console.policy import (
    ConsoleStreamWindow,
    StreamDisposition,
    decide_view_grant,
)
from ctower_kernel.console.postgres import PostgresConsoleAuthority, StreamCloseCode
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.identifiers import uuid7

__all__ = ["ConsoleEventStream", "ConsoleViewer"]


class ConsoleBackendAdapter(Protocol):
    """Narrow process/output boundary; it has no authority or Record client."""

    def inspect(
        self, session_ref: ConsoleSessionRef
    ) -> ConsoleBackendObservation | RecordProblem: ...

    def read(
        self,
        session_ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        maximum_bytes: int,
    ) -> ConsoleOutputBatch | RecordProblem: ...


@dataclass(frozen=True, slots=True)
class ConsoleEventStream:
    """Claimed stream plus its lazily driven SSE body."""

    lease: ConsoleStreamLease
    events: Iterator[bytes]


@dataclass(slots=True)
class _StreamState:
    window: ConsoleStreamWindow
    after_cursor: int
    durable_cursor: int
    source_cursor: int
    reconnect: bool
    close_code: StreamCloseCode = "client_disconnected"
    gap_required: bool = False


class ConsoleViewer:
    """Small public Interface for exact grants and bounded encrypted output streaming."""

    def __init__(
        self,
        authority: PostgresConsoleAuthority,
        output_store: PostgresConsoleOutputStore,
        adapter: ConsoleBackendAdapter,
        cipher: AesGcmConsoleCipher,
        *,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._authority = authority
        self._output_store = output_store
        self._adapter = adapter
        self._cipher = cipher
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper or time.sleep

    def allow_session(
        self, actor: Actor, command: ConsoleSessionAllowCommand
    ) -> ConsoleSessionAllowance | RecordProblem:
        observation = self._adapter.inspect(command.session_ref)
        if isinstance(observation, RecordProblem):
            return observation
        return self._authority.allow_session(actor, command, observation, now=self._clock())

    def visible_sessions(self, actor: Actor) -> tuple[ConsoleSessionAllowance, ...] | RecordProblem:
        candidates = self._authority.visible_allowances(actor)
        if isinstance(candidates, RecordProblem):
            return candidates
        visible: list[ConsoleSessionAllowance] = []
        for allowance in candidates:
            ref = self._authority.session_ref(actor, allowance.allowance_id)
            if isinstance(ref, RecordProblem):
                continue
            observation = self._adapter.inspect(ref)
            if isinstance(observation, RecordProblem) or not _observation_matches(ref, observation):
                continue
            visible.append(allowance)
        return tuple(visible)

    def mint_grant(
        self, actor: Actor, allowance_id: UUID, *, renewal: bool = False
    ) -> ConsoleViewGrant | RecordProblem:
        now = self._clock()
        ref = self._authority.session_ref(actor, allowance_id)
        if isinstance(ref, RecordProblem):
            return ref
        observation = self._adapter.inspect(ref)
        if isinstance(observation, RecordProblem):
            self._authority.record_denial(actor, allowance_id, observation.code, now=now)
            return observation
        facts = self._authority.grant_facts(actor, allowance_id, observation, now=now)
        if isinstance(facts, RecordProblem):
            return facts
        previous = self._authority.previous_grant(actor, allowance_id)
        if renewal and previous is None:
            problem = _problem(
                "console-renewal-unavailable", "There is no prior grant to renew.", 401
            )
            self._authority.record_denial(actor, allowance_id, problem.code, now=now)
            return problem
        if not renewal and previous is not None and previous.expires_at <= now:
            previous = None
        outcome = decide_view_grant(
            facts,
            ConsoleGrantIdentifiers(grant_id=uuid7(now), nonce=uuid7(now)),
            policy=self._authority.policy,
            now=now,
            previous_grant=previous,
        )
        if isinstance(outcome, RecordProblem):
            self._authority.record_denial(actor, allowance_id, outcome.code, now=now)
            return outcome
        self._authority.persist_grant(outcome, now=now)
        return outcome

    def revoke_session(
        self, actor: Actor, command: ConsoleSessionRevocation
    ) -> RecordProblem | None:
        return self._authority.revoke_session(actor, command, now=self._clock())

    def set_global_switch(
        self, actor: Actor, command: ConsoleGlobalSwitchCommand
    ) -> RecordProblem | None:
        return self._authority.set_global_switch(actor, command, now=self._clock())

    def open_stream(
        self, actor: Actor, allowance_id: UUID, *, last_event_id: int | None
    ) -> ConsoleEventStream | RecordProblem:
        ref = self._authority.session_ref(actor, allowance_id)
        if isinstance(ref, RecordProblem):
            return ref
        observation = self._adapter.inspect(ref)
        if isinstance(observation, RecordProblem) or not _observation_matches(ref, observation):
            return (
                observation
                if isinstance(observation, RecordProblem)
                else _problem("console-incarnation-fenced", "The registered runtime was replaced.")
            )
        lease = self._authority.claim_stream(actor, allowance_id, now=self._clock())
        if isinstance(lease, RecordProblem):
            return lease
        events = self._stream_events(
            lease,
            ref,
            after_cursor=last_event_id or 0,
            reconnect=last_event_id is not None,
        )
        return ConsoleEventStream(lease=lease, events=events)

    def _stream_events(
        self,
        lease: ConsoleStreamLease,
        ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        reconnect: bool,
    ) -> Iterator[bytes]:
        state = self._stream_state(lease, after_cursor=after_cursor, reconnect=reconnect)
        try:
            newest = self._newest_durable_cursor(lease)
            initial_gap = self._initial_cursor_gap(lease, state, newest=newest)
            yield from _optional_event(initial_gap)
            while True:
                status = self._authority.stream_close_reason(lease, now=self._clock())
                if status is not None:
                    state.close_code = status
                    yield _closed(status)
                    return
                observation = self._adapter.inspect(ref)
                if isinstance(observation, RecordProblem) or not _observation_matches(
                    ref, observation
                ):
                    state.close_code = "fenced"
                    yield _closed("fenced")
                    return
                replay = self._output_store.outputs_after(
                    lease.grant.allowance_id,
                    lease.grant.tenant_id,
                    state.durable_cursor,
                )
                if replay:
                    terminal = yield from self._replay_outputs(lease, state, replay)
                    if terminal:
                        yield _closed(state.close_code)
                        return
                    continue
                terminal = yield from self._read_adapter(lease, ref, state)
                if terminal:
                    yield _closed(state.close_code)
                    return
        except GeneratorExit:
            state.close_code = "client_disconnected"
            raise
        finally:
            self._authority.close_stream(
                lease,
                state.close_code,
                gap_required=state.gap_required,
                now=self._clock(),
            )

    def _stream_state(
        self, lease: ConsoleStreamLease, *, after_cursor: int, reconnect: bool
    ) -> _StreamState:
        policy = self._authority.policy
        return _StreamState(
            window=ConsoleStreamWindow(
                delivery_window_bytes=policy.delivery_window_bytes,
                delivery_window_seconds=policy.delivery_window_seconds,
                replay_window_bytes=policy.replay_window_bytes,
                replay_window_seconds=policy.replay_window_seconds,
                pending_bytes=policy.pending_bytes,
            ),
            after_cursor=after_cursor,
            durable_cursor=after_cursor,
            source_cursor=self._output_store.latest_source_cursor(
                lease.grant.allowance_id, lease.grant.tenant_id
            ),
            reconnect=reconnect,
        )

    def _initial_cursor_gap(
        self, lease: ConsoleStreamLease, state: _StreamState, *, newest: int
    ) -> bytes | None:
        if state.durable_cursor <= newest:
            return None
        self._record_bounded_gap(lease, state.source_cursor, "unprovable_range")
        state.gap_required = True
        state.durable_cursor = newest
        return _gap(newest, "unprovable_range")

    def _replay_outputs(
        self,
        lease: ConsoleStreamLease,
        state: _StreamState,
        outputs: tuple[StoredConsoleOutput, ...],
    ) -> Generator[bytes, None, bool]:
        now = self._clock()
        for output in outputs:
            if (
                state.window.admit_replay(output.decoded_bytes, at=now)
                is not StreamDisposition.ADMITTED
            ):
                state.close_code = "rate_limited"
                state.gap_required = True
                self._record_bounded_gap(lease, output.source_cursor, "rate_limited")
                yield _gap(output.cursor, "rate_limited")
                return True
            access_kind: Literal["open", "reconnect", "replay", "forensic"] = (
                "reconnect" if state.reconnect else "open"
            )
            if state.durable_cursor != state.after_cursor:
                access_kind = "replay"
            self._output_store.record_output_access(lease, output, access_kind, now=now)
            payload = self._decrypt_output(lease, output)
            if state.window.add_pending(len(payload)) is StreamDisposition.SLOW_CONSUMER:
                state.close_code = "slow_consumer"
                state.gap_required = True
                self._record_bounded_gap(lease, output.source_cursor, "slow_consumer")
                yield _gap(output.cursor, "slow_consumer")
                return True
            yield _chunk(output, payload)
            state.window.flush_pending(len(payload))
            state.durable_cursor = output.cursor
            state.source_cursor = max(state.source_cursor, output.source_cursor)
        return False

    def _read_adapter(
        self,
        lease: ConsoleStreamLease,
        ref: ConsoleSessionRef,
        state: _StreamState,
    ) -> Generator[bytes, None, bool]:
        batch = self._adapter.read(
            ref,
            after_cursor=state.source_cursor,
            maximum_bytes=self._authority.policy.decoded_chunk_bytes,
        )
        if isinstance(batch, RecordProblem):
            state.close_code = "fenced"
            return True
        if batch.gap:
            reason = _gap_reason(batch.gap_reason)
            self._record_bounded_gap(lease, batch.source_cursor, reason)
            state.gap_required = True
            state.source_cursor = batch.source_cursor
            yield _gap(None, reason)
            return False
        if not batch.payload:
            self._sleeper(float(self._authority.policy.revocation_poll_seconds))
            return False
        if (
            state.window.admit_delivery(len(batch.payload), at=self._clock())
            is StreamDisposition.RATE_LIMITED
        ):
            state.close_code = "rate_limited"
            state.gap_required = True
            self._record_bounded_gap(lease, state.source_cursor, "rate_limited")
            yield _gap(None, "rate_limited")
            return True
        self._persist_batch(lease, batch)
        state.source_cursor = batch.source_cursor
        return False

    def _persist_batch(self, lease: ConsoleStreamLease, batch: ConsoleOutputBatch) -> None:
        object_id = uuid7(self._clock())
        aad = _object_aad(
            lease.grant.tenant_id,
            lease.grant.allowance_id,
            batch.source_cursor,
            object_id,
        )
        envelope = self._cipher.encrypt(object_id, batch.payload, aad=aad)
        self._output_store.append_output(
            lease.grant.allowance_id,
            lease.grant.tenant_id,
            batch.source_cursor,
            envelope,
            object_sha256=hashlib.sha256(batch.payload).digest(),
            decoded_bytes=len(batch.payload),
            now=self._clock(),
        )

    def _decrypt_output(self, lease: ConsoleStreamLease, output: StoredConsoleOutput) -> bytes:
        aad = _object_aad(
            lease.grant.tenant_id,
            lease.grant.allowance_id,
            output.source_cursor,
            output.envelope.object_id,
        )
        payload = self._cipher.decrypt(
            output.envelope,
            reader="console_output_reader",
            aad=aad,
        )
        if (
            len(payload) != output.decoded_bytes
            or not hashlib.sha256(payload).digest() == output.object_sha256
        ):
            raise RuntimeError("console output custody digest mismatch")
        return payload

    def _newest_durable_cursor(self, lease: ConsoleStreamLease) -> int:
        return self._output_store.latest_durable_cursor(
            lease.grant.allowance_id, lease.grant.tenant_id
        )

    def _record_bounded_gap(
        self,
        lease: ConsoleStreamLease,
        source_cursor: int,
        reason: Literal[
            "cursor_unavailable",
            "source_truncated",
            "unprovable_range",
            "slow_consumer",
            "rate_limited",
        ],
    ) -> None:
        self._output_store.record_gap(
            lease.grant.allowance_id,
            lease.grant.tenant_id,
            source_cursor,
            reason,
            now=self._clock(),
        )


def _observation_matches(ref: ConsoleSessionRef, observed: ConsoleBackendObservation) -> bool:
    return (
        observed.project_key == ref.project_key
        and observed.runtime_attempt_id == ref.runtime_attempt_id
        and observed.runner_id == ref.runner_id
        and observed.runner_epoch == ref.runner_epoch
        and observed.opaque_backend_ref == ref.opaque_backend_ref
        and observed.backend_incarnation == ref.backend_incarnation
    )


def _optional_event(event: bytes | None) -> Iterator[bytes]:
    if event is not None:
        yield event


def _object_aad(tenant_id: UUID, allowance_id: UUID, source_cursor: int, object_id: UUID) -> bytes:
    return f"{tenant_id}:{allowance_id}:{source_cursor}:{object_id}".encode()


def _chunk(output: StoredConsoleOutput, payload: bytes) -> bytes:
    return _sse(
        "chunk",
        {
            "type": "chunk",
            "cursor": output.cursor,
            "data": base64.b64encode(payload).decode("ascii"),
            "object_digest": f"sha256:{output.object_sha256.hex()}",
        },
        event_id=output.cursor,
    )


def _gap(next_cursor: int | None, reason: str) -> bytes:
    return _sse("gap", {"type": "gap", "reason": reason, "next_cursor": next_cursor})


def _closed(code: str) -> bytes:
    return _sse("closed", {"type": "closed", "code": code})


def _sse(event: str, payload: dict[str, object], *, event_id: int | None = None) -> bytes:
    prefix = b"" if event_id is None else f"id: {event_id}\n".encode()
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return prefix + f"event: {event}\ndata: {body}\n\n".encode()


def _gap_reason(
    value: str | None,
) -> Literal["cursor_unavailable", "source_truncated", "unprovable_range"]:
    if value == "source-truncated":
        return "source_truncated"
    if value == "cursor-unavailable":
        return "cursor_unavailable"
    return "unprovable_range"


def _problem(code: str, detail: str, status: int = 403) -> RecordProblem:
    return RecordProblem(code=code, detail=detail, status=status, title="Console operation refused")

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
    ConsoleGrantFacts,
    ConsoleGrantIdentifiers,
    ConsoleOutputBatch,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleStreamLease,
    ConsoleViewGrant,
    StoredConsoleGap,
    StoredConsoleOutput,
)
from ctower_kernel.console.output_store import PostgresConsoleOutputStore
from ctower_kernel.console.policy import (
    ConsoleStreamWindow,
    StreamDisposition,
    decide_view_grant,
)
from ctower_kernel.console.postgres import PostgresConsoleAuthority, StreamCloseCode
from ctower_kernel.console.stream import ConsoleEventStream, _drain_events, _TransportRequests
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


@dataclass(slots=True)
class _StreamState:
    window: ConsoleStreamWindow
    after_cursor: int
    durable_cursor: int
    source_cursor: int
    source_generation: int
    reconnect: bool
    close_code: StreamCloseCode = "client_disconnected"
    gap_required: bool = False


class _SlowConsumerError(Exception):
    """Private transport-to-kernel signal for one proven pending-byte overflow."""


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
        self._interruptible_sleep = sleeper is None

    def allow_session(
        self, actor: Actor, command: ConsoleSessionAllowCommand
    ) -> ConsoleSessionAllowance | RecordProblem:
        preflight = self._authority.preflight_allow_session(actor, command.session_ref)
        if preflight is not None:
            return preflight
        observation = self._adapter.inspect(command.session_ref)
        if isinstance(observation, RecordProblem):
            return observation
        return self._authority.allow_session(actor, command, observation, now=self._clock())

    def visible_sessions(self, actor: Actor) -> tuple[ConsoleSessionAllowance, ...] | RecordProblem:
        candidates = self._authority.visible_allowances(actor, now=self._clock())
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
            current = self._authority.visible_allowances(actor, now=self._clock())
            if isinstance(current, RecordProblem):
                return current
            if allowance.allowance_id not in {item.allowance_id for item in current}:
                continue
            visible.append(allowance)
        return tuple(visible)

    def mint_grant(
        self, actor: Actor, allowance_id: UUID, *, renewal: bool = False
    ) -> ConsoleViewGrant | RecordProblem:
        with self._authority.grant_decision_lock(actor, allowance_id):
            now = self._clock()
            facts = self._grant_facts_for_decision(actor, allowance_id, now=now)
            if isinstance(facts, RecordProblem):
                return facts
            previous = self._authority.previous_grant(actor, allowance_id)
            if renewal and previous is None:
                problem = _problem(
                    "console-renewal-unavailable", "There is no prior grant to renew.", 401
                )
                self._authority.record_denial(actor, allowance_id, problem.code, now=now)
                return problem
            outcome = decide_view_grant(
                facts,
                ConsoleGrantIdentifiers(grant_id=uuid7(now), nonce=uuid7(now)),
                policy=self._authority.policy,
                now=now,
                previous_grant=previous if renewal else None,
            )
            if isinstance(outcome, RecordProblem):
                self._authority.record_denial(actor, allowance_id, outcome.code, now=now)
                return outcome
            if not renewal and previous is not None and previous.expires_at > now:
                return _problem(
                    "console-grant-already-current",
                    "A current grant already exists; renew it explicitly.",
                    409,
                )
            self._authority.persist_grant(outcome, now=now)
            return outcome

    def _grant_facts_for_decision(
        self,
        actor: Actor,
        allowance_id: UUID,
        *,
        now: datetime,
    ) -> ConsoleGrantFacts | RecordProblem:
        ref = self._authority.preflight_access(actor, allowance_id, operation="grant", now=now)
        if isinstance(ref, RecordProblem):
            return ref
        observation = self._adapter.inspect(ref)
        if isinstance(observation, RecordProblem):
            self._authority.record_denial(actor, allowance_id, observation.code, now=now)
            return observation
        return self._authority.grant_facts(actor, allowance_id, observation, now=now)

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
        now = self._clock()
        ref = self._authority.preflight_access(actor, allowance_id, operation="stream", now=now)
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
        requests = _TransportRequests.create()
        events = self._stream_events(
            lease,
            ref,
            after_cursor=last_event_id or 0,
            reconnect=last_event_id is not None,
            transport_requests=requests,
        )
        return ConsoleEventStream(
            lease=lease,
            events=events,
            maximum_pending_bytes=self._authority.policy.pending_bytes,
            maximum_stall_seconds=self._authority.policy.revocation_poll_seconds,
            _slow_consumer_request=requests.request_slow_consumer,
            _client_disconnected_request=requests.request_client_disconnected,
            _slow_consumer_close=lambda: _drain_events(events),
            _client_disconnected_close=lambda: _drain_events(events),
        )

    def _stream_events(
        self,
        lease: ConsoleStreamLease,
        ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        reconnect: bool,
        transport_requests: _TransportRequests,
    ) -> Iterator[bytes]:
        state = self._stream_state(lease, after_cursor=after_cursor, reconnect=reconnect)
        try:
            newest = self._newest_durable_cursor(lease)
            initial_gap = self._initial_cursor_gap(lease, state, newest=newest)
            yield from _optional_event(initial_gap)
            while True:
                terminal = yield from self._stream_cycle(lease, ref, state, transport_requests)
                if terminal:
                    yield _closed(state.close_code)
                    return
        except _SlowConsumerError:
            state.close_code = "slow_consumer"
            state.gap_required = True
            gap_cursor = self._record_bounded_gap(
                lease,
                state.source_cursor,
                state.source_generation,
                "slow_consumer",
            )
            yield _gap(gap_cursor, "slow_consumer", event_id=gap_cursor)
            yield _closed(state.close_code)
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

    def _stream_cycle(
        self,
        lease: ConsoleStreamLease,
        ref: ConsoleSessionRef,
        state: _StreamState,
        transport_requests: _TransportRequests,
    ) -> Generator[bytes, None, bool]:
        if transport_requests.client_disconnected.is_set():
            state.close_code = "client_disconnected"
            return True
        if transport_requests.slow_consumer.is_set():
            raise _SlowConsumerError
        status = self._active_close_reason(lease, ref)
        if status is not None:
            state.close_code = status
            return True
        access_kind: Literal["open", "reconnect", "replay", "forensic"] = (
            "reconnect" if state.reconnect else "open"
        )
        if state.durable_cursor != state.after_cursor:
            access_kind = "replay"
        replay = self._output_store.outputs_after(
            lease,
            state.durable_cursor,
            access_kind,
            now=self._clock(),
        )
        if isinstance(replay, RecordProblem):
            yield self._custody_gap(lease, state)
            return True
        if replay:
            return (yield from self._replay_outputs(lease, ref, state, replay))
        return (
            yield from self._read_adapter(lease, ref, state, transport_requests=transport_requests)
        )

    def _active_close_reason(
        self, lease: ConsoleStreamLease, ref: ConsoleSessionRef
    ) -> StreamCloseCode | None:
        status = self._authority.stream_close_reason(lease, now=self._clock())
        if status is not None:
            return status
        observation = self._adapter.inspect(ref)
        if isinstance(observation, RecordProblem) or not _observation_matches(ref, observation):
            return "fenced"
        return None

    def _custody_gap(self, lease: ConsoleStreamLease, state: _StreamState) -> bytes:
        state.close_code = "output_unavailable"
        state.gap_required = True
        gap_cursor = self._record_bounded_gap(
            lease,
            state.source_cursor,
            state.source_generation,
            "cursor_unavailable",
        )
        return _gap(gap_cursor, "cursor_unavailable", event_id=gap_cursor)

    def _stream_state(
        self, lease: ConsoleStreamLease, *, after_cursor: int, reconnect: bool
    ) -> _StreamState:
        policy = self._authority.policy
        source_cursor, source_generation = self._output_store.latest_source_position(
            lease.grant.allowance_id, lease.grant.tenant_id
        )
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
            source_cursor=source_cursor,
            source_generation=source_generation,
            reconnect=reconnect,
        )

    def _initial_cursor_gap(
        self, lease: ConsoleStreamLease, state: _StreamState, *, newest: int
    ) -> bytes | None:
        if state.durable_cursor <= newest and self._output_store.owns_cursor(
            lease.grant.allowance_id,
            lease.grant.tenant_id,
            state.durable_cursor,
        ):
            return None
        gap_cursor = self._record_bounded_gap(
            lease,
            state.source_cursor,
            state.source_generation,
            "unprovable_range",
        )
        state.gap_required = True
        state.durable_cursor = gap_cursor
        return _gap(gap_cursor, "unprovable_range", event_id=gap_cursor)

    def _replay_outputs(
        self,
        lease: ConsoleStreamLease,
        ref: ConsoleSessionRef,
        state: _StreamState,
        outputs: tuple[StoredConsoleOutput | StoredConsoleGap, ...],
    ) -> Generator[bytes, None, bool]:
        now = self._clock()
        for output in outputs:
            close_reason = self._active_close_reason(lease, ref)
            if close_reason is not None:
                state.close_code = close_reason
                return True
            if isinstance(output, StoredConsoleGap):
                yield _gap(output.cursor, output.reason, event_id=output.cursor)
                state.durable_cursor = output.cursor
                state.source_cursor = output.source_cursor
                state.source_generation = output.source_generation
                state.gap_required = True
                continue
            if (
                state.window.admit_replay(output.decoded_bytes, at=now)
                is not StreamDisposition.ADMITTED
            ):
                state.close_code = "rate_limited"
                state.gap_required = True
                gap_cursor = self._record_bounded_gap(
                    lease,
                    output.source_cursor,
                    output.source_generation,
                    "rate_limited",
                )
                yield _gap(gap_cursor, "rate_limited", event_id=gap_cursor)
                return True
            try:
                payload = self._decrypt_output(lease, output)
            except (RuntimeError, ValueError):
                state.close_code = "output_unavailable"
                state.gap_required = True
                gap_cursor = self._record_bounded_gap(
                    lease,
                    output.source_cursor,
                    output.source_generation,
                    "cursor_unavailable",
                )
                yield _gap(gap_cursor, "cursor_unavailable", event_id=gap_cursor)
                return True
            yield _chunk(output, payload)
            state.durable_cursor = output.cursor
            state.source_cursor = max(state.source_cursor, output.source_cursor)
            state.source_generation = output.source_generation
        return False

    def _read_adapter(
        self,
        lease: ConsoleStreamLease,
        ref: ConsoleSessionRef,
        state: _StreamState,
        *,
        transport_requests: _TransportRequests,
    ) -> Generator[bytes, None, bool]:
        with self._output_store.collection_lock(lease.grant.allowance_id, lease.grant.tenant_id):
            source_cursor, source_generation = self._output_store.latest_source_position(
                lease.grant.allowance_id, lease.grant.tenant_id
            )
            if (source_cursor, source_generation) != (
                state.source_cursor,
                state.source_generation,
            ):
                state.source_cursor = source_cursor
                state.source_generation = source_generation
                return False
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
                state.source_generation += 1
                gap_cursor = self._output_store.record_gap_locked(
                    lease.grant.allowance_id,
                    lease.grant.tenant_id,
                    source_cursor=batch.source_cursor,
                    source_generation=state.source_generation,
                    reason=reason,
                    advances_source_position=True,
                    now=self._clock(),
                )
                state.gap_required = True
                state.durable_cursor = gap_cursor
                state.source_cursor = batch.source_cursor
                yield _gap(gap_cursor, reason, event_id=gap_cursor)
                return False
            if not batch.payload:
                self._sleep_to_next_authority_check(lease, transport_requests)
                return False
            if (
                state.window.admit_delivery(len(batch.payload), at=self._clock())
                is StreamDisposition.RATE_LIMITED
            ):
                state.close_code = "rate_limited"
                state.gap_required = True
                gap_cursor = self._output_store.record_gap_locked(
                    lease.grant.allowance_id,
                    lease.grant.tenant_id,
                    source_cursor=state.source_cursor,
                    source_generation=state.source_generation,
                    reason="rate_limited",
                    advances_source_position=False,
                    now=self._clock(),
                )
                yield _gap(gap_cursor, "rate_limited", event_id=gap_cursor)
                return True
            self._persist_batch(lease, batch, source_generation=state.source_generation)
            state.source_cursor = batch.source_cursor
        return False

    def _sleep_to_next_authority_check(
        self, lease: ConsoleStreamLease, transport_requests: _TransportRequests
    ) -> None:
        remaining = max(0.0, (lease.grant.expires_at - self._clock()).total_seconds())
        delay = min(float(self._authority.policy.revocation_poll_seconds), remaining)
        if self._interruptible_sleep:
            transport_requests.wake.wait(delay)
        else:
            self._sleeper(delay)

    def _persist_batch(
        self,
        lease: ConsoleStreamLease,
        batch: ConsoleOutputBatch,
        *,
        source_generation: int,
    ) -> None:
        object_id = uuid7(self._clock())
        aad = _object_aad(
            lease.grant.tenant_id,
            lease.grant.allowance_id,
            batch.source_cursor,
            source_generation,
            object_id,
        )
        envelope = self._cipher.encrypt(object_id, batch.payload, aad=aad)
        self._output_store.append_output(
            lease.grant.allowance_id,
            lease.grant.tenant_id,
            batch.source_cursor,
            source_generation,
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
            output.source_generation,
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
        source_generation: int,
        reason: Literal[
            "cursor_unavailable",
            "source_truncated",
            "unprovable_range",
            "slow_consumer",
            "rate_limited",
        ],
    ) -> int:
        return self._output_store.record_gap(
            lease.grant.allowance_id,
            lease.grant.tenant_id,
            source_cursor,
            source_generation,
            reason,
            advances_source_position=False,
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


def _object_aad(
    tenant_id: UUID,
    allowance_id: UUID,
    source_cursor: int,
    source_generation: int,
    object_id: UUID,
) -> bytes:
    return (f"{tenant_id}:{allowance_id}:{source_generation}:{source_cursor}:{object_id}").encode()


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


def _gap(next_cursor: int | None, reason: str, *, event_id: int | None = None) -> bytes:
    return _sse(
        "gap",
        {"type": "gap", "reason": reason, "next_cursor": next_cursor},
        event_id=event_id,
    )


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

"""Lower Record Interface for canonical command and event commits."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from random import SystemRandom
from threading import Timer
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.record import RecordProblem
from ctower_kernel.record._commands import reserve_command
from ctower_kernel.record._event_store import EventSubject, append_event, enqueue_event
from ctower_kernel.record.events import EventEnvelope
from ctower_kernel.record.project_scope import (
    _human_project_grants,
    _operator_scope_allowed,
    _scope_principal,
    _seat_project_grants,
)
from ctower_kernel.telemetry import TelemetryContext

__all__ = [
    "AmbiguousCommitExhaustedError",
    "EventCommit",
    "RecordTransaction",
    "authority_connection",
    "lock_project_delivery_scope",
    "project_delivery_scope_transaction",
    "project_mutation_refusal",
    "project_scope_refusal",
    "recover_ambiguous_commit",
]

_LOGGER = logging.getLogger(__name__)
_RANDOM = SystemRandom()
_CONNECT_TIMEOUT_SECONDS = 2
_MAXIMUM_ATTEMPTS = 3
_MAXIMUM_ELAPSED_SECONDS = 20.0
_INITIAL_BACKOFF_SECONDS = 0.05
_MAXIMUM_BACKOFF_SECONDS = 0.5


def project_scope_refusal(
    connection: psycopg.Connection[dict[str, object]],
    *,
    tenant_id: UUID,
    principal_id: UUID,
    project_keys: tuple[str, ...],
    command_id: UUID | None = None,
    operator_only: bool = False,
    allow_operator_read: bool = False,
) -> RecordProblem | None:
    """Refuse a non-operator principal reaching outside its persisted project grants.

    This is the one place `project-scope-denied` is constructed. The mutation seam
    below resolves ticket ownership first and then asks exactly this question, so a
    read and a write can never disagree about who may see one project's facts. Read
    callers explicitly opt into persisted operator authority; mutation callers retain
    the closed default. A disabled principal never reaches either authority path.
    """

    principal = _scope_principal(connection, tenant_id, principal_id)
    if principal is not None and bool(principal["disabled"]):
        return _project_scope_denied(command_id)
    human_grants = _human_project_grants(principal)
    if _operator_scope_allowed(principal, human_grants, allow_operator_read=allow_operator_read):
        return None
    requested = set(project_keys)
    if not requested and not operator_only:
        return None
    grants = (human_grants or set()) | _seat_project_grants(connection, tenant_id, principal_id)
    if not operator_only and requested <= grants:
        return None
    return _project_scope_denied(command_id)


def _project_scope_denied(command_id: UUID | None) -> RecordProblem:
    return RecordProblem(
        code="project-scope-denied",
        detail="The authenticated project seat cannot reach a ticket from another project.",
        status=403,
        title="Project scope denied",
        command_id=command_id,
    )


def project_mutation_refusal(
    connection: psycopg.Connection[dict[str, object]],
    *,
    tenant_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    ticket_ids: tuple[UUID, ...] = (),
    project_keys: tuple[str, ...] = (),
) -> RecordProblem | None:
    """Refuse a non-operator mutation outside its persisted project-seat grant."""

    rows = connection.execute(
        """
        SELECT DISTINCT project_key
        FROM tickets
        WHERE tenant_id = %s AND ticket_id = ANY(%s)
        """,
        (tenant_id, list(ticket_ids)),
    ).fetchall()
    requested = {str(row["project_key"]) for row in rows} | set(project_keys)
    return project_scope_refusal(
        connection,
        tenant_id=tenant_id,
        principal_id=principal_id,
        project_keys=tuple(requested),
        command_id=command_id,
    )


@dataclass(frozen=True, slots=True)
class EventCommit:
    """One canonical event/outbox pair in a Record-owned atomic batch."""

    event: EventEnvelope
    outbox_id: UUID
    topic: str = "record.events"


class _AuthorityConnection(psycopg.Connection[dict[str, object]]):
    """Connection whose remote-apply commit wait has a cancellation watchdog."""

    _commit_deadline_seconds: float | None = None

    def arm_commit_deadline(self, milliseconds: int) -> None:
        self._commit_deadline_seconds = milliseconds / 1000

    def commit(self) -> None:
        deadline = self._commit_deadline_seconds
        self._commit_deadline_seconds = None
        if deadline is None:
            super().commit()
            return
        watchdog = Timer(deadline, self._cancel_commit_wait)
        watchdog.daemon = True
        watchdog.start()
        try:
            super().commit()
        finally:
            watchdog.cancel()

    def _cancel_commit_wait(self) -> None:
        with suppress(psycopg.Error):
            self.cancel_safe(timeout=_CONNECT_TIMEOUT_SECONDS)


def authority_connection(dsn: str) -> psycopg.Connection[dict[str, object]]:
    """Open the only connection type allowed to issue bounded authority commits."""

    return cast(
        psycopg.Connection[dict[str, object]],
        _AuthorityConnection.connect(
            dsn,
            connect_timeout=_CONNECT_TIMEOUT_SECONDS,
            row_factory=dict_row,
        ),
    )


def arm_remote_apply_deadline(
    connection: psycopg.Connection[dict[str, object]], milliseconds: int
) -> None:
    """Arm the connection watchdog before a remote-apply transaction commits."""

    if not isinstance(connection, _AuthorityConnection):
        raise TypeError("remote-apply authority requires a deadline-capable connection")
    connection.arm_commit_deadline(milliseconds)


class AmbiguousCommitExhaustedError(RuntimeError):
    """A retryable ambiguous-commit recovery spent its finite policy."""

    def __init__(
        self,
        *,
        attempt_count: int,
        elapsed_seconds: float,
        last_failure: psycopg.Error,
    ) -> None:
        self.attempt_count = attempt_count
        self.elapsed_seconds = elapsed_seconds
        self.last_failure = last_failure
        sqlstate = last_failure.sqlstate or "unavailable"
        super().__init__(
            f"ambiguous-commit recovery exhausted after {attempt_count} attempts in "
            f"{elapsed_seconds:.3f}s; last failure {type(last_failure).__name__} "
            f"SQLSTATE {sqlstate}"
        )


def recover_ambiguous_commit[Outcome](operation: Callable[[], Outcome]) -> Outcome:
    """Discard the failed connection and replay through command idempotency authority.

    Every attempt re-runs the caller's full reserve-then-mutate ``operation``, which
    checks the command's idempotency key before it mutates anything (see
    ``reserve_command``). A retry therefore can only ever observe its own prior
    commit through that key -- it can never re-apply it -- so bounding the number of
    attempts or spacing them out with backoff cannot turn an ambiguous commit into a
    double-apply; the same idempotency check runs before every attempt, first or last.
    """

    started = time.monotonic()
    last_failure: psycopg.Error | None = None
    attempt = 0
    for attempt in range(1, _MAXIMUM_ATTEMPTS + 1):
        try:
            return operation()
        except (psycopg.errors.QueryCanceled, psycopg.OperationalError) as error:
            last_failure = error
            if not _back_off(started, attempt):
                break
    if last_failure is None:
        raise RuntimeError("ambiguous commit retry policy ended without a classified failure")
    raise _ambiguous_commit_exhausted(started, attempt, last_failure) from last_failure


def _back_off(started: float, attempt: int) -> bool:
    """Sleep one capped, jittered, deadline-constrained backoff interval."""

    if attempt >= _MAXIMUM_ATTEMPTS:
        return False
    remaining = _MAXIMUM_ELAPSED_SECONDS - (time.monotonic() - started)
    if remaining <= 0:
        return False
    ceiling = min(
        _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
        _MAXIMUM_BACKOFF_SECONDS,
        remaining,
    )
    time.sleep(_RANDOM.uniform(ceiling / 2, ceiling))
    return time.monotonic() - started < _MAXIMUM_ELAPSED_SECONDS


def _ambiguous_commit_exhausted(
    started: float, attempt_count: int, last_failure: psycopg.Error
) -> AmbiguousCommitExhaustedError:
    elapsed = time.monotonic() - started
    exhausted = AmbiguousCommitExhaustedError(
        attempt_count=attempt_count,
        elapsed_seconds=elapsed,
        last_failure=last_failure,
    )
    _LOGGER.error(
        "ambiguous commit recovery exhausted",
        extra={
            "attempt_count": attempt_count,
            "elapsed_seconds": elapsed,
            "last_failure_type": type(last_failure).__name__,
            "last_sqlstate": last_failure.sqlstate,
        },
    )
    return exhausted


def lock_project_delivery_scope(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
) -> None:
    """Fence mutable Catalog and Project Delivery heads for one project."""

    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (_project_delivery_scope(tenant_id, project_key),),
    )


@contextmanager
def project_delivery_scope_transaction(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
) -> Iterator[None]:
    """Acquire the project fence before opening a fixed-snapshot transaction."""

    if connection.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
        raise RuntimeError("project delivery scope requires an idle connection")
    previous_autocommit = connection.autocommit
    connection.autocommit = True
    connection.execute(
        "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
        (_project_delivery_scope(tenant_id, project_key),),
    )
    connection.autocommit = False
    try:
        yield
        connection.commit()
    except BaseException:
        with suppress(psycopg.Error):
            connection.rollback()
        raise
    finally:
        if not connection.closed:
            with suppress(psycopg.Error):
                if not connection.autocommit:
                    connection.rollback()
                    connection.autocommit = True
                connection.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    (_project_delivery_scope(tenant_id, project_key),),
                )
            connection.autocommit = previous_autocommit


def _project_delivery_scope(tenant_id: UUID, project_key: str) -> str:
    return f"project-delivery:{tenant_id}:{project_key}"


class RecordTransaction:
    """Keep idempotency ordering and canonical append choreography Record-owned."""

    def __init__(self, connection: psycopg.Connection[dict[str, object]]) -> None:
        self._connection = connection
        self._mode: str | None = None

    def reserve(
        self,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
    ) -> dict[str, object] | RecordProblem | None:
        """Reserve a principal command key before any aggregate read."""

        self._configure_authority_commit()
        return reserve_command(self._connection, principal_id, command_id, request_digest)

    def reserve_ticket_mutation(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
        ticket_ids: tuple[UUID, ...] = (),
        *,
        project_keys: tuple[str, ...] = (),
        now: datetime,
    ) -> dict[str, object] | RecordProblem | None:
        """Reserve, replay, then enforce the one authoritative ticket-project predicate."""

        existing = self.reserve(principal_id, command_id, request_digest)
        if existing is not None:
            return existing
        return self.require_project_mutation(
            tenant_id,
            principal_id,
            command_id,
            request_digest,
            ticket_ids=ticket_ids,
            project_keys=project_keys,
            now=now,
        )

    def require_project_mutation(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
        *,
        ticket_ids: tuple[UUID, ...] = (),
        project_keys: tuple[str, ...] = (),
        now: datetime,
    ) -> RecordProblem | None:
        """Persist the transaction-seam project refusal before any authority write."""

        problem = project_mutation_refusal(
            self._connection,
            tenant_id=tenant_id,
            principal_id=principal_id,
            command_id=command_id,
            ticket_ids=ticket_ids,
            project_keys=project_keys,
        )
        if problem is None:
            return None
        self.refuse(
            tenant_id,
            principal_id,
            command_id,
            request_digest,
            problem,
            now=now,
        )
        return problem

    def require_durable_subjects(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
        subjects: tuple[EventSubject, ...],
        *,
        now: datetime,
    ) -> RecordProblem | None:
        """Serialize subject heads before aggregate locks and refuse unacknowledged heads.

        The global order is sorted absent-head advisory locks, sorted existing
        ``durability_subject_heads`` row locks, then caller-owned aggregate locks. The
        transaction retains every lock through refusal or committed head movement.
        """

        if self._mode != "cutover_rpo0":
            return None
        ordered = self._ordered_subjects(subjects)
        self._lock_absent_subject_identities(tenant_id, ordered)
        pending = [
            (subject_kind, subject_id)
            for subject_kind, subject_id in ordered
            if self._lock_subject_head(tenant_id, subject_kind, subject_id)
        ]
        if not pending:
            return None
        problem = RecordProblem(
            code="durability_pending",
            detail="A required subject head is not acknowledged on the named standby.",
            status=409,
            title="Subject durability pending",
            command_id=command_id,
            unmet_facts=tuple(f"{kind}:{subject_id}" for kind, subject_id in pending),
        )
        self.refuse(
            tenant_id,
            principal_id,
            command_id,
            request_digest,
            problem,
            now=now,
        )
        return problem

    def commit(
        self,
        event: EventEnvelope,
        *,
        outbox_id: UUID,
        response_body: dict[str, object],
        status_code: int,
        telemetry: TelemetryContext,
        now: datetime,
        subjects: tuple[EventSubject, ...] = (),
        topic: str = "record.events",
    ) -> None:
        """Append one event, exact result, and outbox row in the caller's transaction."""

        self.commit_batch(
            (EventCommit(event=event, outbox_id=outbox_id, topic=topic),),
            response_body=response_body,
            status_code=status_code,
            telemetry=telemetry,
            now=now,
            subjects=subjects,
        )

    def commit_batch(
        self,
        commits: tuple[EventCommit, ...],
        *,
        response_body: dict[str, object],
        status_code: int,
        telemetry: TelemetryContext,
        now: datetime,
        subjects: tuple[EventSubject, ...] = (),
    ) -> None:
        """Append one command's events, exact result, and outbox rows atomically."""

        first = self._validate_batch(commits)
        ordered_subjects = self._ordered_subjects(subjects)
        for item in commits:
            append_event(self._connection, item.event, subjects=ordered_subjects)
        self._connection.execute(
            """
            INSERT INTO command_results (
                tenant_id, principal_id, client_command_id, request_sha256, status_code,
                response_body, event_ids, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                first.tenant_id,
                first.actor_principal_id,
                first.client_command_id,
                first.request_sha256,
                status_code,
                Jsonb(response_body),
                [item.event.event_id for item in commits],
                now,
            ),
        )
        for item in commits:
            enqueue_event(
                self._connection,
                item.outbox_id,
                item.event,
                telemetry,
                now,
                topic=item.topic,
            )
        self._move_subject_heads(commits[-1].event, ordered_subjects, now=now)

    @staticmethod
    def _validate_batch(commits: tuple[EventCommit, ...]) -> EventEnvelope:
        if not commits:
            raise ValueError("event batch must not be empty")
        first = commits[0].event
        identity = (
            first.tenant_id,
            first.actor_principal_id,
            first.client_command_id,
            first.request_sha256,
        )
        if any(
            (
                item.event.tenant_id,
                item.event.actor_principal_id,
                item.event.client_command_id,
                item.event.request_sha256,
            )
            != identity
            for item in commits[1:]
        ):
            raise ValueError("event batch must belong to one exact command")
        if len({item.event.event_id for item in commits}) != len(commits):
            raise ValueError("event batch IDs must be unique")
        return first

    def commit_control(
        self,
        event: EventEnvelope,
        *,
        outbox_id: UUID,
        response_body: dict[str, object],
        status_code: int,
        now: datetime,
        topic: str,
        job_id: UUID | None = None,
    ) -> None:
        """Append a trusted control-plane event without exporting Telemetry upward."""

        trace = hashlib.sha256(event.client_command_id.bytes + b"trace").hexdigest()
        telemetry = TelemetryContext(
            schema="ctower.telemetry-context/v1",
            trace_id=trace[:32],
            span_id=trace[32:48],
            trace_flags=1,
            correlation_id=str(event.correlation_id),
            causation_id=str(event.client_command_id),
            tenant_id=str(event.tenant_id),
            actor_id=str(event.actor_principal_id),
            command_id=str(event.client_command_id),
            job_id=str(job_id) if job_id is not None else None,
        )
        self.commit(
            event,
            outbox_id=outbox_id,
            response_body=response_body,
            status_code=status_code,
            telemetry=telemetry,
            now=now,
            topic=topic,
        )

    def refuse(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
        problem: RecordProblem,
        *,
        now: datetime,
    ) -> None:
        """Persist one exact typed refusal without an event or authoritative mutation."""

        self._connection.execute(
            """
            INSERT INTO command_results (
                tenant_id, principal_id, client_command_id, request_sha256, status_code,
                response_body, event_ids, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                principal_id,
                command_id,
                request_digest,
                problem.status,
                Jsonb(problem.response_payload()),
                [],
                now,
            ),
        )

    def _configure_authority_commit(self) -> None:
        policy = self._connection.execute(
            """
            SELECT mode, commit_deadline_ms
            FROM durability_policy_state WHERE singleton
            """
        ).fetchone()
        if policy is None:
            raise RuntimeError("durability policy is unavailable")
        self._mode = str(policy["mode"])
        deadline_ms = int(cast(int, policy["commit_deadline_ms"]))
        self._connection.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (f"{deadline_ms}ms",),
        )
        if self._mode != "cutover_rpo0":
            return
        self._connection.execute("SELECT set_config('synchronous_commit', 'remote_apply', true)")
        arm_remote_apply_deadline(self._connection, deadline_ms)

    @staticmethod
    def _ordered_subjects(subjects: tuple[EventSubject, ...]) -> tuple[EventSubject, ...]:
        return tuple(sorted(set(subjects), key=lambda item: (item[0], item[1].int)))

    def _lock_absent_subject_identities(
        self, tenant_id: UUID, subjects: tuple[EventSubject, ...]
    ) -> None:
        for subject_kind, subject_id in subjects:
            exists = self._connection.execute(
                """
                SELECT 1 FROM durability_subject_heads
                WHERE tenant_id = %s AND subject_kind = %s AND subject_id = %s
                """,
                (tenant_id, subject_kind, subject_id),
            ).fetchone()
            if exists is not None:
                continue
            identity = f"{tenant_id}:{subject_kind}:{subject_id}"
            self._connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (identity,),
            )

    def _lock_subject_head(self, tenant_id: UUID, subject_kind: str, subject_id: UUID) -> bool:
        row = self._connection.execute(
            """
            SELECT acknowledgement.acceptance_position
            FROM durability_subject_heads AS head
            LEFT JOIN durability_acknowledgements AS acknowledgement
              ON acknowledgement.tenant_id = head.tenant_id
             AND acknowledgement.principal_id = head.principal_id
             AND acknowledgement.client_command_id = head.client_command_id
            WHERE head.tenant_id = %s AND head.subject_kind = %s AND head.subject_id = %s
            FOR UPDATE OF head
            """,
            (tenant_id, subject_kind, subject_id),
        ).fetchone()
        return row is not None and row["acceptance_position"] is None

    def _move_subject_heads(
        self, event: EventEnvelope, subjects: tuple[EventSubject, ...], *, now: datetime
    ) -> None:
        if not subjects:
            return
        self._connection.cursor().executemany(
            """
            INSERT INTO durability_subject_heads (
                tenant_id, subject_kind, subject_id, principal_id, client_command_id, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, subject_kind, subject_id) DO UPDATE
            SET principal_id = EXCLUDED.principal_id,
                client_command_id = EXCLUDED.client_command_id,
                updated_at = EXCLUDED.updated_at
            """,
            (
                (
                    event.tenant_id,
                    subject_kind,
                    subject_id,
                    event.actor_principal_id,
                    event.client_command_id,
                    now,
                )
                for subject_kind, subject_id in subjects
            ),
        )

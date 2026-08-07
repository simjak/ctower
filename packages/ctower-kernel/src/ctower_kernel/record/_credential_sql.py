"""Record-owned project-seat credential append and authentication storage."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.credentials import (
    CredentialScope,
    SeatCredentialIssue,
    SeatCredentialIssuedPayload,
    SeatCredentialReceipt,
    SeatCredentialRevocation,
    SeatCredentialRevokedPayload,
)
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.identifiers import uuid7 as _uuid7
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["actor_for_credential", "issue_seat_credential", "revoke_seat_credential"]

_ZERO_HASH = bytes(32)

# Presence of a 0039-created table is a monotonic fact: schema generation only advances,
# never rolls back, so a positive probe is cached for the dsn's process lifetime and never
# re-asked. A negative probe stays cheap enough — one zero-privilege catalog lookup on the
# connection already open for the call, no separate round trip — to retry on every request,
# so a schema-forward runtime starts serving the instant migration 0039 lands (gh#101),
# without needing a restart to notice.
_seat_credential_generation_confirmed: set[str] = set()


def _seat_credential_generation_refusal(
    connection: psycopg.Connection[dict[str, object]],
    dsn: str,
    *,
    command_id: UUID | None = None,
) -> RecordProblem | None:
    """Refuse by name, in place of UndefinedTable, until generation 0039 is live."""

    if dsn in _seat_credential_generation_confirmed:
        return None
    row = connection.execute(
        "SELECT to_regclass('public.seat_credential_issuances') IS NOT NULL AS available"
    ).fetchone()
    if row is not None and bool(row["available"]):
        _seat_credential_generation_confirmed.add(dsn)
        return None
    return RecordProblem(
        code="credential-authentication-unavailable",
        detail="Credential authentication requires generation >= 0039.",
        status=503,
        title="Credential authentication unavailable",
        command_id=command_id,
    )


def actor_for_credential(dsn: str, credential_digest: bytes) -> Actor | RecordProblem | None:
    """Resolve active bearer authority and preserve a named revocation refusal."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        unavailable = _seat_credential_generation_refusal(connection, dsn)
        if unavailable is not None:
            return unavailable
        row = connection.execute(
            """
            SELECT principal.principal_id, principal.tenant_id, principal.kind,
                principal.disabled, credential.revoked_at,
                issuance.credential_id AS seat_credential_id,
                seat.project_key,
                array_agg(scope.scope ORDER BY scope.scope)
                    FILTER (WHERE scope.scope IS NOT NULL) AS credential_scopes,
                revocation.credential_id IS NOT NULL AS seat_credential_revoked
            FROM principal_credentials AS credential
            JOIN principals AS principal
              ON principal.principal_id = credential.principal_id
             AND principal.tenant_id = credential.tenant_id
            LEFT JOIN seat_credential_issuances AS issuance
              ON issuance.credential_id = credential.credential_id
             AND issuance.tenant_id = credential.tenant_id
            LEFT JOIN seat_credential_revocations AS revocation
              ON revocation.credential_id = issuance.credential_id
             AND revocation.tenant_id = issuance.tenant_id
            LEFT JOIN seat_credential_scopes AS scope
              ON scope.credential_id = issuance.credential_id
             AND scope.tenant_id = issuance.tenant_id
            LEFT JOIN project_seats AS seat
              ON seat.principal_id = principal.principal_id
             AND seat.tenant_id = principal.tenant_id
            WHERE credential.credential_digest = %s
            GROUP BY principal.principal_id, principal.tenant_id, principal.kind,
                principal.disabled, credential.revoked_at, issuance.credential_id,
                seat.project_key, revocation.credential_id
            """,
            (credential_digest,),
        ).fetchone()
    if row is None:
        return None
    if row["revoked_at"] is not None or bool(row["seat_credential_revoked"]):
        return RecordProblem(
            code="credential-revoked",
            detail="The presented project-seat credential has been revoked.",
            status=401,
            title="Credential revoked",
        )
    if bool(row["disabled"]) or str(row["kind"]) not in {
        PrincipalKind.OPERATOR.value,
        PrincipalKind.COMMANDER.value,
    }:
        return None
    scopes = tuple(
        str(value) for value in cast(list[object] | None, row["credential_scopes"]) or []
    )
    project_key = cast(str | None, row["project_key"])
    return Actor(
        principal_id=cast(UUID, row["principal_id"]),
        tenant_id=cast(UUID, row["tenant_id"]),
        kind=PrincipalKind(str(row["kind"])),
        project_grants=frozenset((project_key,)) if project_key is not None else frozenset(),
        credential_scopes=frozenset(CredentialScope(scope) for scope in scopes),
        seat_credential_id=cast(UUID | None, row["seat_credential_id"]),
    )


def issue_seat_credential(
    dsn: str,
    actor: Actor,
    command: SeatCredentialIssue,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SeatCredentialReceipt | RecordProblem:
    """Create or reuse a stable Commander seat and append one credential issuance."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _credential_reservation(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            refusal_code="credential-issuance-refused",
            refusal_detail="Seat credential issuance requires operator authority.",
            now=now,
        )
        if reserved is not None:
            return reserved
        return _append_issuance(
            connection,
            transaction,
            actor,
            command,
            dsn=dsn,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def revoke_seat_credential(
    dsn: str,
    actor: Actor,
    command: SeatCredentialRevocation,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SeatCredentialReceipt | RecordProblem:
    """Append a revocation that authentication observes in the same commit."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _credential_reservation(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            refusal_code="credential-revocation-refused",
            refusal_detail="Seat credential revocation requires operator authority.",
            now=now,
        )
        if reserved is not None:
            return reserved
        return _append_revocation(
            connection,
            transaction,
            actor,
            command,
            dsn=dsn,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _credential_reservation(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    *,
    refusal_code: str,
    refusal_detail: str,
    now: datetime,
) -> SeatCredentialReceipt | RecordProblem | None:
    existing = transaction.reserve(actor.principal_id, command_id, request_digest)
    if isinstance(existing, RecordProblem):
        return existing
    if existing is not None:
        return _receipt_from_payload(existing)
    if actor.kind is PrincipalKind.OPERATOR:
        return None
    problem = _problem(refusal_code, 403, refusal_detail, command_id)
    return _refuse(transaction, actor, command_id, request_digest, problem, now=now)


def _append_issuance(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: SeatCredentialIssue,
    *,
    dsn: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SeatCredentialReceipt | RecordProblem:
    # Not persisted through `_refuse`: command_results only ever holds a committed
    # success or a client (4xx) refusal (migration 0011's check constraint), because
    # both are durable facts about this exact command. A generation gap is neither —
    # it is a transient fact about the environment, so a retry of this same command
    # once generation 0039 lands must actually proceed, not replay a cached 503.
    unavailable = _seat_credential_generation_refusal(
        connection, dsn, command_id=command.client_command_id
    )
    if unavailable is not None:
        return unavailable
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"seat:{actor.tenant_id}:{command.project_key}:{command.seat_key}",),
    )
    conflict = _issuance_conflict(connection, actor, command)
    if conflict is not None:
        return _refuse(
            transaction, actor, command.client_command_id, request_digest, conflict, now=now
        )
    principal_id = _seat_principal(connection, actor, command, now=now)
    credential_id, event_id, outbox_id = (_uuid7(now) for _ in range(3))
    result = _issuance_receipt(command, credential_id, event_id, principal_id)
    _insert_issuance(connection, actor, command, result, now=now)
    event = _issuance_event(actor, command, result, request_digest, telemetry, now=now)
    transaction.commit(
        event,
        outbox_id=outbox_id,
        response_body=result.response_payload(),
        status_code=201,
        telemetry=telemetry,
        now=now,
        subjects=(("access", credential_id),),
    )
    return result


def _issuance_receipt(
    command: SeatCredentialIssue,
    credential_id: UUID,
    event_id: UUID,
    principal_id: UUID,
) -> SeatCredentialReceipt:
    return SeatCredentialReceipt(
        command_id=command.client_command_id,
        credential_id=credential_id,
        event_ids=(event_id,),
        principal_id=principal_id,
        project_key=command.project_key,
        scopes=command.scopes,
        seat_key=command.seat_key,
        state="active",
    )


def _insert_issuance(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SeatCredentialIssue,
    result: SeatCredentialReceipt,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO principal_credentials (
            credential_id, principal_id, tenant_id, credential_digest, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            result.credential_id,
            result.principal_id,
            actor.tenant_id,
            command.credential_digest,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO seat_credential_issuances (
            credential_id, tenant_id, principal_id, credential_ref,
            event_id, issued_by, issued_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.credential_id,
            actor.tenant_id,
            result.principal_id,
            command.credential_ref,
            result.event_ids[0],
            actor.principal_id,
            now,
        ),
    )
    connection.cursor().executemany(
        """
        INSERT INTO seat_credential_scopes (credential_id, tenant_id, scope)
        VALUES (%s, %s, %s)
        """,
        ((result.credential_id, actor.tenant_id, scope.value) for scope in command.scopes),
    )


def _issuance_event(
    actor: Actor,
    command: SeatCredentialIssue,
    result: SeatCredentialReceipt,
    request_digest: bytes,
    telemetry: TelemetryContext,
    *,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=result.credential_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=result.event_ids[0],
        kind=EventKind.SEAT_CREDENTIAL_ISSUED,
        origin=EventOrigin.API,
        payload=SeatCredentialIssuedPayload(
            credential_id=result.credential_id,
            credential_ref=command.credential_ref,
            principal_id=result.principal_id,
            project_key=command.project_key,
            scopes=command.scopes,
            seat_key=command.seat_key,
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"seat-credential:{result.credential_id}",
        tenant_id=actor.tenant_id,
    )


def _append_revocation(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: SeatCredentialRevocation,
    *,
    dsn: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SeatCredentialReceipt | RecordProblem:
    # See _append_issuance: a generation gap is transient, so it is returned directly
    # rather than persisted as a durable command_results outcome.
    unavailable = _seat_credential_generation_refusal(
        connection, dsn, command_id=command.client_command_id
    )
    if unavailable is not None:
        return unavailable
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"seat-credential:{actor.tenant_id}:{command.credential_id}",),
    )
    issuance = _locked_issuance(connection, actor, command)
    if isinstance(issuance, RecordProblem):
        return _refuse(
            transaction, actor, command.client_command_id, request_digest, issuance, now=now
        )
    event_id, outbox_id = (_uuid7(now) for _ in range(2))
    result = _revocation_receipt(command, issuance, event_id)
    _insert_revocation(connection, actor, command, event_id, now=now)
    event = _revocation_event(
        actor, command, issuance, event_id, request_digest, telemetry, now=now
    )
    transaction.commit(
        event,
        outbox_id=outbox_id,
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry,
        now=now,
        subjects=(("access", command.credential_id),),
    )
    return result


def _revocation_receipt(
    command: SeatCredentialRevocation,
    issuance: dict[str, object],
    event_id: UUID,
) -> SeatCredentialReceipt:
    scopes = tuple(CredentialScope(scope) for scope in cast(list[str], issuance["scopes"]))
    return SeatCredentialReceipt(
        command_id=command.client_command_id,
        credential_id=command.credential_id,
        event_ids=(event_id,),
        principal_id=cast(UUID, issuance["principal_id"]),
        project_key=str(issuance["project_key"]),
        scopes=scopes,
        seat_key=str(issuance["seat_key"]),
        state="revoked",
    )


def _insert_revocation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SeatCredentialRevocation,
    event_id: UUID,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO seat_credential_revocations (
            credential_id, tenant_id, event_id, revoked_by, reason, revoked_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            command.credential_id,
            actor.tenant_id,
            event_id,
            actor.principal_id,
            command.reason,
            now,
        ),
    )


def _revocation_event(
    actor: Actor,
    command: SeatCredentialRevocation,
    issuance: dict[str, object],
    event_id: UUID,
    request_digest: bytes,
    telemetry: TelemetryContext,
    *,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.credential_id,
        causation_id=cast(UUID, issuance["event_id"]),
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.SEAT_CREDENTIAL_REVOKED,
        origin=EventOrigin.API,
        payload=SeatCredentialRevokedPayload(command.credential_id, command.reason),
        prev_hash=bytes(cast(bytes, issuance["event_hash"])),
        request_sha256=request_digest,
        sequence=2,
        server_time=now,
        stream_id=f"seat-credential:{command.credential_id}",
        tenant_id=actor.tenant_id,
    )


def _issuance_conflict(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SeatCredentialIssue,
) -> RecordProblem | None:
    digest = connection.execute(
        "SELECT 1 FROM principal_credentials WHERE credential_digest = %s",
        (command.credential_digest,),
    ).fetchone()
    if digest is not None:
        return _problem(
            "credential-digest-conflict",
            409,
            "The credential digest is already bound.",
            command.client_command_id,
        )
    display = connection.execute(
        """
        SELECT principal_id FROM principals
        WHERE tenant_id = %s AND display_name = %s
        """,
        (actor.tenant_id, command.display_name),
    ).fetchone()
    seat = connection.execute(
        """
        SELECT seat.principal_id, principal.display_name
        FROM project_seats AS seat
        JOIN principals AS principal
          ON principal.principal_id = seat.principal_id
         AND principal.tenant_id = seat.tenant_id
        WHERE seat.tenant_id = %s AND seat.project_key = %s AND seat.seat_key = %s
        """,
        (actor.tenant_id, command.project_key, command.seat_key),
    ).fetchone()
    if seat is not None and str(seat["display_name"]) != command.display_name:
        return _problem(
            "seat-binding-conflict",
            409,
            "The stable project seat is bound to another display identity.",
            command.client_command_id,
        )
    if display is not None and (seat is None or display["principal_id"] != seat["principal_id"]):
        return _problem(
            "seat-display-name-conflict",
            409,
            "The seat display name is already bound to another principal.",
            command.client_command_id,
        )
    if seat is None:
        return None
    active = connection.execute(
        """
        SELECT issuance.credential_id
        FROM seat_credential_issuances AS issuance
        LEFT JOIN seat_credential_revocations AS revocation
          ON revocation.credential_id = issuance.credential_id
         AND revocation.tenant_id = issuance.tenant_id
        WHERE issuance.tenant_id = %s AND issuance.principal_id = %s
          AND revocation.credential_id IS NULL
        """,
        (actor.tenant_id, seat["principal_id"]),
    ).fetchone()
    if active is not None:
        return _problem(
            "seat-credential-active",
            409,
            "The project seat already has an active credential.",
            command.client_command_id,
        )
    return None


def _seat_principal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SeatCredentialIssue,
    *,
    now: datetime,
) -> UUID:
    seat = connection.execute(
        """
        SELECT principal_id FROM project_seats
        WHERE tenant_id = %s AND project_key = %s AND seat_key = %s
        """,
        (actor.tenant_id, command.project_key, command.seat_key),
    ).fetchone()
    if seat is not None:
        return cast(UUID, seat["principal_id"])
    principal_id = _uuid7(now)
    connection.execute(
        """
        INSERT INTO principals (
            principal_id, tenant_id, kind, display_name, disabled,
            credential_ref, vault_ref, created_at
        ) VALUES (%s, %s, 'commander', %s, false, NULL, NULL, %s)
        """,
        (principal_id, actor.tenant_id, command.display_name, now),
    )
    connection.execute(
        """
        INSERT INTO project_seats (
            principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            principal_id,
            actor.tenant_id,
            command.project_key,
            command.seat_key,
            actor.principal_id,
            now,
        ),
    )
    return principal_id


def _locked_issuance(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SeatCredentialRevocation,
) -> dict[str, object] | RecordProblem:
    row = connection.execute(
        """
        SELECT issuance.principal_id, issuance.event_id, event.event_hash,
            seat.project_key, seat.seat_key,
            revocation.credential_id IS NOT NULL AS revoked
        FROM seat_credential_issuances AS issuance
        JOIN project_seats AS seat
          ON seat.principal_id = issuance.principal_id
         AND seat.tenant_id = issuance.tenant_id
        JOIN events AS event
          ON event.event_id = issuance.event_id AND event.tenant_id = issuance.tenant_id
        LEFT JOIN seat_credential_revocations AS revocation
          ON revocation.credential_id = issuance.credential_id
         AND revocation.tenant_id = issuance.tenant_id
        WHERE issuance.tenant_id = %s AND issuance.credential_id = %s
        """,
        (actor.tenant_id, command.credential_id),
    ).fetchone()
    if row is None:
        return _problem(
            "seat-credential-unavailable",
            404,
            "The project-seat credential is unavailable.",
            command.client_command_id,
        )
    if bool(row["revoked"]):
        return _problem(
            "credential-already-revoked",
            409,
            "The project-seat credential is already revoked.",
            command.client_command_id,
        )
    scopes = connection.execute(
        """
        SELECT scope FROM seat_credential_scopes
        WHERE tenant_id = %s AND credential_id = %s
        ORDER BY scope
        """,
        (actor.tenant_id, command.credential_id),
    ).fetchall()
    return {**row, "scopes": [str(scope["scope"]) for scope in scopes]}


def _receipt_from_payload(payload: dict[str, object]) -> SeatCredentialReceipt:
    return SeatCredentialReceipt(
        command_id=UUID(str(payload["command_id"])),
        credential_id=UUID(str(payload["credential_id"])),
        event_ids=tuple(UUID(str(value)) for value in cast(list[object], payload["event_ids"])),
        principal_id=UUID(str(payload["principal_id"])),
        project_key=str(payload["project_key"]),
        scopes=tuple(
            CredentialScope(str(value)) for value in cast(list[object], payload["scopes"])
        ),
        seat_key=str(payload["seat_key"]),
        state=cast(Literal["active", "revoked"], str(payload["state"])),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    *,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _problem(code: str, status: int, detail: str, command_id: UUID) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=detail,
        status=status,
        title=detail,
        command_id=command_id,
    )

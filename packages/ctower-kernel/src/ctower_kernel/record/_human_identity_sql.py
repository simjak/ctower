"""Record-owned human role-binding and session persistence.

Role-binding issuance/revocation are idempotent operator commands (the same replay
authority as project-seat credentials) but are not hash-chained events: like
``project_seats``, they are structural authority facts rather than their own audit
stream, so no new ``EventKind`` is introduced. Sessions are the highest-churn part of
this plane and are always re-checked live against the owning binding's current state, so
a revoked binding invalidates every session it ever minted without a separate revocation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record._commands import reserve_command
from ctower_kernel.record.human_identity import (
    HumanBrowserSessionRecord,
    HumanRole,
    HumanRoleBindingIssue,
    HumanRoleBindingReceipt,
    HumanRoleBindingRevocation,
    HumanSessionReceipt,
)
from ctower_kernel.record.identifiers import uuid7 as _uuid7
from ctower_kernel.record.transaction import authority_connection

__all__ = [
    "actor_for_session",
    "bind_human_role",
    "browser_human_session",
    "issue_human_session",
    "resolve_human_role_binding",
    "revoke_human_role",
    "revoke_human_session",
]


def bind_human_role(
    dsn: str,
    actor: Actor,
    command: HumanRoleBindingIssue,
    *,
    request_digest: bytes,
    now: datetime,
) -> HumanRoleBindingReceipt | RecordProblem:
    """Create or replay one operator-issued, append-only human role binding."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{actor.principal_id}:{command.client_command_id}",),
        )
        reserved = reserve_command(
            connection, actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(reserved, RecordProblem):
            return reserved
        if reserved is not None:
            return _receipt_from_payload(reserved)
        if actor.kind is not PrincipalKind.OPERATOR:
            problem = _problem(
                "human-role-binding-refused",
                403,
                "Human role binding issuance requires operator authority.",
                command.client_command_id,
            )
            _refuse(connection, actor, command.client_command_id, request_digest, problem, now=now)
            return problem
        conflict = _binding_conflict(connection, actor, command)
        if conflict is not None:
            _refuse(connection, actor, command.client_command_id, request_digest, conflict, now=now)
            return conflict
        principal_id = _human_principal(connection, actor, command, now=now)
        binding_id = _uuid7(now)
        connection.execute(
            """
            INSERT INTO human_role_bindings (
                binding_id, tenant_id, principal_id, oidc_issuer, oidc_subject,
                role, project_keys, granted_by, granted_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                binding_id,
                actor.tenant_id,
                principal_id,
                command.oidc_issuer,
                command.oidc_subject,
                command.role,
                list(command.project_keys),
                actor.principal_id,
                now,
            ),
        )
        result = HumanRoleBindingReceipt(
            binding_id=binding_id,
            command_id=command.client_command_id,
            oidc_issuer=command.oidc_issuer,
            oidc_subject=command.oidc_subject,
            principal_id=principal_id,
            project_keys=command.project_keys,
            role=command.role,
            state="active",
        )
        _commit_fact(connection, actor, command.client_command_id, request_digest, result, now=now)
        return result


def revoke_human_role(
    dsn: str,
    actor: Actor,
    command: HumanRoleBindingRevocation,
    *,
    request_digest: bytes,
    now: datetime,
) -> HumanRoleBindingReceipt | RecordProblem:
    """Append one revocation that session resolution observes in the same commit."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        _console_authority_lock(connection, actor.tenant_id)
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{actor.principal_id}:{command.client_command_id}",),
        )
        reserved = reserve_command(
            connection, actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(reserved, RecordProblem):
            return reserved
        if reserved is not None:
            return _receipt_from_payload(reserved)
        if actor.kind is not PrincipalKind.OPERATOR:
            problem = _problem(
                "human-role-binding-refused",
                403,
                "Human role binding revocation requires operator authority.",
                command.client_command_id,
            )
            _refuse(connection, actor, command.client_command_id, request_digest, problem, now=now)
            return problem
        binding = _locked_binding(connection, actor, command)
        if isinstance(binding, RecordProblem):
            _refuse(connection, actor, command.client_command_id, request_digest, binding, now=now)
            return binding
        connection.execute(
            """
            INSERT INTO human_role_binding_revocations (
                binding_id, tenant_id, revoked_by, reason, revoked_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (command.binding_id, actor.tenant_id, actor.principal_id, command.reason, now),
        )
        result = HumanRoleBindingReceipt(
            binding_id=command.binding_id,
            command_id=command.client_command_id,
            oidc_issuer=str(binding["oidc_issuer"]),
            oidc_subject=str(binding["oidc_subject"]),
            principal_id=cast(UUID, binding["principal_id"]),
            project_keys=tuple(cast(list[str], binding["project_keys"])),
            role=cast(HumanRole, binding["role"]),
            state="revoked",
        )
        _commit_fact(connection, actor, command.client_command_id, request_digest, result, now=now)
        return result


def resolve_human_role_binding(
    dsn: str, oidc_issuer: str, oidc_subject: str
) -> tuple[UUID, Actor] | None:
    """Resolve one active binding to its binding ID and Actor, or None if unresolved."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT binding.binding_id, binding.tenant_id, binding.principal_id,
                binding.role, binding.project_keys
            FROM human_role_bindings AS binding
            LEFT JOIN human_role_binding_revocations AS revocation
              ON revocation.binding_id = binding.binding_id
             AND revocation.tenant_id = binding.tenant_id
            WHERE binding.oidc_issuer = %s AND binding.oidc_subject = %s
              AND revocation.binding_id IS NULL
            """,
            (oidc_issuer, oidc_subject),
        ).fetchone()
    if row is None:
        return None
    return cast(UUID, row["binding_id"]), _actor_from_binding_row(row)


def issue_human_session(
    dsn: str,
    principal_id: UUID,
    tenant_id: UUID,
    binding_id: UUID,
    role: HumanRole,
    *,
    session_digest: bytes,
    csrf_digest: bytes,
    now: datetime,
    ttl_seconds: int,
) -> HumanSessionReceipt:
    """Mint one revocable, digest-addressed session pointer to an active binding."""

    session_id = _uuid7(now)
    expires_at = now + timedelta(seconds=ttl_seconds)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            INSERT INTO human_sessions (
                session_id, tenant_id, session_digest, principal_id, binding_id,
                issued_at, expires_at, csrf_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                tenant_id,
                session_digest,
                principal_id,
                binding_id,
                now,
                expires_at,
                csrf_digest,
            ),
        )
    return HumanSessionReceipt(
        binding_id=binding_id,
        expires_at=expires_at,
        principal_id=principal_id,
        role=role,
        session_id=session_id,
    )


def actor_for_session(
    dsn: str, session_digest: bytes, *, now: datetime
) -> Actor | RecordProblem | None:
    """Resolve one live session, re-checking the owning binding on every call."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT session.session_id, session.binding_id, session.expires_at,
                session_revocation.session_id IS NOT NULL AS session_revoked,
                binding.tenant_id, binding.principal_id, binding.role, binding.project_keys,
                binding_revocation.binding_id IS NOT NULL AS binding_revoked
            FROM human_sessions AS session
            JOIN human_role_bindings AS binding
              ON binding.binding_id = session.binding_id
             AND binding.tenant_id = session.tenant_id
            LEFT JOIN human_session_revocations AS session_revocation
              ON session_revocation.session_id = session.session_id
             AND session_revocation.tenant_id = session.tenant_id
            LEFT JOIN human_role_binding_revocations AS binding_revocation
              ON binding_revocation.binding_id = binding.binding_id
             AND binding_revocation.tenant_id = binding.tenant_id
            WHERE session.session_digest = %s
            """,
            (session_digest,),
        ).fetchone()
    if row is None:
        return None
    if bool(row["session_revoked"]) or bool(row["binding_revoked"]):
        return RecordProblem(
            code="auth-session-invalid",
            detail="The presented session has been revoked.",
            status=401,
            title="Session invalid",
        )
    if cast(datetime, row["expires_at"]) <= now:
        return RecordProblem(
            code="reauthentication-required",
            detail="The session has expired and requires a fresh login.",
            status=401,
            title="Reauthentication required",
        )
    return _actor_from_binding_row(row)


def browser_human_session(
    dsn: str,
    session_digest: bytes,
    csrf_digest: bytes,
    *,
    now: datetime,
) -> HumanBrowserSessionRecord | RecordProblem | None:
    """Resolve one exact cookie+CSRF pair without leaking which half mismatched."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT session.session_id, session.binding_id, session.expires_at,
                session_revocation.session_id IS NOT NULL AS session_revoked,
                binding.tenant_id, binding.principal_id, binding.role, binding.project_keys,
                binding_revocation.binding_id IS NOT NULL AS binding_revoked
            FROM human_sessions AS session
            JOIN human_role_bindings AS binding
              ON binding.binding_id = session.binding_id
             AND binding.tenant_id = session.tenant_id
            LEFT JOIN human_session_revocations AS session_revocation
              ON session_revocation.session_id = session.session_id
             AND session_revocation.tenant_id = session.tenant_id
            LEFT JOIN human_role_binding_revocations AS binding_revocation
              ON binding_revocation.binding_id = binding.binding_id
             AND binding_revocation.tenant_id = binding.tenant_id
            WHERE session.session_digest = %s AND session.csrf_digest = %s
            """,
            (session_digest, csrf_digest),
        ).fetchone()
    if row is None:
        return RecordProblem(
            code="auth-csrf-invalid",
            detail="The browser CSRF proof is absent or does not match the session.",
            status=403,
            title="CSRF proof invalid",
        )
    if bool(row["session_revoked"]) or bool(row["binding_revoked"]):
        return RecordProblem(
            code="auth-session-invalid",
            detail="The presented session has been revoked.",
            status=401,
            title="Session invalid",
        )
    if cast(datetime, row["expires_at"]) <= now:
        return RecordProblem(
            code="reauthentication-required",
            detail="The session has expired and requires a fresh login.",
            status=401,
            title="Reauthentication required",
        )
    actor = _actor_from_binding_row(row)
    return HumanBrowserSessionRecord(
        actor=actor,
        binding_id=cast(UUID, row["binding_id"]),
        session_id=cast(UUID, row["session_id"]),
    )


def revoke_human_session(dsn: str, session_digest: bytes, *, reason: str, now: datetime) -> None:
    """Revoke one session by digest; a missing or already-revoked session is a no-op."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            "SELECT session_id, tenant_id FROM human_sessions WHERE session_digest = %s",
            (session_digest,),
        ).fetchone()
        if row is None:
            return
        _console_authority_lock(connection, cast(UUID, row["tenant_id"]))
        connection.execute(
            """
            INSERT INTO human_session_revocations (session_id, tenant_id, reason, revoked_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (session_id) DO NOTHING
            """,
            (row["session_id"], row["tenant_id"], reason, now),
        )


def _console_authority_lock(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> None:
    """Serialize revocation facts against Console authority persistence."""

    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"console-authority:{tenant_id}",),
    )


def _actor_from_binding_row(row: dict[str, object]) -> Actor:
    project_keys = cast(list[str], row["project_keys"])
    return Actor(
        principal_id=cast(UUID, row["principal_id"]),
        tenant_id=cast(UUID, row["tenant_id"]),
        kind=PrincipalKind(str(row["role"])),
        project_grants=frozenset(project_keys),
        credential_scopes=frozenset(),
        seat_credential_id=None,
        human_binding_id=cast(UUID | None, row.get("binding_id")),
        human_session_id=cast(UUID | None, row.get("session_id")),
    )


def _binding_conflict(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: HumanRoleBindingIssue,
) -> RecordProblem | None:
    active = connection.execute(
        """
        SELECT binding.binding_id
        FROM human_role_bindings AS binding
        LEFT JOIN human_role_binding_revocations AS revocation
          ON revocation.binding_id = binding.binding_id
         AND revocation.tenant_id = binding.tenant_id
        WHERE binding.tenant_id = %s AND binding.oidc_issuer = %s AND binding.oidc_subject = %s
          AND revocation.binding_id IS NULL
        """,
        (actor.tenant_id, command.oidc_issuer, command.oidc_subject),
    ).fetchone()
    if active is not None:
        return _problem(
            "human-role-binding-active",
            409,
            "The presented identity already has an active human role binding.",
            command.client_command_id,
        )
    display = connection.execute(
        "SELECT principal_id FROM principals WHERE tenant_id = %s AND display_name = %s",
        (actor.tenant_id, command.display_name),
    ).fetchone()
    if display is not None:
        return _problem(
            "human-role-display-name-conflict",
            409,
            "The display name is already bound to another principal.",
            command.client_command_id,
        )
    return None


def _human_principal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: HumanRoleBindingIssue,
    *,
    now: datetime,
) -> UUID:
    # _binding_conflict already proved this display_name is free, so every issuance
    # mints its own principal: a human identity is never silently grafted onto an
    # unrelated (and possibly machine-kind) principal row by name collision.
    principal_id = _uuid7(now)
    connection.execute(
        """
        INSERT INTO principals (
            principal_id, tenant_id, kind, display_name, disabled,
            credential_ref, vault_ref, created_at
        ) VALUES (%s, %s, %s, %s, false, NULL, NULL, %s)
        """,
        (principal_id, actor.tenant_id, command.role, command.display_name, now),
    )
    return principal_id


def _locked_binding(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: HumanRoleBindingRevocation,
) -> dict[str, object] | RecordProblem:
    row = connection.execute(
        """
        SELECT binding.oidc_issuer, binding.oidc_subject, binding.principal_id,
            binding.role, binding.project_keys,
            revocation.binding_id IS NOT NULL AS revoked
        FROM human_role_bindings AS binding
        LEFT JOIN human_role_binding_revocations AS revocation
          ON revocation.binding_id = binding.binding_id
         AND revocation.tenant_id = binding.tenant_id
        WHERE binding.tenant_id = %s AND binding.binding_id = %s
        """,
        (actor.tenant_id, command.binding_id),
    ).fetchone()
    if row is None:
        return _problem(
            "human-role-binding-unavailable",
            404,
            "The human role binding is unavailable.",
            command.client_command_id,
        )
    if bool(row["revoked"]):
        return _problem(
            "human-role-binding-already-revoked",
            409,
            "The human role binding is already revoked.",
            command.client_command_id,
        )
    return row


def _commit_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    result: HumanRoleBindingReceipt,
    *,
    now: datetime,
) -> None:
    status_code = 201 if result.state == "active" else 200
    connection.execute(
        """
        INSERT INTO command_results (
            tenant_id, principal_id, client_command_id, request_sha256, status_code,
            response_body, event_ids, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            actor.principal_id,
            command_id,
            request_digest,
            status_code,
            Jsonb(result.response_payload()),
            [],
            now,
        ),
    )


def _refuse(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO command_results (
            tenant_id, principal_id, client_command_id, request_sha256, status_code,
            response_body, event_ids, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            actor.principal_id,
            command_id,
            request_digest,
            problem.status,
            Jsonb(problem.response_payload()),
            [],
            now,
        ),
    )


def _receipt_from_payload(payload: dict[str, object]) -> HumanRoleBindingReceipt:
    return HumanRoleBindingReceipt(
        binding_id=UUID(str(payload["binding_id"])),
        command_id=UUID(str(payload["command_id"])),
        oidc_issuer=str(payload["oidc_issuer"]),
        oidc_subject=str(payload["oidc_subject"]),
        principal_id=UUID(str(payload["principal_id"])),
        project_keys=tuple(str(value) for value in cast(list[object], payload["project_keys"])),
        role=cast(HumanRole, payload["role"]),
        state=cast(Literal["active", "revoked"], str(payload["state"])),
    )


def _problem(code: str, status: int, detail: str, command_id: UUID) -> RecordProblem:
    return RecordProblem(
        code=code, detail=detail, status=status, title=detail, command_id=command_id
    )

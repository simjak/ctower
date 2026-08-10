"""Request state created by authenticated thread-first intake."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.intake import IntakeCommandResult

__all__ = ["insert_request_state"]


class _RequestAction(Protocol):
    @property
    def request_id(self) -> UUID | None: ...

    @property
    def request_number(self) -> int | None: ...

    @property
    def request_owner_id(self) -> UUID | None: ...


def insert_request_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    action: _RequestAction,
    result: IntakeCommandResult,
    *,
    content: str,
    now: datetime,
) -> None:
    """Append the complete initial Request authority in the intake transaction."""

    if (
        action.request_id is None
        or action.request_number is None
        or action.request_owner_id is None
    ):
        raise RuntimeError("create-request intake action is incomplete")
    digest = hashlib.sha256(content.encode()).digest()
    connection.execute(
        """
        INSERT INTO requests (
            request_id, tenant_id, request_number, project_key, content, content_digest,
            source_kind, source_ref, inbound_event_id, submitted_by, capture_command_id,
            version, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
        """,
        (
            action.request_id,
            actor.tenant_id,
            action.request_number,
            result.project_key,
            content,
            digest,
            result.source.kind,
            result.source.ref,
            result.inbound_event_id,
            actor.principal_id,
            command_id,
            now,
        ),
    )
    _insert_initial_facts(
        connection,
        actor,
        command_id,
        action.request_id,
        action.request_owner_id,
        now=now,
    )
    _insert_triage_attention(
        connection,
        actor,
        command_id,
        action.request_id,
        result.project_key,
        now=now,
    )


def _insert_initial_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_id: UUID,
    owner_id: UUID,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO request_owner_facts (
            request_id, tenant_id, sequence, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, %s, 'server-resolved intake owner', %s, %s, %s)
        """,
        (request_id, actor.tenant_id, owner_id, actor.principal_id, command_id, now),
    )
    connection.execute(
        """
        INSERT INTO request_priority_facts (
            request_id, tenant_id, sequence, priority, is_default, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, 'P2', true, 'server custody default', %s, %s, %s)
        """,
        (request_id, actor.tenant_id, actor.principal_id, command_id, now),
    )
    connection.execute(
        """
        INSERT INTO request_triage_facts (
            request_id, tenant_id, sequence, disposition, reason, canonical_request_id,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, 'UNTRIAGED', NULL, NULL, %s, %s, %s)
        """,
        (request_id, actor.tenant_id, actor.principal_id, command_id, now),
    )


def _insert_triage_attention(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_id: UUID,
    project_key: str,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO request_attention_facts (
            attention_id, request_id, tenant_id, kind, active, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, 'request_triage_required', true, %s,
                  'Commander disposition is required', %s, %s, %s)
        """,
        (
            uuid7(now),
            request_id,
            actor.tenant_id,
            _project_commander(connection, actor.tenant_id, project_key),
            actor.principal_id,
            command_id,
            now,
        ),
    )


def _project_commander(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, project_key: str
) -> UUID:
    row = connection.execute(
        """
        SELECT principal.principal_id
        FROM project_seats AS seat
        JOIN principals AS principal
          ON principal.tenant_id = seat.tenant_id
         AND principal.principal_id = seat.principal_id
        WHERE seat.tenant_id = %s AND seat.project_key = %s
          AND principal.kind = 'commander' AND NOT principal.disabled
        ORDER BY principal.created_at, principal.principal_id LIMIT 1
        """,
        (tenant_id, project_key),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request project has no active Commander")
    return cast(UUID, row["principal_id"])

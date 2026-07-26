"""Exact aliases and provenance-only source-link revisions."""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

import psycopg

from ctower_client.models import (
    CtowerProjectExactAliasOperation,
    CtowerProjectImportBatchRequest,
    CtowerProjectSourceLinkOperation,
    MigrationImportOperationResult,
)
from ctower_kernel.migration._operation_result_sql import (
    canonical,
    commit_migration_result,
    source_matches,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def bind_alias(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectExactAliasOperation,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> MigrationImportOperationResult | RecordProblem:
    if not source_matches(operation):
        return _drift(operation.identity.command_id, "Alias source identity changed")
    target = _lock_alias_target(connection, actor, operation.target_ticket_id)
    if target is None or _alias_forks(target, batch, operation):
        return _problem(
            operation.identity.command_id,
            "migration-alias-conflict",
            "Alias target is unavailable or already bound",
        )
    if target["run_id"] is None:
        _insert_ticket_binding(connection, actor, batch, operation, now)
    connection.execute(
        """
        INSERT INTO migration_alias_revisions (
            alias_id, revision, run_id, namespace, immutable_source_id,
            target_ticket_id, disposition, semantic_digest, supersedes_revision,
            command_id, recorded_at
        ) VALUES (%s, 1, %s, %s, %s, %s, 'alias_linked_existing', %s, NULL, %s, %s)
        """,
        (
            operation.identity.command_id,
            batch.run_id,
            operation.source.namespace,
            operation.source.immutable_source_id,
            operation.target_ticket_id,
            hashlib.sha256(canonical(operation)).digest(),
            operation.identity.command_id,
            now,
        ),
    )
    return commit_migration_result(
        connection,
        actor,
        batch,
        operation,
        target_id=str(operation.target_ticket_id),
        now=now,
        telemetry=telemetry,
    )


def add_source_link(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectSourceLinkOperation,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> MigrationImportOperationResult | RecordProblem:
    if not source_matches(operation) or not _target_exists(connection, actor, batch, operation):
        return _drift(
            operation.identity.command_id,
            "Source link identity or target is unavailable",
        )
    connection.execute(
        """
        INSERT INTO migration_source_link_revisions (
            link_id, revision, run_id, namespace, immutable_source_id, link_class,
            target_kind, target_id, reason_code, semantic_digest, supersedes_revision,
            command_id, recorded_at
        ) VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
        """,
        (
            operation.identity.command_id,
            batch.run_id,
            operation.source.namespace,
            operation.source.immutable_source_id,
            operation.link_class,
            operation.target_kind,
            operation.target_id,
            operation.reason_code,
            hashlib.sha256(canonical(operation)).digest(),
            operation.identity.command_id,
            now,
        ),
    )
    return commit_migration_result(
        connection,
        actor,
        batch,
        operation,
        target_id=operation.target_id,
        now=now,
        telemetry=telemetry,
    )


def _lock_alias_target(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT ticket.ticket_id, binding.run_id, binding.source_namespace,
            binding.immutable_source_id
        FROM tickets AS ticket
        LEFT JOIN ticket_project_bindings AS binding ON binding.ticket_id = ticket.ticket_id
        WHERE ticket.tenant_id = %s AND ticket.ticket_id = %s FOR UPDATE OF ticket
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()


def _alias_forks(
    target: dict[str, object],
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectExactAliasOperation,
) -> bool:
    del operation
    return target["run_id"] is not None and target["run_id"] != batch.run_id


def _insert_ticket_binding(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectExactAliasOperation,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO ticket_project_bindings (
            ticket_id, tenant_id, project_key, run_id, source_namespace,
            immutable_source_id, bound_at
        ) VALUES (%s, %s, 'ctower', %s, %s, %s, %s)
        """,
        (
            operation.target_ticket_id,
            actor.tenant_id,
            batch.run_id,
            operation.source.namespace,
            operation.source.immutable_source_id,
            now,
        ),
    )


def _target_exists(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectSourceLinkOperation,
) -> bool:
    if operation.target_kind == "ticket":
        target_id = _target_uuid(operation.target_id, "ticket:")
        return target_id is not None and _ticket_target(connection, actor, batch, target_id)
    if operation.target_kind == "ticket_relation":
        relation_id = _target_uuid(operation.target_id, "ticket_relation:")
        return relation_id is not None and _relation_target(connection, batch, relation_id)
    if operation.target_kind == "checkpoint":
        return _checkpoint_target(connection, actor, operation.target_id)
    return True


def _ticket_target(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    target_id: UUID,
) -> bool:
    return (
        connection.execute(
            """
        SELECT 1 FROM ticket_project_bindings
        WHERE tenant_id = %s AND run_id = %s AND ticket_id = %s
        """,
            (actor.tenant_id, batch.run_id, target_id),
        ).fetchone()
        is not None
    )


def _relation_target(
    connection: psycopg.Connection[dict[str, object]],
    batch: CtowerProjectImportBatchRequest,
    relation_id: UUID,
) -> bool:
    return (
        connection.execute(
            """
        SELECT 1 FROM migration_relation_validity_facts
        WHERE run_id = %s AND relation_id = %s AND active
        ORDER BY revision DESC LIMIT 1
        """,
            (batch.run_id, relation_id),
        ).fetchone()
        is not None
    )


def _checkpoint_target(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    checkpoint_key: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM project_delivery_checkpoint_definitions
            WHERE tenant_id = %s AND project_key = 'ctower'
              AND checkpoint_key = %s
            ORDER BY definition_revision DESC LIMIT 1
            """,
            (actor.tenant_id, checkpoint_key),
        ).fetchone()
        is not None
    )


def _target_uuid(value: str, prefix: str) -> UUID | None:
    try:
        return UUID(value.removeprefix(prefix))
    except ValueError:
        return None


def _drift(command_id: UUID, title: str) -> RecordProblem:
    return _problem(command_id, "migration-operation-drift", title)


def _problem(command_id: UUID, code: str, title: str) -> RecordProblem:
    return RecordProblem(code, title, 409, title, command_id)

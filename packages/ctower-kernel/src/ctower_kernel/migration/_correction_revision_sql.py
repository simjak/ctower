"""Validated append-only alias, source-link, and relation revision storage."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg

from ctower_client.models import (
    CtowerProjectImportCorrectionRequest,
    MigrationAliasCorrection,
    MigrationRelationCorrection,
    MigrationSourceLinkCorrection,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def current_revision(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportCorrectionRequest,
) -> dict[str, object] | None:
    identity = request.superseded_revision.object_id
    if request.correction_kind == "alias":
        query = """
            SELECT * FROM migration_alias_revisions
            WHERE alias_id = %s AND run_id = %s ORDER BY revision DESC LIMIT 1
        """
    elif request.correction_kind == "source_link":
        query = """
            SELECT * FROM migration_source_link_revisions
            WHERE link_id = %s AND run_id = %s ORDER BY revision DESC LIMIT 1
        """
    else:
        query = """
            SELECT * FROM migration_relation_validity_facts
            WHERE relation_id = %s AND run_id = %s ORDER BY revision DESC LIMIT 1
        """
    return connection.execute(query, (identity, request.run_id)).fetchone()


def append_revision(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    current: dict[str, object],
    *,
    semantic: bytes,
    command_id: UUID,
    now: datetime,
) -> bool:
    replacement = request.replacement
    if request.correction_kind != replacement.kind:
        return False
    if isinstance(replacement, MigrationAliasCorrection):
        return _append_alias(
            connection,
            actor,
            request,
            current,
            replacement=replacement,
            semantic=semantic,
            command_id=command_id,
            now=now,
        )
    if isinstance(replacement, MigrationSourceLinkCorrection):
        return _append_source_link(
            connection,
            actor,
            request,
            current,
            replacement=replacement,
            semantic=semantic,
            command_id=command_id,
            now=now,
        )
    return _append_relation(
        connection,
        request,
        replacement,
        semantic=semantic,
        command_id=command_id,
        now=now,
    )


def _append_alias(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    current: dict[str, object],
    *,
    replacement: MigrationAliasCorrection,
    semantic: bytes,
    command_id: UUID,
    now: datetime,
) -> bool:
    if not _alias_target_available(connection, actor, request, replacement):
        return False
    connection.execute(
        """
        INSERT INTO migration_alias_revisions (
            alias_id, revision, run_id, namespace, immutable_source_id,
            target_ticket_id, disposition, semantic_digest, supersedes_revision,
            command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.superseded_revision.object_id,
            request.superseded_revision.revision + 1,
            request.run_id,
            current["namespace"],
            current["immutable_source_id"],
            replacement.target_ticket_id,
            replacement.disposition,
            semantic,
            request.superseded_revision.revision,
            command_id,
            now,
        ),
    )
    return True


def _alias_target_available(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    replacement: MigrationAliasCorrection,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM ticket_project_bindings
            WHERE ticket_id = %s AND tenant_id = %s AND run_id = %s
              AND NOT EXISTS (
                SELECT 1 FROM migration_alias_revisions AS alias
                WHERE alias.run_id = %s AND alias.target_ticket_id = %s
                  AND alias.alias_id <> %s AND alias.revision = (
                    SELECT max(candidate.revision)
                    FROM migration_alias_revisions AS candidate
                    WHERE candidate.alias_id = alias.alias_id
                  )
              )
            """,
            (
                replacement.target_ticket_id,
                actor.tenant_id,
                request.run_id,
                request.run_id,
                replacement.target_ticket_id,
                request.superseded_revision.object_id,
            ),
        ).fetchone()
        is not None
    )


def _append_source_link(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    current: dict[str, object],
    *,
    replacement: MigrationSourceLinkCorrection,
    semantic: bytes,
    command_id: UUID,
    now: datetime,
) -> bool:
    if not _source_target_valid(connection, actor, request, replacement):
        return False
    link_class = {
        "decision_link": "decision",
        "external_effect_link": "external_effect",
        "artifact_linked_not_proof": "artifact_not_proof",
        "excluded_out_of_scope": "excluded_out_of_scope",
    }.get(replacement.disposition, "provenance")
    connection.execute(
        """
        INSERT INTO migration_source_link_revisions (
            link_id, revision, run_id, namespace, immutable_source_id, link_class,
            target_kind, target_id, reason_code, semantic_digest, supersedes_revision,
            command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.superseded_revision.object_id,
            request.superseded_revision.revision + 1,
            request.run_id,
            current["namespace"],
            current["immutable_source_id"],
            link_class,
            replacement.target_kind,
            replacement.target_id,
            current["reason_code"],
            semantic,
            request.superseded_revision.revision,
            command_id,
            now,
        ),
    )
    return True


def _source_target_valid(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportCorrectionRequest,
    replacement: MigrationSourceLinkCorrection,
) -> bool:
    params: tuple[object, ...]
    if replacement.target_kind == "ticket":
        target_id = _target_uuid(replacement.target_id, "ticket:")
        query = """
            SELECT 1 FROM ticket_project_bindings
            WHERE ticket_id = %s AND tenant_id = %s AND run_id = %s
        """
        params = (target_id, actor.tenant_id, request.run_id)
    elif replacement.target_kind == "ticket_relation":
        target_id = _target_uuid(replacement.target_id, "ticket_relation:")
        query = """
            SELECT active FROM migration_relation_validity_facts
            WHERE relation_id = %s AND run_id = %s ORDER BY revision DESC LIMIT 1
        """
        params = (target_id, request.run_id)
    else:
        return True
    if target_id is None:
        return False
    row = connection.execute(query, params).fetchone()
    return row is not None and (
        replacement.target_kind != "ticket_relation" or row["active"] is True
    )


def _append_relation(
    connection: psycopg.Connection[dict[str, object]],
    request: CtowerProjectImportCorrectionRequest,
    replacement: MigrationRelationCorrection,
    *,
    semantic: bytes,
    command_id: UUID,
    now: datetime,
) -> bool:
    if replacement.replacement_relation_id is not None and not _active_relation(
        connection, request.run_id, replacement.replacement_relation_id
    ):
        return False
    connection.execute(
        """
        INSERT INTO migration_relation_validity_facts (
            relation_id, revision, run_id, active, replacement_relation_id,
            semantic_digest, command_id, recorded_at
        ) VALUES (%s, %s, %s, false, %s, %s, %s, %s)
        """,
        (
            request.superseded_revision.object_id,
            request.superseded_revision.revision + 1,
            request.run_id,
            replacement.replacement_relation_id,
            semantic,
            command_id,
            now,
        ),
    )
    return True


def _active_relation(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    relation_id: UUID,
) -> bool:
    row = connection.execute(
        """
        SELECT active FROM migration_relation_validity_facts
        WHERE relation_id = %s AND run_id = %s ORDER BY revision DESC LIMIT 1
        """,
        (relation_id, run_id),
    ).fetchone()
    return row is not None and row["active"] is True


def _target_uuid(value: str, prefix: str) -> UUID | None:
    try:
        return UUID(value.removeprefix(prefix))
    except ValueError:
        return None

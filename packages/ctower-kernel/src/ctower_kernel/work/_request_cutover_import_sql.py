"""Atomic manifest-bound import of one frozen Request row."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.transaction import (
    RecordTransaction,
    authority_connection,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_artifacts import artifact_digest_bytes
from ctower_kernel.work._request_cutover_common_sql import (
    human_operator_refusal,
    owner_is_active_and_addressable,
    refuse,
    request_cutover_result,
    target_watermark,
)
from ctower_kernel.work._request_cutover_import_events import import_events, import_identities
from ctower_kernel.work._request_cutover_types import RequestCutoverImport, RequestCutoverResult

__all__ = ["import_request_row"]


def import_request_row(
    dsn: str,
    actor: Actor,
    command: RequestCutoverImport,
    *,
    manifest: dict[str, Any],
    fence: dict[str, Any],
    public_key_digest: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestCutoverResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else request_cutover_result(replay)
        row, imported_count, problem = _import_preconditions(
            connection,
            actor,
            command,
            manifest,
            public_key_digest=public_key_digest,
        )
        if problem is not None or row is None:
            return refuse(
                transaction,
                actor,
                command.client_command_id,
                request_digest,
                problem or _problem(command, "migration-operation-drift", "row is unavailable"),
                now=now,
            )
        identities = import_identities(
            cast(str, manifest["ledger_sha256"]), command.source_request_id
        )
        durable = _import_durability(
            transaction,
            actor,
            command,
            identities,
            request_digest=request_digest,
            now=now,
        )
        if durable is not None:
            return durable
        return _commit_import(
            connection,
            transaction,
            actor,
            command,
            row,
            fence=fence,
            identities=identities,
            imported_count=imported_count + 1,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _import_durability(
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestCutoverImport,
    identities: tuple[UUID, UUID, UUID],
    *,
    request_digest: bytes,
    now: datetime,
) -> RequestCutoverResult | RecordProblem | None:
    return transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        (
            ("inbound_thread", identities[0]),
            ("inbound_event", identities[1]),
            ("request", identities[2]),
        ),
        now=now,
    )


def _commit_import(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    *,
    fence: dict[str, Any],
    identities: tuple[UUID, UUID, UUID],
    imported_count: int,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestCutoverResult:
    result = _persist_import(
        connection,
        actor,
        command,
        row,
        fence=fence,
        identities=identities,
        imported_count=imported_count,
        now=now,
    )
    commits = import_events(
        actor,
        command,
        row,
        result,
        identities=identities,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    committed = RequestCutoverResult(
        result.command_id,
        result.operation,
        result.manifest_digest,
        result.state,
        result.imported_count,
        target_watermark(connection) + len(commits),
        result.request_id,
        result.request_number,
        tuple(item.event.event_id for item in commits),
    )
    transaction.commit_batch(
        commits,
        response_body=committed.response_payload(),
        status_code=201,
        telemetry=telemetry,
        now=now,
        subjects=(
            ("inbound_thread", identities[0]),
            ("inbound_event", identities[1]),
            ("request", identities[2]),
        ),
    )
    return committed


def _import_preconditions(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverImport,
    manifest: dict[str, Any],
    *,
    public_key_digest: str,
) -> tuple[dict[str, object] | None, int, RecordProblem | None]:
    problem = human_operator_refusal(connection, actor, command.client_command_id)
    if problem is not None:
        return None, 0, problem
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"request-cutover:{command.manifest_digest}",),
    )
    stored = connection.execute(
        """
        SELECT public_key_digest,
               (SELECT state FROM request_cutover_epoch_facts AS fact
                WHERE fact.tenant_id = manifest.tenant_id
                  AND fact.manifest_digest = manifest.manifest_digest
                ORDER BY sequence DESC LIMIT 1) AS state
        FROM request_import_manifests AS manifest
        WHERE tenant_id = %s AND manifest_digest = %s
        """,
        (actor.tenant_id, artifact_digest_bytes(command.manifest_digest)),
    ).fetchone()
    if stored is None or stored["state"] != "prepared":
        return None, 0, _problem(command, "request-import-forbidden", "epoch is not prepared")
    if bytes(cast(bytes, stored["public_key_digest"])) != artifact_digest_bytes(public_key_digest):
        return None, 0, _problem(command, "migration-signature-invalid", "review key drifted")
    count_row = connection.execute(
        """
        SELECT count(*) AS count FROM request_import_rows
        WHERE tenant_id = %s AND manifest_digest = %s
        """,
        (actor.tenant_id, artifact_digest_bytes(command.manifest_digest)),
    ).fetchone()
    if count_row is None:
        raise RuntimeError("Request import count query returned no row")
    imported_count = int(cast(int, count_row["count"]))
    rows = cast(list[dict[str, object]], manifest["rows"])
    return _expected_row(connection, actor, command, manifest, rows, imported_count)


def _expected_row(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverImport,
    manifest: dict[str, Any],
    rows: list[dict[str, object]],
    imported_count: int,
) -> tuple[dict[str, object] | None, int, RecordProblem | None]:
    if imported_count >= len(rows) or rows[imported_count]["id"] != command.source_request_id:
        problem = _problem(
            command, "migration-operation-drift", "strict serial source order differs"
        )
        return None, imported_count, problem
    row = rows[imported_count]
    owner_id = UUID(cast(str, row["mapped_principal_id"]))
    if not owner_is_active_and_addressable(
        connection, actor.tenant_id, owner_id, cast(str, row["project_key"])
    ):
        return (
            None,
            imported_count,
            _problem(command, "migration-operation-drift", "mapped owner is no longer addressable"),
        )
    expected_id = import_identities(
        cast(str, manifest["ledger_sha256"]), command.source_request_id
    )[2]
    content_digest = f"sha256:{hashlib.sha256(command.content.encode()).hexdigest()}"
    drift: tuple[str, str] | None = None
    if row["command_id"] != str(command.client_command_id):
        drift = "migration-operation-drift", "deterministic command identity differs"
    elif row["request_id"] != str(expected_id):
        drift = "migration-operation-drift", "deterministic Request identity differs"
    elif row["content_sha256"] != content_digest:
        drift = "migration-digest-mismatch", "content digest differs"
    if drift is not None:
        return None, imported_count, _problem(command, *drift)
    return row, imported_count, None


def _persist_import(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    *,
    fence: dict[str, Any],
    identities: tuple[UUID, UUID, UUID],
    imported_count: int,
    now: datetime,
) -> RequestCutoverResult:
    thread_id, inbound_event_id, request_id = identities
    owner_id = UUID(cast(str, row["mapped_principal_id"]))
    created_at = datetime.fromisoformat(cast(str, row["created_at"]))
    content_digest = hashlib.sha256(command.content.encode()).digest()
    _insert_inbound_source(
        connection,
        actor,
        command,
        row,
        thread_id,
        inbound_event_id,
        content_digest,
        created_at=created_at,
        now=now,
    )
    _insert_request(
        connection,
        actor,
        command,
        row,
        request_id,
        inbound_event_id,
        content_digest,
        created_at=created_at,
    )
    _insert_initial_facts(connection, actor, command, row, request_id, owner_id, now=now)
    _insert_import_provenance(
        connection,
        actor,
        command,
        row,
        request_id,
        owner_id,
        fence=fence,
        content_digest=content_digest,
        imported_count=imported_count,
        now=now,
    )
    return RequestCutoverResult(
        command.client_command_id,
        "import",
        command.manifest_digest,
        "prepared",
        imported_count,
        target_watermark(connection),
        request_id,
        int(cast(int, row["request_number"])),
    )


def _insert_inbound_source(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    thread_id: UUID,
    inbound_event_id: UUID,
    content_digest: bytes,
    *,
    created_at: datetime,
    now: datetime,
) -> None:
    source_ref = command.source_request_id
    connection.execute(
        """
        INSERT INTO inbound_threads (
            thread_id, tenant_id, project_key, version, created_by, created_at
        ) VALUES (%s, %s, %s, 1, %s, %s)
        """,
        (thread_id, actor.tenant_id, row["project_key"], actor.principal_id, created_at),
    )
    connection.execute(
        """
        INSERT INTO inbound_events (
            inbound_event_id, tenant_id, thread_id, position, source_kind, source_ref,
            content, content_digest, taint, initial_intent, initial_outcome,
            recorded_by, recorded_at
        ) VALUES (%s, %s, %s, 1, 'mission-control-request', %s, %s, %s,
                  'authenticated', 'create_request', 'request_created', %s, %s)
        """,
        (
            inbound_event_id,
            actor.tenant_id,
            thread_id,
            source_ref,
            command.content,
            content_digest,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO inbound_source_aliases (
            tenant_id, source_kind, source_ref, inbound_event_id, thread_id,
            project_key, recorded_at
        ) VALUES (%s, 'mission-control-request', %s, %s, %s, %s, %s)
        """,
        (actor.tenant_id, source_ref, inbound_event_id, thread_id, row["project_key"], now),
    )


def _insert_request(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    request_id: UUID,
    inbound_event_id: UUID,
    content_digest: bytes,
    *,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO requests (
            request_id, tenant_id, request_number, project_key, content, content_digest,
            source_kind, source_ref, inbound_event_id, submitted_by, capture_command_id,
            version, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, 'mission-control-request', %s,
                  %s, %s, %s, 1, %s)
        """,
        (
            request_id,
            actor.tenant_id,
            row["request_number"],
            row["project_key"],
            command.content,
            content_digest,
            command.source_request_id,
            inbound_event_id,
            actor.principal_id,
            command.client_command_id,
            created_at,
        ),
    )


def _insert_import_provenance(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    request_id: UUID,
    owner_id: UUID,
    *,
    fence: dict[str, Any],
    content_digest: bytes,
    imported_count: int,
    now: datetime,
) -> None:
    digest = artifact_digest_bytes(command.manifest_digest)
    connection.execute(
        """
        INSERT INTO request_import_rows (
            manifest_digest, tenant_id, source_request_number, batch_index, request_id,
            source_row_digest, content_digest, original_owner_digest, relationships_digest,
            fence_digest, imported_by, command_id, imported_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            digest,
            actor.tenant_id,
            row["request_number"],
            (imported_count - 1) // 25,
            request_id,
            artifact_digest_bytes(row["latest_row_sha256"]),
            content_digest,
            artifact_digest_bytes(row["original_owner_sha256"]),
            artifact_digest_bytes(row["relationships_sha256"]),
            artifact_digest_bytes(fence["fence_digest"]),
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO request_owner_aliases (
            request_id, tenant_id, owner_id, source_owner, source_owner_digest,
            manifest_digest, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request_id,
            actor.tenant_id,
            owner_id,
            row["source_owner"],
            artifact_digest_bytes(row["original_owner_sha256"]),
            digest,
            now,
        ),
    )


def _insert_initial_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverImport,
    row: dict[str, object],
    request_id: UUID,
    owner_id: UUID,
    *,
    now: datetime,
) -> None:
    projection = cast(dict[str, object], row["projection"])
    connection.execute(
        """
        INSERT INTO request_owner_facts (
            request_id, tenant_id, sequence, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, %s, 'reviewed source-owner mapping', %s, %s, %s)
        """,
        (request_id, actor.tenant_id, owner_id, actor.principal_id, command.client_command_id, now),
    )
    connection.execute(
        """
        INSERT INTO request_priority_facts (
            request_id, tenant_id, sequence, priority, is_default, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, %s, %s, 'reviewed source-status translation', %s, %s, %s)
        """,
        (
            request_id,
            actor.tenant_id,
            projection["priority"],
            row["source_status"] == "NEW",
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO request_triage_facts (
            request_id, tenant_id, sequence, disposition, reason, canonical_request_id,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, %s, NULL, NULL, %s, %s, %s)
        """,
        (
            request_id,
            actor.tenant_id,
            projection["triage"],
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )
    if bool(projection["blocker"]):
        connection.execute(
            """
            INSERT INTO request_blocker_facts (
                blocker_fact_id, request_id, tenant_id, request_version, blocker_key,
                active, reason, recorded_by, command_id, recorded_at
            ) VALUES (%s, %s, %s, 1, 'source_blocked', true,
                      'frozen source status was BLOCKED', %s, %s, %s)
            """,
            (
                uuid7(now),
                request_id,
                actor.tenant_id,
                actor.principal_id,
                command.client_command_id,
                now,
            ),
        )
    attention = _attention_kind(cast(str, row["source_status"]), cast(list[str], row["refines"]))
    if attention is not None:
        commander = _commander(connection, actor.tenant_id, cast(str, row["project_key"]))
        connection.execute(
            """
            INSERT INTO request_attention_facts (
                attention_id, request_id, tenant_id, kind, active, owner_id, reason,
                recorded_by, command_id, recorded_at
            ) VALUES (%s, %s, %s, %s, true, %s, %s, %s, %s, %s)
            """,
            (
                uuid7(now),
                request_id,
                actor.tenant_id,
                attention[0],
                commander,
                attention[1],
                actor.principal_id,
                command.client_command_id,
                now,
            ),
        )


def _commander(
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
        raise RuntimeError("import project has no active Commander")
    return cast(UUID, row["principal_id"])


def _attention_kind(status: str, refines: list[str]) -> tuple[str, str] | None:
    if status == "NEW":
        return "request_triage_required", "Commander disposition is required"
    if status == "WIP":
        return (
            "request_execution_link_required",
            "Frozen WIP had no verified active same-project required Ticket",
        )
    if refines:
        return "request_import_attention", "Frozen Request refinements require final reconciliation"
    return None


def _problem(command: RequestCutoverImport, code: str, reason: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=f"The signed Request row import refused because {reason}.",
        status=409 if code != "request-import-forbidden" else 404,
        title="Request import refused",
        command_id=command.client_command_id,
    )

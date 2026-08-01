"""Exact signed reconciliation acceptance and importer finalization."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ctower_client.models import (
    CtowerProjectImportFinalizeRequest,
    CtowerProjectImportRun,
    CtowerProjectReconciliationResult,
)
from ctower_kernel.migration import _checkpoint_expectation_sql, _pass_two_sql
from ctower_kernel.migration._artifact import (
    ArtifactError,
    TrustedReviewerKeys,
    reviewer_key,
    verify_signed_artifact,
)
from ctower_kernel.migration._event_sql import commit_event, migration_payload
from ctower_kernel.migration._operation_result_sql import canonical, migration_sequence
from ctower_kernel.migration._run_read_sql import load_run
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.transaction import (
    authority_connection,
    project_delivery_scope_transaction,
    recover_ambiguous_commit,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def finalize_run(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
    trusted_keys: TrustedReviewerKeys,
) -> CtowerProjectReconciliationResult | RecordProblem:
    return recover_ambiguous_commit(
        lambda: _retry_serialization(
            dsn,
            actor,
            request,
            command_id=command_id,
            now=now,
            telemetry=telemetry,
            trusted_keys=trusted_keys,
        )
    )


def _finalize(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
    trusted_keys: TrustedReviewerKeys,
) -> CtowerProjectReconciliationResult | RecordProblem:
    request_digest = hashlib.sha256(canonical(request)).digest()
    try:
        artifact, report_digest = verify_signed_artifact(
            request.reconciliation_artifact,
            "ctower.ctower-project-reconciliation/v2",
            "report_digest",
            trusted_keys,
        )
        result = CtowerProjectReconciliationResult.model_validate_json(
            request.reconciliation_artifact
        )
    except (ArtifactError, ValidationError):
        return _problem(command_id, "migration-import-finalization-refused")
    with _finalization_connection(dsn, actor) as connection:
        replay = _replay(connection, actor, command_id, request_digest)
        if replay is not None:
            return replay
        run = load_run(connection, actor, request.run_id, lock=True)
        if isinstance(run, RecordProblem) or not _scope(run, request, result):
            return _problem(command_id, "migration-import-finalization-refused")
        _lock_run_tickets(connection, actor, request.run_id)
        graph, pass_two = _pass_two_sql.evidence(connection, request.run_id)
        if (
            graph is None
            or pass_two is None
            or not _current_target_matches(connection, request.run_id, graph)
            or not _artifact_matches(
                artifact,
                run,
                graph,
                pass_two,
                report_digest,
            )
        ):
            return _problem(command_id, "migration-import-finalization-refused")
        event_id, position = _commit_reconciliation(
            connection,
            actor,
            request,
            result,
            command_id=command_id,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        _insert_facts(
            connection,
            actor,
            request,
            result,
            artifact,
            event_id=event_id,
            position=position,
            command_id=command_id,
            now=now,
        )
        return result


def _current_target_matches(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    expected_graph: dict[str, object],
) -> bool:
    current = _pass_two_sql.capture(connection, run_id)
    actual_graph = _pass_two_sql.graph(current.body)
    return (
        current.project_delivery_current
        and _checkpoint_expectation_sql.matches(connection, run_id, current.body)
        and actual_graph == expected_graph
    )


def _retry_serialization(
    dsn: str,
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    *,
    command_id: UUID,
    now: datetime,
    telemetry: TelemetryContext,
    trusted_keys: TrustedReviewerKeys,
) -> CtowerProjectReconciliationResult | RecordProblem:
    for attempt in range(2):
        try:
            return _finalize(
                dsn,
                actor,
                request,
                command_id=command_id,
                now=now,
                telemetry=telemetry,
                trusted_keys=trusted_keys,
            )
        except psycopg.errors.SerializationFailure:
            if attempt == 1:
                return _problem(command_id, "migration-import-finalization-refused")
    raise AssertionError("serialization retry loop did not return")


@contextmanager
def _finalization_connection(
    dsn: str,
    actor: Actor,
) -> Iterator[psycopg.Connection[dict[str, object]]]:
    """Acquire the project fence before the serializable target snapshot."""

    with authority_connection(dsn) as connection:
        connection.autocommit = True
        connection.execute("SET ROLE ctower_svc")
        with project_delivery_scope_transaction(connection, actor.tenant_id, "all-projects"):
            connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            yield connection


def _lock_run_tickets(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
) -> None:
    """Hold every mutable Work head in the same UUID order as ordinary writers."""

    connection.execute(
        """
        SELECT ticket.ticket_id
        FROM tickets AS ticket
        JOIN ticket_project_bindings AS binding
          ON binding.tenant_id = ticket.tenant_id
         AND binding.ticket_id = ticket.ticket_id
        WHERE binding.run_id = %s AND ticket.tenant_id = %s
        ORDER BY ticket.ticket_id
        FOR SHARE OF ticket
        """,
        (run_id, actor.tenant_id),
    ).fetchall()


def _artifact_matches(
    artifact: dict[str, Any],
    run: CtowerProjectImportRun,
    graph: dict[str, object],
    pass_two: dict[str, object],
    report_digest: str,
) -> bool:
    key_ref, key_version, key_digest = reviewer_key(artifact)
    pins = cast(dict[str, object], artifact["pinned_digests"])
    watermarks = cast(dict[str, object], artifact["watermarks"])
    return (
        _artifact_scope_matches(artifact, run, graph, pass_two, report_digest)
        and _reviewer_matches(run, key_ref, key_version, key_digest)
        and pins == run.pinned_digests.model_dump(mode="json", by_alias=True)
        and _watermarks_match(run, watermarks)
    )


def _artifact_scope_matches(
    artifact: dict[str, Any],
    run: CtowerProjectImportRun,
    graph: dict[str, object],
    pass_two: dict[str, object],
    report_digest: str,
) -> bool:
    return (
        artifact.get("report_digest") == report_digest
        and artifact.get("run_id") == str(run.run_id)
        and artifact.get("cutover_id") == str(run.cutover_id)
        and artifact.get("project_key") == "ctower"
        and artifact.get("expected_graph") == graph
        and artifact.get("actual_graph") == graph
        and artifact.get("pass_two_measurement") == pass_two
        and artifact.get("target_semantic_digest") == run.semantic_digest
    )


def _reviewer_matches(
    run: CtowerProjectImportRun,
    key_ref: str,
    key_version: int,
    key_digest: str,
) -> bool:
    return (
        key_ref == run.reviewer_key.public_key_ref
        and key_version == run.reviewer_key.key_version
        and key_digest == run.reviewer_key.public_key_digest
    )


def _watermarks_match(
    run: CtowerProjectImportRun,
    watermarks: dict[str, object],
) -> bool:
    return (
        watermarks.get("source_native") == run.source_native_watermark
        and watermarks.get("export_native") == run.export_native_watermark
        and watermarks.get("record_position") == run.record_watermark
        and watermarks.get("projection_position") == run.projection_watermark
    )


def _commit_reconciliation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    result: CtowerProjectReconciliationResult,
    *,
    command_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[UUID, int]:
    return commit_event(
        connection,
        actor,
        aggregate_id=request.run_id,
        command_id=command_id,
        kind=EventKind.MIGRATION_CHANGED,
        payload=migration_payload(
            "reconciled",
            run_id=request.run_id,
            cutover_id=request.cutover_id,
            target_id=str(result.reconciliation_id),
        ),
        request_digest=request_digest,
        sequence=migration_sequence(connection, actor, request.run_id),
        stream_id=f"migration:{request.run_id}",
        now=now,
        telemetry=telemetry,
        response=lambda _event_id, _position: cast(
            dict[str, object],
            result.model_dump(mode="json", by_alias=True),
        ),
        subjects=(("migration", request.run_id),),
    )


def _insert_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    request: CtowerProjectImportFinalizeRequest,
    result: CtowerProjectReconciliationResult,
    artifact: dict[str, Any],
    *,
    event_id: UUID,
    position: int,
    command_id: UUID,
    now: datetime,
) -> None:
    signature = cast(dict[str, object], artifact["signature"])
    canonical_bytes = request.reconciliation_artifact.encode("utf-8")
    connection.execute(
        """
        INSERT INTO migration_verified_artifacts (
            run_id, artifact_kind, artifact_digest, artifact_body,
            reviewer_key_ref, reviewer_key_version, reviewer_key_digest,
            actor_principal_id, command_id, recorded_at, artifact_canonical_bytes
        ) VALUES (%s, 'reconciliation', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            request.run_id,
            _digest_bytes(result.report_digest),
            Jsonb(artifact),
            signature["key_ref"],
            signature["key_version"],
            _digest_bytes(cast(str, signature["public_key_digest"])),
            actor.principal_id,
            command_id,
            now,
            canonical_bytes,
        ),
    )
    connection.execute(
        """
        INSERT INTO migration_reconciliation_facts (
            reconciliation_id, run_id, report_digest, target_semantic_digest,
            report_body, event_id, actor_principal_id, command_id, recorded_at,
            report_canonical_bytes, pass_two_start_digest, pass_two_end_digest
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.reconciliation_id,
            request.run_id,
            _digest_bytes(result.report_digest),
            _digest_bytes(result.target_semantic_digest),
            Jsonb(artifact),
            event_id,
            actor.principal_id,
            command_id,
            now,
            canonical_bytes,
            _digest_bytes(result.pass_two_measurement.start_snapshot_digest),
            _digest_bytes(result.pass_two_measurement.end_snapshot_digest),
        ),
    )
    _insert_run_finalization(
        connection,
        actor,
        request.run_id,
        event_id=event_id,
        position=position,
        semantic_digest=result.report_digest,
        command_id=command_id,
        now=now,
    )
    _revoke_importer(connection, actor, request.run_id, command_id, now)


def _insert_run_finalization(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    *,
    event_id: UUID,
    position: int,
    semantic_digest: str,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_run_facts (
            run_fact_id, run_id, fact_sequence, state, export_equality_digest,
            alias_map_digest, semantic_digest, record_watermark, projection_watermark,
            event_id, actor_principal_id, command_id, recorded_at
        ) SELECT %s, run_id, fact_sequence + 1, 'reconciled', export_equality_digest,
            alias_map_digest, %s, %s, projection_watermark, %s, %s, %s, %s
        FROM migration_import_run_facts WHERE run_id = %s
        ORDER BY fact_sequence DESC LIMIT 1
        """,
        (
            _uuid7(now),
            _digest_bytes(semantic_digest),
            position,
            event_id,
            actor.principal_id,
            command_id,
            now,
            run_id,
        ),
    )


def _revoke_importer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        UPDATE principal_credentials AS credential
        SET revoked_at = %s
        FROM migration_importer_bindings AS binding
        WHERE binding.run_id = %s
          AND credential.principal_id = binding.principal_id
          AND credential.tenant_id = binding.tenant_id
          AND credential.credential_digest = binding.credential_digest
          AND credential.revoked_at IS NULL
        """,
        (now, run_id),
    )
    connection.execute(
        """
        INSERT INTO migration_importer_credential_facts (
            credential_fact_id, run_id, principal_id, fact_sequence, lifecycle,
            actor_principal_id, command_id, recorded_at
        ) SELECT %s, binding.run_id, binding.principal_id,
            lifecycle.fact_sequence + 1, 'revoked', %s, %s, %s
        FROM migration_importer_bindings AS binding
        JOIN LATERAL (
            SELECT max(fact_sequence) AS fact_sequence
            FROM migration_importer_credential_facts
            WHERE run_id = binding.run_id
        ) AS lifecycle ON true
        WHERE binding.run_id = %s
        """,
        (_uuid7(now), actor.principal_id, command_id, now, run_id),
    )


def _scope(
    run: CtowerProjectImportRun,
    request: CtowerProjectImportFinalizeRequest,
    result: CtowerProjectReconciliationResult,
) -> bool:
    return (
        run.state == "pass_two_noop"
        and run.cutover_id == request.cutover_id == result.cutover_id
        and run.run_id == result.run_id
        and run.semantic_digest == request.expected_run_semantic_digest
    )


def _replay(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
) -> CtowerProjectReconciliationResult | RecordProblem | None:
    row = connection.execute(
        """
        SELECT request_sha256, response_body FROM command_results
        WHERE principal_id = %s AND client_command_id = %s
        """,
        (actor.principal_id, command_id),
    ).fetchone()
    if row is None:
        return None
    if bytes(cast(bytes, row["request_sha256"])) != request_digest:
        return _problem(command_id, "migration-operation-drift")
    try:
        return CtowerProjectReconciliationResult.model_validate_json(
            json.dumps(row["response_body"])
        )
    except ValidationError:
        return _problem(command_id, "migration-operation-drift")


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _problem(command_id: UUID, code: str) -> RecordProblem:
    return RecordProblem(
        code,
        "Import run finalization refused",
        409,
        "Finalization refused",
        command_id,
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)

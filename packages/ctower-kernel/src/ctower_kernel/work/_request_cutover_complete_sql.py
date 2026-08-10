"""Finalize a fully reconciled Request authority epoch exactly once."""

from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Any, cast

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_artifacts import artifact_digest_bytes
from ctower_kernel.work._request_cutover_common_sql import (
    commit_cutover_event,
    cutover_id,
    human_operator_refusal,
    refuse,
    request_cutover_result,
    target_watermark,
)
from ctower_kernel.work._request_cutover_types import (
    RequestCutoverComplete,
    RequestCutoverResult,
)

__all__ = ["complete_cutover"]


def complete_cutover(
    dsn: str,
    actor: Actor,
    command: RequestCutoverComplete,
    *,
    manifest: dict[str, Any],
    final_fence: dict[str, Any],
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
        problem = human_operator_refusal(connection, actor, command.client_command_id)
        if problem is None:
            problem = _completion_refusal(
                connection,
                actor,
                command,
                manifest,
                public_key_digest=public_key_digest,
            )
        if problem is not None:
            return refuse(
                transaction,
                actor,
                command.client_command_id,
                request_digest,
                problem,
                now=now,
            )
        return _commit_completion(
            connection,
            transaction,
            actor,
            command,
            manifest,
            final_fence,
            request_digest=request_digest,
            telemetry=telemetry,
            now=now,
        )


def _commit_completion(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestCutoverComplete,
    manifest: dict[str, Any],
    final_fence: dict[str, Any],
    *,
    request_digest: bytes,
    telemetry: TelemetryContext,
    now: datetime,
) -> RequestCutoverResult | RecordProblem:
    durable = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        (("migration", cutover_id(command.manifest_digest)),),
        now=now,
    )
    if durable is not None:
        return durable
    _persist_refinements(connection, actor, command, manifest, now=now)
    _insert_completed_epoch(connection, actor, command, final_fence, now=now)
    result = RequestCutoverResult(
        command.client_command_id,
        "complete",
        command.manifest_digest,
        "completed",
        len(cast(list[object], manifest["rows"])),
        target_watermark(connection),
    )
    return commit_cutover_event(
        connection,
        transaction,
        actor,
        command_id=command.client_command_id,
        manifest_digest=command.manifest_digest,
        operation="request_cutover_completed",
        request_digest=request_digest,
        result=result,
        telemetry=telemetry,
        now=now,
    )


def _insert_completed_epoch(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverComplete,
    final_fence: dict[str, Any],
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO request_cutover_epoch_facts (
            epoch_fact_id, manifest_digest, tenant_id, sequence, state, fence_digest,
            reason, recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, 2, 'completed', %s,
                  'every frozen row and signed batch proof reconciled', %s, %s, %s)
        """,
        (
            uuid7(now),
            artifact_digest_bytes(command.manifest_digest),
            actor.tenant_id,
            artifact_digest_bytes(final_fence["fence_digest"]),
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _completion_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverComplete,
    manifest: dict[str, Any],
    *,
    public_key_digest: str,
) -> RecordProblem | None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"request-cutover:{command.manifest_digest}",),
    )
    row = connection.execute(
        """
        SELECT manifest.public_key_digest,
               (SELECT state FROM request_cutover_epoch_facts AS fact
                WHERE fact.tenant_id = manifest.tenant_id
                  AND fact.manifest_digest = manifest.manifest_digest
                ORDER BY sequence DESC LIMIT 1) AS state,
               (SELECT count(*) FROM request_import_rows AS imported
                WHERE imported.tenant_id = manifest.tenant_id
                  AND imported.manifest_digest = manifest.manifest_digest) AS imported_count,
               (SELECT count(*) FROM request_import_batch_proofs AS proof
                WHERE proof.tenant_id = manifest.tenant_id
                  AND proof.manifest_digest = manifest.manifest_digest) AS proof_count,
               (SELECT count(*) FROM request_import_rows AS imported
                LEFT JOIN durability_acceptance_confirmations AS confirmation
                  ON confirmation.tenant_id = imported.tenant_id
                 AND confirmation.principal_id = imported.imported_by
                 AND confirmation.client_command_id = imported.command_id
                WHERE imported.tenant_id = manifest.tenant_id
                  AND imported.manifest_digest = manifest.manifest_digest
                  AND confirmation.client_command_id IS NULL) AS pending_count
        FROM request_import_manifests AS manifest
        WHERE manifest.tenant_id = %s AND manifest.manifest_digest = %s
        """,
        (actor.tenant_id, artifact_digest_bytes(command.manifest_digest)),
    ).fetchone()
    if row is None or row["state"] != "prepared":
        return _problem(command, "request-import-forbidden", "the epoch is not prepared")
    if bytes(cast(bytes, row["public_key_digest"])) != artifact_digest_bytes(public_key_digest):
        return _problem(command, "migration-signature-invalid", "the reviewer key drifted")
    total = len(cast(list[object], manifest["rows"]))
    if int(cast(int, row["imported_count"])) != total:
        return _problem(command, "migration-import-finalization-refused", "rows are missing")
    if int(cast(int, row["pending_count"])) != 0:
        return _problem(
            command, "migration-import-finalization-refused", "import durability is pending"
        )
    if int(cast(int, row["proof_count"])) != ceil(total / 25):
        return _problem(
            command, "migration-import-finalization-refused", "signed batch proofs are missing"
        )
    return None


def _persist_refinements(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverComplete,
    manifest: dict[str, Any],
    *,
    now: datetime,
) -> None:
    rows = cast(list[dict[str, object]], manifest["rows"])
    by_source = {cast(str, row["id"]): row for row in rows}
    digest = artifact_digest_bytes(command.manifest_digest)
    for source in rows:
        for target_id in cast(list[str], source["refines"]):
            target = by_source.get(target_id)
            if target is None or target["project_key"] != source["project_key"]:
                continue
            connection.execute(
                """
                INSERT INTO request_refinement_facts (
                    refinement_fact_id, request_id, tenant_id, target_request_id,
                    manifest_digest, source_relationship_digest, recorded_by,
                    command_id, recorded_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid7(now),
                    source["request_id"],
                    actor.tenant_id,
                    target["request_id"],
                    digest,
                    artifact_digest_bytes(source["relationships_sha256"]),
                    actor.principal_id,
                    command.client_command_id,
                    now,
                ),
            )


def _problem(command: RequestCutoverComplete, code: str, reason: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=f"The Request cutover cannot complete because {reason}.",
        status=409 if code != "request-import-forbidden" else 404,
        title="Request cutover completion refused",
        command_id=command.client_command_id,
    )

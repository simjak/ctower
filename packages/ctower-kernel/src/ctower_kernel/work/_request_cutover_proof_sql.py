"""Persist one signed batch proof only after exact target reconciliation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import psycopg
from psycopg.types.json import Jsonb

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_artifacts import artifact_digest_bytes
from ctower_kernel.work._request_cutover_common_sql import (
    commit_cutover_event,
    cutover_id,
    human_operator_refusal,
    refuse,
    request_cutover_result,
)
from ctower_kernel.work._request_cutover_types import (
    RequestBatchProof,
    RequestCutoverResult,
    RequestImportReconciliation,
)

__all__ = ["record_batch_proof"]


def record_batch_proof(
    dsn: str,
    actor: Actor,
    command: RequestBatchProof,
    *,
    proof: dict[str, Any],
    reconciliation: RequestImportReconciliation,
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
            problem = _proof_refusal(
                connection,
                actor,
                command,
                proof,
                reconciliation,
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
        return _commit_proof(
            connection,
            transaction,
            actor,
            command,
            proof,
            reconciliation,
            request_digest=request_digest,
            telemetry=telemetry,
            now=now,
        )


def _commit_proof(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestBatchProof,
    proof: dict[str, Any],
    reconciliation: RequestImportReconciliation,
    *,
    request_digest: bytes,
    telemetry: TelemetryContext,
    now: datetime,
) -> RequestCutoverResult | RecordProblem:
    manifest_digest = cast(str, proof["manifest_digest"])
    durable = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        (("migration", cutover_id(manifest_digest)),),
        now=now,
    )
    if durable is not None:
        return durable
    _insert_proof(connection, actor, proof, now=now)
    result = RequestCutoverResult(
        command.client_command_id,
        "reconcile_batch",
        manifest_digest,
        "prepared",
        reconciliation.cumulative_count,
        reconciliation.target_watermark,
    )
    return commit_cutover_event(
        connection,
        transaction,
        actor,
        command_id=command.client_command_id,
        manifest_digest=manifest_digest,
        operation="request_batch_reconciled",
        request_digest=request_digest,
        result=result,
        telemetry=telemetry,
        now=now,
    )


def _insert_proof(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    proof: dict[str, Any],
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO request_import_batch_proofs (
            manifest_digest, tenant_id, batch_index, proof_digest, target_watermark,
            source_count, cumulative_count, proof_artifact, recorded_by, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            artifact_digest_bytes(proof["manifest_digest"]),
            actor.tenant_id,
            proof["batch_index"],
            artifact_digest_bytes(proof["proof_digest"]),
            proof["target_watermark"],
            proof["source_count"],
            proof["cumulative_count"],
            Jsonb(proof),
            actor.principal_id,
            now,
        ),
    )


def _proof_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestBatchProof,
    proof: dict[str, Any],
    reconciliation: RequestImportReconciliation,
    *,
    public_key_digest: str,
) -> RecordProblem | None:
    manifest_digest = cast(str, proof["manifest_digest"])
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"request-cutover:{manifest_digest}",),
    )
    row = connection.execute(
        """
        SELECT manifest.public_key_digest,
               (SELECT state FROM request_cutover_epoch_facts AS fact
                WHERE fact.tenant_id = manifest.tenant_id
                  AND fact.manifest_digest = manifest.manifest_digest
                ORDER BY sequence DESC LIMIT 1) AS state,
               (SELECT count(*) FROM request_import_batch_proofs AS saved
                WHERE saved.tenant_id = manifest.tenant_id
                  AND saved.manifest_digest = manifest.manifest_digest) AS proof_count
        FROM request_import_manifests AS manifest
        WHERE manifest.tenant_id = %s AND manifest.manifest_digest = %s
        """,
        (actor.tenant_id, artifact_digest_bytes(manifest_digest)),
    ).fetchone()
    if row is None or row["state"] != "prepared":
        return _problem(command, "request-import-forbidden", "the epoch is not prepared")
    if bytes(cast(bytes, row["public_key_digest"])) != artifact_digest_bytes(public_key_digest):
        return _problem(command, "migration-signature-invalid", "the reviewer key drifted")
    if int(cast(int, row["proof_count"])) != proof["batch_index"]:
        return _problem(command, "migration-operation-drift", "batch proofs are not serial")
    difference = _proof_difference(proof, reconciliation)
    return (
        None if difference is None else _problem(command, "migration-digest-mismatch", difference)
    )


def _proof_difference(
    proof: dict[str, Any], reconciliation: RequestImportReconciliation
) -> str | None:
    expected = reconciliation.response_payload()
    compared = (
        "batch_index",
        "batch_target_count",
        "batch_target_count_by_project",
        "cumulative_count",
        "cumulative_count_by_project",
        "manifest_digest",
        "rows",
        "source_count",
        "source_count_by_project",
        "target_count",
        "target_count_by_project",
        "target_watermark",
    )
    for key in compared:
        if proof[key] != expected[key]:
            return f"{key} differs"
    by_id = {cast(str, item["id"]): item for item in reconciliation.rows}
    samples = cast(list[dict[str, object]], proof["samples"])
    if tuple(sorted(cast(str, item["id"]) for item in samples)) != reconciliation.sample_ids:
        return "sample roster differs"
    if any(by_id.get(cast(str, item["id"])) != item for item in samples):
        return "public sample differs"
    return None


def _problem(command: RequestBatchProof, code: str, reason: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=f"The Request batch proof refused because {reason}.",
        status=409 if code != "request-import-forbidden" else 404,
        title="Request batch proof refused",
        command_id=command.client_command_id,
    )

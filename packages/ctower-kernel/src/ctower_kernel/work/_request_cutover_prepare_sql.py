"""Prepare exactly one signed Request authority epoch."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_artifacts import artifact_digest_bytes
from ctower_kernel.work._request_cutover_common_sql import (
    commit_cutover_event,
    cutover_id,
    human_operator_refusal,
    owner_is_active_and_addressable,
    refuse,
    request_cutover_result,
    target_authority_inventory,
    target_watermark,
)
from ctower_kernel.work._request_cutover_types import RequestCutoverPrepare, RequestCutoverResult

__all__ = ["prepare_cutover"]


def prepare_cutover(
    dsn: str,
    actor: Actor,
    command: RequestCutoverPrepare,
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
        problem = human_operator_refusal(connection, actor, command.client_command_id)
        if problem is None:
            problem = _preparation_refusal(connection, actor, command, manifest)
        if problem is not None:
            return refuse(
                transaction,
                actor,
                command.client_command_id,
                request_digest,
                problem,
                now=now,
            )
        return _commit_preparation(
            connection,
            transaction,
            actor,
            command,
            manifest,
            fence,
            public_key_digest=public_key_digest,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _commit_preparation(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestCutoverPrepare,
    manifest: dict[str, Any],
    fence: dict[str, Any],
    *,
    public_key_digest: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestCutoverResult | RecordProblem:
    manifest_digest = cast(str, manifest["manifest_digest"])
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
    _persist_preparation(
        connection,
        actor,
        command,
        manifest,
        fence,
        public_key_digest=public_key_digest,
        now=now,
    )
    result = RequestCutoverResult(
        command.client_command_id,
        "prepare",
        manifest_digest,
        "prepared",
        0,
        target_watermark(connection),
    )
    return commit_cutover_event(
        connection,
        transaction,
        actor,
        command_id=command.client_command_id,
        manifest_digest=manifest_digest,
        operation="request_cutover_prepared",
        request_digest=request_digest,
        result=result,
        telemetry=telemetry,
        now=now,
    )


def _preparation_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverPrepare,
    manifest: dict[str, Any],
) -> RecordProblem | None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"request-cutover-tenant:{actor.tenant_id}",),
    )
    if manifest["target_tenant_id"] != str(actor.tenant_id):
        return _problem(command, "migration-digest-mismatch", "target tenant binding differs")
    inventory = target_authority_inventory(connection, actor.tenant_id)
    if manifest["target_authority_digest"] != inventory["authority_digest"]:
        return _problem(command, "migration-digest-mismatch", "target authority inventory drifted")
    existing = connection.execute(
        "SELECT 1 FROM requests WHERE tenant_id = %s LIMIT 1", (actor.tenant_id,)
    ).fetchone()
    if existing is not None:
        return _problem(command, "migration-run-conflict", "target already contains Requests")
    epoch = connection.execute(
        "SELECT 1 FROM request_cutover_epoch_facts WHERE tenant_id = %s LIMIT 1",
        (actor.tenant_id,),
    ).fetchone()
    if epoch is not None:
        return _problem(command, "migration-run-conflict", "a Request cutover epoch already exists")
    for item in cast(list[dict[str, object]], manifest["rows"]):
        if not owner_is_active_and_addressable(
            connection,
            actor.tenant_id,
            UUID(cast(str, item["mapped_principal_id"])),
            cast(str, item["project_key"]),
        ):
            return _problem(
                command,
                "migration-operation-drift",
                f"mapped owner is unavailable for {item['id']}",
            )
    return None


def _persist_preparation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCutoverPrepare,
    manifest: dict[str, Any],
    fence: dict[str, Any],
    *,
    public_key_digest: str,
    now: datetime,
) -> None:
    digest = artifact_digest_bytes(manifest["manifest_digest"])
    counts = cast(dict[str, object], manifest["counts"])
    source_identity = cast(dict[str, object], manifest["source_identity"])
    connection.execute(
        """
        INSERT INTO request_import_manifests (
            manifest_digest, tenant_id, archive_ref, ledger_digest, rows_digest,
            row_count, maximum_request_number, project_counts, owner_mapping_digest,
            target_authority_digest, observed_file_size, manifest_artifact,
            public_key_digest, fence_digest, sealed_at, recorded_by, recorded_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            digest,
            actor.tenant_id,
            manifest["archive_ref"],
            artifact_digest_bytes(manifest["ledger_sha256"]),
            artifact_digest_bytes(manifest["rows_digest"]),
            counts["open_requests"],
            manifest["maximum_request_number"],
            Jsonb(_project_count_mapping(counts["open_by_project"])),
            artifact_digest_bytes(manifest["owner_mapping_sha256"]),
            artifact_digest_bytes(manifest["target_authority_digest"]),
            source_identity["size"],
            Jsonb(manifest),
            artifact_digest_bytes(public_key_digest),
            artifact_digest_bytes(fence["fence_digest"]),
            now,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO request_number_allocators (tenant_id, last_number, advanced_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (tenant_id) DO UPDATE
        SET last_number = GREATEST(
                request_number_allocators.last_number,
                EXCLUDED.last_number
            ),
            advanced_at = EXCLUDED.advanced_at
        """,
        (actor.tenant_id, manifest["maximum_request_number"], now),
    )
    connection.execute(
        """
        INSERT INTO request_cutover_epoch_facts (
            epoch_fact_id, manifest_digest, tenant_id, sequence, state, fence_digest,
            reason, recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, 1, 'prepared', %s,
                  'signed source denominator prepared', %s, %s, %s)
        """,
        (
            uuid7(now),
            digest,
            actor.tenant_id,
            artifact_digest_bytes(fence["fence_digest"]),
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _problem(command: RequestCutoverPrepare, code: str, reason: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=f"The signed Request cutover cannot prepare because {reason}.",
        status=409,
        title="Request cutover preparation refused",
        command_id=command.client_command_id,
    )


def _project_count_mapping(value: object) -> dict[str, int]:
    items = cast(list[dict[str, object]], value)
    return {cast(str, item["project_key"]): cast(int, item["count"]) for item in items}

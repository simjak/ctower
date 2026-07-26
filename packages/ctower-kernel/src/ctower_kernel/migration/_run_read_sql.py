"""Run-scoped read model and strict generated-boundary reconstruction."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import ValidationError

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectImportRun,
    CtowerProjectImportRunCreateRequest,
    DurabilityState,
    MigrationImportCounts,
    MigrationImporterBinding,
    MigrationPinnedDigests,
)
from ctower_kernel.migration._measurement_sql import MigrationMeasurement, measure
from ctower_kernel.record import Actor, RecordProblem

__all__: tuple[str, ...] = ()

_RUN_QUERY = """
    SELECT run.*, binding.credential_digest, binding.expires_at,
        credential.lifecycle,
        CASE
            WHEN fact.state = 'pass_one_complete'
             AND coalesce(plan.operation_count, 0) > 0
             AND coalesce((
                SELECT sum(operation_count)
                FROM migration_import_replay_receipts AS replay_state
                WHERE replay_state.run_id = run.run_id
             ), 0) = plan.operation_count
            THEN 'pass_two_noop'
            ELSE fact.state
        END AS state,
        fact.export_equality_digest,
        fact.alias_map_digest, fact.semantic_digest, fact.record_watermark,
        fact.projection_watermark, plan.plan_digest, registry.registry_digest,
        (SELECT count(*) FROM migration_import_operation_results AS operation
         WHERE operation.run_id = run.run_id) AS applied_operations,
        coalesce(plan.operation_count, 0) AS planned_operations,
        (SELECT coalesce(sum(operation_count), 0)
         FROM migration_import_replay_receipts AS replay
         WHERE replay.run_id = run.run_id) AS replayed_operations
    FROM migration_import_runs AS run
    JOIN migration_importer_bindings AS binding ON binding.run_id = run.run_id
    JOIN LATERAL (
        SELECT lifecycle FROM migration_importer_credential_facts
        WHERE run_id = run.run_id ORDER BY fact_sequence DESC LIMIT 1
    ) AS credential ON true
    JOIN LATERAL (
        SELECT * FROM migration_import_run_facts
        WHERE run_id = run.run_id ORDER BY fact_sequence DESC LIMIT 1
    ) AS fact ON true
    LEFT JOIN migration_import_plans AS plan ON plan.run_id = run.run_id
    LEFT JOIN migration_fence_registries AS registry ON registry.run_id = run.run_id
    WHERE run.run_id = %s AND run.tenant_id = %s
"""


def get_run(dsn: str, actor: Actor, run_id: UUID) -> CtowerProjectImportRun | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        return load_run(connection, actor, run_id)


def load_run(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    *,
    lock: bool = False,
) -> CtowerProjectImportRun | RecordProblem:
    if lock:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"migration-run:{run_id}",),
        )
    row = connection.execute(_RUN_QUERY, (run_id, actor.tenant_id)).fetchone()
    if row is None:
        return RecordProblem(
            "migration-run-conflict",
            "Import run unavailable",
            404,
            "Import run unavailable",
        )
    return _model_from_row(row, measure(connection, run_id))


def initial_model(
    request: CtowerProjectImportRunCreateRequest,
    run_id: UUID,
    *,
    semantic_digest: str,
) -> CtowerProjectImportRun:
    return CtowerProjectImportRun.model_validate(
        {
            "schema": "ctower.ctower-project-import-run/v1",
            "run_id": run_id,
            "cutover_id": request.cutover_id,
            "tenant_key": "ctower",
            "project_key": "ctower",
            "state": "created",
            "pinned_digests": _initial_pins(request),
            "importer_binding": {
                "principal_kind": "migration_importer",
                "credential_digest": request.importer_credential_digest,
                "expires_at": request.importer_expires_at,
                "revoked": False,
            },
            "counts": _counts(0, 0, 0),
            "dispositions": None,
            "conservation": None,
            "source_native_watermark": 0,
            "export_native_watermark": 0,
            "record_watermark": 0,
            "projection_watermark": 0,
            "refusals": (),
            "semantic_digest": semantic_digest,
            "durability_state": DurabilityState.DURABILITY_PENDING,
            "accepted_position": None,
        }
    )


def replay_run(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
) -> CtowerProjectImportRun | RecordProblem | None:
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
        return _drift(command_id, "Command replay changed")
    try:
        return CtowerProjectImportRun.model_validate_json(json.dumps(row["response_body"]))
    except ValidationError:
        return _drift(command_id, "Command identity was reused")


def valid_export(
    current: CtowerProjectImportRun, request: CtowerProjectExportEqualityBindRequest
) -> bool:
    return (
        current.state == "created"
        and current.cutover_id == request.cutover_id
        and current.pinned_digests.source_selection == request.selection_digest
        and current.pinned_digests.reviewer_public_key == request.reviewer_public_key_digest
    )


def valid_alias(
    current: CtowerProjectImportRun, request: CtowerProjectAliasPlanBindRequest
) -> bool:
    return (
        current.state == "export_equality_bound"
        and current.cutover_id == request.cutover_id
        and current.pinned_digests.export_equality == request.export_equality_digest
        and current.pinned_digests.reviewer_public_key == request.reviewer_public_key_digest
    )


def ctower_scope_available(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    cutover_id: UUID,
) -> bool:
    tenant = connection.execute(
        "SELECT 1 FROM tenants WHERE tenant_id = %s AND slug = 'ctower'",
        (actor.tenant_id,),
    ).fetchone()
    duplicate = connection.execute(
        "SELECT 1 FROM migration_import_runs WHERE tenant_id = %s AND cutover_id = %s",
        (actor.tenant_id, cutover_id),
    ).fetchone()
    return tenant is not None and duplicate is None


def _initial_pins(request: CtowerProjectImportRunCreateRequest) -> dict[str, object]:
    return {
        "source_selection": request.source_selection_digest,
        "export_equality": None,
        "alias_map": None,
        "import_plan": None,
        "fence_registry": None,
        "build": request.build_digest,
        "client": request.client_digest,
        "schema": request.schema_digest,
        "operation_registry": request.operation_registry_digest,
        "reviewer_public_key": request.reviewer_public_key_digest,
    }


def _model_from_row(
    row: dict[str, object],
    measurement: MigrationMeasurement | None,
) -> CtowerProjectImportRun:
    pinned = MigrationPinnedDigests.model_validate(
        {
            "source_selection": _digest_text(row["source_selection_digest"]),
            "export_equality": _optional_digest(row["export_equality_digest"]),
            "alias_map": _optional_digest(row["alias_map_digest"]),
            "import_plan": _optional_digest(row["plan_digest"]),
            "fence_registry": _optional_digest(row["registry_digest"]),
            "build": _digest_text(row["build_digest"]),
            "client": _digest_text(row["client_digest"]),
            "schema": _digest_text(row["schema_digest"]),
            "operation_registry": _digest_text(row["operation_registry_digest"]),
            "reviewer_public_key": _digest_text(row["reviewer_public_key_digest"]),
        }
    )
    return CtowerProjectImportRun.model_validate(
        {
            "schema": "ctower.ctower-project-import-run/v1",
            "run_id": row["run_id"],
            "cutover_id": row["cutover_id"],
            "tenant_key": "ctower",
            "project_key": "ctower",
            "state": row["state"],
            "pinned_digests": pinned,
            "importer_binding": _binding(row),
            "counts": _counts(
                int(cast(int, row["planned_operations"])),
                int(cast(int, row["applied_operations"])),
                int(cast(int, row["replayed_operations"])),
            ),
            "dispositions": measurement.dispositions if measurement is not None else None,
            "conservation": measurement.conservation if measurement is not None else None,
            "source_native_watermark": (
                measurement.source_native_watermark if measurement is not None else 0
            ),
            "export_native_watermark": (
                measurement.export_native_watermark if measurement is not None else 0
            ),
            "record_watermark": row["record_watermark"],
            "projection_watermark": row["projection_watermark"],
            "refusals": (),
            "semantic_digest": _digest_text(row["semantic_digest"]),
            "durability_state": DurabilityState.DURABILITY_PENDING,
            "accepted_position": None,
        }
    )


def _binding(row: dict[str, object]) -> MigrationImporterBinding:
    return MigrationImporterBinding(
        principal_kind="migration_importer",
        credential_digest=_digest_text(row["credential_digest"]),
        expires_at=cast(datetime, row["expires_at"]),
        revoked=row["lifecycle"] == "revoked",
    )


def _counts(planned: int, applied: int, replayed: int) -> MigrationImportCounts:
    return MigrationImportCounts(
        planned_operations=planned,
        applied_operations=applied,
        replayed_operations=replayed,
        refused_operations=0,
    )


def _digest_text(value: object) -> str:
    return f"sha256:{bytes(cast(bytes, value)).hex()}"


def _optional_digest(value: object) -> str | None:
    return None if value is None else _digest_text(value)


def _drift(command_id: UUID, title: str) -> RecordProblem:
    return RecordProblem("migration-operation-drift", title, 409, title, command_id)

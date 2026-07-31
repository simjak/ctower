"""Verified artifact graph persistence and exact plan capability activation."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid5

import psycopg
import rfc8785
from psycopg.types.json import Jsonb

from ctower_client.models import (
    CtowerProjectAliasPlanBindRequest,
    CtowerProjectExportEqualityBindRequest,
    CtowerProjectImportRun,
    CtowerProjectImportRunCreateRequest,
)
from ctower_kernel.migration._artifact import (
    ArtifactError,
    TrustedReviewerKeys,
    parse_artifact,
    reviewer_key,
    verify_signed_artifact,
)
from ctower_kernel.record import Actor

__all__ = [
    "persist_export_graph",
    "persist_plan_graph",
    "persist_source_selection",
    "verify_source_selection",
]

_COMMAND_NAMESPACE = UUID("7c4ef338-17fd-5be3-a6b7-c89205ecb574")


def persist_source_selection(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    artifact: dict[str, Any],
    digest: str,
    *,
    run_id: UUID,
    command_id: UUID,
    now: datetime,
) -> None:
    _insert_artifact(
        connection, actor, run_id, "source_selection", artifact, digest, command_id, now
    )


def verify_source_selection(
    request: CtowerProjectImportRunCreateRequest,
    trusted_keys: TrustedReviewerKeys,
) -> tuple[dict[str, Any], str]:
    artifact, digest = verify_signed_artifact(
        request.source_selection_artifact,
        "ctower.ctower-project-source-selection/v1",
        "manifest_digest",
        trusted_keys,
    )
    signature = cast(dict[str, object], artifact["signature"])
    scope = cast(dict[str, object], artifact["cutover_scope"])
    key_ref, key_version, key_digest = reviewer_key(artifact)
    if (
        digest != request.source_selection_digest
        or signature["public_key_digest"] != key_digest
        or key_ref != request.reviewer_key_ref
        or key_version != request.reviewer_key_version
        or key_digest != request.reviewer_public_key_digest
        or scope.get("tenant_key") != "ctower"
        or scope.get("project_key") != "ctower"
    ):
        raise ArtifactError("source-selection-rebound")
    return artifact, digest


def persist_export_graph(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run: CtowerProjectImportRun,
    request: CtowerProjectExportEqualityBindRequest,
    *,
    command_id: UUID,
    now: datetime,
    trusted_keys: TrustedReviewerKeys,
) -> None:
    export_a = _unsigned_export(request.export_a_artifact)
    export_b = _unsigned_export(request.export_b_artifact)
    equality, equality_digest = verify_signed_artifact(
        request.export_equality_artifact,
        "ctower.ctower-project-export-equality/v1",
        "report_digest",
        trusted_keys,
    )
    _require_run_reviewer(connection, run.run_id, equality)
    digest_a, digest_b = str(export_a["artifact_digest"]), str(export_b["artifact_digest"])
    target_a = cast(dict[str, object], export_a["target_inventory"])
    target_b = cast(dict[str, object], export_b["target_inventory"])
    if not _equality_graph_valid(
        run,
        request,
        equality,
        equality_digest,
        digest_a,
        digest_b,
    ) or not _export_pair_valid(
        request,
        export_a,
        export_b,
        target_a,
        target_b,
        digest_a,
        digest_b,
        run.pinned_digests,
    ):
        raise ArtifactError("export-graph-rebound")
    for kind, artifact, digest in (
        ("export_a", export_a, digest_a),
        ("export_b", export_b, digest_b),
        ("export_equality", equality, equality_digest),
    ):
        _insert_artifact(connection, actor, run.run_id, kind, artifact, digest, command_id, now)


def persist_plan_graph(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run: CtowerProjectImportRun,
    request: CtowerProjectAliasPlanBindRequest,
    *,
    command_id: UUID,
    now: datetime,
    trusted_keys: TrustedReviewerKeys,
) -> tuple[str, str]:
    alias, alias_digest = verify_signed_artifact(
        request.alias_map_artifact,
        "ctower.ctower-project-alias-map/v2",
        "map_digest",
        trusted_keys,
    )
    plan, plan_digest = verify_signed_artifact(
        request.import_plan_artifact,
        "ctower.ctower-project-import-plan/v2",
        "plan_digest",
        trusted_keys,
    )
    registry, registry_digest = verify_signed_artifact(
        request.fence_registry_artifact,
        "ctower.ctower-project-fence-registry/v2",
        "registry_digest",
        trusted_keys,
    )
    for artifact in (alias, plan, registry):
        _require_run_reviewer(connection, run.run_id, artifact)
    selection = _stored_artifact(connection, run.run_id, "source_selection")
    request_ids = cast(list[object], selection["selected_request_ids"])
    stable_ids = cast(list[object], selection["stable_item_ids"])
    checkpoint_keys = cast(list[object], selection["checkpoint_keys"])
    if not _plan_graph_valid(
        run,
        request,
        alias,
        alias_digest,
        plan,
        registry,
        request_ids,
        stable_ids,
        checkpoint_keys,
    ):
        raise ArtifactError("plan-graph-rebound")
    batches = cast(list[dict[str, Any]], plan["batches"])
    _verify_batches(run, batches, int(cast(int, plan["operation_count"])))
    for kind, artifact, digest in (
        ("alias_map", alias, alias_digest),
        ("import_plan", plan, plan_digest),
        ("fence_registry", registry, registry_digest),
    ):
        _insert_artifact(connection, actor, run.run_id, kind, artifact, digest, command_id, now)
    _insert_plan(connection, run.run_id, plan, batches, now)
    _insert_stable_aliases(connection, actor, run.run_id, alias, now)
    _activate_importer(connection, actor, run.run_id, command_id, now)
    _create_observer(connection, actor, run, request, registry, registry_digest, now)
    return plan_digest, registry_digest


def _unsigned_export(text: str) -> dict[str, Any]:
    artifact = parse_artifact(text, "ctower.ctower-project-export-manifest/v1")
    claimed = artifact.get("artifact_digest")
    body = {key: value for key, value in artifact.items() if key != "artifact_digest"}
    expected = f"sha256:{hashlib.sha256(rfc8785.dumps(body)).hexdigest()}"
    if claimed != expected:
        raise ArtifactError("export-digest-rebound")
    return artifact


def _target_pins(target: dict[str, object], pins: object) -> bool:
    values = cast(Any, pins)
    return (
        target.get("tenant_key") == "ctower"
        and target.get("project_key") == "ctower"
        and target.get("build_digest") == values.build
        and target.get("client_digest") == values.client
        and target.get("schema_digest") == values.schema_id
        and target.get("operation_registry_digest") == values.operation_registry
    )


def _equality_graph_valid(
    run: CtowerProjectImportRun,
    request: CtowerProjectExportEqualityBindRequest,
    equality: dict[str, Any],
    equality_digest: str,
    digest_a: str,
    digest_b: str,
) -> bool:
    return (
        equality_digest == request.equality_report_digest
        and equality.get("result") == "equal"
        and equality.get("mismatches") == []
        and equality.get("cutover_id") == str(run.cutover_id)
        and equality.get("selection_digest") == run.pinned_digests.source_selection
        and {equality.get("export_a_digest"), equality.get("export_b_digest")}
        == {digest_a, digest_b}
    )


def _export_pair_valid(
    request: CtowerProjectExportEqualityBindRequest,
    export_a: dict[str, Any],
    export_b: dict[str, Any],
    target_a: dict[str, object],
    target_b: dict[str, object],
    digest_a: str,
    digest_b: str,
    pins: object,
) -> bool:
    return (
        request.inventory_a_digest == target_a["inventory_digest"]
        and request.inventory_b_digest == target_b["inventory_digest"]
        and request.export_digest in {digest_a, digest_b}
        and export_a.get("exporter_pass") == "export_a"
        and export_b.get("exporter_pass") == "export_b"
        and _target_pins(target_a, pins)
        and target_a == target_b
    )


def _plan_graph_valid(
    run: CtowerProjectImportRun,
    request: CtowerProjectAliasPlanBindRequest,
    alias: dict[str, Any],
    alias_digest: str,
    plan: dict[str, Any],
    registry: dict[str, Any],
    request_ids: list[object],
    stable_ids: list[object],
    checkpoint_keys: list[object],
) -> bool:
    return (
        _alias_graph_valid(run, request, alias, alias_digest, stable_ids)
        and _plan_binding_valid(run, plan, alias, alias_digest, checkpoint_keys)
        and _registry_binding_valid(run, registry, request_ids)
    )


def _alias_graph_valid(
    run: CtowerProjectImportRun,
    request: CtowerProjectAliasPlanBindRequest,
    alias: dict[str, Any],
    alias_digest: str,
    stable_ids: list[object],
) -> bool:
    entries = cast(list[dict[str, object]], alias["entries"])
    stable_aliases = cast(list[dict[str, object]], alias["stable_aliases"])
    return (
        alias_digest == request.alias_map_digest
        and alias.get("attention_required") == 0
        and all(item.get("disposition") != "attention_required" for item in entries)
        and alias.get("cutover_id") == str(run.cutover_id)
        and alias.get("selection_digest") == run.pinned_digests.source_selection
        and alias.get("export_equality_digest") == run.pinned_digests.export_equality
        and _exact_unique_values(
            stable_ids,
            (item.get("stable_item_id") for item in stable_aliases),
        )
    )


def _plan_binding_valid(
    run: CtowerProjectImportRun,
    plan: dict[str, Any],
    alias: dict[str, Any],
    alias_digest: str,
    checkpoint_keys: list[object],
) -> bool:
    definitions = cast(list[dict[str, object]], plan["checkpoint_definitions"])
    return (
        plan.get("run_id") == str(run.run_id)
        and plan.get("cutover_id") == str(run.cutover_id)
        and plan.get("selection_digest") == run.pinned_digests.source_selection
        and plan.get("export_equality_digest") == run.pinned_digests.export_equality
        and plan.get("alias_map_digest") == alias_digest
        and _exact_unique_values(
            checkpoint_keys,
            (item.get("checkpoint_key") for item in definitions),
        )
        and _stable_alias_operations_match(plan, alias)
    )


def _stable_alias_operations_match(
    plan: dict[str, Any],
    alias: dict[str, Any],
) -> bool:
    expected = {
        (
            str(item["stable_item_id"]),
            str(item["target_ticket_id"]),
        )
        for item in cast(list[dict[str, object]], alias["stable_aliases"])
    }
    actual: list[tuple[str, str]] = []
    for batch in cast(list[dict[str, Any]], plan["batches"]):
        for operation in cast(list[dict[str, Any]], batch["operations"]):
            identity = cast(dict[str, object], operation["identity"])
            source = cast(dict[str, object], operation.get("source", {}))
            if identity.get("namespace") != "stable-backlog":
                continue
            if operation.get("operation") != "exact_alias":
                return False
            actual.append(
                (
                    str(source.get("immutable_source_id")),
                    str(operation.get("target_ticket_id")),
                )
            )
    return _exact_unique_values(expected, actual)


def _exact_unique_values(
    expected: Iterable[object],
    actual: Iterable[object],
) -> bool:
    expected_values = tuple(str(value) for value in expected)
    actual_values = tuple(str(value) for value in actual)
    return (
        len(expected_values) == len(set(expected_values))
        and len(actual_values) == len(set(actual_values))
        and set(actual_values) == set(expected_values)
    )


def _registry_binding_valid(
    run: CtowerProjectImportRun,
    registry: dict[str, Any],
    request_ids: list[object],
) -> bool:
    pointer = cast(dict[str, object], registry["source_pointer"])
    pointer_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, pointer))).hexdigest()}"
    return _registry_scope_valid(
        run, registry, request_ids, pointer_digest
    ) and _registry_policy_valid(registry)


def _registry_scope_valid(
    run: CtowerProjectImportRun,
    registry: dict[str, Any],
    request_ids: list[object],
    pointer_digest: str,
) -> bool:
    return (
        registry.get("cutover_id") == str(run.cutover_id)
        and registry.get("source_selection_digest") == run.pinned_digests.source_selection
        and registry.get("tenant_key") == "ctower"
        and registry.get("project_key") == "ctower"
        and registry.get("operation_registry_digest") == run.pinned_digests.operation_registry
        and _exact_unique_values(
            request_ids,
            cast(list[object], registry.get("selected_request_ids", [])),
        )
        and registry.get("selected_task_ids") == []
        and registry.get("source_pointer_digest") == pointer_digest
    )


def _registry_policy_valid(registry: dict[str, Any]) -> bool:
    monitor = int(cast(int, registry["monitor_interval_seconds"]))
    return (
        monitor >= 1
        and int(cast(int, registry["max_observation_age_seconds"])) >= monitor
        and int(cast(int, registry["max_future_clock_skew_seconds"])) >= 0
    )


def _verify_batches(
    run: CtowerProjectImportRun,
    batches: list[dict[str, Any]],
    operation_count: int,
) -> None:
    if len(batches) < 1 or operation_count != sum(len(batch["operations"]) for batch in batches):
        raise ArtifactError("plan-nonexhaustive")
    for index, batch in enumerate(batches):
        body = {key: value for key, value in batch.items() if key != "batch_digest"}
        expected_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(body)).hexdigest()}"
        if (
            batch.get("run_id") != str(run.run_id)
            or batch.get("cutover_id") != str(run.cutover_id)
            or batch.get("batch_index") != index
            or batch.get("batch_digest") != expected_digest
        ):
            raise ArtifactError("plan-batch-rebound")
        for operation in cast(list[dict[str, Any]], batch["operations"]):
            identity = cast(dict[str, object], operation["identity"])
            stable = "|".join(
                str(identity[key])
                for key in (
                    "namespace",
                    "immutable_source_id",
                    "source_version_or_digest",
                    "operation_kind",
                    "planned_target_ref",
                )
            )
            if identity.get("command_id") != str(uuid5(_COMMAND_NAMESPACE, stable)):
                raise ArtifactError("plan-command-rebound")


def _insert_artifact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    kind: str,
    artifact: dict[str, Any],
    digest: str,
    command_id: UUID,
    now: datetime,
) -> None:
    signature = cast(dict[str, object] | None, artifact.get("signature"))
    connection.execute(
        """
        INSERT INTO migration_verified_artifacts (
            run_id, artifact_kind, artifact_digest, artifact_body,
            reviewer_key_ref, reviewer_key_version, reviewer_key_digest,
            actor_principal_id, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            kind,
            _digest_bytes(digest),
            Jsonb(artifact),
            signature.get("key_ref") if signature else None,
            signature.get("key_version") if signature else None,
            _digest_bytes(cast(str, signature["public_key_digest"])) if signature else None,
            actor.principal_id,
            command_id,
            now,
        ),
    )


def _require_run_reviewer(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    artifact: dict[str, Any],
) -> None:
    row = connection.execute(
        """
        SELECT reviewer_key_ref, reviewer_key_version, reviewer_public_key_digest
        FROM migration_import_runs WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        raise ArtifactError("artifact-run-unavailable")
    key_ref, key_version, key_digest = reviewer_key(artifact)
    pinned_digest = _digest_bytes(key_digest)
    if (
        row["reviewer_key_ref"] != key_ref
        or row["reviewer_key_version"] != key_version
        or bytes(cast(bytes, row["reviewer_public_key_digest"])) != pinned_digest
    ):
        raise ArtifactError("review-key-transition-refused")


def _insert_plan(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    plan: dict[str, Any],
    batches: list[dict[str, Any]],
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_import_plans (
            run_id, plan_id, plan_digest, batch_count, operation_count,
            source_native_watermark, export_native_watermark, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            plan["plan_id"],
            _digest_bytes(cast(str, plan["plan_digest"])),
            len(batches),
            plan["operation_count"],
            plan["source_native_watermark"],
            plan["export_native_watermark"],
            now,
        ),
    )
    for batch in batches:
        request_digest = hashlib.sha256(rfc8785.dumps(batch)).digest()
        connection.execute(
            """
            INSERT INTO migration_import_plan_batches (
                run_id, batch_index, batch_digest, request_digest, operation_count, batch_body
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                batch["batch_index"],
                _digest_bytes(cast(str, batch["batch_digest"])),
                request_digest,
                len(batch["operations"]),
                Jsonb(batch),
            ),
        )


def _insert_stable_aliases(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    alias: dict[str, Any],
    now: datetime,
) -> None:
    aliases = cast(list[dict[str, object]], alias["stable_aliases"])
    target_ids = [UUID(str(item["target_ticket_id"])) for item in aliases]
    row = connection.execute(
        """
        SELECT count(*) AS count FROM tickets
        WHERE tenant_id = %s AND ticket_id = ANY(%s)
        """,
        (actor.tenant_id, target_ids),
    ).fetchone()
    if row is None or int(cast(int, row["count"])) != len(set(target_ids)):
        raise ArtifactError("stable-alias-target-unavailable")
    for item in aliases:
        material = {
            "stable_item_id": item["stable_item_id"],
            "target_ticket_id": item["target_ticket_id"],
        }
        connection.execute(
            """
            INSERT INTO migration_stable_alias_bindings (
                run_id, stable_item_id, target_ticket_id, mapping_digest, recorded_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                run_id,
                item["stable_item_id"],
                item["target_ticket_id"],
                hashlib.sha256(rfc8785.dumps(cast(Any, material))).digest(),
                now,
            ),
        )


def _activate_importer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run_id: UUID,
    command_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_importer_credential_facts (
            credential_fact_id, run_id, principal_id, fact_sequence, lifecycle,
            actor_principal_id, command_id, recorded_at
        ) SELECT %s, run_id, principal_id, 2, 'activated', %s, %s, %s
        FROM migration_importer_bindings WHERE run_id = %s
        """,
        (_uuid7(now), actor.principal_id, command_id, now, run_id),
    )


def _create_observer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    run: CtowerProjectImportRun,
    request: CtowerProjectAliasPlanBindRequest,
    registry: dict[str, Any],
    registry_digest: str,
    now: datetime,
) -> None:
    principal_id, credential_id = _uuid7(now), _uuid7(now)
    connection.execute(
        """
        INSERT INTO principals (
            principal_id, tenant_id, kind, display_name, disabled, created_at
        ) VALUES (%s, %s, 'fence_observer', %s, false, %s)
        """,
        (principal_id, actor.tenant_id, f"ctower:fence-observer:{run.run_id}", now),
    )
    connection.execute(
        """
        INSERT INTO principal_credentials (
            credential_id, principal_id, tenant_id, credential_digest, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            credential_id,
            principal_id,
            actor.tenant_id,
            _digest_bytes(request.fence_observer_credential_digest),
            now,
        ),
    )
    values = (
        run.run_id,
        actor.tenant_id,
        run.cutover_id,
        registry["registry_id"],
        registry["revision"],
        _digest_bytes(registry_digest),
    )
    pointer = cast(dict[str, object], registry["source_pointer"])
    connection.execute(
        """
        INSERT INTO migration_fence_registries (
            run_id, tenant_id, cutover_id, project_key, registry_id,
            registry_revision, registry_digest, source_selection_digest,
            source_pointer_digest, source_pointer_device, source_pointer_inode,
            source_pointer_offset, source_pointer_scoped_digest,
            monitor_interval_seconds, max_observation_age_seconds,
            max_future_clock_skew_seconds
        ) VALUES (
            %s, %s, %s, 'ctower', %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        """,
        (
            *values,
            _digest_bytes(run.pinned_digests.source_selection),
            _digest_bytes(cast(str, registry["source_pointer_digest"])),
            pointer["device"],
            pointer["inode"],
            pointer["last_complete_offset"],
            _digest_bytes(cast(str, pointer["scoped_rows_digest"])),
            registry["monitor_interval_seconds"],
            registry["max_observation_age_seconds"],
            registry["max_future_clock_skew_seconds"],
        ),
    )
    connection.execute(
        """
        INSERT INTO migration_fence_observer_bindings (
            run_id, tenant_id, cutover_id, project_key, registry_id,
            registry_revision, registry_digest, principal_id, credential_digest,
            expires_at, created_at
        ) VALUES (%s, %s, %s, 'ctower', %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            *values,
            principal_id,
            _digest_bytes(request.fence_observer_credential_digest),
            request.fence_observer_expires_at,
            now,
        ),
    )


def _stored_artifact(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    kind: str,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT artifact_body FROM migration_verified_artifacts
        WHERE run_id = %s AND artifact_kind = %s
        """,
        (run_id, kind),
    ).fetchone()
    if row is None:
        raise ArtifactError("artifact-graph-incomplete")
    return cast(dict[str, Any], row["artifact_body"])


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)

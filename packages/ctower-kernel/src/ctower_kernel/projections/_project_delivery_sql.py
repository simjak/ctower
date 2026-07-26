"""Read-only Postgres queries for I1.7 authority and Project Delivery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.projections.project_delivery import (
    CtowerProjectCutoverHealth,
    DeliveryState,
    MigrationHealthDigests,
    ProjectDeliveryRow,
    ProjectDeliveryView,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _MigrationState:
    run_id: UUID
    cutover_id: UUID
    phase: str
    record_watermark: int
    projection_watermark: int
    digests: MigrationHealthDigests
    fence_status: str | None


@dataclass(frozen=True, slots=True)
class _HealthState:
    source: int
    projected: int
    complete: str
    split_brain: str
    fence: str
    writes_enabled: bool


def cutover_health(dsn: str, actor: Actor) -> CtowerProjectCutoverHealth:
    """Return the latest append-only fact, defaulting safely before I1.7B/C."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        fact, ambiguous = _select_authority_fact(connection, actor.tenant_id)
        stats = _projection_stats(connection, actor.tenant_id)
        migration = _migration_state(connection, actor.tenant_id)
    state = _health_state(fact, migration, stats, ambiguous=ambiguous)
    if fact is None:
        return _preauthority_health(migration, state)
    return _authority_health(fact, migration, state)


def _health_state(
    fact: dict[str, object] | None,
    migration: _MigrationState | None,
    stats: dict[str, int],
    *,
    ambiguous: bool,
) -> _HealthState:
    source = _source_watermark(fact, migration)
    projected = _projection_watermark(fact, migration, stats)
    complete = _completeness(
        stats,
        source,
        fact_present=fact is not None,
        ambiguous=ambiguous,
    )
    if fact is None and migration is not None:
        complete = "current" if source == projected else "STATE_UNKNOWN"
    split_brain = str(fact["split_brain"]) if fact is not None else _fence_health(migration)
    fence = str(fact["legacy_writer_fence"]) if fact is not None else "not_armed"
    writes_enabled = bool(fact["writes_enabled"]) if fact is not None else False
    if complete == "STATE_UNKNOWN" or split_brain != "clear" or fence == "unknown":
        writes_enabled = False
    return _HealthState(source, projected, complete, split_brain, fence, writes_enabled)


def _source_watermark(
    fact: dict[str, object] | None,
    migration: _MigrationState | None,
) -> int:
    if fact is not None:
        return int(cast(int, fact["source_watermark"]))
    return migration.record_watermark if migration is not None else 0


def _projection_watermark(
    fact: dict[str, object] | None,
    migration: _MigrationState | None,
    stats: dict[str, int],
) -> int:
    if fact is not None or migration is None:
        return stats["max_projection"]
    return migration.projection_watermark


def _preauthority_health(
    migration: _MigrationState | None,
    state: _HealthState,
) -> CtowerProjectCutoverHealth:
    if migration is None:
        return CtowerProjectCutoverHealth(
            projection_completeness=state.complete,
            source_watermark=state.source,
            projection_watermark=state.projected,
            writes_enabled=state.writes_enabled,
            legacy_writer_fence=state.fence,
            split_brain=state.split_brain,
        )
    return CtowerProjectCutoverHealth(
        cutover_id=migration.cutover_id,
        phase=migration.phase,
        projection_completeness=state.complete,
        source_watermark=state.source,
        projection_watermark=state.projected,
        writes_enabled=state.writes_enabled,
        legacy_writer_fence=state.fence,
        split_brain=state.split_brain,
        import_run_id=migration.run_id,
        migration_digests=migration.digests,
    )


def _authority_health(
    fact: dict[str, object],
    migration: _MigrationState | None,
    state: _HealthState,
) -> CtowerProjectCutoverHealth:
    return CtowerProjectCutoverHealth(
        cutover_id=cast(UUID, fact["cutover_id"]),
        authority_mode=str(fact["authority_mode"]),
        phase=str(fact["phase"]),
        writes_enabled=state.writes_enabled,
        durability_claim=str(fact["durability_claim"]),
        recovery_claim=str(fact["recovery_claim"]),
        data_class=str(fact["data_class"]),
        legacy_writer_fence=state.fence,
        split_brain=state.split_brain,
        projection_completeness=state.complete,
        source_watermark=state.source,
        projection_watermark=state.projected,
        import_run_id=migration.run_id if migration is not None else None,
        migration_digests=(
            migration.digests if migration is not None else MigrationHealthDigests()
        ),
    )


def project_delivery(
    dsn: str,
    actor: Actor,
    project_key: str,
) -> ProjectDeliveryView | None:
    """Return stored rows for exactly one tenant/project without catch-up."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        rows = connection.execute(
            """
            SELECT row.row_payload, definition.company_key,
                transaction_timestamp() AS server_now
            FROM project_delivery_projection_rows AS row
            JOIN LATERAL (
                SELECT company_key, ordered_position
                FROM project_delivery_checkpoint_definitions
                WHERE tenant_id = row.tenant_id
                  AND project_key = row.project_key
                  AND checkpoint_key = row.checkpoint_key
                ORDER BY definition_revision DESC LIMIT 1
            ) AS definition ON true
            WHERE row.tenant_id = %s AND row.project_key = %s
            ORDER BY definition.ordered_position, row.checkpoint_key
            """,
            (actor.tenant_id, project_key),
        ).fetchall()
    if not rows:
        return None
    company_key = str(rows[0]["company_key"])
    server_now = cast(datetime, rows[0]["server_now"])
    projected_rows = tuple(
        _row(cast(dict[str, object], item["row_payload"]), observed_at=server_now) for item in rows
    )
    reconciled_at = max(row.reconciled_at for row in projected_rows)
    freshness_due_at = min(row.freshness_due_at for row in projected_rows)
    source = max(row.source_watermark for row in projected_rows)
    projection = min(row.projection_watermark for row in projected_rows)
    generation = max(row.rebuild_generation for row in projected_rows)
    return ProjectDeliveryView(
        company_key=company_key,
        project_key=project_key,
        rows=projected_rows,
        source_record_position=source,
        projection_record_position=projection,
        reconciled_at=reconciled_at,
        freshness_due_at=freshness_due_at,
        projection_semantic_digest=_view_digest(project_key, projected_rows, source, projection),
        rebuild_generation=generation,
    )


def _select_authority_fact(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> tuple[dict[str, object] | None, bool]:
    """Select the latest fact by transactional append order within one cutover.

    The repository's authority order is the transactional ``events.record_position``
    with an ``event_id`` tie-break (matching ``0013_durability_authority.sql``), not
    the caller-supplied ``recorded_at`` wall clock, so a backdated or restored
    correction cannot suppress a newer armed fact. Returns ``(fact, ambiguous)``;
    when more than one cutover lineage has facts the active cutover is ambiguous
    and the caller must fail closed rather than silently picking one.
    """

    lineages = connection.execute(
        "SELECT DISTINCT cutover_id FROM ctower_project_cutover_facts WHERE tenant_id = %s",
        (tenant_id,),
    ).fetchall()
    if not lineages:
        return None, False
    if len(lineages) > 1:
        return None, True
    fact = connection.execute(
        """
        SELECT fact.*
        FROM ctower_project_cutover_facts AS fact
        JOIN events AS event
          ON event.event_id = fact.event_id
         AND event.tenant_id = fact.tenant_id
        WHERE fact.tenant_id = %s
        ORDER BY event.record_position DESC, fact.event_id DESC
        LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    return fact, False


def _migration_state(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> _MigrationState | None:
    row = connection.execute(
        """
        SELECT run.run_id, run.cutover_id, run.source_selection_digest,
            fact.state, fact.export_equality_digest, fact.alias_map_digest,
            fact.record_watermark, fact.projection_watermark,
            reconciliation.report_digest,
            registry.registry_digest,
            observation.observation_digest, observation.observation_body,
            CASE
                WHEN observation.observation_body IS NULL THEN NULL
                WHEN registry.max_observation_age_seconds IS NULL
                  OR registry.max_future_clock_skew_seconds IS NULL
                  OR registry.source_pointer_digest IS NULL
                  OR observation.observation_body ->> 'schema'
                     <> 'ctower.ctower-project-fence-observation/v2'
                  OR observation.observation_body ->> 'source_pointer_digest'
                     <> 'sha256:' || encode(registry.source_pointer_digest, 'hex')
                  OR (observation.observation_body ->> 'observed_at')::timestamptz
                     < transaction_timestamp()
                       - make_interval(secs => registry.max_observation_age_seconds)
                  OR (observation.observation_body ->> 'observed_at')::timestamptz
                     > transaction_timestamp()
                       + make_interval(secs => registry.max_future_clock_skew_seconds)
                THEN 'unknown'
                ELSE observation.observation_body ->> 'status'
            END AS fence_status
        FROM migration_import_runs AS run
        JOIN LATERAL (
            SELECT * FROM migration_import_run_facts
            WHERE run_id = run.run_id ORDER BY fact_sequence DESC LIMIT 1
        ) AS fact ON true
        LEFT JOIN migration_reconciliation_facts AS reconciliation
          ON reconciliation.run_id = run.run_id
        LEFT JOIN migration_fence_registries AS registry
          ON registry.run_id = run.run_id
        LEFT JOIN LATERAL (
            SELECT observation_digest, observation_body
            FROM migration_fence_observations
            WHERE tenant_id = run.tenant_id
              AND registry_id = registry.registry_id
              AND registry_revision = registry.registry_revision
              AND observation_body ->> 'run_id' = run.run_id::text
              AND observation_body ->> 'cutover_id' = run.cutover_id::text
              AND observation_body ->> 'project_key' = run.project_key
            ORDER BY sequence DESC LIMIT 1
        ) AS observation ON true
        WHERE run.tenant_id = %s
        ORDER BY run.created_at DESC, run.run_id DESC LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        return None
    return _MigrationState(
        run_id=cast(UUID, row["run_id"]),
        cutover_id=cast(UUID, row["cutover_id"]),
        phase=_migration_phase(str(row["state"])),
        record_watermark=int(cast(int, row["record_watermark"])),
        projection_watermark=int(cast(int, row["projection_watermark"])),
        digests=MigrationHealthDigests(
            source_selection=_digest(row["source_selection_digest"]),
            export_equality=_digest(row["export_equality_digest"]),
            alias_map=_digest(row["alias_map_digest"]),
            reconciliation=_digest(row["report_digest"]),
            fence_registry=_digest(row["registry_digest"]),
            fence_observation=_digest(row["observation_digest"]),
        ),
        fence_status=str(row["fence_status"]) if row["fence_status"] is not None else None,
    )


def _migration_phase(state: str) -> str:
    return {
        "created": "source_selection_frozen",
        "export_equality_bound": "export_equal",
        "alias_plan_bound": "alias_plan_bound",
        "importing": "import_in_progress",
        "pass_one_complete": "import_in_progress",
        "pass_two_started": "import_in_progress",
        "pass_two_noop": "import_in_progress",
        "reconciled": "reconciled",
    }[state]


def _digest(value: object) -> str | None:
    return f"sha256:{bytes(cast(bytes, value)).hex()}" if value is not None else None


def _fence_health(migration: _MigrationState | None) -> str:
    if migration is None:
        return "clear"
    if migration.fence_status is None:
        return "unknown"
    return "clear" if migration.fence_status == "clear" else migration.fence_status


def _projection_stats(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
            count(*) AS row_count,
            COALESCE(MIN(source_watermark), 0) AS min_source,
            COALESCE(MAX(source_watermark), 0) AS max_source,
            COALESCE(MIN(projection_watermark), 0) AS min_projection,
            COALESCE(MAX(projection_watermark), 0) AS max_projection
        FROM project_delivery_projection_rows WHERE tenant_id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        return {
            "row_count": 0,
            "min_source": 0,
            "max_source": 0,
            "min_projection": 0,
            "max_projection": 0,
        }
    return cast(dict[str, int], row)


def _completeness(
    stats: dict[str, int],
    source: int,
    *,
    fact_present: bool,
    ambiguous: bool,
) -> str:
    """Report projection completeness truthfully, failing closed on uncertainty.

    Ambiguous authority, or any delivery row without a corresponding authority
    fact, renders completeness ``STATE_UNKNOWN``; the pristine empty case (no
    fact and no rows) is the only no-fact state that stays ``current``.
    """

    if ambiguous:
        return "STATE_UNKNOWN"
    if not fact_present:
        return "STATE_UNKNOWN" if stats["row_count"] > 0 else "current"
    empty_current = stats["row_count"] == 0 and source == 0
    all_rows_current = (
        stats["row_count"] > 0
        and stats["min_source"]
        == stats["max_source"]
        == stats["min_projection"]
        == stats["max_projection"]
        == source
    )
    return "current" if empty_current or all_rows_current else "STATE_UNKNOWN"


def _row(payload: dict[str, object], *, observed_at: datetime) -> ProjectDeliveryRow:
    criteria = cast(dict[str, object], payload["criteria"])
    row = ProjectDeliveryRow(
        checkpoint_key=str(payload["checkpoint_key"]),
        checkpoint_label=str(payload["checkpoint_label"]),
        headline_state=DeliveryState(str(payload["headline_state"])),
        underlying_maturity=DeliveryState(str(payload["underlying_maturity"])),
        outcome=str(payload["outcome"]),
        accountable_owner=str(payload["accountable_owner"]),
        proven_criteria=int(cast(int, criteria["proven"])),
        declared_criteria=int(cast(int, criteria["declared"])),
        source_watermark=int(cast(int, payload["source_watermark"])),
        projection_watermark=int(cast(int, payload["projection_watermark"])),
        freshness=str(payload["freshness"]),
        confidence=str(payload["confidence"]),
        health=str(payload["health"]),
        durability=str(payload["durability"]),
        recovery=str(payload["recovery"]),
        data_class=str(payload["data_class"]),
        semantic_digest=str(payload["semantic_digest"]),
        reconciled_at=datetime.fromisoformat(str(payload["reconciled_at"])),
        freshness_due_at=datetime.fromisoformat(str(payload["freshness_due_at"])),
        rebuild_generation=int(cast(int, payload["rebuild_generation"])),
        source_ids=tuple(str(item) for item in cast(list[object], payload["source_ids"])),
        derivation_reasons=tuple(
            str(item) for item in cast(list[object], payload["derivation_reasons"])
        ),
    )
    if row.freshness == "fresh" and observed_at > row.freshness_due_at:
        return replace(row, freshness="stale")
    return row


def _view_digest(
    project_key: str,
    rows: tuple[ProjectDeliveryRow, ...],
    source: int,
    projection: int,
) -> str:
    payload = {
        "project_key": project_key,
        "projection_record_position": projection,
        "rows": tuple(row.semantic_digest for row in rows),
        "source_record_position": source,
    }
    content = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"

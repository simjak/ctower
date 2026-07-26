"""One PostgreSQL authority for migration dispositions and conservation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

import psycopg

from ctower_client.models import MigrationConservation, MigrationDispositions
from ctower_kernel.migration import _pass_two_sql

__all__ = ["MigrationMeasurement", "measure"]


@dataclass(frozen=True, slots=True)
class MigrationMeasurement:
    dispositions: MigrationDispositions
    conservation: MigrationConservation | None
    source_native_watermark: int
    export_native_watermark: int


def measure(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
) -> MigrationMeasurement | None:
    artifacts = connection.execute(
        """
        SELECT artifact_kind, artifact_body FROM migration_verified_artifacts
        WHERE run_id = %s AND artifact_kind IN ('source_selection', 'alias_map')
        """,
        (run_id,),
    ).fetchall()
    values = {
        str(row["artifact_kind"]): cast(dict[str, object], row["artifact_body"])
        for row in artifacts
    }
    selection, alias = values.get("source_selection"), values.get("alias_map")
    plan = connection.execute(
        "SELECT * FROM migration_import_plans WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    if selection is None or alias is None or plan is None:
        return None
    entries = cast(list[dict[str, object]], alias["entries"])
    dispositions = _dispositions(entries)
    inventories = cast(list[dict[str, object]], selection["source_inventories"])
    request_physical = sum(
        int(cast(int, item["selected_physical_items"]))
        for item in inventories
        if item["source_key"] == "mission_control_requests"
    )
    graph, pass_two = _pass_two_sql.evidence(connection, run_id)
    conservation = _conservation(
        selection,
        entries,
        request_physical,
        graph,
        pass_two,
    )
    return MigrationMeasurement(
        dispositions,
        conservation,
        int(cast(int, plan["source_native_watermark"])),
        int(cast(int, plan["export_native_watermark"])),
    )


def _dispositions(entries: list[dict[str, object]]) -> MigrationDispositions:
    counts: dict[str, int] = {}
    for entry in entries:
        key = str(entry["disposition"])
        counts[key] = counts.get(key, 0) + 1
    return MigrationDispositions.model_validate(
        {
            "created_ticket": counts.get("created_ticket", 0),
            "alias_linked_existing": counts.get("alias_linked_existing", 0),
            "project_checkpoint_definition": counts.get("project_checkpoint_definition", 0),
            "decision_link": counts.get("decision_link", 0),
            "external_effect_link": counts.get("external_effect_link", 0),
            "artifact_linked_not_proof": counts.get("artifact_linked_not_proof", 0),
            "provenance_only": counts.get("provenance_only", 0),
            "exact_duplicate": counts.get("exact_duplicate", 0),
            "excluded_out_of_scope": counts.get("excluded_out_of_scope", 0),
            "attention_required": counts.get("attention_required", 0),
        }
    )


def _conservation(
    selection: dict[str, object],
    entries: list[dict[str, object]],
    request_physical: int,
    graph: dict[str, object] | None,
    pass_two: dict[str, object] | None,
) -> MigrationConservation | None:
    if graph is None or pass_two is None:
        return None
    anomalies = {
        key: len(cast(list[object], graph[key]))
        for key in ("unexpected", "forbidden", "unresolved", "cycles")
    }
    if any(anomalies.values()):
        return None
    return MigrationConservation.model_validate(
        {
            "selected_logical_items": len(entries),
            "selected_request_logical": len(cast(list[object], selection["selected_request_ids"])),
            "selected_request_physical_snapshots": request_physical,
            "stable_aliases": len(cast(list[object], graph["stable_aliases"])),
            "checkpoint_definitions": len(cast(list[object], graph["checkpoint_definitions"])),
            "unresolved_aliases": anomalies["unresolved"],
            "alias_forks_or_cycles": anomalies["cycles"],
            "missing_relation_endpoints": anomalies["unresolved"],
            "forbidden_relation_cycles": anomalies["cycles"],
            "unresolved_active_claims": anomalies["unresolved"],
            "unexpected_sources": anomalies["unexpected"],
            "forbidden_data_items": anomalies["forbidden"],
            "pass_two_new_domain_facts": pass_two["new_domain_facts"],
            "pass_two_new_events": pass_two["new_events"],
            "pass_two_new_outbox_rows": pass_two["new_outbox_rows"],
            "pass_two_record_position_delta": pass_two["record_position_delta"],
            "pass_two_projection_semantic_delta": pass_two["projection_semantic_delta"],
        }
    )

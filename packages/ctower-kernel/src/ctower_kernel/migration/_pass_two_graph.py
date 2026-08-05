"""Pure projection of a pass-two target snapshot into stable reconciliation sets."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any, cast

import rfc8785

from ctower_kernel.migration import _checkpoint_expectation_sql, _target_anomaly

__all__ = ["graph", "project_delivery_values"]

_PROJECT_DELIVERY_VOLATILE = frozenset(
    {
        "freshness_due_at",
        "projection_watermark",
        "rebuild_generation",
        "reconciled_at",
        "semantic_digest",
        "source_watermark",
    }
)


def _signed_checkpoint_snapshot(snapshot_body: dict[str, object]) -> dict[str, object]:
    signed_keys = {
        str(value) for value in cast(list[object], snapshot_body.get("signed_checkpoint_keys", []))
    }
    if not signed_keys:
        # No signed checkpoint plan exists for this run: ready_for_pass_two() already
        # fails closed via _checkpoint_expectation_sql.mismatches(), which returns a
        # non-empty mismatch the moment signed_keys is empty. So returning the snapshot
        # unfiltered here never reaches a readiness/finalization decision — it only
        # affects display paths (evidence()) for a run that never signed a checkpoint.
        return snapshot_body
    definitions = [
        row
        for row in cast(list[dict[str, object]], snapshot_body["checkpoint_definitions"])
        if str(row["checkpoint_key"]) in signed_keys
    ]
    definition_ids = {str(row["checkpoint_definition_id"]) for row in definitions}
    return {
        **snapshot_body,
        "checkpoint_definitions": definitions,
        "checkpoint_criteria": [
            row
            for row in cast(list[dict[str, object]], snapshot_body["checkpoint_criteria"])
            if str(row["checkpoint_definition_id"]) in definition_ids
        ],
        "project_delivery_rows": [
            row
            for row in cast(list[dict[str, object]], snapshot_body["project_delivery_rows"])
            if str(row["checkpoint_key"]) in signed_keys
        ],
    }


def graph(snapshot_body: dict[str, object]) -> dict[str, object]:
    """Project the exhaustive snapshot into stable, sorted reconciliation sets."""

    relations = _set(snapshot_body, "relations")
    custody = cast(list[dict[str, object]], snapshot_body["custody_intervals"])
    unexpected, forbidden, unresolved, cycles = _target_anomaly.sets(snapshot_body)
    signed_snapshot = _signed_checkpoint_snapshot(snapshot_body)
    checkpoint_definitions, checkpoint_criteria = _checkpoint_expectation_sql.graph_sets(
        signed_snapshot
    )
    value: dict[str, object] = {
        "stable_aliases": _set(snapshot_body, "stable_aliases"),
        "operation_identities": _set(snapshot_body, "planned_operations"),
        "operation_results": _set(snapshot_body, "operation_results"),
        "tickets": _set(snapshot_body, "ticket_bindings"),
        "lifecycle_facts": _set(snapshot_body, "lifecycle_episodes"),
        "priority_facts": _set(snapshot_body, "priority_facts"),
        "custody_intervals": _set(snapshot_body, "custody_intervals"),
        "active_claims": _canonical_set(row for row in custody if row.get("released_at") is None),
        "alias_revisions": _set(snapshot_body, "alias_revisions"),
        "relations": relations,
        "relation_endpoints": sorted(
            {
                f"{row['source_ticket_id']}->{row['target_ticket_id']}"
                for row in cast(list[dict[str, object]], snapshot_body["relations"])
            }
        ),
        "source_links": _set(snapshot_body, "source_link_revisions"),
        "checkpoint_definitions": checkpoint_definitions,
        "checkpoint_criteria": checkpoint_criteria,
        "project_delivery_rows": _canonical_set(project_delivery_values(signed_snapshot)),
        "events": _set(snapshot_body, "event_ids"),
        "outbox_rows": _set(snapshot_body, "outbox_rows"),
        "unexpected": unexpected,
        "forbidden": forbidden,
        "unresolved": unresolved,
        "cycles": cycles,
    }
    digest = hashlib.sha256(rfc8785.dumps(cast(Any, value))).hexdigest()
    value["graph_digest"] = f"sha256:{digest}"
    return value


def _set(snapshot_body: dict[str, object], key: str) -> list[str]:
    return _canonical_set(cast(list[object], snapshot_body[key]))


def project_delivery_values(snapshot_body: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "project_key": row["project_key"],
            "checkpoint_key": row["checkpoint_key"],
            "row_payload": {
                key: value
                for key, value in cast(dict[str, object], row["row_payload"]).items()
                if key not in _PROJECT_DELIVERY_VOLATILE
            },
        }
        for row in cast(list[dict[str, object]], snapshot_body["project_delivery_rows"])
    ]


def _canonical_set(values: Iterable[object]) -> list[str]:
    return sorted({rfc8785.dumps(cast(Any, item)).decode("utf-8") for item in values})

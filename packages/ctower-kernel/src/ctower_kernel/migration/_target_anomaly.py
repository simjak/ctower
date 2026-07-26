"""Canonical set-difference anomalies for migration target snapshots."""

from __future__ import annotations

from typing import Any, cast

import rfc8785

__all__ = ["sets"]


def sets(
    snapshot_body: dict[str, object],
) -> tuple[list[str], list[str], list[str], list[str]]:
    planned_rows = cast(list[dict[str, object]], snapshot_body["planned_operations"])
    result_rows = cast(list[dict[str, object]], snapshot_body["operation_results"])
    planned = {_identity_key(cast(dict[str, object], row["identity"])): row for row in planned_rows}
    results = {_identity_key(row): row for row in result_rows}
    unexpected = {f"operation_result:{identity}" for identity in results.keys() - planned.keys()}
    unresolved = {f"operation_result:{identity}" for identity in planned.keys() - results.keys()}
    planned_pairs: dict[str, set[tuple[str, str]]] = {}
    for row in planned_rows:
        identity = cast(dict[str, object], row["identity"])
        planned_pairs.setdefault(str(row["operation"]), set()).add(_source_pair(identity))
    _source_anomalies(snapshot_body, planned_pairs, unexpected, unresolved)
    _stable_anomalies(snapshot_body, planned_pairs, unexpected, unresolved)
    actual_relations = cast(list[dict[str, object]], snapshot_body["relations"])
    ticket_ids = {
        str(row["ticket_id"])
        for row in cast(list[dict[str, object]], snapshot_body["ticket_bindings"])
    }
    _relation_anomalies(planned, results, actual_relations, unexpected, unresolved)
    _ticket_fact_anomalies(snapshot_body, ticket_ids, unresolved)
    forbidden = {
        f"relation_endpoint:{row['relation_id']}"
        for row in actual_relations
        if str(row["source_ticket_id"]) not in ticket_ids
        or str(row["target_ticket_id"]) not in ticket_ids
    }
    return (
        sorted(unexpected),
        sorted(forbidden),
        sorted(unresolved),
        _relation_cycles(actual_relations),
    )


def _source_anomalies(
    snapshot_body: dict[str, object],
    planned_pairs: dict[str, set[tuple[str, str]]],
    unexpected: set[str],
    unresolved: set[str],
) -> None:
    _compare_source_rows(
        "alias_revision",
        planned_pairs.get("exact_alias", set()),
        cast(list[dict[str, object]], snapshot_body["alias_revisions"]),
        unexpected,
        unresolved,
    )
    _compare_source_rows(
        "source_link",
        planned_pairs.get("source_link", set()),
        cast(list[dict[str, object]], snapshot_body["source_link_revisions"]),
        unexpected,
        unresolved,
    )
    binding_pairs = {
        (str(row["source_namespace"]), str(row["immutable_source_id"]))
        for row in cast(list[dict[str, object]], snapshot_body["ticket_bindings"])
    }
    planned_ticket_pairs = planned_pairs.get("ticket_seed", set())
    unresolved.update(
        f"ticket_binding:{_pair_text(pair)}" for pair in planned_ticket_pairs - binding_pairs
    )
    allowed_binding_pairs = planned_ticket_pairs | planned_pairs.get("exact_alias", set())
    unexpected.update(
        f"ticket_binding:{_pair_text(pair)}" for pair in binding_pairs - allowed_binding_pairs
    )


def _stable_anomalies(
    snapshot_body: dict[str, object],
    planned_pairs: dict[str, set[tuple[str, str]]],
    unexpected: set[str],
    unresolved: set[str],
) -> None:
    expected_stable = {
        identity[1]
        for identity in planned_pairs.get("exact_alias", set())
        if identity[0] == "stable-backlog"
    }
    actual_stable = {
        str(row["stable_item_id"])
        for row in cast(list[dict[str, object]], snapshot_body["stable_aliases"])
    }
    unresolved.update(
        f"stable_alias:stable-backlog:{identity}" for identity in expected_stable - actual_stable
    )
    unexpected.update(
        f"stable_alias:stable-backlog:{identity}" for identity in actual_stable - expected_stable
    )


def _relation_anomalies(
    planned: dict[str, dict[str, object]],
    results: dict[str, dict[str, object]],
    actual_relations: list[dict[str, object]],
    unexpected: set[str],
    unresolved: set[str],
) -> None:
    expected_relation_ids = {
        str(results[identity]["target_id"])
        for identity, row in planned.items()
        if row["operation"] == "ticket_relation" and identity in results
    }
    actual_relation_ids = {str(row["relation_id"]) for row in actual_relations}
    unresolved.update(
        f"relation:{identity}" for identity in expected_relation_ids - actual_relation_ids
    )
    unexpected.update(
        f"relation:{identity}" for identity in actual_relation_ids - expected_relation_ids
    )


def _ticket_fact_anomalies(
    snapshot_body: dict[str, object],
    ticket_ids: set[str],
    unresolved: set[str],
) -> None:
    _require_ticket_facts(
        "lifecycle",
        ticket_ids,
        cast(list[dict[str, object]], snapshot_body["lifecycle_episodes"]),
        unresolved,
    )
    _require_ticket_facts(
        "priority",
        ticket_ids,
        cast(list[dict[str, object]], snapshot_body["priority_facts"]),
        unresolved,
    )
    active_custody = [
        row
        for row in cast(list[dict[str, object]], snapshot_body["custody_intervals"])
        if row["released_at"] is None
    ]
    _require_ticket_facts("active_custody", ticket_ids, active_custody, unresolved)


def _compare_source_rows(
    label: str,
    expected: set[tuple[str, str]],
    rows: list[dict[str, object]],
    unexpected: set[str],
    unresolved: set[str],
) -> None:
    actual = {_source_pair(row) for row in rows}
    unresolved.update(f"{label}:{_pair_text(pair)}" for pair in expected - actual)
    unexpected.update(f"{label}:{_pair_text(pair)}" for pair in actual - expected)


def _require_ticket_facts(
    label: str,
    ticket_ids: set[str],
    rows: list[dict[str, object]],
    unresolved: set[str],
) -> None:
    actual = {str(row["ticket_id"]) for row in rows}
    unresolved.update(f"{label}:{ticket_id}" for ticket_id in ticket_ids - actual)


def _identity_key(identity: dict[str, object]) -> str:
    return rfc8785.dumps(
        cast(
            Any,
            {
                key: identity[key]
                for key in (
                    "namespace",
                    "immutable_source_id",
                    "source_version_or_digest",
                    "operation_kind",
                    "planned_target_ref",
                    "command_id",
                )
            },
        )
    ).decode("utf-8")


def _source_pair(row: dict[str, object]) -> tuple[str, str]:
    return str(row["namespace"]), str(row["immutable_source_id"])


def _pair_text(pair: tuple[str, str]) -> str:
    return f"{pair[0]}:{pair[1]}"


def _relation_cycles(relations: list[dict[str, object]]) -> list[str]:
    edges: dict[str, set[str]] = {}
    for row in relations:
        if not bool(row["active"]):
            continue
        edges.setdefault(str(row["source_ticket_id"]), set()).add(str(row["target_ticket_id"]))
    cycles: set[str] = set()

    def visit(origin: str, current: str, path: tuple[str, ...]) -> None:
        for target in sorted(edges.get(current, set())):
            if target == origin:
                cycles.add("->".join((*path, current, origin)))
            elif target not in path and len(path) <= len(edges):
                visit(origin, target, (*path, current))

    for node in sorted(edges):
        visit(node, node, ())
    return sorted(cycles)

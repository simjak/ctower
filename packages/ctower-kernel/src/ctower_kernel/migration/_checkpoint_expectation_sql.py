"""Signed checkpoint expectations compared with current Catalog authority."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import psycopg
import rfc8785

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, order=True)
class _Expectation:
    checkpoint_key: str
    catalog_revision: str
    definition_digest: str
    criteria_digest: str


def matches(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    snapshot_body: dict[str, object],
) -> bool:
    """Compare the verified plan with independently derived current Catalog facts."""

    expected = _stored(connection, run_id)
    definitions = cast(list[dict[str, object]], snapshot_body["checkpoint_definitions"])
    actual = _current(snapshot_body)
    return (
        bool(expected)
        and _unique_checkpoint_keys(expected)
        and _unique_checkpoint_keys(actual)
        and all(str(row["accountable_owner"]).strip() for row in definitions)
        and expected == actual
    )


def _unique_checkpoint_keys(expectations: Iterable[_Expectation]) -> bool:
    keys = [item.checkpoint_key for item in expectations]
    return len(keys) == len(set(keys))


def graph_sets(snapshot_body: dict[str, object]) -> tuple[list[str], list[str]]:
    """Project current Catalog identities into the reconciliation graph."""

    return _sets(_current(snapshot_body))


def _stored(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
) -> tuple[_Expectation, ...]:
    row = connection.execute(
        """
        SELECT artifact_body -> 'checkpoint_definitions' AS definitions
        FROM migration_verified_artifacts
        WHERE run_id = %s AND artifact_kind = 'import_plan'
        ORDER BY recorded_at DESC LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if row is None or not isinstance(row["definitions"], list):
        return ()
    result: list[_Expectation] = []
    for item in cast(list[object], row["definitions"]):
        if not isinstance(item, dict):
            return ()
        values = cast(dict[str, object], item)
        fields = (
            values.get("checkpoint_key"),
            values.get("catalog_revision"),
            values.get("definition_digest"),
            values.get("criteria_digest"),
        )
        if not all(isinstance(value, str) for value in fields):
            return ()
        result.append(_Expectation(*cast(tuple[str, str, str, str], fields)))
    return tuple(sorted(result))


def _current(snapshot_body: dict[str, object]) -> tuple[_Expectation, ...]:
    definitions = cast(list[dict[str, object]], snapshot_body["checkpoint_definitions"])
    criteria = cast(list[dict[str, object]], snapshot_body["checkpoint_criteria"])
    by_definition: dict[str, list[dict[str, object]]] = {}
    for row in criteria:
        by_definition.setdefault(str(row["checkpoint_definition_id"]), []).append(row)
    return tuple(
        sorted(
            _Expectation(
                checkpoint_key=str(row["checkpoint_key"]),
                catalog_revision=str(row["catalog_revision"]),
                definition_digest=str(row["catalog_digest"]),
                criteria_digest=_criteria_digest(
                    by_definition.get(str(row["checkpoint_definition_id"]), ())
                ),
            )
            for row in definitions
        )
    )


def _criteria_digest(rows: Iterable[dict[str, object]]) -> str:
    ordered = sorted(rows, key=lambda row: int(cast(int, row["ordinal"])))
    material = [
        {
            "ordinal": row["ordinal"],
            "criterion_key": row["criterion_key"],
            "description": row["description"],
            "proof_ticket_id": row["proof_ticket_id"],
            "proof_criterion_key": row["proof_criterion_key"],
            "source_ids": row["source_ids"],
        }
        for row in ordered
    ]
    return f"sha256:{hashlib.sha256(rfc8785.dumps(cast(Any, material))).hexdigest()}"


def _sets(expectations: Iterable[_Expectation]) -> tuple[list[str], list[str]]:
    definitions = [
        {
            "checkpoint_key": item.checkpoint_key,
            "catalog_revision": item.catalog_revision,
            "definition_digest": item.definition_digest,
        }
        for item in expectations
    ]
    criteria = [
        {
            "checkpoint_key": item.checkpoint_key,
            "criteria_digest": item.criteria_digest,
        }
        for item in expectations
    ]
    return _canonical_set(definitions), _canonical_set(criteria)


def _canonical_set(values: Iterable[object]) -> list[str]:
    return sorted({rfc8785.dumps(cast(Any, item)).decode("utf-8") for item in values})

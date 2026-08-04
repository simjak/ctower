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


@dataclass(frozen=True, slots=True)
class CheckpointMismatch:
    """One checkpoint expectation the live Catalog projection does not currently satisfy."""

    checkpoint_key: str
    detail: str


def mismatches(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
    snapshot_body: dict[str, object],
) -> tuple[CheckpointMismatch, ...]:
    """Name every checkpoint whose signed expectation the current Catalog fails to satisfy.

    An empty result means every signed checkpoint expectation is satisfied exactly.
    """

    expected = _stored(connection, run_id)
    if not expected:
        return (
            CheckpointMismatch("(unsigned)", "no checkpoint expectations are signed for this run"),
        )
    definitions = cast(list[dict[str, object]], snapshot_body["checkpoint_definitions"])
    actual = _current(snapshot_body)
    shape_failures = (
        *_duplicate_failures("signed", expected),
        *_duplicate_failures("observed", actual),
        *(
            CheckpointMismatch(str(row["checkpoint_key"]), "checkpoint has no accountable owner")
            for row in definitions
            if not str(row["accountable_owner"]).strip()
        ),
    )
    if shape_failures:
        return shape_failures
    return _key_mismatches(expected, _signed_current(expected, actual))


def _duplicate_failures(
    scope: str,
    expectations: Iterable[_Expectation],
) -> tuple[CheckpointMismatch, ...]:
    keys = [item.checkpoint_key for item in expectations]
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    return tuple(
        CheckpointMismatch(key, f"checkpoint is duplicated in the {scope} set")
        for key in duplicated
    )


def _key_mismatches(
    expected: Iterable[_Expectation],
    signed_actual: Iterable[_Expectation],
) -> tuple[CheckpointMismatch, ...]:
    by_expected = {item.checkpoint_key: item for item in expected}
    by_actual = {item.checkpoint_key: item for item in signed_actual}
    failures: list[CheckpointMismatch] = []
    for key in sorted(set(by_expected) | set(by_actual)):
        left, right = by_expected.get(key), by_actual.get(key)
        if left != right:
            failures.append(
                CheckpointMismatch(key, f"expected {_describe(left)}, observed {_describe(right)}")
            )
    return tuple(failures)


def _describe(item: _Expectation | None) -> str:
    if item is None:
        return "missing"
    return (
        f"catalog_revision={item.catalog_revision} "
        f"definition_digest={item.definition_digest} "
        f"criteria_digest={item.criteria_digest}"
    )


def _signed_current(
    expected: Iterable[_Expectation],
    actual: Iterable[_Expectation],
) -> tuple[_Expectation, ...]:
    expected_keys = {item.checkpoint_key for item in expected}
    return tuple(sorted(item for item in actual if item.checkpoint_key in expected_keys))


def signed_keys(
    connection: psycopg.Connection[dict[str, object]],
    run_id: UUID,
) -> list[str]:
    """Return the exact checkpoint identity set signed into the verified plan."""

    return [item.checkpoint_key for item in _stored(connection, run_id)]


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

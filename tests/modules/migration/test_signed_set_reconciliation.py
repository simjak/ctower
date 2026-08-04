"""Signed-set reconciliation refuses identity or digest drift without fixed counts."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from ctower_kernel.migration import (
    _artifact_sql,
    _checkpoint_expectation_sql,
    _operation_sql,
    _pass_two_sql,
    _reconciliation_sql,
)

__all__: tuple[str, ...] = ()


def test_exact_signed_set_accepts_authored_expansion_without_product_edit() -> None:
    expected, snapshot = _exact_graph()

    assert not _mismatches(expected, snapshot)


def test_authored_target_extension_outside_signed_source_set_is_current() -> None:
    expected, snapshot = _exact_graph()

    assert not _mismatches(expected[:-1], snapshot)


def test_signed_set_substitution_fails_closed_by_name() -> None:
    expected, snapshot = _exact_graph()
    assert not _mismatches(expected, snapshot)
    definitions = cast(list[dict[str, object]], snapshot["checkpoint_definitions"])
    definitions[0]["catalog_digest"] = f"sha256:{'f' * 64}"

    found = _mismatches(expected, snapshot)
    assert [item.checkpoint_key for item in found] == ["I1.0"]
    assert "expected" in found[0].detail and "observed" in found[0].detail


def test_signed_set_missing_member_fails_closed_by_name() -> None:
    expected, snapshot = _exact_graph()
    assert not _mismatches(expected, snapshot)
    definitions = cast(list[dict[str, object]], snapshot["checkpoint_definitions"])
    missing = definitions.pop()
    missing_key = str(missing["checkpoint_key"])
    criteria = cast(list[dict[str, object]], snapshot["checkpoint_criteria"])
    criteria[:] = [
        row
        for row in criteria
        if row["checkpoint_definition_id"] != missing["checkpoint_definition_id"]
    ]

    found = _mismatches(expected, snapshot)
    assert [item.checkpoint_key for item in found] == [missing_key]
    assert "observed missing" in found[0].detail


def test_signed_set_extra_member_fails_closed_by_name() -> None:
    expected, snapshot = _exact_graph()
    assert not _mismatches(expected, snapshot)
    extra_expected, _ = _checkpoint("I1.extra", 99)
    expected.extend(extra_expected)

    found = _mismatches(expected, snapshot)
    assert [item.checkpoint_key for item in found] == ["I1.extra"]
    assert "observed missing" in found[0].detail


def test_signed_set_duplicate_member_fails_closed_by_name() -> None:
    expected, snapshot = _exact_graph()
    assert not _mismatches(expected, snapshot)
    definitions = cast(list[dict[str, object]], snapshot["checkpoint_definitions"])
    criteria = cast(list[dict[str, object]], snapshot["checkpoint_criteria"])
    duplicated_key = str(definitions[0]["checkpoint_key"])
    definitions.append(deepcopy(definitions[0]))
    criteria.append(deepcopy(criteria[0]))

    found = _mismatches(expected, snapshot)
    assert [item.checkpoint_key for item in found] == [duplicated_key]
    assert "duplicated" in found[0].detail


def test_signed_set_same_count_wrong_member_fails_closed_by_name() -> None:
    expected, snapshot = _exact_graph()
    assert not _mismatches(expected, snapshot)
    _, replacement = _checkpoint("I1.wrong-member", 100)
    definitions = cast(list[dict[str, object]], snapshot["checkpoint_definitions"])
    criteria = cast(list[dict[str, object]], snapshot["checkpoint_criteria"])
    replaced_id = definitions[-1]["checkpoint_definition_id"]
    replaced_key = str(definitions[-1]["checkpoint_key"])
    definitions[-1] = cast(list[dict[str, object]], replacement["checkpoint_definitions"])[0]
    criteria[-1] = cast(list[dict[str, object]], replacement["checkpoint_criteria"])[0]
    assert criteria[-1]["checkpoint_definition_id"] != replaced_id

    found = _mismatches(expected, snapshot)
    assert [item.checkpoint_key for item in found] == [replaced_key]
    assert "observed missing" in found[0].detail


def test_signed_source_set_accepts_authored_expansion_without_product_edit() -> None:
    run, request = _run_and_request()
    stable_ids = cast(list[object], [f"stable-{index}" for index in range(28)])
    alias = {
        "attention_required": 0,
        "cutover_id": str(run.cutover_id),
        "selection_digest": run.pinned_digests.source_selection,
        "export_equality_digest": run.pinned_digests.export_equality,
        "entries": [],
        "stable_aliases": [
            {"stable_item_id": identity, "target_ticket_id": str(uuid4())}
            for identity in stable_ids
        ],
    }

    assert _artifact_sql._alias_graph_valid(run, request, alias, "alias-digest", stable_ids)


def test_signed_checkpoint_plan_accepts_authored_expansion_without_product_edit() -> None:
    run, _ = _run_and_request()
    checkpoint_keys = cast(list[object], [f"I1.{index}" for index in range(15)])
    alias: dict[str, object] = {"stable_aliases": []}
    plan = {
        "run_id": str(run.run_id),
        "cutover_id": str(run.cutover_id),
        "selection_digest": run.pinned_digests.source_selection,
        "export_equality_digest": run.pinned_digests.export_equality,
        "alias_map_digest": "alias-digest",
        "checkpoint_definitions": [
            {"checkpoint_key": checkpoint_key} for checkpoint_key in checkpoint_keys
        ],
        "batches": [],
    }

    assert _artifact_sql._plan_binding_valid(
        run,
        plan,
        alias,
        "alias-digest",
        checkpoint_keys,
    )


def test_duplicate_signed_source_operation_fails_closed_by_name() -> None:
    alias = {"stable_aliases": [{"stable_item_id": "stable-1", "target_ticket_id": "ticket-1"}]}
    operation = {
        "operation": "exact_alias",
        "identity": {"namespace": "stable-backlog"},
        "source": {"immutable_source_id": "stable-1"},
        "target_ticket_id": "ticket-1",
    }
    plan = {"batches": [{"operations": [operation, deepcopy(operation)]}]}

    assert not _artifact_sql._stable_alias_operations_match(plan, alias)


def test_duplicate_signed_request_identity_fails_closed_by_name() -> None:
    run, _ = _run_and_request()
    pointer_digest = "sha256:pointer"
    request_ids = cast(list[object], ["request-1", "request-1"])
    registry = {
        "cutover_id": str(run.cutover_id),
        "source_selection_digest": run.pinned_digests.source_selection,
        "tenant_key": "ctower",
        "project_key": "ctower",
        "operation_registry_digest": run.pinned_digests.operation_registry,
        "selected_request_ids": request_ids,
        "selected_task_ids": [],
        "source_pointer_digest": pointer_digest,
    }

    assert not _artifact_sql._registry_scope_valid(
        run,
        registry,
        request_ids,
        pointer_digest,
    )


def test_project_delivery_current_derives_exact_checkpoint_and_alias_identities() -> None:
    graph = _project_delivery_graph()

    assert _pass_two_sql._project_delivery_current(graph, [1])

    duplicate = deepcopy(graph)
    definitions = cast(list[dict[str, object]], duplicate["checkpoint_definitions"])
    delivery_rows = cast(list[dict[str, object]], duplicate["project_delivery_rows"])
    definitions.append(deepcopy(definitions[0]))
    delivery_rows.append(deepcopy(delivery_rows[0]))
    assert not _pass_two_sql._project_delivery_current(duplicate, [1])


def test_reconciliation_graph_projects_only_signed_checkpoint_source_set() -> None:
    snapshot = {
        "signed_checkpoint_keys": ["I1.0"],
        "checkpoint_definitions": [
            {"checkpoint_definition_id": "definition-0", "checkpoint_key": "I1.0"},
            {"checkpoint_definition_id": "definition-1", "checkpoint_key": "I1.1"},
        ],
        "checkpoint_criteria": [
            {"checkpoint_definition_id": "definition-0", "criterion_key": "criterion-0"},
            {"checkpoint_definition_id": "definition-1", "criterion_key": "criterion-1"},
        ],
        "project_delivery_rows": [
            {"checkpoint_key": "I1.0"},
            {"checkpoint_key": "I1.1"},
        ],
    }

    signed = _pass_two_sql._signed_checkpoint_snapshot(snapshot)
    definitions = cast(list[dict[str, object]], signed["checkpoint_definitions"])
    criteria = cast(list[dict[str, object]], signed["checkpoint_criteria"])
    delivery_rows = cast(list[dict[str, object]], signed["project_delivery_rows"])

    assert [row["checkpoint_key"] for row in definitions] == ["I1.0"]
    assert [row["criterion_key"] for row in criteria] == ["criterion-0"]
    assert [row["checkpoint_key"] for row in delivery_rows] == ["I1.0"]


def test_finalization_rechecks_signed_set_currentness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = SimpleNamespace(body={"current": True}, project_delivery_current=False)
    monkeypatch.setattr(_pass_two_sql, "capture", lambda _connection, _run_id: current)
    monkeypatch.setattr(_pass_two_sql, "graph", lambda _body: {"graph": "exact"})
    monkeypatch.setattr(
        _checkpoint_expectation_sql,
        "mismatches",
        lambda _connection, _run_id, _body: (),
    )

    result = _reconciliation_sql._current_target_matches(
        cast(Any, object()),
        uuid4(),
        {"graph": "exact"},
    )

    assert not result.matches
    assert not result.checkpoint_mismatches


def test_finalization_names_checkpoint_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = SimpleNamespace(body={"current": True}, project_delivery_current=True)
    mismatch = _checkpoint_expectation_sql.CheckpointMismatch(
        "I1.0",
        "expected catalog_revision=ctower.I1.0@1, observed catalog_revision=ctower.I1.0@2",
    )
    monkeypatch.setattr(_pass_two_sql, "capture", lambda _connection, _run_id: current)
    monkeypatch.setattr(_pass_two_sql, "graph", lambda _body: {"graph": "exact"})
    monkeypatch.setattr(
        _checkpoint_expectation_sql,
        "mismatches",
        lambda _connection, _run_id, _body: (mismatch,),
    )

    result = _reconciliation_sql._current_target_matches(
        cast(Any, object()),
        uuid4(),
        {"graph": "exact"},
    )

    assert not result.matches
    assert result.checkpoint_mismatches == (mismatch,)

    refused = _reconciliation_sql._checkpoint_conflict(uuid4(), result.checkpoint_mismatches)
    assert refused.code == "migration-import-finalization-refused"
    assert "I1.0" in refused.detail
    assert refused.unmet_facts == ("checkpoint:I1.0",)


def test_pass_two_readiness_names_checkpoint_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mismatch = _checkpoint_expectation_sql.CheckpointMismatch(
        "I1.0",
        "expected catalog_revision=ctower.I1.0@1, observed catalog_revision=ctower.I1.0@2",
    )
    snapshot = SimpleNamespace(body={"current": True}, project_delivery_current=True)
    monkeypatch.setattr(
        _pass_two_sql,
        "graph",
        lambda _body: {"unexpected": [], "forbidden": [], "unresolved": [], "cycles": []},
    )
    monkeypatch.setattr(
        _checkpoint_expectation_sql,
        "mismatches",
        lambda _connection, _run_id, _body: (mismatch,),
    )

    readiness = _pass_two_sql.ready_for_pass_two(cast(Any, object()), uuid4(), cast(Any, snapshot))

    assert not readiness.ready
    assert readiness.checkpoint_mismatches == (mismatch,)

    refused = _operation_sql._checkpoint_conflict(
        "Project Delivery target is not current for pass two",
        readiness.checkpoint_mismatches,
    )
    assert refused.code == "migration-run-conflict"
    assert "I1.0" in refused.detail
    assert refused.unmet_facts == ("checkpoint:I1.0",)


def test_pass_two_readiness_keeps_generic_refusal_without_checkpoint_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = SimpleNamespace(body={"current": True}, project_delivery_current=False)
    monkeypatch.setattr(
        _pass_two_sql,
        "graph",
        lambda _body: {"unexpected": [], "forbidden": [], "unresolved": [], "cycles": []},
    )
    monkeypatch.setattr(
        _checkpoint_expectation_sql,
        "mismatches",
        lambda _connection, _run_id, _body: (),
    )

    readiness = _pass_two_sql.ready_for_pass_two(cast(Any, object()), uuid4(), cast(Any, snapshot))

    assert not readiness.ready
    assert not readiness.checkpoint_mismatches

    refused = _operation_sql._checkpoint_conflict(
        "Project Delivery target is not current for pass two",
        readiness.checkpoint_mismatches,
    )
    assert refused.detail == "Project Delivery target is not current for pass two"
    assert refused.unmet_facts == ()


def _run_and_request() -> tuple[Any, Any]:
    run = SimpleNamespace(
        run_id=uuid4(),
        cutover_id=uuid4(),
        pinned_digests=SimpleNamespace(
            source_selection="selection-digest",
            export_equality="export-digest",
            operation_registry="operation-registry-digest",
        ),
    )
    request = SimpleNamespace(alias_map_digest="alias-digest")
    return run, request


def _project_delivery_graph() -> dict[str, object]:
    definitions = [
        {
            "checkpoint_definition_id": f"definition-{index}",
            "checkpoint_key": f"I1.{index}",
            "accountable_owner": "ctower-operator",
        }
        for index in range(15)
    ]
    return {
        "stable_aliases": [
            {"stable_item_id": f"stable-{index}", "mapping_digest": f"digest-{index}"}
            for index in range(28)
        ],
        "checkpoint_definitions": definitions,
        "checkpoint_criteria": [
            {"checkpoint_definition_id": row["checkpoint_definition_id"]} for row in definitions
        ],
        "project_delivery_rows": [
            {
                "checkpoint_key": row["checkpoint_key"],
                "source_watermark": 1,
                "projection_watermark": 1,
            }
            for row in definitions
        ],
    }


def _exact_graph() -> tuple[list[dict[str, object]], dict[str, object]]:
    expected: list[dict[str, object]] = []
    definitions: list[dict[str, object]] = []
    criteria: list[dict[str, object]] = []
    for index in range(15):
        item_expected, item_snapshot = _checkpoint(f"I1.{index}", index)
        expected.extend(item_expected)
        definitions.extend(cast(list[dict[str, object]], item_snapshot["checkpoint_definitions"]))
        criteria.extend(cast(list[dict[str, object]], item_snapshot["checkpoint_criteria"]))
    return expected, {
        "checkpoint_definitions": definitions,
        "checkpoint_criteria": criteria,
    }


def _checkpoint(
    checkpoint_key: str,
    index: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    definition_id = f"definition-{index}"
    definition_digest = f"sha256:{index:064x}"
    criterion = {
        "checkpoint_definition_id": definition_id,
        "ordinal": 1,
        "criterion_key": f"criterion-{index}",
        "description": f"Criterion {index}",
        "proof_ticket_id": None,
        "proof_criterion_key": None,
        "source_ids": [],
    }
    criteria_digest = _checkpoint_expectation_sql._criteria_digest((criterion,))
    return [
        {
            "checkpoint_key": checkpoint_key,
            "catalog_revision": f"ctower.{checkpoint_key}@1",
            "definition_digest": definition_digest,
            "criteria_digest": criteria_digest,
        }
    ], {
        "checkpoint_definitions": [
            {
                "checkpoint_definition_id": definition_id,
                "checkpoint_key": checkpoint_key,
                "catalog_revision": f"ctower.{checkpoint_key}@1",
                "catalog_digest": definition_digest,
                "accountable_owner": "ctower-operator",
            }
        ],
        "checkpoint_criteria": [criterion],
    }


def _mismatches(
    expected: list[dict[str, object]],
    snapshot: dict[str, object],
) -> tuple[_checkpoint_expectation_sql.CheckpointMismatch, ...]:
    connection = _Connection(expected)
    return _checkpoint_expectation_sql.mismatches(
        cast(Any, connection),
        cast(Any, "run-id"),
        deepcopy(snapshot),
    )


class _Connection:
    def __init__(self, definitions: list[dict[str, object]]) -> None:
        self._definitions = deepcopy(definitions)

    def execute(self, query: str, parameters: tuple[object, ...]) -> _Cursor:
        assert "migration_verified_artifacts" in query
        assert parameters == ("run-id",)
        return _Cursor(self._definitions)


class _Cursor:
    def __init__(self, definitions: list[dict[str, object]]) -> None:
        self._definitions = definitions

    def fetchone(self) -> dict[str, object]:
        return {"definitions": self._definitions}

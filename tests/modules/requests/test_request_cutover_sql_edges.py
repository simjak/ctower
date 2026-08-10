"""Fail-closed Request cutover SQL decision edges."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.work import _request_cutover_common_sql as common
from ctower_kernel.work import _request_cutover_complete_sql as complete
from ctower_kernel.work import _request_cutover_guard as guard
from ctower_kernel.work import _request_cutover_import_sql as import_sql
from ctower_kernel.work import _request_cutover_prepare_sql as prepare
from ctower_kernel.work import _request_cutover_proof_sql as proof_sql
from ctower_kernel.work import _request_cutover_reconcile_sql as reconcile
from ctower_kernel.work.request_cutover import (
    RequestBatchProof,
    RequestCutoverComplete,
    RequestCutoverImport,
    RequestCutoverPrepare,
    RequestImportReconciliation,
)

__all__: tuple[str, ...] = ()

_DIGEST = "sha256:" + "1" * 64
_KEY_DIGEST = "sha256:" + "2" * 64
_NOW = datetime(2026, 8, 10, tzinfo=UTC)
_FORBIDDEN = 403
_WATERMARK = 9
_REQUEST_NUMBER = 7


class _Cursor:
    def __init__(self, value: object) -> None:
        self._value = value

    def fetchone(self) -> dict[str, object] | None:
        return cast(dict[str, object] | None, self._value)

    def fetchall(self) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], self._value)


class _Connection:
    def __init__(self, *responses: object) -> None:
        self.responses = iter(responses)
        self.statements: list[str] = []

    def execute(self, statement: str, _params: object = None) -> _Cursor:
        self.statements.append(statement)
        return _Cursor(next(self.responses, None))


def test_mutation_epoch_guard_covers_every_fence_state() -> None:
    tenant_id, command_id = uuid4(), uuid4()
    assert (
        guard.request_mutation_epoch_refusal(
            cast(
                Any,
                _Connection(
                    {"state": None, "acceptance_position": None, "pre_epoch_fenced": False}
                ),
            ),
            tenant_id,
            command_id,
        )
        is None
    )
    pre_epoch = _epoch_problem(
        {"state": None, "acceptance_position": None, "pre_epoch_fenced": True}
    )
    prepared = _epoch_problem(
        {"state": "prepared", "acceptance_position": None, "pre_epoch_fenced": True}
    )
    pending = _epoch_problem(
        {"state": "completed", "acceptance_position": None, "pre_epoch_fenced": True}
    )
    accepted = guard.request_mutation_epoch_refusal(
        cast(
            Any,
            _Connection({"state": "completed", "acceptance_position": 1, "pre_epoch_fenced": True}),
        ),
        tenant_id,
        command_id,
    )
    assert (pre_epoch.code, prepared.code, pending.code, accepted) == (
        "migration-import-finalization-refused",
        "migration-import-finalization-refused",
        "durability_pending",
        None,
    )


def test_common_sql_parses_inventory_manifest_watermark_and_refusal() -> None:
    actor = _actor()
    assert common.human_operator_refusal(cast(Any, _Connection({"ok": 1})), actor, uuid4()) is None
    denied = common.human_operator_refusal(cast(Any, _Connection(None)), actor, uuid4())
    assert isinstance(denied, RecordProblem) and denied.status == _FORBIDDEN
    assert common.owner_is_active_and_addressable(
        cast(Any, _Connection({"ok": 1})), actor.tenant_id, actor.principal_id, "ctower"
    )
    assert not common.owner_is_active_and_addressable(
        cast(Any, _Connection(None)), actor.tenant_id, actor.principal_id, "ctower"
    )
    inventory = common.target_authority_inventory(
        cast(Any, _Connection([_principal(actor), _principal(actor, disabled=True)])),
        actor.tenant_id,
    )
    assert cast(list[dict[str, object]], inventory["principals"])[0]["project_keys"] == ["ctower"]
    assert str(inventory["authority_digest"]).startswith("sha256:")
    assert common.load_manifest(cast(Any, _Connection(None)), actor, _DIGEST) is None
    assert common.load_manifest(
        cast(Any, _Connection({"manifest_artifact": {"ok": True}})), actor, _DIGEST
    ) == {"ok": True}
    assert (
        common.target_watermark(cast(Any, _Connection({"last_position": _WATERMARK}))) == _WATERMARK
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        common.target_watermark(cast(Any, _Connection(None)))

    transaction = cast(Any, _RefusingTransaction())
    problem = RecordProblem("migration-digest-mismatch", "drift", 409, "Drift")
    assert common.refuse(transaction, actor, uuid4(), bytes(32), problem, now=_NOW) is problem
    assert transaction.called


def test_cutover_result_rehydrates_optional_import_identity() -> None:
    command_id, request_id, event_id = uuid4(), uuid4(), uuid4()
    base: dict[str, object] = {
        "command_id": str(command_id),
        "operation": "import",
        "manifest_digest": _DIGEST,
        "state": "prepared",
        "imported_count": 1,
        "target_watermark": 2,
        "event_ids": [str(event_id)],
    }
    absent = common.request_cutover_result({**base, "request_id": None, "request_number": None})
    present = common.request_cutover_result(
        {**base, "request_id": str(request_id), "request_number": _REQUEST_NUMBER}
    )
    assert absent.request_id is None and absent.request_number is None
    assert present.request_id == request_id and present.request_number == _REQUEST_NUMBER


def test_prepare_refuses_every_authority_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    actor, command = _actor(), RequestCutoverPrepare(uuid4(), "{}", "{}", "pem")
    manifest = _prepare_manifest(actor)
    monkeypatch.setattr(
        prepare,
        "target_authority_inventory",
        lambda *_args: {"authority_digest": _DIGEST},
    )
    monkeypatch.setattr(prepare, "owner_is_active_and_addressable", lambda *_args: True)

    assert (
        _prepare_problem(
            _Connection(), actor, command, {**manifest, "target_tenant_id": str(uuid4())}
        ).code
        == "migration-digest-mismatch"
    )
    assert (
        _prepare_problem(
            _Connection(),
            actor,
            command,
            {**manifest, "target_authority_digest": "sha256:" + "9" * 64},
        ).code
        == "migration-digest-mismatch"
    )
    assert (
        _prepare_problem(_Connection(None, {"exists": 1}), actor, command, manifest).code
        == "migration-run-conflict"
    )
    assert (
        _prepare_problem(_Connection(None, None, {"exists": 1}), actor, command, manifest).code
        == "migration-run-conflict"
    )
    monkeypatch.setattr(prepare, "owner_is_active_and_addressable", lambda *_args: False)
    assert (
        _prepare_problem(_Connection(None, None, None), actor, command, manifest).code
        == "migration-operation-drift"
    )
    manifest["rows"] = []
    assert (
        prepare._preparation_refusal(
            cast(Any, _Connection(None, None, None)), actor, command, manifest
        )
        is None
    )


def test_import_preconditions_refuse_epoch_key_and_count_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, command = _actor(), RequestCutoverImport(uuid4(), _DIGEST, "R1", "intent", "{}", "pem")
    manifest: dict[str, Any] = {"rows": []}
    denial = RecordProblem("request-import-forbidden", "denied", 403, "Denied")
    monkeypatch.setattr(import_sql, "human_operator_refusal", lambda *_args: denial)
    assert (
        import_sql._import_preconditions(
            cast(Any, _Connection()), actor, command, manifest, public_key_digest=_KEY_DIGEST
        )[2]
        is denial
    )

    monkeypatch.setattr(import_sql, "human_operator_refusal", lambda *_args: None)
    for stored in (None, {"state": "completed", "public_key_digest": bytes.fromhex("2" * 64)}):
        outcome = import_sql._import_preconditions(
            cast(Any, _Connection(None, stored)),
            actor,
            command,
            manifest,
            public_key_digest=_KEY_DIGEST,
        )
        assert (
            isinstance(outcome[2], RecordProblem) and outcome[2].code == "request-import-forbidden"
        )
    wrong_key = {"state": "prepared", "public_key_digest": bytes.fromhex("3" * 64)}
    outcome = import_sql._import_preconditions(
        cast(Any, _Connection(None, wrong_key)),
        actor,
        command,
        manifest,
        public_key_digest=_KEY_DIGEST,
    )
    assert (
        isinstance(outcome[2], RecordProblem) and outcome[2].code == "migration-signature-invalid"
    )
    stored = {"state": "prepared", "public_key_digest": bytes.fromhex("2" * 64)}
    with pytest.raises(RuntimeError, match="count query"):
        import_sql._import_preconditions(
            cast(Any, _Connection(None, stored, None)),
            actor,
            command,
            manifest,
            public_key_digest=_KEY_DIGEST,
        )
    monkeypatch.setattr(import_sql, "_expected_row", lambda *_args: ({"id": "R1"}, 0, None))
    assert import_sql._import_preconditions(
        cast(Any, _Connection(None, stored, {"count": 0})),
        actor,
        command,
        manifest,
        public_key_digest=_KEY_DIGEST,
    ) == ({"id": "R1"}, 0, None)


def test_expected_import_row_is_strictly_serial_and_digest_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, expected_id = _actor(), uuid4()
    command = RequestCutoverImport(uuid4(), _DIGEST, "R1", "intent", "{}", "pem")
    row = _import_row(command, expected_id)
    manifest = {"ledger_sha256": _DIGEST}
    monkeypatch.setattr(
        import_sql, "import_identities", lambda *_args: (uuid4(), uuid4(), expected_id)
    )
    monkeypatch.setattr(import_sql, "owner_is_active_and_addressable", lambda *_args: True)

    assert _expected_problem(actor, command, manifest, [], 0).code == "migration-operation-drift"
    assert (
        _expected_problem(actor, command, manifest, [{**row, "id": "R2"}], 0).code
        == "migration-operation-drift"
    )
    monkeypatch.setattr(import_sql, "owner_is_active_and_addressable", lambda *_args: False)
    assert _expected_problem(actor, command, manifest, [row], 0).code == "migration-operation-drift"
    monkeypatch.setattr(import_sql, "owner_is_active_and_addressable", lambda *_args: True)
    assert (
        _expected_problem(actor, command, manifest, [{**row, "command_id": str(uuid4())}], 0).code
        == "migration-operation-drift"
    )
    assert (
        _expected_problem(actor, command, manifest, [{**row, "request_id": str(uuid4())}], 0).code
        == "migration-operation-drift"
    )
    assert (
        _expected_problem(
            actor, command, manifest, [{**row, "content_sha256": "sha256:" + "9" * 64}], 0
        ).code
        == "migration-digest-mismatch"
    )
    assert import_sql._expected_row(
        cast(Any, _Connection()), actor, command, manifest, [row], 0
    ) == (row, 0, None)


def test_reconciliation_compares_acceptance_and_exact_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected, observed = _reconciliation_rows()
    assert reconcile._comparison(expected, None) is None
    assert reconcile._comparison(expected, {**observed, "acceptance_position": None}) is None
    assert reconcile._comparison(expected, {**observed, "priority": "P2"}) is None
    comparison = reconcile._comparison(expected, observed)
    assert comparison is not None and comparison["durability_state"] == "accepted"
    assert isinstance(reconcile._compare_batch([expected], []), RecordProblem)

    manifest = {"rows": [expected], "batches": [{"sample_ids": ["R1"]}]}
    invalid = reconcile.reconcile_import_batch(
        "dsn", _actor(), manifest, manifest_digest=_DIGEST, batch_index=-1
    )
    assert isinstance(invalid, RecordProblem)
    monkeypatch.setattr(reconcile, "_load_observed", lambda *_args: ([], []))
    missing = reconcile.reconcile_import_batch(
        "dsn", _actor(), manifest, manifest_digest=_DIGEST, batch_index=0
    )
    assert isinstance(missing, RecordProblem)
    monkeypatch.setattr(
        reconcile,
        "_load_observed",
        lambda *_args: ([observed], [{"project_key": "other", "count": 1}]),
    )
    counts = reconcile.reconcile_import_batch(
        "dsn", _actor(), manifest, manifest_digest=_DIGEST, batch_index=0
    )
    assert isinstance(counts, RecordProblem)
    monkeypatch.setattr(
        reconcile,
        "_load_observed",
        lambda *_args: ([observed], [{"project_key": "ctower", "count": 1}]),
    )
    valid = reconcile.reconcile_import_batch(
        "dsn", _actor(), manifest, manifest_digest=_DIGEST, batch_index=0
    )
    assert isinstance(valid, RequestImportReconciliation) and valid.sample_ids == ("R1",)


def test_batch_proof_refuses_epoch_key_serial_and_payload_drift() -> None:
    actor, command = _actor(), RequestBatchProof(uuid4(), "{}", "pem")
    reconciliation = _reconciliation()
    proof = _proof(reconciliation)
    stored = {"state": "prepared", "public_key_digest": bytes.fromhex("2" * 64), "proof_count": 0}
    for row, code in (
        (None, "request-import-forbidden"),
        ({**stored, "state": "completed"}, "request-import-forbidden"),
        ({**stored, "public_key_digest": bytes.fromhex("3" * 64)}, "migration-signature-invalid"),
        ({**stored, "proof_count": 1}, "migration-operation-drift"),
    ):
        problem = proof_sql._proof_refusal(
            cast(Any, _Connection(None, row)),
            actor,
            command,
            proof,
            reconciliation,
            public_key_digest=_KEY_DIGEST,
        )
        assert isinstance(problem, RecordProblem) and problem.code == code
    assert (
        proof_sql._proof_refusal(
            cast(Any, _Connection(None, stored)),
            actor,
            command,
            proof,
            reconciliation,
            public_key_digest=_KEY_DIGEST,
        )
        is None
    )
    changed = {**proof, "target_count": 2}
    assert proof_sql._proof_difference(changed, reconciliation) == "target_count differs"
    assert (
        proof_sql._proof_difference({**proof, "samples": []}, reconciliation)
        == "sample roster differs"
    )
    assert (
        proof_sql._proof_difference({**proof, "samples": [{"id": "R1"}]}, reconciliation)
        == "public sample differs"
    )


def test_completion_refuses_incomplete_epoch_and_persists_only_valid_refinements() -> None:
    actor, command = _actor(), RequestCutoverComplete(uuid4(), _DIGEST, "{}", "pem")
    manifest: dict[str, Any] = {"rows": [{"id": "R1"}]}
    ready = {
        "state": "prepared",
        "public_key_digest": bytes.fromhex("2" * 64),
        "imported_count": 1,
        "pending_count": 0,
        "proof_count": 1,
    }
    cases = (
        (None, "request-import-forbidden"),
        ({**ready, "state": "completed"}, "request-import-forbidden"),
        ({**ready, "public_key_digest": bytes.fromhex("3" * 64)}, "migration-signature-invalid"),
        ({**ready, "imported_count": 0}, "migration-import-finalization-refused"),
        ({**ready, "pending_count": 1}, "migration-import-finalization-refused"),
        ({**ready, "proof_count": 0}, "migration-import-finalization-refused"),
    )
    for row, code in cases:
        problem = complete._completion_refusal(
            cast(Any, _Connection(None, row)),
            actor,
            command,
            manifest,
            public_key_digest=_KEY_DIGEST,
        )
        assert isinstance(problem, RecordProblem) and problem.code == code
    assert (
        complete._completion_refusal(
            cast(Any, _Connection(None, ready)),
            actor,
            command,
            manifest,
            public_key_digest=_KEY_DIGEST,
        )
        is None
    )

    first, second = uuid4(), uuid4()
    rows = [
        {
            "id": "R1",
            "request_id": first,
            "project_key": "ctower",
            "relationships_sha256": _DIGEST,
            "refines": ["absent", "R2", "R3"],
        },
        {
            "id": "R2",
            "request_id": second,
            "project_key": "other",
            "relationships_sha256": _DIGEST,
            "refines": [],
        },
        {
            "id": "R3",
            "request_id": second,
            "project_key": "ctower",
            "relationships_sha256": _DIGEST,
            "refines": [],
        },
    ]
    connection = _Connection()
    complete._persist_refinements(cast(Any, connection), actor, command, {"rows": rows}, now=_NOW)
    assert (
        sum("INSERT INTO request_refinement_facts" in item for item in connection.statements) == 1
    )


class _RefusingTransaction:
    def __init__(self) -> None:
        self.called = False

    def refuse(self, *_args: object, **_kwargs: object) -> None:
        self.called = True


def _actor() -> Actor:
    return Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)


def _epoch_problem(row: dict[str, object]) -> RecordProblem:
    problem = guard.request_mutation_epoch_refusal(cast(Any, _Connection(row)), uuid4(), uuid4())
    assert isinstance(problem, RecordProblem)
    return problem


def _principal(actor: Actor, *, disabled: bool = False) -> dict[str, object]:
    return {
        "principal_id": actor.principal_id,
        "kind": "operator",
        "disabled": disabled,
        "project_keys": ["ctower"],
    }


def _prepare_manifest(actor: Actor) -> dict[str, Any]:
    return {
        "target_tenant_id": str(actor.tenant_id),
        "target_authority_digest": _DIGEST,
        "rows": [
            {"id": "R1", "mapped_principal_id": str(actor.principal_id), "project_key": "ctower"}
        ],
    }


def _prepare_problem(
    connection: _Connection, actor: Actor, command: RequestCutoverPrepare, manifest: dict[str, Any]
) -> RecordProblem:
    problem = prepare._preparation_refusal(cast(Any, connection), actor, command, manifest)
    assert isinstance(problem, RecordProblem)
    return problem


def _import_row(command: RequestCutoverImport, expected_id: UUID) -> dict[str, object]:
    return {
        "id": "R1",
        "command_id": str(command.client_command_id),
        "request_id": str(expected_id),
        "mapped_principal_id": str(uuid4()),
        "project_key": "ctower",
        "content_sha256": f"sha256:{hashlib.sha256(command.content.encode()).hexdigest()}",
    }


def _expected_problem(
    actor: Actor,
    command: RequestCutoverImport,
    manifest: dict[str, Any],
    rows: list[dict[str, object]],
    imported_count: int,
) -> RecordProblem:
    _row, _count, problem = import_sql._expected_row(
        cast(Any, _Connection()), actor, command, manifest, rows, imported_count
    )
    assert isinstance(problem, RecordProblem)
    return problem


def _reconciliation_rows() -> tuple[dict[str, object], dict[str, object]]:
    request_id, owner_id = uuid4(), uuid4()
    raw = bytes.fromhex("1" * 64)
    expected: dict[str, object] = {
        "id": "R1",
        "request_id": str(request_id),
        "request_number": 1,
        "project_key": "ctower",
        "mapped_principal_id": str(owner_id),
        "content_sha256": _DIGEST,
        "original_owner_sha256": _DIGEST,
        "relationships_sha256": _DIGEST,
        "projection": {"priority": "P1", "state": "NEW", "triage": "UNTRIAGED"},
    }
    observed: dict[str, object] = {
        "acceptance_position": 2,
        "content_digest": raw,
        "created_at": _NOW,
        "disposition": "UNTRIAGED",
        "ticket_count": 0,
        "original_owner_digest": raw,
        "owner_id": owner_id,
        "priority": "P1",
        "project_key": "ctower",
        "relationships_digest": raw,
        "request_id": request_id,
        "source_request_number": 1,
        "source_ref": "R1",
        "last_position": 4,
    }
    return expected, observed


def _reconciliation() -> RequestImportReconciliation:
    expected, observed = _reconciliation_rows()
    row = reconcile._comparison(expected, observed)
    assert row is not None
    return RequestImportReconciliation(
        _DIGEST,
        0,
        1,
        {"ctower": 1},
        1,
        {"ctower": 1},
        1,
        {"ctower": 1},
        1,
        {"ctower": 1},
        4,
        (row,),
        ("R1",),
    )


def _proof(reconciliation: RequestImportReconciliation) -> dict[str, Any]:
    value = reconciliation.response_payload()
    value["samples"] = [reconciliation.rows[0]]
    return value

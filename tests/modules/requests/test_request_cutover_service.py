"""Request cutover service orchestration and epoch absence."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.artifacts import ArtifactError
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import request_cutover as module
from ctower_kernel.work.request_cutover import (
    PostgresRequestCutover,
    RequestBatchProof,
    RequestCutover,
    RequestCutoverComplete,
    RequestCutoverImport,
    RequestCutoverPrepare,
    RequestCutoverResult,
    RequestImportReconciliation,
)

__all__: tuple[str, ...] = ()

_DIGEST = "sha256:" + "1" * 64
_KEY_DIGEST = "sha256:" + "2" * 64
_NOW = datetime(2026, 8, 10, tzinfo=UTC)
_HTTP_NOT_FOUND = 404
_EXPECTED_ROLE_CALLS = 5


class _Store:
    def __init__(self) -> None:
        self.manifest_value: dict[str, Any] | RecordProblem = {"signature": {}}
        self.outcome: RequestCutoverResult | RecordProblem = _result()
        self.reconciliation: RequestImportReconciliation | RecordProblem = _reconciliation()
        self.calls: list[str] = []

    def authority_inventory(self, _actor: Actor) -> dict[str, object]:
        self.calls.append("inventory")
        return {"authority_digest": _DIGEST}

    def manifest(self, _actor: Actor, _digest: str) -> dict[str, Any] | RecordProblem:
        self.calls.append("manifest")
        return self.manifest_value

    def prepare(self, *_args: object, **_kwargs: object) -> RequestCutoverResult | RecordProblem:
        self.calls.append("prepare")
        return self.outcome

    def import_row(self, *_args: object, **_kwargs: object) -> RequestCutoverResult | RecordProblem:
        self.calls.append("import")
        return self.outcome

    def reconcile(
        self, *_args: object, **_kwargs: object
    ) -> RequestImportReconciliation | RecordProblem:
        self.calls.append("reconcile")
        return self.reconciliation

    def record_proof(
        self, *_args: object, **_kwargs: object
    ) -> RequestCutoverResult | RecordProblem:
        self.calls.append("proof")
        return self.outcome

    def complete(self, *_args: object, **_kwargs: object) -> RequestCutoverResult | RecordProblem:
        self.calls.append("complete")
        return self.outcome


class _Telemetry:
    def __init__(self) -> None:
        self.outcomes: list[str] = []

    def emit(self, _name: str, _context: TelemetryContext, *, outcome: str, reason: str) -> None:
        self.outcomes.append(f"{outcome}:{reason}")


def test_service_runs_each_verified_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    store, telemetry = _Store(), _Telemetry()
    _valid_artifacts(monkeypatch)
    authority = RequestCutover(cast(Any, store), clock=lambda: _NOW, telemetry=telemetry)
    actor, context = _actor(), _context()

    inventory = authority.authority_inventory(actor)
    assert isinstance(inventory, dict) and inventory["authority_digest"] == _DIGEST
    assert isinstance(authority.prepare(actor, _prepare(), telemetry=context), RequestCutoverResult)
    assert isinstance(
        authority.import_row(actor, _import(), telemetry=context), RequestCutoverResult
    )
    assert isinstance(authority.reconcile(actor, _DIGEST, 0), RequestImportReconciliation)
    assert isinstance(
        authority.record_batch_proof(actor, _proof(), telemetry=context), RequestCutoverResult
    )
    assert isinstance(
        authority.complete(actor, _complete(), telemetry=context), RequestCutoverResult
    )
    assert store.calls == [
        "inventory",
        "prepare",
        "manifest",
        "import",
        "manifest",
        "reconcile",
        "manifest",
        "reconcile",
        "proof",
        "manifest",
        "complete",
    ]
    assert telemetry.outcomes == [
        "ok:prepared",
        "ok:prepared",
        "ok:prepared",
        "ok:prepared",
    ]


def test_service_propagates_epoch_and_reconciliation_refusals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    _valid_artifacts(monkeypatch)
    authority = RequestCutover(cast(Any, store), clock=lambda: _NOW)
    actor, context = _actor(), _context()
    problem = _problem()

    store.manifest_value = problem
    assert authority.import_row(actor, _import(), telemetry=context) is problem
    assert authority.reconcile(actor, _DIGEST, 0) is problem
    assert authority.complete(actor, _complete(), telemetry=context) is problem
    assert authority.record_batch_proof(actor, _proof(), telemetry=context) is problem

    store.manifest_value = {"signature": {}}
    store.reconciliation = problem
    assert authority.record_batch_proof(actor, _proof(), telemetry=context) is problem
    store.outcome = problem
    store.reconciliation = _reconciliation()
    assert authority.prepare(actor, _prepare(), telemetry=context) is problem

    def refuse_manifest_key(*_args: object, **_kwargs: object) -> None:
        raise ValueError("reviewer key differs")

    monkeypatch.setattr(module, "validate_manifest_key", refuse_manifest_key)
    signature = authority.record_batch_proof(actor, _proof(), telemetry=context)
    assert isinstance(signature, RecordProblem) and signature.code == "migration-digest-mismatch"


def test_service_translates_artifact_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store()
    authority = RequestCutover(cast(Any, store), clock=lambda: _NOW)
    actor, context = _actor(), _context()

    monkeypatch.setattr(module, "load_reviewer_key", _raise_digest)
    refused = authority.prepare(actor, _prepare(), telemetry=context)
    assert isinstance(refused, RecordProblem) and refused.code == "migration-digest-mismatch"
    refused = authority.import_row(actor, _import(), telemetry=context)
    assert isinstance(refused, RecordProblem) and refused.code == "migration-digest-mismatch"
    refused = authority.record_batch_proof(actor, _proof(), telemetry=context)
    assert isinstance(refused, RecordProblem) and refused.code == "migration-digest-mismatch"
    refused = authority.complete(actor, _complete(), telemetry=context)
    assert isinstance(refused, RecordProblem) and refused.code == "migration-digest-mismatch"

    monkeypatch.setattr(module, "load_reviewer_key", _raise_key)
    signature = authority.prepare(actor, _prepare(), telemetry=context)
    assert isinstance(signature, RecordProblem) and signature.code == "migration-signature-invalid"


def test_postgres_store_exposes_only_prepared_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(module, "authority_connection", _connections(connection))
    monkeypatch.setattr(module, "human_operator_refusal", lambda *_args: None)
    monkeypatch.setattr(module, "target_authority_inventory", lambda *_args: {"ok": True})
    monkeypatch.setattr(module, "load_manifest", lambda *_args: {"manifest": True})
    store = PostgresRequestCutover("postgresql://unused")
    actor = _actor()

    assert store.authority_inventory(actor) == {"ok": True}
    assert store.manifest(actor, _DIGEST) == {"manifest": True}
    monkeypatch.setattr(module, "load_manifest", lambda *_args: None)
    missing = store.manifest(actor, _DIGEST)
    assert isinstance(missing, RecordProblem) and missing.status == _HTTP_NOT_FOUND
    denial = _problem()
    monkeypatch.setattr(module, "human_operator_refusal", lambda *_args: denial)
    assert store.authority_inventory(actor) is denial
    assert store.manifest(actor, _DIGEST) is denial
    assert connection.roles == _EXPECTED_ROLE_CALLS


def test_postgres_store_delegates_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    result, reconciliation = _result(), _reconciliation()
    monkeypatch.setattr(module, "recover_ambiguous_commit", lambda operation: operation())
    monkeypatch.setattr(module, "prepare_cutover", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(module, "import_request_row", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(module, "reconcile_import_batch", lambda *_args, **_kwargs: reconciliation)
    monkeypatch.setattr(module, "record_batch_proof", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(module, "complete_cutover", lambda *_args, **_kwargs: result)
    store = PostgresRequestCutover("postgresql://unused")
    context = _context()
    assert (
        store.prepare(
            _actor(),
            _prepare(),
            manifest={},
            fence={},
            public_key_digest=_KEY_DIGEST,
            request_digest=bytes(32),
            now=_NOW,
            telemetry=context,
        )
        is result
    )
    assert (
        store.import_row(
            _actor(),
            _import(),
            manifest={},
            fence={},
            public_key_digest=_KEY_DIGEST,
            request_digest=bytes(32),
            now=_NOW,
            telemetry=context,
        )
        is result
    )
    assert store.reconcile(_actor(), {}, digest=_DIGEST, batch_index=0) is reconciliation
    assert (
        store.record_proof(
            _actor(),
            _proof(),
            proof={},
            reconciliation=reconciliation,
            public_key_digest=_KEY_DIGEST,
            request_digest=bytes(32),
            now=_NOW,
            telemetry=context,
        )
        is result
    )
    assert (
        store.complete(
            _actor(),
            _complete(),
            manifest={},
            final_fence={},
            public_key_digest=_KEY_DIGEST,
            request_digest=bytes(32),
            now=_NOW,
            telemetry=context,
        )
        is result
    )


class _Connection:
    def __init__(self) -> None:
        self.roles = 0

    def execute(self, statement: str) -> None:
        assert statement == "SET ROLE ctower_svc"
        self.roles += 1


def _connections(
    connection: _Connection,
) -> Callable[[str], AbstractContextManager[_Connection]]:
    @contextmanager
    def connect(_dsn: str) -> Iterator[_Connection]:
        yield connection

    return connect


def _valid_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "load_reviewer_key", lambda _pem: (object(), _KEY_DIGEST))

    def verify(_text: str, schema: str, _field: str, _key: object) -> tuple[dict[str, Any], str]:
        if schema == "ctower.request-batch-proof/v1":
            return {"manifest_digest": _DIGEST, "batch_index": 0}, _DIGEST
        if schema == "ctower.request-import-manifest/v1":
            return {"signature": {}}, _DIGEST
        return {"phase": "freeze"}, _DIGEST

    monkeypatch.setattr(module, "verify_request_artifact", verify)
    monkeypatch.setattr(module, "validate_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "validate_manifest_key", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "validate_fence", lambda *_args, **_kwargs: None)


def _raise_digest(_pem: str) -> tuple[object, str]:
    raise ValueError("digest differs")


def _raise_key(_pem: str) -> tuple[object, str]:
    raise ArtifactError("review-key-invalid")


def _actor() -> Actor:
    return Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)


def _context() -> TelemetryContext:
    command_id = uuid4()
    return TelemetryContext(
        "ctower.telemetry-context/v1",
        command_id.hex,
        command_id.hex[:16],
        1,
        str(command_id),
        str(command_id),
        "unresolved",
        "unresolved",
        str(command_id),
    )


def _result() -> RequestCutoverResult:
    return RequestCutoverResult(uuid4(), "prepare", _DIGEST, "prepared", 0, 1)


def _reconciliation() -> RequestImportReconciliation:
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
        1,
        (),
        (),
    )


def _problem() -> RecordProblem:
    return RecordProblem("request-import-forbidden", "absent", 404, "Absent")


def _prepare() -> RequestCutoverPrepare:
    return RequestCutoverPrepare(uuid4(), "{}", "{}", "pem")


def _import() -> RequestCutoverImport:
    return RequestCutoverImport(uuid4(), _DIGEST, "R1", "content", "{}", "pem")


def _proof() -> RequestBatchProof:
    return RequestBatchProof(uuid4(), "{}", "pem")


def _complete() -> RequestCutoverComplete:
    return RequestCutoverComplete(uuid4(), _DIGEST, "{}", "pem")

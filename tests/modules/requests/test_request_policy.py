"""Small policy tests for Request inputs before persistence is reachable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NoReturn
from uuid import UUID, uuid4

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_similarity import (
    ALGORITHM_REF,
    MINIMUM_SIMILARITY,
    embed,
    similarity,
)
from ctower_kernel.work.requests import (
    RequestCapture,
    RequestClosureEvaluation,
    RequestPriority,
    Requests,
)

__all__: tuple[str, ...] = ()

EXPECTED_MINIMUM_SIMILARITY = 0.72
EXPECTED_NEAR_SIMILARITY = 0.921748
EXPECTED_UNRELATED_SIMILARITY = 0.232564


class _UnreachableStore:
    def capture(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("refused capture reached persistence")

    def list(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("refused list reached persistence")

    def change(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("refused change reached persistence")


def test_local_request_embedding_is_fixed_reproducible_and_discriminating() -> None:
    """AC-REQ-12: the authored local vector and threshold are stable evidence."""

    original = embed("Please add duplicate-aware Request capture to the operator workflow.")
    resemblance = embed("Please add duplicate aware Request capture in the operator workflow.")
    unrelated = embed("Rotate the backup encryption key after the restore drill.")
    normalized = embed("\uff23apture REQUESTS—duplicate aware")

    assert ALGORITHM_REF == "ctower.local-hashed-subword/v1"
    assert MINIMUM_SIMILARITY == EXPECTED_MINIMUM_SIMILARITY
    assert original.digest.hex() == (
        "dbc8739f4e3caa5e3a02ce240555ddb93dee497741cc658d4f76aa55487c7971"
    )
    assert similarity(original, resemblance) == EXPECTED_NEAR_SIMILARITY
    assert similarity(original, unrelated) == EXPECTED_UNRELATED_SIMILARITY
    assert similarity(original, resemblance) >= MINIMUM_SIMILARITY
    assert similarity(original, unrelated) < MINIMUM_SIMILARITY
    assert normalized == embed("capture requests-duplicate AWARE")


def test_viewer_missing_scope_and_prohibited_content_refuse_before_store() -> None:
    tenant_id, principal_id = uuid4(), uuid4()
    requests = Requests(_UnreachableStore(), clock=lambda: datetime(2026, 8, 10, tzinfo=UTC))
    viewer = Actor(principal_id, tenant_id, PrincipalKind.VIEWER)
    commander_without_scope = Actor(
        principal_id,
        tenant_id,
        PrincipalKind.COMMANDER,
        credential_scopes=frozenset({CredentialScope.TRANSITION}),
        seat_credential_id=uuid4(),
    )
    commander = Actor(principal_id, tenant_id, PrincipalKind.COMMANDER)

    viewer_result = requests.capture(
        viewer,
        RequestCapture(uuid4(), "ctower", "Visible operator intent"),
        telemetry=_telemetry(tenant_id, principal_id),
    )
    scope_result = requests.capture(
        commander_without_scope,
        RequestCapture(uuid4(), "ctower", "Visible operator intent"),
        telemetry=_telemetry(tenant_id, principal_id),
    )
    prohibited_result = requests.capture(
        commander,
        RequestCapture(uuid4(), "ctower", "Customer records copied from production"),
        telemetry=_telemetry(tenant_id, principal_id),
    )

    assert isinstance(viewer_result, RecordProblem)
    assert viewer_result.code == "request-capture-forbidden"
    assert isinstance(scope_result, RecordProblem)
    assert scope_result.code == "credential-scope-denied"
    assert isinstance(prohibited_result, RecordProblem)
    assert prohibited_result.code == "prohibited-data-class"


def test_transition_shape_and_scope_refuse_before_store() -> None:
    tenant_id, principal_id, request_id = uuid4(), uuid4(), uuid4()
    requests = Requests(_UnreachableStore())
    missing_transition = Actor(
        principal_id,
        tenant_id,
        PrincipalKind.COMMANDER,
        credential_scopes=frozenset({CredentialScope.CAPTURE}),
        seat_credential_id=uuid4(),
    )
    commander = Actor(principal_id, tenant_id, PrincipalKind.COMMANDER)

    scope_result = requests.evaluate_closure(
        missing_transition,
        RequestClosureEvaluation(uuid4(), request_id, 1, "evaluate current facts"),
        telemetry=_telemetry(tenant_id, principal_id),
    )
    shape_result = requests.prioritize(
        commander,
        RequestPriority(uuid4(), request_id, 1, "urgent", "invalid enum"),
        telemetry=_telemetry(tenant_id, principal_id),
    )

    assert isinstance(scope_result, RecordProblem)
    assert scope_result.code == "credential-scope-denied"
    assert isinstance(shape_result, RecordProblem)
    assert shape_result.code == "invalid-request"


def _telemetry(tenant_id: UUID, principal_id: UUID) -> TelemetryContext:
    command_id = uuid4()
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(tenant_id),
        actor_id=str(principal_id),
        command_id=str(command_id),
    )

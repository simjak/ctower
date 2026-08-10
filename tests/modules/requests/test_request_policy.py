"""Small policy tests for Request inputs before persistence is reachable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NoReturn
from uuid import UUID, uuid4

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import (
    RequestCapture,
    RequestClosureEvaluation,
    RequestPriority,
    Requests,
)

__all__: tuple[str, ...] = ()


class _UnreachableStore:
    def capture(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("refused capture reached persistence")

    def list(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("refused list reached persistence")

    def change(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("refused change reached persistence")


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

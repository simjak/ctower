"""Operator-only issuance and revocation of human role bindings."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from ctower_kernel.access import Access
from ctower_kernel.record import Actor, PrincipalKind, Record, RecordProblem
from ctower_kernel.record.human_identity import (
    HumanRoleBindingIssue,
    HumanRoleBindingReceipt,
    HumanRoleBindingRevocation,
)
from ctower_kernel.telemetry import TelemetryContext

from ._fakes import FakeRecord

__all__: tuple[str, ...] = ()


def _telemetry() -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=0,
        correlation_id=str(uuid4()),
        causation_id=str(uuid4()),
        tenant_id="test",
        actor_id="test",
        command_id=str(uuid4()),
    )


def _access(record: FakeRecord) -> Access:
    return Access(cast(Record, record), clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))


def _issue_command(*, role: str = "viewer") -> HumanRoleBindingIssue:
    return HumanRoleBindingIssue(
        client_command_id=uuid4(),
        display_name="Jamie Reviewer",
        oidc_issuer="https://idp.example.test",
        oidc_subject="user-9",
        project_keys=("ctower",),
        role=role,  # type: ignore[arg-type]
    )


def test_operator_can_bind_a_human_role() -> None:
    record = FakeRecord()
    access = _access(record)
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)

    receipt = access.human.bind_role(operator, _issue_command(), telemetry=_telemetry())

    assert isinstance(receipt, HumanRoleBindingReceipt)
    assert receipt.role == "viewer"
    assert receipt.state == "active"


def test_non_operator_cannot_bind_a_human_role() -> None:
    record = FakeRecord()
    access = _access(record)
    commander = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)

    outcome = access.human.bind_role(commander, _issue_command(), telemetry=_telemetry())

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "human-role-binding-refused"


def test_binding_the_same_identity_twice_conflicts() -> None:
    record = FakeRecord()
    access = _access(record)
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    first = access.human.bind_role(operator, _issue_command(), telemetry=_telemetry())
    assert isinstance(first, HumanRoleBindingReceipt)

    second = access.human.bind_role(operator, _issue_command(), telemetry=_telemetry())

    assert isinstance(second, RecordProblem)
    assert second.code == "human-role-binding-active"


def test_operator_can_revoke_a_bound_role_and_it_becomes_unresolvable() -> None:
    record = FakeRecord()
    access = _access(record)
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    bound = access.human.bind_role(operator, _issue_command(), telemetry=_telemetry())
    assert isinstance(bound, HumanRoleBindingReceipt)

    revoked = access.human.revoke_role(
        operator,
        HumanRoleBindingRevocation(
            client_command_id=uuid4(), binding_id=bound.binding_id, reason="offboarded"
        ),
        telemetry=_telemetry(),
    )

    assert isinstance(revoked, HumanRoleBindingReceipt)
    assert revoked.state == "revoked"
    assert record.human_identity.resolve_role_binding("https://idp.example.test", "user-9") is None


def test_non_operator_cannot_revoke_a_human_role() -> None:
    record = FakeRecord()
    access = _access(record)
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    bound = access.human.bind_role(operator, _issue_command(), telemetry=_telemetry())
    assert isinstance(bound, HumanRoleBindingReceipt)
    viewer = Actor(uuid4(), uuid4(), PrincipalKind.VIEWER)

    outcome = access.human.revoke_role(
        viewer,
        HumanRoleBindingRevocation(
            client_command_id=uuid4(), binding_id=bound.binding_id, reason="x"
        ),
        telemetry=_telemetry(),
    )

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "human-role-binding-refused"


def test_revoking_an_unknown_binding_refuses() -> None:
    record = FakeRecord()
    access = _access(record)
    operator = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)

    outcome = access.human.revoke_role(
        operator,
        HumanRoleBindingRevocation(client_command_id=uuid4(), binding_id=uuid4(), reason="x"),
        telemetry=_telemetry(),
    )

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "human-role-binding-unavailable"

"""DENY-axis and owner-seat authority evidence for first-class Requests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import psycopg
from support.acceptance import accept_pending_commands
from support.request_authority import (
    assert_command_id_reuse_cannot_cross_principal_authority,
    assert_non_commander_project_seat_cannot_directly_triage,
    assert_payload_authority_cannot_override_authenticated_principal,
    assert_routine_held_seat_cannot_directly_triage,
)
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.credentials import CredentialScope
from ctower_kernel.record.human_identity import HumanRole, HumanRoleBindingIssue
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestBlocker,
    RequestCapture,
    RequestCaptureResult,
    RequestChangeResult,
    RequestClosureEvaluation,
    RequestOwner,
    RequestPriority,
    Requests,
    RequestTriage,
)

__all__: tuple[str, ...] = ()
HTTP_FORBIDDEN = 403


def test_empty_bound_operator_cannot_capture_or_prioritize_requests(
    tenant: TenantFixture,
) -> None:
    """R2-1: the read-only operator exemption cannot authorize Request writes."""
    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    machine_operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    bound_operator = _bound_human(tenant, machine_operator, "operator", project_keys=())
    seed = _accepted_capture(tenant, authority, machine_operator, "R2-1 transition seed")
    before = _request_counts(tenant)
    capture_text = "R2-1 empty-bound operator capture"
    capture = authority.capture(
        bound_operator,
        RequestCapture(uuid4(), "ctower", capture_text),
        telemetry=_telemetry(bound_operator),
    )
    priority_reason = "R2-1 empty-bound operator priority"
    priority = authority.prioritize(
        bound_operator,
        RequestPriority(uuid4(), seed.request_id, 1, "P1", priority_reason),
        telemetry=_telemetry(bound_operator),
    )
    markers = (str(bound_operator.principal_id), str(seed.request_id))
    _assert_scope_refusal(capture, (*markers, capture_text))
    _assert_scope_refusal(priority, (*markers, priority_reason))
    assert _request_counts(tenant) == before


def test_viewer_is_denied_every_request_mutation_axis_and_cannot_be_owner(
    tenant: TenantFixture,
) -> None:
    """OR-05: viewer denies are named and owner identity cannot elevate the role."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    viewer = _bound_human(tenant, operator, "viewer")
    captured = _accepted_capture(tenant, authority, commander, "Authority matrix intent")

    denied = (
        authority.prioritize(
            viewer,
            RequestPriority(uuid4(), captured.request_id, 1, "P1", "viewer priority"),
            telemetry=_telemetry(viewer),
        ),
        authority.triage(
            viewer,
            RequestTriage(uuid4(), captured.request_id, 1, "ACCEPTED"),
            telemetry=_telemetry(viewer),
        ),
        authority.assign_owner(
            viewer,
            RequestOwner(
                uuid4(), captured.request_id, 1, tenant.commander_id, "viewer owner change"
            ),
            telemetry=_telemetry(viewer),
        ),
        authority.set_blocker(
            viewer,
            RequestBlocker(
                uuid4(),
                captured.request_id,
                1,
                "viewer",
                active=True,
                reason="viewer blocker",
            ),
            telemetry=_telemetry(viewer),
        ),
        authority.evaluate_closure(
            viewer,
            RequestClosureEvaluation(uuid4(), captured.request_id, 1, "viewer closure"),
            telemetry=_telemetry(viewer),
        ),
    )
    assert [cast(RecordProblem, outcome).code for outcome in denied] == [
        "request-transition-forbidden",
        "request-triage-forbidden",
        "request-owner-forbidden",
        "request-transition-forbidden",
        "request-transition-forbidden",
    ]
    assert all(
        isinstance(outcome, RecordProblem) and outcome.status == HTTP_FORBIDDEN
        for outcome in denied
    )

    assignment = authority.assign_owner(
        commander,
        RequestOwner(uuid4(), captured.request_id, 1, viewer.principal_id, "viewer is not a seat"),
        telemetry=_telemetry(commander),
    )
    assert isinstance(assignment, RecordProblem)
    assert assignment.code == "request-owner-forbidden"


def test_viewer_owner_id_cannot_bypass_the_principal_kind_gate(
    tenant: TenantFixture,
) -> None:
    """OR-05: malformed owner history cannot elevate a viewer principal."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    viewer = _bound_human(tenant, operator, "viewer")
    captured = _accepted_capture(tenant, authority, commander, "Owner-kind gate intent")

    # Even malformed historical state cannot turn principal-id equality into
    # authority: the current owner must also resolve as a Project seat Actor.
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO request_owner_facts (
                request_id, tenant_id, sequence, owner_id, reason,
                recorded_by, command_id, recorded_at
            ) VALUES (%s, %s, 2, %s, %s, %s, %s, %s)
            """,
            (
                captured.request_id,
                tenant.tenant_id,
                viewer.principal_id,
                "principal-kind gate probe",
                tenant.operator_id,
                uuid4(),
                datetime.now(UTC),
            ),
        )
    owner_denied = authority.set_blocker(
        viewer,
        RequestBlocker(
            uuid4(),
            captured.request_id,
            1,
            "owner",
            active=True,
            reason="viewer owner probe",
        ),
        telemetry=_telemetry(viewer),
    )
    assert isinstance(owner_denied, RecordProblem)
    assert owner_denied.code == "request-transition-forbidden"


def test_owner_project_seat_with_transition_scope_can_mutate(
    tenant: TenantFixture,
) -> None:
    """OR-05: a non-Commander owner seat gains only the transition path."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    owner = _project_owner_seat(tenant)
    captured = _accepted_capture(tenant, authority, commander, "Seat-owned intent")
    assigned = authority.assign_owner(
        operator,
        RequestOwner(uuid4(), captured.request_id, 1, owner.principal_id, "seat accountability"),
        telemetry=_telemetry(operator),
    )
    accepted_assignment = _accepted_change(tenant, assigned)

    blocked = authority.set_blocker(
        owner,
        RequestBlocker(
            uuid4(),
            captured.request_id,
            accepted_assignment.version,
            "seat-decision",
            active=True,
            reason="owner seat transition",
        ),
        telemetry=_telemetry(owner),
    )

    assert isinstance(blocked, RequestChangeResult)


def test_non_commander_project_seat_cannot_directly_triage(
    tenant: TenantFixture,
) -> None:
    assert_non_commander_project_seat_cannot_directly_triage(tenant)


def test_routine_held_seat_cannot_directly_triage(tenant: TenantFixture) -> None:
    assert_routine_held_seat_cannot_directly_triage(tenant)


def test_payload_authority_field_cannot_substitute_authenticated_principal(
    tenant: TenantFixture,
) -> None:
    assert_payload_authority_cannot_override_authenticated_principal(tenant)


def test_operator_command_id_cannot_be_reused_across_principals(
    tenant: TenantFixture,
) -> None:
    assert_command_id_reuse_cannot_cross_principal_authority(tenant)


def test_cross_tenant_rejected_and_self_duplicate_outcomes_are_explicit(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
) -> None:
    """OR-02/05: foreign identity, REJECTED, and self-duplicate never collapse."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    foreign = Actor(
        second_tenant.commander_id,
        second_tenant.tenant_id,
        PrincipalKind.COMMANDER,
    )
    rejected = _accepted_capture(tenant, authority, commander, "Reject this intent")
    foreign_outcome = authority.prioritize(
        foreign,
        RequestPriority(uuid4(), rejected.request_id, 1, "P1", "foreign probe"),
        telemetry=_telemetry(foreign),
    )
    assert isinstance(foreign_outcome, RecordProblem)
    assert foreign_outcome.code == "tenant-scope-denied"
    assert foreign_outcome.current_version is None

    prioritized = _accepted_change(
        tenant,
        authority.prioritize(
            commander,
            RequestPriority(uuid4(), rejected.request_id, 1, "P2", "reviewed default"),
            telemetry=_telemetry(commander),
        ),
    )
    rejected_outcome = _accepted_change(
        tenant,
        authority.triage(
            commander,
            RequestTriage(
                uuid4(), rejected.request_id, prioritized.version, "REJECTED", "not pursued"
            ),
            telemetry=_telemetry(commander),
        ),
    )
    assert rejected_outcome.state == "TRIAGED"

    duplicate = _accepted_capture(tenant, authority, commander, "Self duplicate probe")
    self_duplicate = authority.triage(
        commander,
        RequestTriage(
            uuid4(),
            duplicate.request_id,
            1,
            "DUPLICATE",
            "same identity",
            duplicate.request_id,
        ),
        telemetry=_telemetry(commander),
    )
    assert isinstance(self_duplicate, RecordProblem)
    assert self_duplicate.code == "request-triage-forbidden"


def _accepted_capture(
    tenant: TenantFixture, authority: Requests, actor: Actor, text: str
) -> RequestCaptureResult:
    command = RequestCapture(uuid4(), "ctower", text)
    outcome = authority.capture(actor, command, telemetry=_telemetry(actor))
    assert isinstance(outcome, RequestCaptureResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome


def _accepted_change(tenant: TenantFixture, outcome: object) -> RequestChangeResult:
    assert isinstance(outcome, RequestChangeResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome


def _request_counts(tenant: TenantFixture) -> tuple[int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT (SELECT count(*) FROM requests), (SELECT count(*) FROM request_priority_facts)"
        ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def _assert_scope_refusal(outcome: object, markers: tuple[str, ...]) -> None:
    assert isinstance(outcome, RecordProblem)
    problem: RecordProblem = outcome
    assert (problem.code, problem.status) == ("project-scope-denied", HTTP_FORBIDDEN)
    assert all(marker not in str(problem.response_payload()) for marker in markers)


def _bound_human(
    tenant: TenantFixture,
    operator: Actor,
    role: str,
    *,
    project_keys: tuple[str, ...] = ("ctower",),
) -> Actor:
    record = PostgresRecord(tenant.database.runtime_dsn)
    subject = f"request-authority-{role}-{uuid4().hex}"
    receipt = record.human_identity.bind_role(
        operator,
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name=f"Request authority {role} {uuid4().hex[:8]}",
            oidc_issuer="https://request-authority.example.test",
            oidc_subject=subject,
            project_keys=project_keys,
            role=cast(HumanRole, role),
        ),
        request_digest=hashlib.sha256(subject.encode()).digest(),
        now=datetime.now(UTC),
        telemetry=_telemetry(operator),
    )
    assert not isinstance(receipt, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    resolved = record.human_identity.resolve_role_binding(
        "https://request-authority.example.test", subject
    )
    assert resolved is not None
    return resolved[1]


def _project_owner_seat(tenant: TenantFixture) -> Actor:
    principal_id = uuid4()
    now = datetime.now(UTC)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled,
                credential_ref, vault_ref, created_at
            ) VALUES (%s, %s, 'commander', %s, false, NULL, %s, %s)
            """,
            (
                principal_id,
                tenant.tenant_id,
                f"Request owner seat {principal_id}",
                f"vault-ref:request-owner/{principal_id}",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO project_seats (
                principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
            ) VALUES (%s, %s, 'ctower', %s, %s, %s)
            """,
            (
                principal_id,
                tenant.tenant_id,
                f"ctower-request-owner-{principal_id.hex[:12]}",
                tenant.operator_id,
                now,
            ),
        )
    return Actor(
        principal_id,
        tenant.tenant_id,
        PrincipalKind.COMMANDER,
        project_grants=frozenset({"ctower"}),
        credential_scopes=frozenset({CredentialScope.TRANSITION}),
        seat_credential_id=uuid4(),
    )


def _telemetry(actor: Actor) -> TelemetryContext:
    command_id = uuid4()
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )

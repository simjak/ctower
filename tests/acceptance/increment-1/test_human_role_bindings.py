"""Real-Postgres acceptance evidence for the human role-binding and session tables."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingIssue, HumanRoleBindingRevocation
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import NoopTelemetry, TelemetryContext

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


def test_bound_identity_resolves_a_session_that_a_revocation_ends(
    tenant: TenantFixture,
) -> None:
    record = PostgresRecord(tenant.database.runtime_dsn, telemetry=NoopTelemetry())
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    now = datetime.now(UTC)
    issuer = "https://fake-idp.example.test"
    subject = f"user-{uuid4().hex}"

    bound = record.human_identity.bind_role(
        operator,
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name=f"Acceptance Viewer {uuid4().hex[:8]}",
            oidc_issuer=issuer,
            oidc_subject=subject,
            project_keys=("ctower",),
            role="viewer",
        ),
        request_digest=hashlib.sha256(b"bind").digest(),
        now=now,
        telemetry=_telemetry(),
    )
    assert not isinstance(bound, RecordProblem)
    assert bound.role == "viewer"

    resolved = record.human_identity.resolve_role_binding(issuer, subject)
    assert resolved is not None
    binding_id, actor = resolved
    assert actor.kind is PrincipalKind.VIEWER
    assert actor.project_grants == frozenset({"ctower"})

    session_token = "acceptance-session-" + uuid4().hex
    digest = hashlib.sha256(session_token.encode()).digest()
    receipt = record.human_identity.issue_session(
        actor.principal_id,
        actor.tenant_id,
        binding_id,
        "viewer",
        session_digest=digest,
        csrf_digest=hashlib.sha256(b"acceptance-csrf").digest(),
        now=now,
        ttl_seconds=3600,
    )
    assert receipt.role == "viewer"

    live = record.human_identity.actor_for_session(digest, now=now)
    assert not isinstance(live, RecordProblem)
    assert live is not None
    assert live.principal_id == actor.principal_id

    record.human_identity.revoke_session(digest, reason="acceptance test logout", now=now)

    after_logout = record.human_identity.actor_for_session(digest, now=now)
    assert isinstance(after_logout, RecordProblem)
    assert after_logout.code == "auth-session-invalid"

    revoked = record.human_identity.revoke_role(
        operator,
        HumanRoleBindingRevocation(
            client_command_id=uuid4(), binding_id=binding_id, reason="acceptance test offboarding"
        ),
        request_digest=hashlib.sha256(b"revoke").digest(),
        now=now,
        telemetry=_telemetry(),
    )
    assert not isinstance(revoked, RecordProblem)
    assert revoked.state == "revoked"
    assert record.human_identity.resolve_role_binding(issuer, subject) is None


def test_binding_requires_operator_authority(tenant: TenantFixture) -> None:
    record = PostgresRecord(tenant.database.runtime_dsn, telemetry=NoopTelemetry())
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)

    outcome = record.human_identity.bind_role(
        commander,
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name="Should Not Bind",
            oidc_issuer="https://fake-idp.example.test",
            oidc_subject=f"user-{uuid4().hex}",
            project_keys=(),
            role="operator",
        ),
        request_digest=hashlib.sha256(b"bind-refused").digest(),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )

    assert isinstance(outcome, RecordProblem)
    assert outcome.code == "human-role-binding-refused"

"""Public Interface evidence for immutable refusal command outcomes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from support.server import running_api, start_and_admit
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_client import (
    AdmitIntent,
    AuditEvent,
    BlockIntent,
    CtowerClient,
    CtowerProblemError,
    CustodyTransferRequest,
    FreezeCriteriaRequest,
    Priority,
    PriorityChangeRequest,
    Problem,
    ProofCriterion,
    RelationKind,
    RelationRequest,
    SourceReference,
    TicketCreateRequest,
    TicketIntentRequest,
    WorkflowStartRequest,
)
from ctower_kernel.workflow import WorkflowGraph

__all__: tuple[str, ...] = ()

INDEPENDENT_TICKET_VERSION = 3
THREE_EVENT_TRACE = 3
TWO_EVENT_TRACE = 2
HTTP_PENDING = 202
HTTP_UNAUTHORIZED = 401
HTTP_CONFLICT = 409
ROOT = Path(__file__).parents[3]


def test_ticket_relation_and_blocker_refusals_replay_without_mutation(
    tenant: TenantFixture,
) -> None:
    with (
        running_api(tenant.database.runtime_dsn) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        _assert_ticket_refusal(client, tenant)
        _assert_relation_refusal(client, tenant)
        _assert_blocker_refusal(client, tenant)


def _assert_ticket_refusal(client: CtowerClient, tenant: TenantFixture) -> None:
    command_id = uuid4()
    refused_request = _ticket_request(uuid4(), "refused-ticket")
    first = _problem(lambda: client.create_ticket(refused_request, command_id=command_id))
    accepted = client.create_ticket(
        _ticket_request(tenant.commander_id, "independent-ticket"), command_id=uuid4()
    )
    replay = _problem(lambda: client.create_ticket(refused_request, command_id=command_id))
    changed = _problem(
        lambda: client.create_ticket(
            refused_request.model_copy(update={"title": "changed refusal body"}),
            command_id=command_id,
        )
    )

    assert first.code == "unauthorized"
    assert replay == first
    assert changed.code == "idempotency-conflict"
    assert all(
        event.command_id != command_id for event in _audit(client, accepted.ticket.ticket_id)
    )


def _assert_relation_refusal(client: CtowerClient, tenant: TenantFixture) -> None:
    source = client.create_ticket(
        _ticket_request(tenant.commander_id, "relation-source"), command_id=uuid4()
    ).ticket.ticket_id
    target = client.create_ticket(
        _ticket_request(tenant.commander_id, "relation-target"), command_id=uuid4()
    ).ticket.ticket_id
    client.add_ticket_relation(
        source,
        RelationRequest(
            expected_version=1,
            reason="Source depends on target",
            relation_kind=RelationKind.DEPENDS_ON,
            target_ticket_id=target,
        ),
        command_id=uuid4(),
    )
    command_id = uuid4()
    refused_request = RelationRequest(
        expected_version=2,
        reason="Duplicate relation refused",
        relation_kind=RelationKind.DEPENDS_ON,
        target_ticket_id=target,
    )
    first = _problem(
        lambda: client.add_ticket_relation(source, refused_request, command_id=command_id)
    )
    client.change_ticket_priority(
        source,
        PriorityChangeRequest(
            expected_version=2, priority=Priority.P1, reason="Independent version advance"
        ),
        command_id=uuid4(),
    )
    replay = _problem(
        lambda: client.add_ticket_relation(source, refused_request, command_id=command_id)
    )
    changed = _problem(
        lambda: client.add_ticket_relation(
            source,
            refused_request.model_copy(update={"reason": "Changed duplicate relation"}),
            command_id=command_id,
        )
    )

    assert first.code == "work-relation-exists"
    assert replay == first
    assert changed.code == "idempotency-conflict"
    assert client.get_ticket(source, project_key="ctower").version == INDEPENDENT_TICKET_VERSION
    events = _audit(client, source)
    assert len(events) == THREE_EVENT_TRACE
    assert all(event.command_id != command_id for event in events)


def _assert_blocker_refusal(client: CtowerClient, tenant: TenantFixture) -> None:
    ticket_id = client.create_ticket(
        _ticket_request(tenant.commander_id, "blocker-ticket"), command_id=uuid4()
    ).ticket.ticket_id
    blocker_id = uuid4()
    client.apply_ticket_intent(
        ticket_id,
        TicketIntentRequest(intent=_block(tenant, blocker_id, version=1, reason="First blocker")),
        command_id=uuid4(),
    )
    command_id = uuid4()
    refused_request = TicketIntentRequest(
        intent=_block(tenant, blocker_id, version=2, reason="Duplicate blocker refused")
    )
    first = _problem(
        lambda: client.apply_ticket_intent(ticket_id, refused_request, command_id=command_id)
    )
    client.change_ticket_priority(
        ticket_id,
        PriorityChangeRequest(
            expected_version=2, priority=Priority.P1, reason="Independent version advance"
        ),
        command_id=uuid4(),
    )
    replay = _problem(
        lambda: client.apply_ticket_intent(ticket_id, refused_request, command_id=command_id)
    )
    changed = _problem(
        lambda: client.apply_ticket_intent(
            ticket_id,
            TicketIntentRequest(
                intent=refused_request.intent.model_copy(update={"reason": "Changed blocker"})
            ),
            command_id=command_id,
        )
    )

    assert first.code == "work-blocker-id-conflict"
    assert replay == first
    assert changed.code == "idempotency-conflict"
    assert client.get_ticket(ticket_id, project_key="ctower").version == INDEPENDENT_TICKET_VERSION
    events = _audit(client, ticket_id)
    assert len(events) == THREE_EVENT_TRACE
    assert all(event.command_id != command_id for event in events)


def test_custody_and_proof_refusals_replay_original_versions(
    tenant: TenantFixture,
) -> None:
    with running_api(tenant.database.runtime_dsn) as base_url:
        with CtowerClient(base_url, credential=tenant.operator_credential) as operator:
            _assert_custody_refusal(operator, tenant)
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            _assert_proof_refusal(commander, tenant)


def test_http_refusal_survives_state_change_and_preauth_does_not_reserve(
    tenant: TenantFixture,
) -> None:
    with (
        running_api(tenant.database.runtime_dsn) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as commander,
        httpx.Client(base_url=base_url) as raw,
    ):
        ticket_id = _create_public_ticket(commander, tenant, "workflow-refusal")
        _start(commander, ticket_id)
        command_id = uuid4()
        request = {
            "expected_version": 1,
            "workflow_ref": "ctower.trust-spine-four-stage@1",
            "source_stage": "capture",
            "destination_stage": "frame",
        }
        before = _record_counts(tenant, command_id)
        first = raw.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json=request,
            headers=_headers(tenant.commander_credential, command_id, ticket_id),
        )
        after = _record_counts(tenant, command_id)
        commander.apply_ticket_intent(
            ticket_id,
            TicketIntentRequest(
                intent=AdmitIntent(
                    kind="admit",
                    expected_version=1,
                    reason="Business predicate is now satisfied",
                )
            ),
            command_id=uuid4(),
        )
        replay = raw.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json=request,
            headers=_headers(tenant.commander_credential, command_id, ticket_id),
        )
        changed = raw.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json={**request, "destination_stage": "verify"},
            headers=_headers(tenant.commander_credential, command_id, ticket_id),
        )

        ready_id = _create_public_ticket(commander, tenant, "preauth-key")
        start_and_admit(commander, ready_id)
        preauth_id = uuid4()
        unauthorized = raw.post(
            f"/v1/tickets/{ready_id}/workflow/transition",
            json=request,
            headers=_headers("invalid-credential", preauth_id, ready_id),
        )
        assert _record_counts(tenant, preauth_id) == (0, 0, 0)
        authorized = raw.post(
            f"/v1/tickets/{ready_id}/workflow/transition",
            json=request,
            headers=_headers(tenant.commander_credential, preauth_id, ready_id),
        )

    assert first.status_code == HTTP_CONFLICT
    assert first.json()["code"] == "workflow-predicate-unsatisfied"
    assert before == (0, 0, 0)
    assert after == (1, 0, 0)
    assert replay.content == first.content
    assert changed.status_code == HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"
    assert unauthorized.status_code == HTTP_UNAUTHORIZED
    assert authorized.status_code == HTTP_PENDING
    assert _record_counts(tenant, preauth_id) == (1, 1, 1)


def _assert_custody_refusal(client: CtowerClient, tenant: TenantFixture) -> None:
    ticket_id = client.create_ticket(
        _ticket_request(tenant.commander_id, "custody-ticket"), command_id=uuid4()
    ).ticket.ticket_id
    command_id = uuid4()
    refused_request = CustodyTransferRequest(
        expected_version=2,
        from_custodian_id=tenant.commander_id,
        protected_transfer=True,
        reason="Premature custody transfer",
        to_custodian_id=tenant.operator_id,
    )
    first = _problem(
        lambda: client.transfer_ticket_custody(ticket_id, refused_request, command_id=command_id)
    )
    client.transfer_ticket_custody(
        ticket_id,
        refused_request.model_copy(
            update={"expected_version": 1, "reason": "Independent custody transfer"}
        ),
        command_id=uuid4(),
    )
    replay = _problem(
        lambda: client.transfer_ticket_custody(ticket_id, refused_request, command_id=command_id)
    )
    changed = _problem(
        lambda: client.transfer_ticket_custody(
            ticket_id,
            refused_request.model_copy(update={"reason": "Changed custody refusal"}),
            command_id=command_id,
        )
    )

    assert first.code == "version-conflict" and first.current_version == 1
    assert replay == first
    assert changed.code == "idempotency-conflict"
    ticket = client.get_ticket(ticket_id, project_key="ctower")
    assert (ticket.version, ticket.custodian_id) == (2, tenant.operator_id)
    assert (
        len(client.get_ticket_timeline(ticket_id, project_key="ctower").events) == TWO_EVENT_TRACE
    )
    assert all(event.command_id != command_id for event in _audit(client, ticket_id))


def _assert_proof_refusal(client: CtowerClient, tenant: TenantFixture) -> None:
    ticket_id = client.create_ticket(
        _ticket_request(tenant.commander_id, "proof-ticket"), command_id=uuid4()
    ).ticket.ticket_id
    _start(client, ticket_id)
    command_id = uuid4()
    refused_request = _freeze_request(expected_version=1, fill="a")
    first = _problem(
        lambda: client.freeze_proof_criteria(ticket_id, refused_request, command_id=command_id)
    )
    committed = client.freeze_proof_criteria(
        ticket_id,
        _freeze_request(expected_version=0, fill="b"),
        command_id=uuid4(),
    )
    replay = _problem(
        lambda: client.freeze_proof_criteria(ticket_id, refused_request, command_id=command_id)
    )
    changed = _problem(
        lambda: client.freeze_proof_criteria(
            ticket_id,
            refused_request.model_copy(update={"candidate_digest": "sha256:" + "c" * 64}),
            command_id=command_id,
        )
    )

    assert first.code == "version-conflict" and first.current_version == 0
    assert replay == first
    assert changed.code == "idempotency-conflict"
    assert committed.version == 1
    events = _audit(client, ticket_id)
    assert len(events) == THREE_EVENT_TRACE
    assert all(event.command_id != command_id for event in events)


def _ticket_request(custodian_id: UUID, suffix: str) -> TicketCreateRequest:
    return TicketCreateRequest(
        initial_custodian_id=custodian_id,
        priority=Priority.P2,
        project_key="ctower",
        source=SourceReference(kind="test", ref=f"test:{suffix}:{uuid4()}"),
        title=suffix,
    )


def _block(tenant: TenantFixture, blocker_id: UUID, *, version: int, reason: str) -> BlockIntent:
    return BlockIntent(
        kind="block",
        expected_version=version,
        reason=reason,
        blocker_id=blocker_id,
        blocker_kind="dependency",
        reason_class="external_dependency",
        owner_principal_id=tenant.commander_id,
        source_ref="test:blocker",
        affected_stage="capture",
        resolution_condition="Dependency is available",
        next_check_at=datetime.now(UTC) + timedelta(hours=1),
        dependency_ref="ticket:external",
        board_impact=True,
    )


def _freeze_request(*, expected_version: int, fill: str) -> FreezeCriteriaRequest:
    return FreezeCriteriaRequest(
        expected_version=expected_version,
        candidate_digest="sha256:" + fill * 64,
        criteria=(
            ProofCriterion(
                key="artifact-current",
                description="Artifact evidence matches the current candidate.",
                candidate_dependent=True,
                requires_verdict=True,
            ),
        ),
    )


def _create_public_ticket(client: CtowerClient, tenant: TenantFixture, suffix: str) -> UUID:
    return client.create_ticket(
        _ticket_request(tenant.commander_id, suffix), command_id=uuid4()
    ).ticket.ticket_id


def _start(client: CtowerClient, ticket_id: UUID) -> None:
    graph = WorkflowGraph.from_mapping(
        json.loads(
            (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    client.start_ticket_workflow(
        ticket_id,
        WorkflowStartRequest(
            workflow_ref=graph.reference,
            workflow_digest=graph.digest,
            execution_policy_ref="ctower.trust-spine-four-stage.execution@1",
            execution_policy_digest=_digest(
                "packs/policies/execution/trust-spine-four-stage-v1.yaml"
            ),
            gate_policy_ref="ctower.trust-spine-four-stage.gates@1",
            gate_policy_digest=_digest("packs/policies/gates/trust-spine-four-stage-v1.yaml"),
            evidence_policy_ref="ctower.trust-spine-four-stage.evidence@1",
            evidence_policy_digest=_digest(
                "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
            ),
        ),
        command_id=uuid4(),
    )


def _digest(relative: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _headers(credential: str, command_id: UUID, ticket_id: UUID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id, ticket_id=ticket_id),
    }


def _record_counts(tenant: TenantFixture, command_id: UUID) -> tuple[int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM command_results WHERE client_command_id = %s),
                (SELECT count(*) FROM events WHERE client_command_id = %s),
                (SELECT count(*) FROM outbox WHERE event_id IN (
                    SELECT event_id FROM events WHERE client_command_id = %s
                ))
            """,
            (command_id, command_id, command_id),
        ).fetchone()
    return cast(tuple[int, int, int], row)


def _problem[T](operation: Callable[[], T]) -> Problem:
    with pytest.raises(CtowerProblemError) as captured:
        operation()
    return cast(Problem, captured.value.problem)


def _audit(client: CtowerClient, ticket_id: UUID) -> tuple[AuditEvent, ...]:
    return tuple(client.list_ticket_audit_events(ticket_id, project_key="ctower", limit=100).events)

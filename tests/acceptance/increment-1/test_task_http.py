"""In-process HTTP coverage for the public task-management boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from support.acceptance import accept_pending_commands
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.workflow import Workflow, WorkflowGraph
from ctower_kernel.workflow.postgres import PostgresWorkflow

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[3]
HTTP_OK = 200
HTTP_PENDING = 202
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE_ENTITY = 422


@dataclass(frozen=True, slots=True)
class _TaskTrace:
    priority: Response
    assigned: Response
    assignments: Response
    deferred: Response
    admitted: Response
    blocked: Response
    board: Response
    unblocked: Response
    related: Response
    refused_reopen: Response
    audit: Response
    invalid_board: Response


def test_task_http_routes_preserve_typed_work_board_and_audit_facts(
    tenant: TenantFixture,
) -> None:
    with TestClient(_app(tenant)) as client:
        ticket_id = _create_ticket(client, tenant)
        _start_and_admit(client, tenant, ticket_id)
        trace = _exercise_task_routes(client, tenant, ticket_id)

    successful = (
        trace.priority,
        trace.assigned,
        trace.assignments,
        trace.deferred,
        trace.admitted,
        trace.blocked,
        trace.board,
        trace.unblocked,
        trace.related,
        trace.audit,
    )
    assert [response.status_code for response in successful] == [
        HTTP_PENDING,
        HTTP_PENDING,
        HTTP_OK,
        HTTP_PENDING,
        HTTP_PENDING,
        HTTP_PENDING,
        HTTP_OK,
        HTTP_PENDING,
        HTTP_PENDING,
        HTTP_OK,
    ]
    assert trace.assignments.json()["assignments"][0]["principal_id"] == str(tenant.operator_id)
    assert trace.board.json()["health"] == "CURRENT"
    assert trace.board.json()["cards"][0]["lane"] == "blocked"
    assert trace.board.json()["cards"][0]["underlying_lane"] == "ready"
    assert (trace.refused_reopen.status_code, trace.refused_reopen.json()["code"]) == (
        HTTP_CONFLICT,
        "work-reopen-unmet",
    )
    assert {event["kind"] for event in trace.audit.json()["events"]} >= {
        "ticket.created",
        "work.changed",
        "workflow.changed",
    }
    assert (trace.invalid_board.status_code, trace.invalid_board.json()["code"]) == (
        HTTP_UNPROCESSABLE_ENTITY,
        "validation-error",
    )


def _exercise_task_routes(client: TestClient, tenant: TenantFixture, ticket_id: UUID) -> _TaskTrace:
    blocker_id = uuid4()
    priority = _post(
        client,
        tenant,
        ticket_id,
        "priority",
        {"expected_version": 2, "priority": "P2", "reason": "Queue ordering changed"},
    )
    assigned = _post(client, tenant, ticket_id, "assignments", _assignment(tenant))
    assignments = client.get(
        f"/v1/tickets/{ticket_id}/assignments", headers=_headers(tenant, ticket_id)
    )
    deferred = _post(client, tenant, ticket_id, "intents", _defer())
    admitted = _post(client, tenant, ticket_id, "intents", _admit())
    blocked = _post(client, tenant, ticket_id, "intents", _block(tenant, blocker_id))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
    board = _read_blocked_board(client, tenant)
    unblocked = _post(client, tenant, ticket_id, "intents", _unblock(blocker_id))
    target_id = _create_ticket(client, tenant)
    related = _post(client, tenant, ticket_id, "relations", _relation(target_id))
    refused_reopen = _post(client, tenant, ticket_id, "intents", _reopen())
    audit = client.get(
        f"/v1/tickets/{ticket_id}/audit",
        params={"cursor": 0, "limit": 100},
        headers=_headers(tenant, ticket_id),
    )
    invalid_board = client.get("/v1/board", params={"priority": "P9"}, headers=_headers(tenant))
    return _TaskTrace(
        priority,
        assigned,
        assignments,
        deferred,
        admitted,
        blocked,
        board,
        unblocked,
        related,
        refused_reopen,
        audit,
        invalid_board,
    )


def _read_blocked_board(client: TestClient, tenant: TenantFixture) -> Response:
    return cast(
        Response,
        client.get(
            "/v1/board",
            params={
                "lane": "blocked",
                "priority": "P2",
                "stage_key": "capture",
                "custodian_id": str(tenant.commander_id),
                "assignee_id": str(tenant.operator_id),
            },
            headers=_headers(tenant),
        ),
    )


def _assignment(tenant: TenantFixture) -> dict[str, object]:
    return {
        "assignment_kind": "current_assignee",
        "expected_version": 3,
        "reason": "Operator owns execution",
        "to_principal_id": str(tenant.operator_id),
    }


def _defer() -> dict[str, object]:
    return {
        "intent": {
            "kind": "defer",
            "expected_version": 4,
            "reason": "Wait for the review window",
            "review_after": "2026-07-22T08:00:00Z",
        }
    }


def _admit() -> dict[str, object]:
    return {"intent": {"kind": "admit", "expected_version": 5, "reason": "Resume work"}}


def _block(tenant: TenantFixture, blocker_id: UUID) -> dict[str, object]:
    return {
        "intent": {
            "kind": "block",
            "expected_version": 6,
            "reason": "Dependency unavailable",
            "blocker_id": str(blocker_id),
            "blocker_kind": "dependency",
            "reason_class": "external_dependency",
            "owner_principal_id": str(tenant.commander_id),
            "source_ref": "test:http-blocker",
            "affected_stage": "capture",
            "resolution_condition": "Dependency is restored",
            "next_check_at": "2026-07-22T09:00:00Z",
            "dependency_ref": "ticket:dependency",
            "board_impact": True,
        }
    }


def _unblock(blocker_id: UUID) -> dict[str, object]:
    return {
        "intent": {
            "kind": "unblock",
            "expected_version": 7,
            "reason": "Dependency restored",
            "blocker_id": str(blocker_id),
            "resolution_evidence_ref": "proof:dependency",
        }
    }


def _relation(target_id: UUID) -> dict[str, object]:
    return {
        "expected_version": 8,
        "reason": "Target supplies a prerequisite",
        "relation_kind": "depends_on",
        "target_ticket_id": str(target_id),
    }


def _reopen() -> dict[str, object]:
    return {
        "intent": {
            "kind": "reopen",
            "expected_version": 9,
            "reason": "Still active",
            "priority_policy": "carry_forward",
        }
    }


def _create_ticket(client: TestClient, tenant: TenantFixture) -> UUID:
    response = client.post(
        "/v1/tickets",
        json={
            "initial_custodian_id": str(tenant.commander_id),
            "priority": "P1",
            "source": {"kind": "test", "ref": f"test:task-http:{uuid4()}"},
            "title": "Task HTTP behavior",
        },
        headers=_headers(tenant),
    )
    assert response.status_code == HTTP_PENDING
    return UUID(cast(str, response.json()["ticket"]["ticket_id"]))


def _start_and_admit(client: TestClient, tenant: TenantFixture, ticket_id: UUID) -> None:
    graph = WorkflowGraph.from_mapping(
        json.loads(
            (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    started = _post(
        client,
        tenant,
        ticket_id,
        "workflow/start",
        {
            "workflow_ref": graph.reference,
            "workflow_digest": graph.digest,
            "execution_policy_ref": "ctower.trust-spine-four-stage.execution@1",
            "execution_policy_digest": _digest(
                "packs/policies/execution/trust-spine-four-stage-v1.yaml"
            ),
            "gate_policy_ref": "ctower.trust-spine-four-stage.gates@1",
            "gate_policy_digest": _digest("packs/policies/gates/trust-spine-four-stage-v1.yaml"),
            "evidence_policy_ref": "ctower.trust-spine-four-stage.evidence@1",
            "evidence_policy_digest": _digest(
                "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
            ),
        },
    )
    admitted = _post(
        client,
        tenant,
        ticket_id,
        "intents",
        {"intent": {"kind": "admit", "expected_version": 1, "reason": "Ready"}},
    )
    assert (started.status_code, admitted.status_code) == (HTTP_PENDING, HTTP_PENDING)


def _post(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    route: str,
    payload: dict[str, object],
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/{route}",
            json=payload,
            headers=_headers(tenant, ticket_id),
        ),
    )


def _headers(tenant: TenantFixture, ticket_id: UUID | None = None) -> dict[str, str]:
    command_id = uuid4()
    return {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id, ticket_id=ticket_id),
    }


def _app(tenant: TenantFixture) -> FastAPI:
    runtime_dsn = tenant.database.runtime_dsn
    proof_store = PostgresProof(runtime_dsn)
    work_store = PostgresWork(runtime_dsn)
    workflow_store = PostgresWorkflow(
        runtime_dsn, proof_gate=proof_store, readiness_gate=work_store
    )
    graph = WorkflowGraph.from_mapping(
        json.loads(
            (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    record = PostgresRecord(runtime_dsn)
    return create_app(
        record,
        workflow=Workflow(
            (graph,),
            writer=workflow_store,
            policy_digests={
                "ctower.trust-spine-four-stage.execution@1": _digest(
                    "packs/policies/execution/trust-spine-four-stage-v1.yaml"
                ),
                "ctower.trust-spine-four-stage.gates@1": _digest(
                    "packs/policies/gates/trust-spine-four-stage-v1.yaml"
                ),
                "ctower.trust-spine-four-stage.evidence@1": _digest(
                    "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
                ),
            },
        ),
        work=Work(record, writer=work_store),
        projections=Projections(PostgresProjections(tenant.database.projection_dsn)),
    )


def _digest(relative: str) -> str:
    return f"sha256:{hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()}"

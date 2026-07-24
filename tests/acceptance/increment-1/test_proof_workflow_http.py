"""Public HTTP behavior for the Proof-gated Workflow slice."""

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
from support.server import proof_policy
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.proof import Proof, ProofPolicy
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.record.transaction import authority_connection
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.workflow import Workflow, WorkflowGraph
from ctower_kernel.workflow.postgres import PostgresWorkflow, PostgresWorkflowPolicyPins

__all__: tuple[str, ...] = ()
HTTP_PENDING = 202
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE_ENTITY = 422
FIRST_TRANSITION_VERSION = 2
ROOT = Path(__file__).parents[3]


@dataclass(frozen=True, slots=True)
class _ProofTrace:
    frame: Response
    frozen: Response
    verification: Response
    corrupt: Response
    evidence: Response
    self_review: Response
    verdict: Response


@dataclass(frozen=True, slots=True)
class _CloseTrace:
    premature: Response
    terminal: Response
    closed: Response


def test_criteria_freeze_refuses_a_missing_ticket(tenant: TenantFixture) -> None:
    missing_ticket_id = uuid4()
    command_id = uuid4()

    with TestClient(_app(tenant)) as client:
        response = client.post(
            f"/v1/tickets/{missing_ticket_id}/proof/criteria",
            json={
                "expected_version": 0,
                "candidate_digest": "sha256:" + "a" * 64,
                "criteria": [
                    {
                        "key": "artifact-current",
                        "description": "The artifact matches the reviewed candidate.",
                        "candidate_dependent": True,
                        "requires_verdict": True,
                    }
                ],
            },
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id, ticket_id=missing_ticket_id),
            },
        )

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].partition(";")[0] == "application/problem+json"
    assert response.json()["code"] == "tenant-scope-denied"
    assert response.json()["status"] == HTTP_NOT_FOUND


def test_transition_replay_is_stable_and_changed_reuse_is_refused(
    tenant: TenantFixture,
) -> None:
    command_id = uuid4()
    with TestClient(_app(tenant)) as client:
        ticket_id = _create_ticket(client, tenant)
        _start_and_admit(client, tenant, ticket_id)
        request = {
            "expected_version": 1,
            "workflow_ref": "ctower.trust-spine-four-stage@1",
            "source_stage": "capture",
            "destination_stage": "frame",
        }
        first = client.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json=request,
            headers=_command_headers(tenant.commander_credential, command_id, ticket_id),
        )
        replay = client.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json=request,
            headers=_command_headers(tenant.commander_credential, command_id, ticket_id),
        )
        changed = client.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json={**request, "destination_stage": "verify"},
            headers=_command_headers(tenant.commander_credential, command_id, ticket_id),
        )

    assert first.status_code == HTTP_PENDING
    assert first.json() == replay.json()
    assert first.json()["stage"] == "frame"
    assert first.json()["version"] == FIRST_TRANSITION_VERSION
    assert changed.status_code == HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"


def test_undeclared_transition_is_refused_without_advancing_state(
    tenant: TenantFixture,
) -> None:
    with TestClient(_app(tenant)) as client:
        ticket_id = _create_ticket(client, tenant)
        _start_and_admit(client, tenant, ticket_id)
        refused_id = uuid4()
        refused = client.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json={
                "expected_version": 1,
                "workflow_ref": "ctower.trust-spine-four-stage@1",
                "source_stage": "capture",
                "destination_stage": "verify",
            },
            headers=_command_headers(tenant.commander_credential, refused_id, ticket_id),
        )
        accepted_id = uuid4()
        accepted = client.post(
            f"/v1/tickets/{ticket_id}/workflow/transition",
            json={
                "expected_version": 1,
                "workflow_ref": "ctower.trust-spine-four-stage@1",
                "source_stage": "capture",
                "destination_stage": "frame",
            },
            headers=_command_headers(tenant.commander_credential, accepted_id, ticket_id),
        )

    assert refused.status_code == HTTP_CONFLICT
    assert refused.json()["code"] == "workflow-transition-not-declared"
    assert refused.json()["current_version"] == 1
    assert accepted.status_code == HTTP_PENDING
    assert accepted.json()["stage"] == "frame"
    assert accepted.json()["version"] == FIRST_TRANSITION_VERSION


def test_current_independent_proof_is_required_before_atomic_close(
    tenant: TenantFixture,
) -> None:
    candidate_digest = "sha256:" + "c" * 64
    content = "reviewed artifact"
    artifact_digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    with TestClient(_app(tenant)) as client:
        ticket_id = _create_ticket(client, tenant)
        _start_and_admit(client, tenant, ticket_id)
        proof_trace = _prepare_current_proof(
            client, tenant, ticket_id, candidate_digest, artifact_digest, content
        )
        close_trace = _close_current_proof(client, tenant, ticket_id)

    assert (proof_trace.frame.status_code, proof_trace.frame.json()["stage"]) == (
        HTTP_PENDING,
        "frame",
    )
    assert (proof_trace.frozen.status_code, proof_trace.frozen.json()["version"]) == (
        HTTP_PENDING,
        1,
    )
    assert proof_trace.verification.json()["activity_class"] == "verification"
    assert (proof_trace.corrupt.status_code, proof_trace.corrupt.json()["code"]) == (
        HTTP_CONFLICT,
        "proof-evidence-digest-mismatch",
    )
    assert (proof_trace.evidence.status_code, proof_trace.evidence.json()["version"]) == (
        HTTP_PENDING,
        2,
    )
    assert (proof_trace.self_review.status_code, proof_trace.self_review.json()["code"]) == (
        HTTP_FORBIDDEN,
        "proof-self-review-refused",
    )
    assert (proof_trace.verdict.status_code, proof_trace.verdict.json()["satisfied"]) == (
        HTTP_PENDING,
        True,
    )
    assert (close_trace.premature.status_code, close_trace.premature.json()["code"]) == (
        HTTP_CONFLICT,
        "workflow-not-terminal",
    )
    assert (close_trace.terminal.status_code, close_trace.terminal.json()["stage"]) == (
        HTTP_PENDING,
        "close",
    )
    assert (close_trace.closed.status_code, close_trace.closed.json()["lifecycle_facts"]) == (
        HTTP_PENDING,
        ["resolved", "closed"],
    )


def test_proof_http_boundary_authenticates_before_strict_payload_validation(
    tenant: TenantFixture,
) -> None:
    with TestClient(_app(tenant)) as client:
        unauthorized = client.post(
            "/v1/tickets/not-a-uuid/proof/evidence",
            content=b"{",
        )
        ticket_id = _create_ticket(client, tenant)
        command_id = uuid4()
        malformed = client.post(
            f"/v1/tickets/{ticket_id}/proof/evidence",
            json={
                "expected_version": 1,
                "evidence_id": str(uuid4()),
                "criterion_key": "artifact-current",
                "candidate_digest": "sha256:" + "a" * 64,
                "artifact_digest": "sha256:" + "b" * 64,
                "content": "artifact",
                "unexpected": True,
            },
            headers=_command_headers(tenant.commander_credential, command_id, ticket_id),
        )

    assert unauthorized.status_code == HTTP_UNAUTHORIZED
    assert unauthorized.json()["code"] == "unauthorized"
    assert malformed.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert malformed.json()["code"] == "validation-error"


def test_caller_cannot_weaken_the_pinned_gate_policy(tenant: TenantFixture) -> None:
    candidate_digest = "sha256:" + "d" * 64
    with TestClient(_app(tenant)) as client:
        ticket_id = _create_ticket(client, tenant)
        _start_and_admit(client, tenant, ticket_id)
        weakened = _post_command(
            client,
            tenant.commander_credential,
            ticket_id,
            "proof/criteria",
            {
                "expected_version": 0,
                "candidate_digest": candidate_digest,
                "criteria": [
                    {
                        "key": "artifact-current",
                        "description": "Artifact evidence matches the current candidate.",
                        "candidate_dependent": True,
                        "requires_verdict": False,
                    }
                ],
            },
        )
        exact = _freeze(client, tenant, ticket_id, candidate_digest)

    assert weakened.status_code == HTTP_CONFLICT
    assert weakened.json()["code"] == "proof-criteria-policy-mismatch"
    assert exact.status_code == HTTP_PENDING
    assert exact.json()["version"] == 1


def test_postgres_policy_registration_binds_exact_bytes_to_the_workflow_pin(
    tenant: TenantFixture,
) -> None:
    weakened_store = PostgresProof(
        tenant.database.runtime_dsn,
        policies=(_weakened_proof_policy(),),
        policy_pins=PostgresWorkflowPolicyPins(),
    )
    candidate_digest = "sha256:" + "e" * 64
    content = "exact policy bytes"
    artifact_digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()

    with TestClient(_app(tenant, proof_store=weakened_store)) as client:
        ticket_id = _create_ticket(client, tenant)
        _start_and_admit(client, tenant, ticket_id)
        weakened = _post_command(
            client,
            tenant.commander_credential,
            ticket_id,
            "proof/criteria",
            {
                "expected_version": 0,
                "candidate_digest": candidate_digest,
                "criteria": [
                    {
                        "key": "artifact-current",
                        "description": "Artifact evidence matches the current candidate.",
                        "candidate_dependent": True,
                        "requires_verdict": False,
                    }
                ],
            },
        )

    exact_store = PostgresProof(
        tenant.database.runtime_dsn,
        policies=(proof_policy(),),
        policy_pins=PostgresWorkflowPolicyPins(),
    )
    with TestClient(_app(tenant, proof_store=exact_store)) as client:
        exact = _prepare_current_proof(
            client,
            tenant,
            ticket_id,
            candidate_digest,
            artifact_digest,
            content,
        )

    assert (weakened.status_code, weakened.json()["code"]) == (
        HTTP_CONFLICT,
        "proof-policy-pin-mismatch",
    )
    assert not _is_current(weakened_store, tenant, ticket_id)
    assert (exact.frozen.status_code, exact.frozen.json()["version"]) == (HTTP_PENDING, 1)
    assert (exact.verdict.status_code, exact.verdict.json()["satisfied"]) == (
        HTTP_PENDING,
        True,
    )
    assert _is_current(exact_store, tenant, ticket_id)


def _prepare_current_proof(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    candidate_digest: str,
    artifact_digest: str,
    content: str,
) -> _ProofTrace:
    return _ProofTrace(
        frame=_transition(client, tenant, ticket_id, 1, "capture", "frame"),
        frozen=_freeze(client, tenant, ticket_id, candidate_digest),
        verification=_transition(client, tenant, ticket_id, 2, "frame", "verify"),
        corrupt=_evidence(
            client, tenant, ticket_id, candidate_digest, artifact_digest, "tampered artifact"
        ),
        evidence=_evidence(client, tenant, ticket_id, candidate_digest, artifact_digest, content),
        self_review=_verdict(client, tenant.commander_credential, ticket_id, candidate_digest),
        verdict=_verdict(client, tenant.operator_credential, ticket_id, candidate_digest),
    )


def _close_current_proof(client: TestClient, tenant: TenantFixture, ticket_id: UUID) -> _CloseTrace:
    return _CloseTrace(
        premature=_resolve_close(client, tenant, ticket_id, 3),
        terminal=_transition(client, tenant, ticket_id, 3, "verify", "close"),
        closed=_resolve_close(client, tenant, ticket_id, 4),
    )


def _transition(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    expected_version: int,
    source: str,
    destination: str,
) -> Response:
    return _post_command(
        client,
        tenant.commander_credential,
        ticket_id,
        "workflow/transition",
        {
            "expected_version": expected_version,
            "workflow_ref": "ctower.trust-spine-four-stage@1",
            "source_stage": source,
            "destination_stage": destination,
        },
    )


def _freeze(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    candidate_digest: str,
) -> Response:
    return _post_command(
        client,
        tenant.commander_credential,
        ticket_id,
        "proof/criteria",
        {
            "expected_version": 0,
            "candidate_digest": candidate_digest,
            "criteria": [
                {
                    "key": "artifact-current",
                    "description": "Artifact evidence matches the current candidate.",
                    "candidate_dependent": True,
                    "requires_verdict": True,
                }
            ],
        },
    )


def _evidence(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    candidate_digest: str,
    artifact_digest: str,
    content: str,
) -> Response:
    return _post_command(
        client,
        tenant.commander_credential,
        ticket_id,
        "proof/evidence",
        {
            "expected_version": 1,
            "evidence_id": str(uuid4()),
            "criterion_key": "artifact-current",
            "candidate_digest": candidate_digest,
            "artifact_digest": artifact_digest,
            "content": content,
        },
    )


def _verdict(
    client: TestClient,
    credential: str,
    ticket_id: UUID,
    candidate_digest: str,
) -> Response:
    return _post_command(
        client,
        credential,
        ticket_id,
        "proof/verdict",
        {
            "expected_version": 2,
            "verdict_id": str(uuid4()),
            "criterion_key": "artifact-current",
            "candidate_digest": candidate_digest,
            "decision": "pass",
        },
    )


def _resolve_close(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    expected_version: int,
) -> Response:
    return _post_command(
        client,
        tenant.commander_credential,
        ticket_id,
        "workflow/resolve-close",
        {
            "expected_version": expected_version,
            "workflow_ref": "ctower.trust-spine-four-stage@1",
        },
    )


def _create_ticket(client: TestClient, tenant: TenantFixture) -> UUID:
    command_id = uuid4()
    response = client.post(
        "/v1/tickets",
        json={
            "initial_custodian_id": str(tenant.commander_id),
            "priority": "P1",
            "source": {"kind": "test", "ref": "test:proof-workflow-http"},
            "title": "Proof workflow HTTP behavior",
        },
        headers=_command_headers(tenant.commander_credential, command_id),
    )
    assert response.status_code == HTTP_PENDING
    return UUID(cast(str, response.json()["ticket"]["ticket_id"]))


def _start_and_admit(client: TestClient, tenant: TenantFixture, ticket_id: UUID) -> None:
    graph_payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    graph = WorkflowGraph.from_mapping(graph_payload)
    started = _post_command(
        client,
        tenant.commander_credential,
        ticket_id,
        "workflow/start",
        {
            "workflow_ref": graph.reference,
            "workflow_digest": graph.digest,
            "execution_policy_ref": "ctower.trust-spine-four-stage.execution@1",
            "execution_policy_digest": _file_digest(
                "packs/policies/execution/trust-spine-four-stage-v1.yaml"
            ),
            "gate_policy_ref": "ctower.trust-spine-four-stage.gates@1",
            "gate_policy_digest": _file_digest(
                "packs/policies/gates/trust-spine-four-stage-v1.yaml"
            ),
            "evidence_policy_ref": "ctower.trust-spine-four-stage.evidence@1",
            "evidence_policy_digest": _file_digest(
                "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
            ),
        },
    )
    admitted = _post_command(
        client,
        tenant.commander_credential,
        ticket_id,
        "intents",
        {"intent": {"kind": "admit", "expected_version": 1, "reason": "Ready"}},
    )
    assert (started.status_code, admitted.status_code) == (HTTP_PENDING, HTTP_PENDING)


def _file_digest(relative: str) -> str:
    return f"sha256:{hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()}"


def _weakened_proof_policy() -> ProofPolicy:
    gate_bytes = (ROOT / "packs/policies/gates/trust-spine-four-stage-v1.yaml").read_bytes()
    evidence_bytes = (ROOT / "packs/policies/evidence/trust-spine-four-stage-v1.yaml").read_bytes()
    weakened_gate_bytes = gate_bytes.replace(
        b'"requires_verdict": true',
        b'"requires_verdict": false',
    )
    assert weakened_gate_bytes != gate_bytes
    return ProofPolicy.from_bytes(weakened_gate_bytes, evidence_bytes)


def _is_current(
    store: PostgresProof,
    tenant: TenantFixture,
    ticket_id: UUID,
) -> bool:
    with authority_connection(tenant.database.runtime_dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        return store.is_current(connection, tenant.tenant_id, ticket_id)


def _command_headers(
    credential: str, command_id: UUID, ticket_id: UUID | None = None
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id, ticket_id=ticket_id),
    }


def _post_command(
    client: TestClient,
    credential: str,
    ticket_id: UUID,
    route: str,
    payload: dict[str, object],
) -> Response:
    command_id = uuid4()
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/{route}",
            json=payload,
            headers=_command_headers(credential, command_id, ticket_id),
        ),
    )


def _app(
    tenant: TenantFixture,
    *,
    proof_store: PostgresProof | None = None,
) -> FastAPI:
    runtime_dsn = tenant.database.runtime_dsn
    proof_store = proof_store or PostgresProof(
        runtime_dsn, policies=(proof_policy(),), policy_pins=PostgresWorkflowPolicyPins()
    )
    workflow_store = PostgresWorkflow(
        runtime_dsn, proof_gate=proof_store, readiness_gate=PostgresWork(runtime_dsn)
    )
    graph_payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    record = PostgresRecord(runtime_dsn)
    return create_app(
        record,
        proof=Proof(writer=proof_store),
        workflow=Workflow(
            (WorkflowGraph.from_mapping(graph_payload),),
            writer=workflow_store,
            policy_digests={
                "ctower.trust-spine-four-stage.execution@1": _file_digest(
                    "packs/policies/execution/trust-spine-four-stage-v1.yaml"
                ),
                "ctower.trust-spine-four-stage.gates@1": _file_digest(
                    "packs/policies/gates/trust-spine-four-stage-v1.yaml"
                ),
                "ctower.trust-spine-four-stage.evidence@1": _file_digest(
                    "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
                ),
            },
        ),
        work=Work(record, writer=PostgresWork(runtime_dsn)),
    )

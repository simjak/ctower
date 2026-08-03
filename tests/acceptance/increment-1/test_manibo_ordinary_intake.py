"""Ordinary item-by-item portfolio intake under D30 clause 3's prohibited-class barrier.

CT-I1-011 admits the portfolio backlog one signed command at a time. This suite proves the
barrier that must exist before the first item crosses: every prohibited class refuses by its
exact stable name at the one intake seam and at Evidence recording, a compliant BH.Loop item
is admitted, and refused content reaches no durable byte anywhere in the database.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from support.project_hierarchy import declare_project
from support.server import proof_policy
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.proof import Proof
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.workflow import Workflow, WorkflowGraph
from ctower_kernel.workflow.postgres import PostgresWorkflow, PostgresWorkflowPolicyPins

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
HTTP_PENDING = 202
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_ENTITY = 422
PROHIBITED_CODE = "prohibited-data-class"

# One canary per probe: a token that exists nowhere else, carried inside the prohibited
# content so a durable-byte scan can prove the whole submission was dropped, not just its
# recognized fragment. Each probe also carries the project key such an item really arrives
# under, so the refusal is proven to be the class barrier and not a project-scope accident.
_PROBES: tuple[tuple[str, str, str], ...] = (
    (
        "credential_material",
        "manibo",
        "manibo-canary-1af0 rotate the runner: password = notarealsecret",
    ),
    (
        "production_customer_data",
        "manibo",
        "manibo-canary-2b31 the customer export from the production tenant reproduces it",
    ),
    (
        "phi_hipaa_covered",
        "bh-loop",
        "bhloop-canary-3c42 the patient could not complete the clinical intake form",
    ),
    (
        "pii_beyond_staff_identity",
        "bh-loop",
        "bhloop-canary-4d53 reporter SSN 123-45-6789 was pasted into the issue body",
    ),
    (
        "live_incident_indicator",
        "ctower",
        "ctower-canary-5e64 SEV-1 declared on the ingest path, still an active incident",
    ),
)

# What D30 keeps allowed for BH.Loop: D11 control references, GitHub/GitLab artifact IDs,
# and de-identified control IDs — and nothing about a patient.
_COMPLIANT_BH_LOOP = (
    "Refs D11-CTL-0091 control coverage. Mirrors jakit-labs/bh-loop#412 and "
    "gitlab nfq-technologies/apps/call-center#118. Artifact sha256:" + "a" * 64 + ". "
    "De-identified control ID BHL-CTL-0091 is the only identity carried."
)


@pytest.fixture(autouse=True)
def declared_projects(tenant: TenantFixture) -> None:
    for project_key in ("ctower", "manibo", "bh-loop"):
        declare_project(tenant, project_key)


@pytest.mark.parametrize(("prohibited_class", "project_key", "content"), _PROBES)
def test_ordinary_intake_refuses_every_prohibited_class_by_its_exact_name(
    tenant: TenantFixture,
    prohibited_class: str,
    project_key: str,
    content: str,
) -> None:
    command_id = uuid4()

    with _client(tenant) as client:
        response = _submit(
            client, tenant, _intake_body(tenant, content, project_key=project_key), command_id
        )

    problem = cast(dict[str, object], response.json())
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert response.headers["content-type"].partition(";")[0] == "application/problem+json"
    assert problem["code"] == PROHIBITED_CODE
    assert problem["prohibited_classes"] == [prohibited_class]
    assert problem["command_id"] == str(command_id)
    assert _authority_counts(tenant) == (0, 0, 0, 0)
    assert _durable_occurrences(tenant, content.split(" ", 1)[0]) == ()


def test_a_phi_shaped_bh_loop_item_refuses_while_the_compliant_one_is_admitted(
    tenant: TenantFixture,
) -> None:
    phi_content = (
        "bh-loop control D11-CTL-0091 failed for the patient whose clinical notes "
        "were exported: MRN 88213, ICD-10 F41.1."
    )

    with _client(tenant) as client:
        refused = _submit(
            client,
            tenant,
            _intake_body(tenant, phi_content, project_key="bh-loop"),
            uuid4(),
        )
        admitted = _submit(
            client,
            tenant,
            _intake_body(tenant, _COMPLIANT_BH_LOOP),
            uuid4(),
        )
        project_gated = _submit(
            client,
            tenant,
            _intake_body(tenant, _COMPLIANT_BH_LOOP, project_key="bh-loop"),
            uuid4(),
        )

    # The class barrier decides before project scope does: a PHI item is refused by name,
    # never by the roster refusal that would otherwise hide why it was rejected.
    assert refused.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert refused.json()["code"] == PROHIBITED_CODE
    assert refused.json()["prohibited_classes"] == ["phi_hipaa_covered"]
    assert admitted.status_code == HTTP_PENDING
    assert admitted.json()["outcome"] == "ticket_created"
    # A compliant item carries no class, so the only thing still refusing it under the
    # `bh-loop` key is the project roster literal that CT-I1-011's first prerequisite (#197)
    # removes — a separate gate, named separately.
    assert project_gated.status_code == HTTP_NOT_FOUND
    assert project_gated.json()["code"] == "tenant-scope-denied"
    assert _authority_counts(tenant) == (1, 1, 1, 1)
    assert _durable_occurrences(tenant, "MRN 88213") == ()


def test_refused_content_never_reaches_a_durable_byte_on_any_intake_path(
    tenant: TenantFixture,
) -> None:
    quarantine_canary = f"quarantine-canary-{uuid4().hex}"
    promotion_canary = f"promotion-canary-{uuid4().hex}"

    with _client(tenant) as client:
        discussion = _submit(client, tenant, _discussion("Ordinary discussion"), uuid4()).json()
        quarantined = _submit(
            client,
            tenant,
            {
                **_discussion(f"{quarantine_canary} patient chart attached"),
                "taint": "quarantine_required",
            },
            uuid4(),
        )
        promotion = _promote(
            client,
            tenant,
            UUID(str(discussion["inbound_event_id"])),
            {
                "expected_thread_version": 1,
                "initial_custodian_id": str(tenant.commander_id),
                "intent": "create_ticket",
                "priority": "P2",
                "title": f"{promotion_canary} SEV-1 active incident",
            },
            uuid4(),
        )

    assert quarantined.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert quarantined.json()["prohibited_classes"] == ["phi_hipaa_covered"]
    assert promotion.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert promotion.json()["prohibited_classes"] == ["live_incident_indicator"]
    # The ordinary discussion is the control: one thread, one event, no ticket from either refusal.
    assert _authority_counts(tenant) == (1, 1, 1, 0)
    for canary in (quarantine_canary, promotion_canary):
        assert _durable_occurrences(tenant, canary) == ()


def test_evidence_recording_refuses_a_prohibited_class_and_then_accepts_the_compliant_artifact(
    tenant: TenantFixture,
) -> None:
    candidate_digest = "sha256:" + "c" * 64
    prohibited = f"evidence-canary-{uuid4().hex}: patient MRN 88213 in the attached export"

    with _client(tenant) as client:
        ticket_id = _create_ticket(client, tenant)
        _start_and_admit(client, tenant, ticket_id)
        _transition(client, tenant, ticket_id, 1, "capture", "frame")
        frozen = _freeze(client, tenant, ticket_id, candidate_digest)
        _transition(client, tenant, ticket_id, 2, "frame", "verify")
        refused = _evidence(client, tenant, ticket_id, candidate_digest, prohibited)
        accepted = _evidence(client, tenant, ticket_id, candidate_digest, _COMPLIANT_BH_LOOP)

    assert frozen.status_code == HTTP_PENDING
    assert refused.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert refused.json()["code"] == PROHIBITED_CODE
    assert refused.json()["prohibited_classes"] == ["phi_hipaa_covered"]
    assert accepted.status_code == HTTP_PENDING
    assert _durable_occurrences(tenant, prohibited.split(":", 1)[0]) == ()
    assert _evidence_digests(tenant, ticket_id) == (
        hashlib.sha256(_COMPLIANT_BH_LOOP.encode()).hexdigest(),
    )


def _client(tenant: TenantFixture) -> TestClient:
    return TestClient(_app(tenant), client=("127.0.0.1", 51000))


def _app(tenant: TenantFixture) -> FastAPI:
    """Compose the authored I1 surface so intake and Evidence share one running seam."""

    runtime_dsn = tenant.database.runtime_dsn
    proof_store = PostgresProof(
        runtime_dsn, policies=(proof_policy(),), policy_pins=PostgresWorkflowPolicyPins()
    )
    record = PostgresRecord(runtime_dsn)
    return create_app(
        record,
        proof=Proof(writer=proof_store),
        workflow=Workflow(
            (_workflow_graph(),),
            writer=PostgresWorkflow(
                runtime_dsn, proof_gate=proof_store, readiness_gate=PostgresWork(runtime_dsn)
            ),
            policy_digests={
                f"ctower.trust-spine-four-stage.{name}@1": _policy_digest(name)
                for name in ("execution", "gates", "evidence")
            },
        ),
        work=Work(record, writer=PostgresWork(runtime_dsn)),
    )


def _policy_digest(name: str) -> str:
    payload = (ROOT / f"packs/policies/{name}/trust-spine-four-stage-v1.yaml").read_bytes()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _workflow_graph() -> WorkflowGraph:
    payload = (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(
        encoding="utf-8"
    )
    return WorkflowGraph.from_mapping(json.loads(payload))


def _start_and_admit(client: TestClient, tenant: TenantFixture, ticket_id: UUID) -> None:
    graph = _workflow_graph()
    started = _post_command(
        client,
        tenant,
        ticket_id,
        "workflow/start",
        {
            "workflow_ref": graph.reference,
            "workflow_digest": graph.digest,
            "execution_policy_ref": "ctower.trust-spine-four-stage.execution@1",
            "execution_policy_digest": _policy_digest("execution"),
            "gate_policy_ref": "ctower.trust-spine-four-stage.gates@1",
            "gate_policy_digest": _policy_digest("gates"),
            "evidence_policy_ref": "ctower.trust-spine-four-stage.evidence@1",
            "evidence_policy_digest": _policy_digest("evidence"),
        },
    )
    admitted = _post_command(
        client,
        tenant,
        ticket_id,
        "intents",
        {"intent": {"kind": "admit", "expected_version": 1, "reason": "Ready"}},
    )
    assert (started.status_code, admitted.status_code) == (HTTP_PENDING, HTTP_PENDING)


def _transition(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    expected_version: int,
    source: str,
    destination: str,
) -> None:
    response = _post_command(
        client,
        tenant,
        ticket_id,
        "workflow/transition",
        {
            "expected_version": expected_version,
            "workflow_ref": "ctower.trust-spine-four-stage@1",
            "source_stage": source,
            "destination_stage": destination,
        },
    )
    assert response.status_code == HTTP_PENDING, response.json()


def _submit(
    client: TestClient,
    tenant: TenantFixture,
    body: dict[str, object],
    command_id: UUID,
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/intake",
            json=body,
            headers=_headers(tenant, command_id),
        ),
    )


def _promote(
    client: TestClient,
    tenant: TenantFixture,
    inbound_event_id: UUID,
    body: dict[str, object],
    command_id: UUID,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/intake/events/{inbound_event_id}/promotion",
            json=body,
            headers=_headers(tenant, command_id),
        ),
    )


def _create_ticket(client: TestClient, tenant: TenantFixture) -> UUID:
    command_id = uuid4()
    response = client.post(
        "/v1/tickets",
        json={
            "initial_custodian_id": str(tenant.commander_id),
            "priority": "P2",
            "source": {"kind": "github-issue", "ref": f"jakit-labs/bh-loop#{uuid4().int % 1000}"},
            "title": "Portfolio evidence boundary",
        },
        headers=_headers(tenant, command_id),
    )
    assert response.status_code == HTTP_PENDING
    return UUID(cast(str, response.json()["ticket"]["ticket_id"]))


def _freeze(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    candidate_digest: str,
) -> Response:
    return _post_command(
        client,
        tenant,
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
    content: str,
) -> Response:
    return _post_command(
        client,
        tenant,
        ticket_id,
        "proof/evidence",
        {
            "expected_version": 1,
            "evidence_id": str(uuid4()),
            "criterion_key": "artifact-current",
            "candidate_digest": candidate_digest,
            "artifact_digest": "sha256:" + hashlib.sha256(content.encode()).hexdigest(),
            "content": content,
        },
    )


def _post_command(
    client: TestClient,
    tenant: TenantFixture,
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
            headers=_headers(tenant, command_id, ticket_id),
        ),
    )


def _headers(
    tenant: TenantFixture, command_id: UUID, ticket_id: UUID | None = None
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id, ticket_id=ticket_id),
    }


def _discussion(content: str, *, project_key: str = "ctower") -> dict[str, object]:
    return {
        "content": content,
        "project_key": project_key,
        "source": {"kind": "github-issue", "ref": f"jakit-labs/manibo#{uuid4().int % 100000}"},
    }


def _intake_body(
    tenant: TenantFixture,
    content: str,
    *,
    project_key: str = "ctower",
) -> dict[str, object]:
    """Build exactly the per-item submission the backfill plan §3 maps an issue onto."""

    return {
        **_discussion(content, project_key=project_key),
        "initial_custodian_id": str(tenant.commander_id),
        "intent": "create_ticket",
        "priority": "P2",
        "title": "Portfolio backlog item",
    }


def _authority_counts(tenant: TenantFixture) -> tuple[int, int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM inbound_threads WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_events WHERE tenant_id = %s),
              (SELECT count(*) FROM inbound_source_aliases WHERE tenant_id = %s),
              (SELECT count(*) FROM tickets WHERE tenant_id = %s)
            """,
            (tenant.tenant_id,) * 4,
        ).fetchone()
    if row is None:
        raise RuntimeError("authority count query returned no row")
    return cast(tuple[int, int, int, int], row)


def _evidence_digests(tenant: TenantFixture, ticket_id: UUID) -> tuple[str, ...]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT encode(evidence.artifact_digest, 'hex')
            FROM proof_evidence AS evidence
            JOIN proof_bundles AS bundle
              ON bundle.proof_id = evidence.proof_id AND bundle.tenant_id = evidence.tenant_id
            WHERE evidence.tenant_id = %s AND bundle.ticket_id = %s
            ORDER BY 1
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _durable_occurrences(tenant: TenantFixture, needle: str) -> tuple[str, ...]:
    """Search every textual and JSON column in the database for one refused fragment."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name FROM information_schema.columns
            WHERE table_schema = 'public'
              AND data_type IN ('text', 'character varying', 'json', 'jsonb')
            ORDER BY table_name, column_name
            """
        ).fetchall()
        found = []
        for table_name, column_name in columns:
            hits = connection.execute(
                f'SELECT count(*) FROM public."{table_name}" '  # noqa: S608 - catalog identifiers
                f'WHERE "{column_name}"::text LIKE %s',
                (f"%{needle}%",),
            ).fetchone()
            if hits is not None and int(cast(int, hits[0])) > 0:
                found.append(f"{table_name}.{column_name}")
    return tuple(found)

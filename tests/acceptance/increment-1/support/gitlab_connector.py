"""Shared real-PostgreSQL GitLab connector fixtures and proof-close setup."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import rfc8785
from psycopg.rows import dict_row
from support.catalog import (
    FileSchemas,
    MemoryObjectStore,
    actor_for,
    minimal_bundle,
    telemetry_for,
)
from support.server import fixture_proof_policy, fixture_proof_store
from support.tenant_fixture import TenantFixture

from ctower_api.connectors.gitlab import GitLabIssueConnector, GitLabRuntimeRegistration
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.catalog import CatalogProblem, CompanyBundle, CompanyBundleApply, PostgresCatalog
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import IssueConnectorService
from ctower_kernel.integrations.postgres import PostgresConnectorStore
from ctower_kernel.proof import (
    Criterion,
    FreezeCriteria,
    Proof,
    ProofActor,
    ProofMutation,
    ProofReceipt,
    RecordEvidence,
    RecordVerdict,
    VerdictDecision,
)
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Intake
from ctower_kernel.workflow import (
    ActivityClass,
    ResolveClose,
    Stage,
    Transition,
    Workflow,
    WorkflowActor,
    WorkflowGraph,
    WorkflowMutation,
    WorkflowReceipt,
    WorkflowStart,
)
from ctower_kernel.workflow.postgres import PostgresWorkflow

__all__ = [
    "Clock",
    "ProviderFixture",
    "activate_catalog_configuration",
    "activate_two_connector_configurations",
    "connector_service",
    "integration_payload",
    "proof_gate_close",
]

_INTEGRATION_KEY = "gitlab.feedback"
_PROJECT_ID = 42
_ISSUE_IID = 7


class _AlwaysReady:
    def unmet_facts(
        self,
        _connection: psycopg.Connection[dict[str, object]],
        _tenant_id: UUID,
        _ticket_id: UUID,
    ) -> tuple[str, ...]:
        return ()


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class ProviderFixture:
    def __init__(self, *, project_id: int = _PROJECT_ID, issue_iid: int = _ISSUE_IID) -> None:
        self.project_id = project_id
        self.issue_iid = issue_iid
        self.issue: dict[str, object] = {
            "project_id": project_id,
            "iid": issue_iid,
            "title": "Feedback title",
            "description": "Feedback body",
            "labels": ["bug", "feedback"],
            "author": {"username": "reporter", "name": "Report Person"},
            "state": "opened",
            "web_url": f"https://gitlab.example.test/group/project/-/issues/{issue_iid}",
            "updated_at": "2026-08-08T08:01:00Z",
        }
        self.notes: list[str] = []
        self.issue_list_calls = 0
        self.note_posts = 0
        self.close_puts = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/issues"):
            self.issue_list_calls += 1
            updated_after = datetime.fromisoformat(request.url.params["updated_after"])
            issue_updated_at = datetime.fromisoformat(str(self.issue["updated_at"]))
            payload = [self.issue] if issue_updated_at > updated_after else []
            return httpx.Response(200, request=request, json=payload)
        if request.method == "GET" and request.url.path.endswith("/notes"):
            return httpx.Response(200, json=[{"body": body} for body in reversed(self.notes)])
        if request.method == "POST" and request.url.path.endswith("/notes"):
            self.note_posts += 1
            note_payload = cast(dict[str, str], json.loads(request.read()))
            self.notes.append(note_payload["body"])
            return httpx.Response(201, json={"body": note_payload["body"]})
        if request.method == "PUT" and request.url.path.endswith(f"/{self.issue_iid}"):
            self.close_puts += 1
            assert cast(dict[str, str], json.loads(request.read())) == {"state_event": "close"}
            self.issue["state"] = "closed"
            self.issue["updated_at"] = "2026-08-08T08:05:00Z"
            return httpx.Response(200, json=self.issue)
        raise AssertionError(f"unexpected GitLab request {request.method} {request.url}")


def activate_catalog_configuration(tenant: TenantFixture) -> tuple[UUID, str]:
    payload = integration_payload(tenant.commander_id)
    _activate_payloads(tenant, (payload,))
    revision_id, digest = _revision_identity(tenant, payload)
    return revision_id, digest


def activate_two_connector_configurations(
    tenant: TenantFixture,
) -> tuple[GitLabRuntimeRegistration, GitLabRuntimeRegistration]:
    payloads = (
        integration_payload(
            tenant.commander_id,
            key="gitlab.feedback-a",
            project_id=42,
            credential_reference="GITLAB_FEEDBACK_A_TOKEN",
        ),
        integration_payload(
            tenant.commander_id,
            key="gitlab.feedback-b",
            project_id=84,
            credential_reference="GITLAB_FEEDBACK_B_TOKEN",
        ),
    )
    _activate_payloads(tenant, payloads)
    runtimes = tuple(_runtime_registration(tenant, payload) for payload in payloads)
    return runtimes[0], runtimes[1]


def _activate_payloads(
    tenant: TenantFixture,
    payloads: tuple[dict[str, JsonValue], ...],
) -> None:
    raw_bundle = cast(dict[str, JsonValue], json.loads(minimal_bundle().model_dump_json()))
    resources = cast(list[JsonValue], raw_bundle["resources"])
    resources.extend(
        _resource(
            kind="integration",
            key=str(payload["key"]),
            schema_ref="ctower.integration/v2",
            payload=payload,
        )
        for payload in payloads
    )
    resources.append(_label_vocabulary())
    secret_refs = cast(list[JsonValue], raw_bundle["secret_binding_refs"])
    secret_refs.extend(
        {"name": str(payload["token_binding"]), "reference_class": "runtime-binding"}
        for payload in payloads
    )
    bundle = CompanyBundle.model_validate_json(json.dumps(raw_bundle))
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
    )
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem)
    command_id = uuid4()
    result = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=bundle,
            expected_active_version=0,
            plan_digest=plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, command_id),
    )
    assert not isinstance(result, CatalogProblem)


def _label_vocabulary() -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "schema": "ctower.label-vocabulary/v1",
        "key": "board.ticket-labels",
        "display_name": "Ticket labels",
        "members": [{"key": "security", "label": "Security"}],
    }
    return _resource(
        kind="label_vocabulary",
        key="board.ticket-labels",
        schema_ref="ctower.label-vocabulary/v1",
        payload=payload,
    )


def _runtime_registration(
    tenant: TenantFixture, payload: dict[str, JsonValue]
) -> GitLabRuntimeRegistration:
    revision_id, digest = _revision_identity(tenant, payload)
    return GitLabRuntimeRegistration.from_catalog(
        payload,
        revision_id=revision_id,
        revision_digest=digest,
    )


def _revision_identity(tenant: TenantFixture, payload: dict[str, JsonValue]) -> tuple[UUID, str]:
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT revision.component_revision_id
            FROM catalog_component_revisions AS revision
            JOIN catalog_components AS component
              ON component.component_id = revision.component_id
             AND component.tenant_id = revision.tenant_id
            WHERE revision.tenant_id = %s AND component.kind = 'integration'
              AND component.component_key = %s AND revision.content_digest = %s
            """,
            (
                tenant.tenant_id,
                payload["key"],
                bytes.fromhex(digest.removeprefix("sha256:")),
            ),
        ).fetchone()
    assert row is not None
    return cast(UUID, row["component_revision_id"]), digest


def integration_payload(
    commander_id: UUID,
    *,
    key: str = _INTEGRATION_KEY,
    project_id: int = _PROJECT_ID,
    credential_reference: str = "GITLAB_FEEDBACK_TOKEN",
) -> dict[str, JsonValue]:
    return {
        "schema": "ctower.integration/v2",
        "key": key,
        "adapter": "gitlab-issues",
        "authority": "co_source",
        "execution": "standing_sync",
        "gitlab": {
            "base_url": "https://gitlab.example.test",
            "project_id": project_id,
            "import_updated_after": "2026-08-08T08:00:00Z",
            "page_size": 50,
            "poll_interval_seconds": 60,
        },
        "ctower": {"project_key": "ctower", "initial_custodian_id": str(commander_id)},
        "label_map": [{"gitlab": "bug", "ctower": "security"}],
        "token_binding": credential_reference,
    }


def connector_service(
    tenant: TenantFixture,
    runtime: GitLabRuntimeRegistration,
    provider: ProviderFixture,
    record: PostgresRecord,
    store: PostgresConnectorStore,
    clock: Clock,
) -> IssueConnectorService:
    connector = GitLabIssueConnector(
        runtime.config,
        token=str(uuid4()),
        client=httpx.Client(transport=httpx.MockTransport(provider.handle)),
    )
    return IssueConnectorService(
        connector,
        store,
        Intake(record),
        record,
        record.event_audit,
        BoardContextFacts(PostgresBoardContextFacts(tenant.database.runtime_dsn)),
        clock=clock,
    )


def _resource(
    *, kind: str, key: str, schema_ref: str, payload: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": kind,
            "key": key,
            "scope": {"tenant": "ctower", "project": None},
            "revision": 1,
            "content_digest": digest,
            "schema_ref": schema_ref,
            "lifecycle": "published",
            "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
            "provenance": [
                {
                    "kind": "reviewed-contract",
                    "source": "SPEC#gitlab-feedback-ingestion",
                    "digest": digest,
                }
            ],
            "payload_ref": "object:" + digest,
        },
        "payload": payload,
    }


def proof_gate_close(tenant: TenantFixture, ticket_id: UUID) -> UUID:
    criterion = Criterion(
        key="current",
        description="Evidence is current.",
        candidate_dependent=True,
        requires_verdict=True,
    )
    policy = fixture_proof_policy("fixture.gitlab-close@1", criterion)
    proof_store = fixture_proof_store(tenant.database.runtime_dsn, policy)
    graph = _gitlab_close_graph()
    workflow = Workflow(
        (graph,),
        writer=PostgresWorkflow(
            tenant.database.runtime_dsn,
            proof_gate=proof_store,
            readiness_gate=_AlwaysReady(),
        ),
        policy_digests={
            "fixture.execution@1": "sha256:" + "1" * 64,
            policy.gate_policy_ref: policy.gate_policy_digest,
            policy.evidence_policy_ref: policy.evidence_policy_digest,
        },
    )
    actor = WorkflowActor(tenant.commander_id, tenant.tenant_id)
    started = workflow.start(
        actor,
        WorkflowStart(
            uuid4(),
            ticket_id,
            graph.reference,
            graph.digest,
            "fixture.execution@1",
            "sha256:" + "1" * 64,
            policy.gate_policy_ref,
            policy.gate_policy_digest,
            policy.evidence_policy_ref,
            policy.evidence_policy_digest,
        ),
        telemetry=_telemetry(),
    )
    moved = workflow.advance(
        actor,
        WorkflowMutation(uuid4(), ticket_id, graph.reference, 1, "start", "terminal"),
        telemetry=_telemetry(),
    )
    assert isinstance(started, WorkflowReceipt)
    assert isinstance(moved, WorkflowReceipt)
    _complete_proof(proof_store, tenant, ticket_id)
    close_id = uuid4()
    closed = workflow.resolve_close(
        actor,
        ResolveClose(close_id, ticket_id, graph.reference, 2),
        telemetry=_telemetry(),
    )
    assert isinstance(closed, WorkflowReceipt)
    assert closed.lifecycle_facts == ("resolved", "closed")
    return _recorded_close_event_id(tenant, close_id)


def _gitlab_close_graph() -> WorkflowGraph:
    return WorkflowGraph(
        key="fixture.gitlab-close",
        revision=1,
        initial_stage="start",
        stages=(
            Stage("start", ActivityClass.WORK),
            Stage("terminal", ActivityClass.WORK),
        ),
        transitions=(Transition("start", "terminal", "entry.ready@1"),),
        execution_policy_ref="fixture.execution@1",
        gate_policy_ref="fixture.gates@1",
    )


def _recorded_close_event_id(tenant: TenantFixture, close_id: UUID) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        event = connection.execute(
            """
            SELECT event_id FROM events
            WHERE tenant_id = %s AND client_command_id = %s
              AND kind = 'workflow.changed'
            """,
            (tenant.tenant_id, close_id),
        ).fetchone()
    assert event is not None
    return UUID(str(event["event_id"]))


def _complete_proof(store: PostgresProof, tenant: TenantFixture, ticket_id: UUID) -> None:
    proof = Proof(writer=store)
    author = ProofActor(tenant.commander_id, tenant.tenant_id, "commander")
    reviewer = ProofActor(tenant.operator_id, tenant.tenant_id, "operator")
    candidate = "sha256:" + "a" * 64
    frozen = proof.execute(
        author,
        ProofMutation(
            uuid4(),
            ticket_id,
            0,
            FreezeCriteria(
                candidate,
                author.principal_id,
                (
                    Criterion(
                        key="current",
                        description="Evidence is current.",
                        candidate_dependent=True,
                        requires_verdict=True,
                    ),
                ),
            ),
        ),
        telemetry=_telemetry(),
    )
    content = b"current proof"
    evidence = proof.execute(
        author,
        ProofMutation(
            uuid4(),
            ticket_id,
            1,
            RecordEvidence(
                uuid4(),
                "current",
                candidate,
                "sha256:" + hashlib.sha256(content).hexdigest(),
                content,
            ),
        ),
        telemetry=_telemetry(),
    )
    verdict = proof.execute(
        reviewer,
        ProofMutation(
            uuid4(),
            ticket_id,
            2,
            RecordVerdict(uuid4(), "current", candidate, VerdictDecision.PASSING),
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(frozen, ProofReceipt)
    assert isinstance(evidence, ProofReceipt)
    assert isinstance(verdict, ProofReceipt)


def _telemetry() -> TelemetryContext:
    correlation = uuid4()
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="1" * 32,
        span_id="2" * 16,
        trace_flags=1,
        correlation_id=str(correlation),
        causation_id=str(correlation),
        tenant_id="",
        actor_id="",
        command_id="",
    )

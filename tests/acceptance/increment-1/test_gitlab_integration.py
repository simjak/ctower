"""GitLab issue ingestion and proof-gated close against real ctower persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
import rfc8785
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.catalog import (
    FileSchemas,
    MemoryObjectStore,
    actor_for,
    minimal_bundle,
    telemetry_for,
)
from support.server import fixture_proof_policy, fixture_proof_store
from support.tenant_fixture import TenantFixture

from ctower_api.gitlab_adapter import GitLabHttpAdapter
from ctower_api.gitlab_loop import GitLabRuntimeRevision
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.catalog import CatalogProblem, CompanyBundle, CompanyBundleApply, PostgresCatalog
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import GitLabIssueSync, GitLabSyncError
from ctower_kernel.integrations.postgres import PostgresGitLabIntegrationStore
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
from ctower_kernel.record import Actor, PrincipalKind
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

__all__: tuple[str, ...] = ()

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


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def test_gitlab_issue_roundtrip_preserves_one_custody_chain_and_proof_gated_close(
    tenant: TenantFixture,
) -> None:
    """AC-GL-01/02/03: real DB + real HTTP Adapter over an honest GitLab fixture."""

    revision_id, revision_digest = _activate_catalog_configuration(tenant)
    runtime_revision = GitLabRuntimeRevision.from_catalog(
        _integration_payload(tenant.commander_id),
        revision_id=revision_id,
        revision_digest=revision_digest,
    )
    binding = runtime_revision.binding
    provider = _ProviderFixture()
    client = httpx.Client(transport=httpx.MockTransport(provider.handle))
    adapter = GitLabHttpAdapter(runtime_revision.base_url, token=str(uuid4()), client=client)
    clock = _Clock()
    record = PostgresRecord(tenant.database.runtime_dsn)
    sync = GitLabIssueSync(
        adapter,
        PostgresGitLabIntegrationStore(tenant.database.runtime_dsn),
        Intake(record),
        record,
        record.event_audit,
        BoardContextFacts(PostgresBoardContextFacts(tenant.database.runtime_dsn)),
        clock=clock,
    )
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)

    inactive = sync.tick(commander, replace(binding, revision_id=uuid4()))
    assert not inactive.claimed and provider.issue_list_calls == 0
    first = sync.tick(commander, binding)
    immediate = sync.tick(commander, binding)
    ticket_id = _linked_ticket(tenant)

    assert first.tickets_created == 1 and first.issues_seen == 1
    assert not immediate.claimed and provider.issue_list_calls == 1
    _assert_ingested_mapping(tenant, ticket_id)

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    clock.now += timedelta(seconds=60)
    second = sync.tick(commander, binding)
    assert second.tickets_created == 0
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    provider.issue["description"] = "Feedback body after reporter edit"
    provider.issue["updated_at"] = "2026-08-08T08:04:00Z"
    clock.now += timedelta(seconds=60)
    update = sync.tick(commander, binding)
    assert update.ticket_updates == 1
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    _assert_update_comment(tenant, ticket_id)

    close_event_id = _proof_gate_close(tenant, ticket_id)
    clock.now += timedelta(seconds=60)
    closed = sync.tick(commander, binding)
    no_storm = sync.tick(commander, binding)

    assert closed.closures_delivered == 1
    assert provider.issue["state"] == "closed"
    assert len(provider.notes) == 1
    assert "current-proof gate" in provider.notes[0]
    assert f"ctower-sync:{close_event_id}" in provider.notes[0]
    assert not no_storm.claimed
    assert provider.note_posts == 1 and provider.close_puts == 1
    clock.now += timedelta(seconds=60)
    reflected_close = sync.tick(commander, binding)
    assert reflected_close.ticket_updates == 0 and reflected_close.closures_delivered == 0
    assert provider.note_posts == 1 and provider.close_puts == 1
    _assert_single_custody_and_delivery(tenant, ticket_id, close_event_id)


def test_gitlab_claim_lease_blocks_then_expires_and_fences_the_stale_worker(
    tenant: TenantFixture,
) -> None:
    revision_id, revision_digest = _activate_catalog_configuration(tenant)
    binding = GitLabRuntimeRevision.from_catalog(
        _integration_payload(tenant.commander_id),
        revision_id=revision_id,
        revision_digest=revision_digest,
    ).binding
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    first_store = PostgresGitLabIntegrationStore(tenant.database.runtime_dsn)
    second_store = PostgresGitLabIntegrationStore(tenant.database.runtime_dsn)
    started_at = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    first_claim = first_store.claim(actor, binding, owner_id=uuid4(), now=started_at)
    concurrent = second_store.claim(
        actor,
        binding,
        owner_id=uuid4(),
        now=started_at + binding.poll_interval,
    )

    assert first_claim is not None
    assert concurrent is None
    replacement = second_store.claim(
        actor,
        binding,
        owner_id=uuid4(),
        now=first_claim.expires_at,
    )
    assert replacement is not None
    assert replacement.fence > first_claim.fence
    with pytest.raises(GitLabSyncError, match="stale or unavailable"):
        first_store.complete(
            actor,
            binding,
            first_claim,
            first_claim.cursor,
            now=first_claim.expires_at,
        )
    with pytest.raises(GitLabSyncError, match="stale, expired, or unavailable"):
        first_store.fail(actor, binding, first_claim, now=first_claim.expires_at)


def test_gitlab_failures_persist_an_increasing_retry_delay(tenant: TenantFixture) -> None:
    revision_id, revision_digest = _activate_catalog_configuration(tenant)
    binding = GitLabRuntimeRevision.from_catalog(
        _integration_payload(tenant.commander_id),
        revision_id=revision_id,
        revision_digest=revision_digest,
    ).binding
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    store = PostgresGitLabIntegrationStore(tenant.database.runtime_dsn)
    started_at = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    first_claim = store.claim(actor, binding, owner_id=uuid4(), now=started_at)
    assert first_claim is not None
    store.fail(actor, binding, first_claim, now=started_at)
    first_due, first_failures = _retry_state(tenant)
    first_delay = first_due - started_at
    second_claim = store.claim(actor, binding, owner_id=uuid4(), now=first_due)
    assert second_claim is not None
    store.fail(actor, binding, second_claim, now=first_due)
    second_due, second_failures = _retry_state(tenant)
    second_delay = second_due - first_due

    assert (first_failures, second_failures) == (1, 2)
    assert second_delay > first_delay


class _ProviderFixture:
    def __init__(self) -> None:
        self.issue: dict[str, object] = {
            "project_id": _PROJECT_ID,
            "iid": _ISSUE_IID,
            "title": "Feedback title",
            "description": "Feedback body",
            "labels": ["bug", "feedback"],
            "author": {"username": "reporter", "name": "Report Person"},
            "state": "opened",
            "web_url": "https://gitlab.example.test/group/project/-/issues/7",
            "updated_at": "2026-08-08T08:01:00Z",
        }
        self.notes: list[str] = []
        self.issue_list_calls = 0
        self.note_posts = 0
        self.close_puts = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/issues"):
            self.issue_list_calls += 1
            return httpx.Response(200, json=[self.issue])
        if request.method == "GET" and request.url.path.endswith("/notes"):
            return httpx.Response(200, json=[{"body": body} for body in reversed(self.notes)])
        if request.method == "POST" and request.url.path.endswith("/notes"):
            self.note_posts += 1
            payload = cast(dict[str, str], json.loads(request.read()))
            self.notes.append(payload["body"])
            return httpx.Response(201, json={"body": payload["body"]})
        if request.method == "PUT" and request.url.path.endswith(f"/{_ISSUE_IID}"):
            self.close_puts += 1
            payload = cast(dict[str, str], json.loads(request.read()))
            assert payload == {"state_event": "close"}
            self.issue["state"] = "closed"
            self.issue["updated_at"] = "2026-08-08T08:05:00Z"
            return httpx.Response(200, json=self.issue)
        raise AssertionError(f"unexpected GitLab request {request.method} {request.url}")


def _activate_catalog_configuration(tenant: TenantFixture) -> tuple[UUID, str]:
    integration = _integration_payload(tenant.commander_id)
    integration_resource = _resource(
        kind="integration",
        key=_INTEGRATION_KEY,
        schema_ref="ctower.integration/v2",
        payload=integration,
    )
    labels = _resource(
        kind="label_vocabulary",
        key="board.ticket-labels",
        schema_ref="ctower.label-vocabulary/v1",
        payload={
            "schema": "ctower.label-vocabulary/v1",
            "key": "board.ticket-labels",
            "display_name": "Ticket labels",
            "members": [{"key": "security", "label": "Security"}],
        },
    )
    raw_bundle = cast(dict[str, JsonValue], json.loads(minimal_bundle().model_dump_json()))
    resources = cast(list[JsonValue], raw_bundle["resources"])
    resources.extend((integration_resource, labels))
    secret_refs = cast(list[JsonValue], raw_bundle["secret_binding_refs"])
    secret_refs.append({"name": "GITLAB_FEEDBACK_TOKEN", "reference_class": "runtime-binding"})
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
    digest = cast(
        str,
        cast(dict[str, object], integration_resource["component"])["content_digest"],
    )
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
            (tenant.tenant_id, _INTEGRATION_KEY, bytes.fromhex(digest.removeprefix("sha256:"))),
        ).fetchone()
    assert row is not None
    return cast(UUID, row["component_revision_id"]), digest


def _integration_payload(commander_id: UUID) -> dict[str, JsonValue]:
    return {
        "schema": "ctower.integration/v2",
        "key": _INTEGRATION_KEY,
        "adapter": "gitlab-issues",
        "authority": "co_source",
        "execution": "standing_sync",
        "gitlab": {
            "base_url": "https://gitlab.example.test",
            "project_id": _PROJECT_ID,
            "import_updated_after": "2026-08-08T08:00:00Z",
            "page_size": 50,
            "poll_interval_seconds": 60,
        },
        "ctower": {"project_key": "ctower", "initial_custodian_id": str(commander_id)},
        "label_map": [{"gitlab": "bug", "ctower": "security"}],
        "token_binding": "GITLAB_FEEDBACK_TOKEN",
    }


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


def _linked_ticket(tenant: TenantFixture) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT ticket_id FROM integration_gitlab_issue_links
            WHERE tenant_id = %s AND integration_key = %s
              AND gitlab_project_id = %s AND issue_iid = %s
            """,
            (tenant.tenant_id, _INTEGRATION_KEY, _PROJECT_ID, _ISSUE_IID),
        ).fetchall()
    assert len(rows) == 1
    return cast(UUID, rows[0]["ticket_id"])


def _assert_ingested_mapping(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        ticket = connection.execute(
            """
            SELECT title, source_kind, source_ref FROM tickets
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
        inbound = connection.execute(
            """
            SELECT content FROM inbound_events
            WHERE tenant_id = %s AND source_kind = 'gitlab-issue'
              AND source_ref = 'gitlab:42:7'
            """,
            (tenant.tenant_id,),
        ).fetchone()
        observation = connection.execute(
            """
            SELECT labels, reporter_username, reporter_name FROM
                integration_gitlab_issue_observations
            WHERE tenant_id = %s AND integration_key = %s
            """,
            (tenant.tenant_id, _INTEGRATION_KEY),
        ).fetchone()
    assert ticket == {
        "title": "Feedback title",
        "source_kind": "gitlab-issue",
        "source_ref": "gitlab:42:7",
    }
    assert inbound is not None and "Feedback body" in str(inbound["content"])
    assert inbound is not None and "Report Person (@reporter)" in str(inbound["content"])
    assert observation is not None
    assert observation["labels"] == ["bug", "feedback"]
    assert observation["reporter_username"] == "reporter"
    assert observation["reporter_name"] == "Report Person"


def _assert_update_comment(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT payload->>'body' AS body FROM events
            WHERE tenant_id = %s AND aggregate_id = %s
              AND kind = 'ticket.comment_added'
            ORDER BY sequence
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchall()
    assert len(rows) == 1
    assert "Feedback body after reporter edit" in str(rows[0]["body"])


def _proof_gate_close(tenant: TenantFixture, ticket_id: UUID) -> UUID:
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
        WorkflowMutation(
            uuid4(),
            ticket_id,
            graph.reference,
            1,
            "start",
            "terminal",
        ),
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


def _assert_single_custody_and_delivery(
    tenant: TenantFixture, ticket_id: UUID, event_id: UUID
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM tickets WHERE tenant_id = %s
                    AND source_kind = 'gitlab-issue' AND source_ref = 'gitlab:42:7') AS tickets,
                (SELECT count(*) FROM integration_gitlab_issue_links WHERE tenant_id = %s
                    AND ticket_id = %s) AS links,
                (SELECT count(*) FROM integration_gitlab_close_deliveries WHERE tenant_id = %s
                    AND event_id = %s) AS deliveries
            """,
            (
                tenant.tenant_id,
                tenant.tenant_id,
                ticket_id,
                tenant.tenant_id,
                event_id,
            ),
        ).fetchone()
    assert counts == {"tickets": 1, "links": 1, "deliveries": 1}


def _retry_state(tenant: TenantFixture) -> tuple[datetime, int]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT next_poll_at, consecutive_failures
            FROM integration_gitlab_sync_progress
            WHERE tenant_id = %s AND integration_key = %s
            """,
            (tenant.tenant_id, _INTEGRATION_KEY),
        ).fetchone()
    assert row is not None
    return cast(datetime, row["next_poll_at"]), int(cast(int, row["consecutive_failures"]))


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

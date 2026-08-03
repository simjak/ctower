"""Project Delivery proof-link and seat derivation against a real database."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
import rfc8785
from support.catalog import FileSchemas, MemoryObjectStore, actor_for, telemetry_for
from support.project_delivery_evidence import (
    activate_catalog_revision,
    link_alpha_evidence_assignment,
    seed_stageless_alpha_proof,
    slot_reasons,
)
from support.server import fixture_proof_policy, fixture_proof_store
from support.tenant_fixture import TenantFixture

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.projections import ProjectDeliveryRow, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.proof import (
    ChangeCandidate,
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
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, TicketCommand
from ctower_kernel.record import SourceReference as RecordSourceReference
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.workflow import (
    ActivityClass,
    Stage,
    Transition,
    Workflow,
    WorkflowActor,
    WorkflowGraph,
    WorkflowReceipt,
    WorkflowStart,
)
from ctower_kernel.workflow.postgres import PostgresWorkflow

__all__: tuple[str, ...] = ()

_CANDIDATE = "sha256:" + "a" * 64
_SUCCESSOR_CANDIDATE = "sha256:" + "b" * 64
_WORKFLOW_REF = "fixture.project-delivery-evidence@1"

# One frozen proof bundle carrying more criteria than any single checkpoint configures.
_ALPHA = Criterion(
    key="alpha",
    description="Evidence alone establishes this criterion.",
    candidate_dependent=False,
    requires_verdict=False,
)
_AWAITS_REVIEW = Criterion(
    key="awaits-review",
    description="Evidence is recorded and independent review is still pending.",
    candidate_dependent=False,
    requires_verdict=True,
)
_REJECTED = Criterion(
    key="rejected",
    description="Evidence is recorded and independent review refused it.",
    candidate_dependent=False,
    requires_verdict=True,
)
_SIBLING = Criterion(
    key="sibling-nobody-asked-for",
    description="A criterion of the same ticket that no checkpoint configures.",
    candidate_dependent=False,
    requires_verdict=False,
)
_SUPERSEDED = Criterion(
    key="superseded",
    description="Evidence and verdict are invalidated by a new candidate digest.",
    candidate_dependent=True,
    requires_verdict=True,
)
_BUNDLE_CRITERIA = (_ALPHA, _AWAITS_REVIEW, _REJECTED, _SIBLING, _SUPERSEDED)

# Every checkpoint declares this one criterion through its authored bundle payload, and
# the Catalog stores it with no proof link because the contract cannot express one. It is
# therefore genuinely unestablishable, and every row below carries its honest UNKNOWN.
_DECLARATION = "declaration"

# checkpoint_key -> ordered (exit criterion key, linked proof criterion key, ticket).
# "stageless" names the ticket that has no workflow run, so it has no current stage.
_CHECKPOINT_LINKS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "evidence.alpha": (("link-alpha", "alpha", "linked"),),
    "evidence.pending": (("link-awaits-review", "awaits-review", "linked"),),
    "evidence.refused": (("link-rejected", "rejected", "linked"),),
    "evidence.superseded": (("link-superseded", "superseded", "linked"),),
    "evidence.unfrozen": (("link-never-frozen", "never-frozen", "linked"),),
    "evidence.stageless": (("link-alpha", "alpha", "stageless"),),
    "evidence.collision": (
        ("first-alpha-slot", "alpha", "linked"),
        ("second-alpha-slot", "alpha", "linked"),
    ),
}


def test_slot_denominator_is_exactly_the_configured_links(tenant: TenantFixture) -> None:
    """B2: a checkpoint configuring one link publishes one slot, not the whole bundle."""

    rows = _reconciled_rows(tenant)
    row = rows["evidence.alpha"]

    assert slot_reasons(row) == ("slot_filled:link-alpha", f"slot_unknown:{_DECLARATION}")
    assert (row.qualifying_stage_slots_filled, row.qualifying_stage_slots_required) == (1, 2)
    assert row.qualifying_stage_unfilled_or_unknown_slot_keys == (_DECLARATION,)


def test_evidence_recorded_with_review_pending_is_unfilled_not_unknown(
    tenant: TenantFixture,
) -> None:
    """B3: sources that fully establish a slot never publish UNKNOWN."""

    rows = _reconciled_rows(tenant)
    pending = rows["evidence.pending"]
    refused = rows["evidence.refused"]
    superseded = rows["evidence.superseded"]

    assert slot_reasons(pending) == (
        "slot_unfilled:link-awaits-review",
        f"slot_unknown:{_DECLARATION}",
    )
    assert pending.qualifying_stage_unfilled_or_unknown_slot_keys == (
        _DECLARATION,
        "link-awaits-review",
    )
    assert slot_reasons(refused) == (
        "slot_unfilled:link-rejected",
        f"slot_unknown:{_DECLARATION}",
    )
    assert slot_reasons(superseded) == (
        "slot_unfilled:link-superseded",
        f"slot_unknown:{_DECLARATION}",
    )
    for row in (pending, refused, superseded):
        assert (row.qualifying_stage_slots_filled, row.qualifying_stage_slots_required) == (0, 2)


def test_unestablishable_link_stays_unknown_but_stageless_proof_agrees(
    tenant: TenantFixture,
) -> None:
    """A missing criterion is unknown; an established proof needs no Workflow stage."""

    rows = _reconciled_rows(tenant)
    unfrozen = rows["evidence.unfrozen"]
    stageless = rows["evidence.stageless"]

    assert slot_reasons(unfrozen) == (
        f"slot_unknown:{_DECLARATION}",
        "slot_unknown:link-never-frozen",
    )
    assert slot_reasons(stageless) == (
        "slot_filled:link-alpha",
        f"slot_unknown:{_DECLARATION}",
    )
    assert (unfrozen.qualifying_stage_slots_filled, unfrozen.qualifying_stage_slots_required) == (
        0,
        2,
    )
    assert (stageless.proven_criteria, stageless.qualifying_stage_slots_filled) == (1, 1)


def test_two_exit_criteria_linking_one_proof_key_remain_two_slots(
    tenant: TenantFixture,
) -> None:
    """Issue 177: slot identity is the configured exit-criterion key."""

    collision = _reconciled_rows(tenant)["evidence.collision"]

    assert slot_reasons(collision) == (
        "slot_filled:first-alpha-slot",
        "slot_filled:second-alpha-slot",
        f"slot_unknown:{_DECLARATION}",
    )
    assert (collision.proven_criteria, collision.declared_criteria) == (2, 3)
    assert (collision.qualifying_stage_slots_filled, collision.qualifying_stage_slots_required) == (
        2,
        3,
    )


def test_assigned_unassigned_and_signing_seats_project_from_explicit_facts(
    tenant: TenantFixture,
) -> None:
    """D28 seat truth comes from pins and an Evidence assignment reference."""

    rows = _reconciled_rows(tenant)
    alpha = rows["evidence.alpha"]
    slots = {slot.key: slot for slot in alpha.qualifying_stage_slots}
    linked = slots["link-alpha"]
    declaration = slots[_DECLARATION]

    assert linked.assigned_seat is not None
    assert linked.signing_seat is not None
    assert linked.assigned_seat.key == "maker"
    assert linked.assigned_seat.label == "Maker"
    assert linked.signing_seat.key == "reviewer"
    assert linked.signing_seat.label == "Reviewer"
    assert linked.assigned_seat != linked.signing_seat
    assert declaration.assigned_seat is None
    assert declaration.response_payload()["assigned_seat"] == {"state": "unassigned"}
    assert f"slot_unassigned:{_DECLARATION}" in alpha.derivation_reasons
    assert "slot_assigned_seat:link-alpha:maker" in alpha.derivation_reasons
    assert "slot_signing_seat:link-alpha:reviewer" in alpha.derivation_reasons
    assert any(source.startswith("evidence:") for source in alpha.source_ids)
    assert any(source.startswith("assignment:") for source in alpha.source_ids)

    _activate_catalog_without_maker(tenant)
    _advance_source_cursor(tenant, now=datetime.now(UTC))
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    now = datetime.now(UTC)
    assert projections.reconcile_project_delivery(tenant.tenant_id, now=now) == len(
        _CHECKPOINT_LINKS
    )
    after_removal = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        "ctower",
    )
    assert after_removal is not None
    pinned = next(row for row in after_removal.rows if row.checkpoint_key == "evidence.alpha")
    pinned_slot = next(slot for slot in pinned.qualifying_stage_slots if slot.key == "link-alpha")
    assert pinned_slot.assigned_seat is not None
    assert pinned_slot.assigned_seat.label == "Maker"
    assert projections.rebuild_project_delivery(tenant.tenant_id, now=now) == len(_CHECKPOINT_LINKS)
    rebuilt_view = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        "ctower",
    )
    assert rebuilt_view is not None
    rebuilt = next(row for row in rebuilt_view.rows if row.checkpoint_key == "evidence.alpha")
    assert rebuilt.semantic_digest == pinned.semantic_digest
    assert rebuilt.qualifying_stage_slots == pinned.qualifying_stage_slots
    assert rebuilt.derivation_reasons == pinned.derivation_reasons
    assert rebuilt.source_ids == pinned.source_ids


def test_criterion_proof_coverage_agrees_with_slot_coverage(tenant: TenantFixture) -> None:
    """One predicate: proven/declared and filled/required cannot disagree."""

    rows = _reconciled_rows(tenant)

    for checkpoint_key, row in rows.items():
        filled = sum(reason.startswith("slot_filled:") for reason in slot_reasons(row))
        assert (row.proven_criteria, row.qualifying_stage_slots_filled) == (filled, filled), (
            checkpoint_key
        )
        assert row.declared_criteria == row.qualifying_stage_slots_required, checkpoint_key


def _reconciled_rows(tenant: TenantFixture) -> dict[str, ProjectDeliveryRow]:
    """Build the whole proof landscape, link it, reconcile, and read it back."""

    now = datetime.now(UTC)
    linked_ticket = _ticket(tenant, "linked proof ticket")
    stageless_ticket = _ticket(tenant, "ticket without a workflow run")
    _start_workflow(tenant, linked_ticket)
    _freeze_and_prove(tenant, linked_ticket)
    seed_stageless_alpha_proof(tenant, linked_ticket, stageless_ticket)
    _apply_checkpoints(
        tenant,
        linked=linked_ticket,
        stageless=stageless_ticket,
        now=now,
    )
    link_alpha_evidence_assignment(tenant, linked_ticket)
    _advance_source_cursor(tenant, now=now)

    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    affected = projections.reconcile_project_delivery(tenant.tenant_id, now=now)
    view = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        "ctower",
    )

    assert affected == len(_CHECKPOINT_LINKS)
    assert view is not None
    # A row whose sources are incomplete cannot speak for its slots at all. This
    # landscape is complete by construction, so any source_incomplete reason means the
    # source-integrity derivation itself regressed, and every slot assertion below would
    # otherwise be reading a row that had already given up.
    assert all("source_incomplete" not in row.derivation_reasons for row in view.rows)
    return {row.checkpoint_key: row for row in view.rows}


def _ticket(tenant: TenantFixture, title: str) -> UUID:
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER),
        TicketCommand(
            uuid4(),
            tenant.commander_id,
            "P1",
            "ctower",
            RecordSourceReference("test", f"test:project-delivery-evidence:{uuid4()}"),
            title,
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    return outcome.ticket.ticket_id


def _start_workflow(tenant: TenantFixture, ticket_id: UUID) -> None:
    policy = fixture_proof_policy(_WORKFLOW_REF, *_BUNDLE_CRITERIA)
    store = PostgresWorkflow(
        tenant.database.runtime_dsn,
        proof_gate=fixture_proof_store(tenant.database.runtime_dsn, policy),
        readiness_gate=_AlwaysReady(),
    )
    graph = _graph()
    workflow = Workflow(
        (graph,),
        writer=store,
        policy_digests={
            "fixture.execution@1": "sha256:" + "1" * 64,
            policy.gate_policy_ref: policy.gate_policy_digest,
            policy.evidence_policy_ref: policy.evidence_policy_digest,
        },
    )
    started = workflow.start(
        WorkflowActor(tenant.commander_id, tenant.tenant_id),
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
    assert isinstance(started, WorkflowReceipt), started


def _freeze_and_prove(tenant: TenantFixture, ticket_id: UUID) -> None:
    """Record exactly the proof facts each derived slot state must read back."""

    policy = fixture_proof_policy(_WORKFLOW_REF, *_BUNDLE_CRITERIA)
    proof = Proof(writer=fixture_proof_store(tenant.database.runtime_dsn, policy))
    author = ProofActor(tenant.commander_id, tenant.tenant_id, "commander")
    reviewer = ProofActor(tenant.operator_id, tenant.tenant_id, "operator")
    version = 0
    version = _apply(
        proof,
        author,
        ticket_id,
        version,
        FreezeCriteria(_CANDIDATE, tenant.commander_id, _BUNDLE_CRITERIA),
    )
    for criterion in (_ALPHA, _AWAITS_REVIEW, _REJECTED, _SUPERSEDED):
        content = f"evidence for {criterion.key}".encode()
        version = _apply(
            proof,
            author,
            ticket_id,
            version,
            RecordEvidence(
                uuid4(),
                criterion.key,
                _CANDIDATE if criterion.candidate_dependent else None,
                "sha256:" + hashlib.sha256(content).hexdigest(),
                content,
            ),
        )
    version = _apply(
        proof,
        reviewer,
        ticket_id,
        version,
        RecordVerdict(uuid4(), _REJECTED.key, None, VerdictDecision.FAILING),
    )
    version = _apply(
        proof,
        reviewer,
        ticket_id,
        version,
        RecordVerdict(uuid4(), _SUPERSEDED.key, _CANDIDATE, VerdictDecision.PASSING),
    )
    # AC-PD-05: a superseding candidate invalidates the proof that depended on it.
    _apply(proof, author, ticket_id, version, ChangeCandidate(_SUCCESSOR_CANDIDATE))


def _apply(
    proof: Proof,
    actor: ProofActor,
    ticket_id: UUID,
    expected_version: int,
    command: FreezeCriteria | RecordEvidence | RecordVerdict | ChangeCandidate,
) -> int:
    outcome = proof.execute(
        actor,
        ProofMutation(uuid4(), ticket_id, expected_version, command),
        telemetry=_telemetry(),
    )
    assert isinstance(outcome, ProofReceipt), outcome
    return expected_version + 1


def _apply_checkpoints(
    tenant: TenantFixture,
    *,
    linked: UUID,
    stageless: UUID,
    now: datetime,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: now,
    )
    bundle = _checkpoint_bundle(linked=linked, stageless=stageless)
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem), plan
    command_id = uuid4()
    applied = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=bundle,
            expected_active_version=0,
            plan_digest=plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, command_id),
    )
    assert isinstance(applied, CompanyBundleCommandResult), applied


def _advance_source_cursor(tenant: TenantFixture, *, now: datetime) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(record_position), 0) FROM events WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
        assert row is not None and int(row[0]) > 0
        connection.execute(
            """
            INSERT INTO outbox_consumer_cursors (
                consumer_key, tenant_id, topic, generation, acceptance_position,
                health, detail, blocked_outbox_id, updated_at
            ) VALUES (
                'board_projection', %s, 'record.events', 1, %s,
                'CURRENT', 'project-delivery-evidence', NULL, %s
            )
            ON CONFLICT (consumer_key, tenant_id, topic) DO UPDATE
            SET acceptance_position = EXCLUDED.acceptance_position,
                health = EXCLUDED.health, detail = EXCLUDED.detail,
                blocked_outbox_id = NULL, updated_at = EXCLUDED.updated_at
            """,
            (tenant.tenant_id, int(row[0]), now),
        )


def _activate_catalog_without_maker(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        links = connection.execute(
            """
            SELECT definition.checkpoint_key, criterion.proof_ticket_id
            FROM project_delivery_exit_criteria AS criterion
            JOIN project_delivery_checkpoint_definitions AS definition
              ON definition.checkpoint_definition_id = criterion.checkpoint_definition_id
             AND definition.tenant_id = criterion.tenant_id
            WHERE criterion.tenant_id = %s
              AND definition.checkpoint_key IN ('evidence.alpha', 'evidence.stageless')
              AND criterion.criterion_key = 'link-alpha'
            """,
            (tenant.tenant_id,),
        ).fetchall()
    tickets = {str(row[0]): cast(UUID, row[1]) for row in links}
    prior_bundle = _checkpoint_bundle(
        linked=tickets["evidence.alpha"],
        stageless=tickets["evidence.stageless"],
    )
    bundle = _checkpoint_bundle(
        linked=tickets["evidence.alpha"],
        stageless=tickets["evidence.stageless"],
        seat_revision=2,
    )
    activate_catalog_revision(tenant, prior_bundle, bundle)


def _checkpoint_bundle(
    *,
    linked: UUID,
    stageless: UUID,
    seat_revision: int = 1,
) -> CompanyBundle:
    tickets = {"linked": linked, "stageless": stageless}
    resources = [
        _seat_catalog_resource(revision=seat_revision),
        *(
            _checkpoint_resource(checkpoint_key, tickets=tickets)
            for checkpoint_key in _CHECKPOINT_LINKS
        ),
    ]
    return CompanyBundle.model_validate_json(
        json.dumps(
            {
                "schema": "ctower.company-bundle/v1",
                "company": {"key": "ctower", "display_name": "ctower"},
                "resources": resources,
                "assignments": [],
                "secret_binding_refs": [],
            }
        )
    )


def _checkpoint_resource(checkpoint_key: str, *, tickets: dict[str, UUID]) -> JsonValue:
    key = checkpoint_key.casefold().replace(".", "-")
    criteria: list[JsonValue] = [
        {
            "key": _DECLARATION,
            "description": f"The declared {checkpoint_key} outcome",
            "required": True,
            "evidence_policy_refs": [],
        }
    ]
    criteria.extend(
        {
            "key": criterion_key,
            "description": f"Current proof for {proof_key}",
            "required": True,
            "evidence_policy_refs": [],
            "proof_link": {
                "ticket_id": str(tickets[owner]),
                "criterion_key": proof_key,
            },
            "assigned_seat": {
                "seat_key": "maker",
                "catalog_key": "fixture.delivery-seats",
                "catalog_revision": 1,
                "catalog_digest": _seat_catalog_digest(1),
            },
        }
        for criterion_key, proof_key, owner in _CHECKPOINT_LINKS[checkpoint_key]
    )
    payload: JsonValue = {
        "schema": "ctower.checkpoint/v1",
        "key": f"ctower.{key}",
        "checkpoint_key": checkpoint_key,
        "display_name": f"ctower checkpoint {checkpoint_key}",
        "outcome": f"ctower establishes the declared {checkpoint_key} outcome",
        "accountable_owner": "ctower-operator",
        "criteria": criteria,
        "dependency_refs": [],
    }
    digest = f"sha256:{hashlib.sha256(rfc8785.dumps(payload)).hexdigest()}"
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": "checkpoint",
            "key": f"ctower.{key}",
            "scope": {"tenant": "ctower", "project": "ctower"},
            "revision": 1,
            "content_digest": digest,
            "schema_ref": "ctower.checkpoint/v1",
            "lifecycle": "published",
            "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
            "provenance": [
                {
                    "kind": "reviewed-contract",
                    "source": "SPEC#project-delivery-projection",
                    "digest": digest,
                }
            ],
            "payload_ref": f"object:{digest}",
        },
        "payload": payload,
    }


def _seat_catalog_resource(*, revision: int) -> JsonValue:
    payload = _seat_catalog_payload(revision)
    digest = _seat_catalog_digest(revision)
    component: dict[str, JsonValue] = {
        "schema": "ctower.versioned-component/v1",
        "kind": "seat_catalog",
        "key": "fixture.delivery-seats",
        "scope": {"tenant": "ctower", "project": None},
        "revision": revision,
        "content_digest": digest,
        "schema_ref": "ctower.seat-catalog/v1",
        "lifecycle": "published",
        "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
        "provenance": [
            {
                "kind": "reviewed-contract",
                "source": "SPEC#project-delivery-projection",
                "digest": digest,
            }
        ],
        "payload_ref": f"object:{digest}",
    }
    if revision > 1:
        component["supersedes"] = {
            "kind": "seat_catalog",
            "key": "fixture.delivery-seats",
            "revision": revision - 1,
            "content_digest": _seat_catalog_digest(revision - 1),
        }
    return {"component": component, "payload": payload}


def _seat_catalog_payload(revision: int) -> JsonValue:
    members: list[JsonValue]
    if revision == 1:
        members = [
            {"key": "maker", "label": "Maker"},
            {"key": "reviewer", "label": "Reviewer"},
        ]
    else:
        members = [
            {"key": "observer", "label": "Observer"},
            {"key": "reviewer", "label": "Review lead"},
        ]
    return {
        "schema": "ctower.seat-catalog/v1",
        "key": "fixture.delivery-seats",
        "display_name": "Fixture delivery seats",
        "members": members,
    }


def _seat_catalog_digest(revision: int) -> str:
    return f"sha256:{hashlib.sha256(rfc8785.dumps(_seat_catalog_payload(revision))).hexdigest()}"


def _graph() -> WorkflowGraph:
    return WorkflowGraph(
        key="fixture.project-delivery-evidence",
        revision=1,
        initial_stage="capture",
        stages=(
            Stage("capture", ActivityClass.WORK),
            Stage("verify", ActivityClass.VERIFICATION),
        ),
        transitions=(Transition("capture", "verify", "criteria.frozen@1"),),
        execution_policy_ref="fixture.execution@1",
        gate_policy_ref="fixture.gates@1",
    )


class _AlwaysReady:
    def unmet_facts(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> tuple[str, ...]:
        del connection, tenant_id, ticket_id
        return ()


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

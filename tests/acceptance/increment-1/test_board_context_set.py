"""Board card context set: INV-66/INV-67 against a real database.

Every context-set member the Board card carries derives from an explicit recorded
fact — never a name, a lane, or silence. These tests exercise the real write
commands (change reference, label, Attention finding, finding disposition) through
the generated client, then read the Board back and assert each member's exact
derived shape, including the "unavailable" states INV-66 requires to be explicit
rather than omitted.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import rfc8785
from support.acceptance import accept_pending_commands
from support.catalog import FileSchemas, MemoryObjectStore, actor_for, telemetry_for
from support.server import running_api
from support.tenant_fixture import TenantFixture

from ctower_client import (
    AppendFindingRequest,
    ApplyLabelRequest,
    AttentionFindingResult,
    BlockIntent,
    BoardCard,
    BoardView,
    ChangeReferenceRequest,
    CtowerClient,
    FindingDispositionRequest,
    Priority,
    SourceReference,
    TicketCreateRequest,
    TicketIntentRequest,
)
from ctower_kernel.catalog import CatalogProblem, CompanyBundle, CompanyBundleApply, PostgresCatalog
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections

__all__: tuple[str, ...] = ()

_LABEL_CATALOG_KEY = "board.ticket-labels"
_ATTENTION_CATALOG_KEY = "attention.needs-you-kinds"
_RENAMED_VOCABULARY_REVISION = 2


def test_change_references_and_applied_labels_are_recorded_exactly(
    tenant: TenantFixture,
) -> None:
    """AC-TM-07: change references and labels expose exactly what was recorded."""

    _apply_bundle(
        tenant,
        [
            _label_vocabulary_resource(
                revision=1,
                members=[
                    {"key": "customer-facing", "label": "Customer facing"},
                    {"key": "security", "label": "Security"},
                ],
            )
        ],
    )
    with (
        running_api(
            tenant.database.runtime_dsn, projection_dsn=tenant.database.projection_dsn
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        labeled = _new_ticket(client, tenant.commander_id, "labeled")
        bare = _new_ticket(client, tenant.commander_id, "bare")

        client.record_ticket_change_reference(
            labeled,
            ChangeReferenceRequest(
                repository="simjak/ctower",
                change_identity="284",
                reference="https://github.com/simjak/ctower/pull/284",
            ),
            command_id=uuid4(),
        )
        client.apply_ticket_label(
            labeled, ApplyLabelRequest(label_key="security"), command_id=uuid4()
        )

        board = _refresh_board(tenant, client)
        labeled_card = _card(board, labeled)
        bare_card = _card(board, bare)

    assert [item.model_dump() for item in labeled_card.change_references] == [
        {
            "repository": "simjak/ctower",
            "change_identity": "284",
            "reference": "https://github.com/simjak/ctower/pull/284",
            "recorded_at": labeled_card.change_references[0].recorded_at,
        }
    ]
    assert [item.label_key for item in labeled_card.applied_labels] == ["security"]
    assert labeled_card.applied_labels[0].label == "Security"
    assert labeled_card.applied_labels[0].vocabulary_revision == 1

    # Absent fixture: a ticket with no facts reads as an explicit empty set, not omitted.
    assert bare_card.change_references == ()
    assert bare_card.applied_labels == ()

    # Complete fixture: tenant display identity is always the tenant's recorded name.
    assert labeled_card.tenant_display_identity.state == "known"
    assert labeled_card.tenant_display_identity.display_name == "Ctower"


def test_label_vocabulary_rename_leaves_historical_applied_label_intact(
    tenant: TenantFixture,
) -> None:
    """INV-66: a later label-vocabulary revision never rewrites a pinned historical fact."""

    catalog = _catalog(tenant)
    _apply_bundle(
        tenant,
        [
            _label_vocabulary_resource(
                revision=1, members=[{"key": "security", "label": "Security"}]
            )
        ],
        catalog=catalog,
    )
    with running_api(
        tenant.database.runtime_dsn, projection_dsn=tenant.database.projection_dsn
    ) as base_url:
        with CtowerClient(base_url, credential=tenant.commander_credential) as client:
            first = _new_ticket(client, tenant.commander_id, "first-revision")
            client.apply_ticket_label(
                first, ApplyLabelRequest(label_key="security"), command_id=uuid4()
            )
            board_before = _refresh_board(tenant, client)
            pinned_label = _card(board_before, first).applied_labels[0]

        _apply_bundle(
            tenant,
            [
                _label_vocabulary_resource(
                    revision=2,
                    members=[{"key": "security", "label": "Security review required"}],
                    previous_members=[{"key": "security", "label": "Security"}],
                )
            ],
            catalog=catalog,
            expected_active_version=1,
        )

        with CtowerClient(base_url, credential=tenant.commander_credential) as client:
            second = _new_ticket(client, tenant.commander_id, "second-revision")
            client.apply_ticket_label(
                second, ApplyLabelRequest(label_key="security"), command_id=uuid4()
            )
            board_after = _refresh_board(tenant, client)
            still_pinned = _card(board_after, first).applied_labels[0]
            fresh = _card(board_after, second).applied_labels[0]

    assert pinned_label.label == "Security"
    assert still_pinned.label == "Security"
    assert still_pinned.vocabulary_revision == 1
    assert fresh.label == "Security review required"
    assert fresh.vocabulary_revision == _RENAMED_VOCABULARY_REVISION


def test_human_waiting_qualifies_only_from_an_open_operator_owned_finding(
    tenant: TenantFixture,
) -> None:
    """AC-TM-08: human-waiting derives only from a qualifying Attention finding."""

    _apply_bundle(
        tenant,
        [
            _attention_kind_catalog_resource(
                revision=1,
                members=[{"key": "needs_decision", "label": "Needs a decision"}],
            )
        ],
    )
    with (
        running_api(
            tenant.database.runtime_dsn, projection_dsn=tenant.database.projection_dsn
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        waiting_ticket = _new_ticket(client, tenant.commander_id, "operator-owned")
        commander_ticket = _new_ticket(client, tenant.commander_id, "commander-owned")
        ordinary_blocked = _new_ticket(client, tenant.commander_id, "ordinary-blocked")
        finding = _seed_findings_and_blocker(
            client, tenant, waiting_ticket, commander_ticket, ordinary_blocked
        )

        board = _refresh_board(tenant, client)
        waiting_card = _card(board, waiting_ticket)
        commander_card = _card(board, commander_ticket)
        blocked_card = _card(board, ordinary_blocked)

        assert waiting_card.human_waiting.state == "waiting"
        assert waiting_card.human_waiting.finding_id == finding.finding_id
        assert waiting_card.human_waiting.kind_key == "needs_decision"
        assert waiting_card.human_waiting.reason_code == "gate_decision"

        # Commander-owned findings never qualify as operator human-waiting.
        assert commander_card.human_waiting.state == "not_waiting"

        # Ordinary blocked-by-a-blocker is never coerced into human-waiting.
        assert blocked_card.lane.value == "blocked"
        assert blocked_card.human_waiting.state == "not_waiting"

        client.record_attention_finding_disposition(
            finding.finding_id,
            FindingDispositionRequest(outcome="resolved", reason="Decision made"),
            command_id=uuid4(),
        )
        resolved_board = _refresh_board(tenant, client)
        resolved_card = _card(resolved_board, waiting_ticket)

    assert resolved_card.human_waiting.state == "not_waiting"


def _new_ticket(client: CtowerClient, custodian_id: UUID, suffix: str) -> UUID:
    return client.create_ticket(
        TicketCreateRequest(
            initial_custodian_id=custodian_id,
            priority=Priority.P2,
            project_key="ctower",
            source=SourceReference(kind="test", ref=f"test:{suffix}:{uuid4()}"),
            title=suffix,
        ),
        command_id=uuid4(),
    ).ticket.ticket_id


def _seed_findings_and_blocker(
    client: CtowerClient,
    tenant: TenantFixture,
    waiting_ticket: UUID,
    commander_ticket: UUID,
    ordinary_blocked: UUID,
) -> AttentionFindingResult:
    finding = client.append_attention_finding(
        AppendFindingRequest(
            subject_ticket_id=waiting_ticket,
            kind_key="needs_decision",
            reason_code="gate_decision",
            effective_owner="operator",
            recommendation="Approve the release train",
            alternatives=("Defer to next window",),
            consequence="Release stays blocked",
            deadline=None,
            dedupe_key="release-gate-284",
            source_facts=("gate:release-284",),
        ),
        command_id=uuid4(),
    )
    client.append_attention_finding(
        AppendFindingRequest(
            subject_ticket_id=commander_ticket,
            kind_key="needs_decision",
            reason_code="budget_decision",
            effective_owner="commander",
            recommendation="Approve the added budget",
            alternatives=(),
            consequence="Spend request stays open",
            deadline=None,
            dedupe_key="budget-gate-1",
            source_facts=("gate:budget-1",),
        ),
        command_id=uuid4(),
    )
    client.apply_ticket_intent(
        ordinary_blocked,
        TicketIntentRequest(
            intent=BlockIntent(
                kind="block",
                expected_version=1,
                reason="Waiting on an external vendor",
                blocker_id=uuid4(),
                blocker_kind="dependency",
                reason_class="external",
                owner_principal_id=tenant.commander_id,
                source_ref="test:vendor-wait",
                affected_stage=None,
                resolution_condition="Vendor responds",
                next_check_at=None,
                dependency_ref=None,
                board_impact=True,
            )
        ),
        command_id=uuid4(),
    )
    return finding


def _refresh_board(tenant: TenantFixture, client: CtowerClient) -> BoardView:
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
    return client.get_board(project_key="ctower")


def _card(board: BoardView, ticket_id: UUID) -> BoardCard:
    matches = [card for card in board.cards if card.ticket_id == ticket_id]
    assert len(matches) == 1
    return matches[0]


def _catalog(tenant: TenantFixture) -> PostgresCatalog:
    return PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 8, 5, tzinfo=UTC),
    )


def _apply_bundle(
    tenant: TenantFixture,
    resources: list[JsonValue],
    *,
    catalog: PostgresCatalog | None = None,
    expected_active_version: int = 0,
) -> None:
    catalog = catalog if catalog is not None else _catalog(tenant)
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    bundle = CompanyBundle.model_validate_json(
        json.dumps(
            {
                "schema": "ctower.company-bundle/v1",
                "company": {"key": "ctower", "display_name": "Ctower"},
                "resources": resources,
                "assignments": [],
                "secret_binding_refs": [],
            }
        )
    )
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem), plan
    command_id = uuid4()
    result = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=bundle,
            expected_active_version=expected_active_version,
            plan_digest=plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, command_id),
    )
    assert not isinstance(result, CatalogProblem), result


def _label_vocabulary_resource(
    *,
    revision: int,
    members: list[JsonValue],
    previous_members: list[JsonValue] | None = None,
) -> JsonValue:
    def payload(members: list[JsonValue]) -> JsonValue:
        return {
            "schema": "ctower.label-vocabulary/v1",
            "key": _LABEL_CATALOG_KEY,
            "display_name": "Ticket labels",
            "members": members,
        }

    return _tenant_wide_catalog_resource(
        kind="label_vocabulary",
        schema_ref="ctower.label-vocabulary/v1",
        key=_LABEL_CATALOG_KEY,
        revision=revision,
        payload=payload(members),
        previous_payload=payload(previous_members) if previous_members is not None else None,
    )


def _attention_kind_catalog_resource(*, revision: int, members: list[JsonValue]) -> JsonValue:
    return _tenant_wide_catalog_resource(
        kind="attention_kind_catalog",
        schema_ref="ctower.attention-kind-catalog/v1",
        key=_ATTENTION_CATALOG_KEY,
        revision=revision,
        payload={
            "schema": "ctower.attention-kind-catalog/v1",
            "key": _ATTENTION_CATALOG_KEY,
            "display_name": "Needs You kinds",
            "members": members,
        },
        previous_payload=None,
    )


def _tenant_wide_catalog_resource(
    *,
    kind: str,
    schema_ref: str,
    key: str,
    revision: int,
    payload: JsonValue,
    previous_payload: JsonValue | None,
) -> JsonValue:
    digest = f"sha256:{hashlib.sha256(rfc8785.dumps(payload)).hexdigest()}"
    component: dict[str, JsonValue] = {
        "schema": "ctower.versioned-component/v1",
        "kind": kind,
        "key": key,
        "scope": {"tenant": "ctower", "project": None},
        "revision": revision,
        "content_digest": digest,
        "schema_ref": schema_ref,
        "lifecycle": "published",
        "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
        "provenance": [
            {"kind": "reviewed-contract", "source": "SPEC#board-card-context", "digest": digest}
        ],
        "payload_ref": f"object:{digest}",
    }
    if revision > 1:
        if previous_payload is None:
            raise ValueError("a superseding revision must supply the previous payload")
        previous_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(previous_payload)).hexdigest()}"
        component["supersedes"] = {
            "kind": kind,
            "key": key,
            "revision": revision - 1,
            "content_digest": previous_digest,
        }
    return {"component": component, "payload": payload}

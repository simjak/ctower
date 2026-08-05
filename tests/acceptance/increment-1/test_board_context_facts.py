"""Board-context and Attention kernel command facts, direct and real (INV-66/67).

test_board_context_set.py proves the wire-level journey through the generated
client and HTTP surface. These tests call BoardContextFacts and Attention
directly against real Postgres to prove replay safety and every refusal
branch the two command modules declare, mirroring test_company_bundle.py's
ticket-comment pattern.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import rfc8785
from support.catalog import FileSchemas, MemoryObjectStore, actor_for, telemetry_for
from support.tenant_fixture import TenantFixture

from ctower_kernel.attention import (
    AppendFinding,
    Attention,
    AttentionFindingReceipt,
    FindingDisposition,
    FindingDispositionOutcome,
    FindingDispositionReceipt,
)
from ctower_kernel.attention.postgres import PostgresAttention
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.change_references import (
    ChangeReferenceCommand,
    ChangeReferenceResult,
)
from ctower_kernel.board_context.labels import ApplyLabelCommand, ApplyLabelResult
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.catalog import CatalogProblem, CompanyBundle, CompanyBundleApply, PostgresCatalog
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.record import Actor, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

_LABEL_CATALOG_KEY = "board.ticket-labels"
_ATTENTION_CATALOG_KEY = "attention.needs-you-kinds"
_NOW = datetime(2026, 8, 5, tzinfo=UTC)


def test_change_reference_is_replay_safe_and_rejects_a_duplicate_link(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    record = PostgresRecord(tenant.database.runtime_dsn)
    facts = BoardContextFacts(PostgresBoardContextFacts(tenant.database.runtime_dsn))
    ticket_id = _create_ticket(record, actor, tenant, "Change-reference facts")

    command_id = uuid4()
    command = ChangeReferenceCommand(
        client_command_id=command_id,
        ticket_id=ticket_id,
        repository="simjak/ctower",
        change_identity="284",
        reference="https://github.com/simjak/ctower/pull/284",
    )
    digest = _digest(command.request_payload())

    recorded = facts.record_change_reference(
        actor, command, request_digest=digest, now=_NOW, telemetry=telemetry_for(actor, command_id)
    )
    replay = facts.record_change_reference(
        actor, command, request_digest=digest, now=_NOW, telemetry=telemetry_for(actor, command_id)
    )
    assert isinstance(recorded, ChangeReferenceResult)
    assert replay == recorded

    duplicate = ChangeReferenceCommand(
        client_command_id=uuid4(),
        ticket_id=ticket_id,
        repository="simjak/ctower",
        change_identity="284",
        reference="https://github.com/simjak/ctower/pull/284",
    )
    refused = facts.record_change_reference(
        actor,
        duplicate,
        request_digest=_digest(duplicate.request_payload()),
        now=_NOW,
        telemetry=telemetry_for(actor, duplicate.client_command_id),
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "change-reference-duplicate"


def test_change_reference_refuses_a_ticket_outside_the_tenant(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    facts = BoardContextFacts(PostgresBoardContextFacts(tenant.database.runtime_dsn))
    command = ChangeReferenceCommand(
        client_command_id=uuid4(),
        ticket_id=uuid4(),
        repository="simjak/ctower",
        change_identity="1",
        reference="https://github.com/simjak/ctower/pull/1",
    )
    refused = facts.record_change_reference(
        actor,
        command,
        request_digest=_digest(command.request_payload()),
        now=_NOW,
        telemetry=telemetry_for(actor, command.client_command_id),
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "tenant-scope-denied"


def test_apply_label_is_replay_safe_and_rejects_unrecognized_or_repeated_keys(
    tenant: TenantFixture,
) -> None:
    _apply_bundle(
        tenant,
        [
            _label_vocabulary_resource(
                revision=1, members=[{"key": "security", "label": "Security"}]
            )
        ],
    )
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    record = PostgresRecord(tenant.database.runtime_dsn)
    facts = BoardContextFacts(PostgresBoardContextFacts(tenant.database.runtime_dsn))
    ticket_id = _create_ticket(record, actor, tenant, "Label facts")

    command_id = uuid4()
    command = ApplyLabelCommand(
        client_command_id=command_id, ticket_id=ticket_id, label_key="security"
    )
    digest = _digest(command.request_payload())
    applied = facts.apply_label(
        actor, command, request_digest=digest, now=_NOW, telemetry=telemetry_for(actor, command_id)
    )
    replay = facts.apply_label(
        actor, command, request_digest=digest, now=_NOW, telemetry=telemetry_for(actor, command_id)
    )
    assert isinstance(applied, ApplyLabelResult)
    assert replay == applied

    unknown = ApplyLabelCommand(
        client_command_id=uuid4(), ticket_id=ticket_id, label_key="unrecognized"
    )
    refused_unknown = facts.apply_label(
        actor,
        unknown,
        request_digest=_digest(unknown.request_payload()),
        now=_NOW,
        telemetry=telemetry_for(actor, unknown.client_command_id),
    )
    assert isinstance(refused_unknown, RecordProblem)
    assert refused_unknown.code == "label-key-unrecognized"

    repeat = ApplyLabelCommand(client_command_id=uuid4(), ticket_id=ticket_id, label_key="security")
    refused_repeat = facts.apply_label(
        actor,
        repeat,
        request_digest=_digest(repeat.request_payload()),
        now=_NOW,
        telemetry=telemetry_for(actor, repeat.client_command_id),
    )
    assert isinstance(refused_repeat, RecordProblem)
    assert refused_repeat.code == "label-already-applied"


def test_append_finding_is_replay_safe_and_rejects_an_unrecognized_kind_or_subject(
    tenant: TenantFixture,
) -> None:
    _apply_bundle(
        tenant,
        [
            _attention_kind_catalog_resource(
                revision=1, members=[{"key": "needs_decision", "label": "Needs a decision"}]
            )
        ],
    )
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    record = PostgresRecord(tenant.database.runtime_dsn)
    attention = Attention(PostgresAttention(tenant.database.runtime_dsn))
    ticket_id = _create_ticket(record, actor, tenant, "Attention finding facts")

    command = _finding_command(ticket_id, kind_key="needs_decision", dedupe_key="release-gate-1")
    appended = attention.append_finding(actor, command)
    replay = attention.append_finding(actor, command)
    assert isinstance(appended, AttentionFindingReceipt)
    assert replay == appended

    unrecognized = _finding_command(
        ticket_id, kind_key="unrecognized_kind", dedupe_key="release-gate-2"
    )
    refused_kind = attention.append_finding(actor, unrecognized)
    assert isinstance(refused_kind, RecordProblem)
    assert refused_kind.code == "attention-kind-unrecognized"

    missing_subject = _finding_command(
        uuid4(), kind_key="needs_decision", dedupe_key="release-gate-3"
    )
    refused_subject = attention.append_finding(actor, missing_subject)
    assert isinstance(refused_subject, RecordProblem)
    assert refused_subject.code == "tenant-scope-denied"


def test_finding_disposition_is_replay_safe_and_rejects_repeat_or_unknown_finding(
    tenant: TenantFixture,
) -> None:
    _apply_bundle(
        tenant,
        [
            _attention_kind_catalog_resource(
                revision=1, members=[{"key": "needs_decision", "label": "Needs a decision"}]
            )
        ],
    )
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    record = PostgresRecord(tenant.database.runtime_dsn)
    attention = Attention(PostgresAttention(tenant.database.runtime_dsn))
    ticket_id = _create_ticket(record, actor, tenant, "Disposition facts")
    finding = attention.append_finding(
        actor, _finding_command(ticket_id, kind_key="needs_decision", dedupe_key="release-gate-4")
    )
    assert isinstance(finding, AttentionFindingReceipt)

    command = FindingDisposition(
        client_command_id=uuid4(),
        finding_id=finding.finding_id,
        outcome=FindingDispositionOutcome.RESOLVED,
        reason="Decision made",
    )
    disposed = attention.record_finding_disposition(actor, command)
    replay = attention.record_finding_disposition(actor, command)
    assert isinstance(disposed, FindingDispositionReceipt)
    assert replay == disposed

    repeat = FindingDisposition(
        client_command_id=uuid4(),
        finding_id=finding.finding_id,
        outcome=FindingDispositionOutcome.SNOOZED,
        reason="Trying again",
    )
    refused_repeat = attention.record_finding_disposition(actor, repeat)
    assert isinstance(refused_repeat, RecordProblem)
    assert refused_repeat.code == "attention-finding-already-disposed"

    unknown = FindingDisposition(
        client_command_id=uuid4(),
        finding_id=uuid4(),
        outcome=FindingDispositionOutcome.RESOLVED,
        reason="No such finding",
    )
    refused_unknown = attention.record_finding_disposition(actor, unknown)
    assert isinstance(refused_unknown, RecordProblem)
    assert refused_unknown.code == "attention-finding-not-found"


def _finding_command(ticket_id: UUID, *, kind_key: str, dedupe_key: str) -> AppendFinding:
    return AppendFinding(
        client_command_id=uuid4(),
        subject_ticket_id=ticket_id,
        kind_key=kind_key,
        reason_code="gate_decision",
        effective_owner="operator",
        recommendation="Approve the release train",
        alternatives=("Defer to next window",),
        consequence="Release stays blocked",
        deadline=None,
        dedupe_key=dedupe_key,
        source_facts=("gate:release-1",),
    )


def _create_ticket(record: PostgresRecord, actor: Actor, tenant: TenantFixture, title: str) -> UUID:
    command_id = uuid4()
    created = record.create_ticket(
        actor,
        TicketCommand(
            client_command_id=command_id,
            title=title,
            source=SourceReference("acceptance", "board-context-facts"),
            priority="P1",
            project_key="ctower",
            initial_custodian_id=tenant.commander_id,
        ),
        request_digest=hashlib.sha256(title.encode()).digest(),
        now=_NOW,
        telemetry=telemetry_for(actor, command_id),
    )
    assert not isinstance(created, RecordProblem)
    return created.ticket.ticket_id


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()


def _catalog(tenant: TenantFixture) -> PostgresCatalog:
    return PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: _NOW,
    )


def _apply_bundle(tenant: TenantFixture, resources: list[JsonValue]) -> None:
    catalog = _catalog(tenant)
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
            expected_active_version=0,
            plan_digest=plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, command_id),
    )
    assert not isinstance(result, CatalogProblem), result


def _label_vocabulary_resource(*, revision: int, members: list[JsonValue]) -> JsonValue:
    return _tenant_wide_catalog_resource(
        kind="label_vocabulary",
        schema_ref="ctower.label-vocabulary/v1",
        key=_LABEL_CATALOG_KEY,
        revision=revision,
        payload={
            "schema": "ctower.label-vocabulary/v1",
            "key": _LABEL_CATALOG_KEY,
            "display_name": "Ticket labels",
            "members": members,
        },
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
    )


def _tenant_wide_catalog_resource(
    *, kind: str, schema_ref: str, key: str, revision: int, payload: JsonValue
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
    return {"component": component, "payload": payload}

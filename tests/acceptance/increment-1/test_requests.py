"""Real-PostgreSQL acceptance for the first-class Request authority."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.server import application
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.human_identity import HumanRole, HumanRoleBindingIssue
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.work._request_similarity import embed
from ctower_kernel.work.requests import (
    PostgresRequests,
    RequestBlocker,
    RequestCapture,
    RequestCaptureResult,
    RequestChangeResult,
    RequestClosureEvaluation,
    RequestOwner,
    RequestPriority,
    Requests,
    RequestSame,
    RequestTicketRelation,
    RequestTriage,
)

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_PENDING = 202
PARALLEL_CAPTURE_COUNT = 100
PRIORITIZED_VERSION = 2
TRIAGED_VERSION = 3
RELATED_VERSION = 4
BLOCKED_VERSION = 5


def test_resembling_capture_speaks_links_and_operator_same_preserves_provenance(
    tenant: TenantFixture,
) -> None:
    """AC-REQ-09/10: capture speaks; only literal operator same merges Requests."""

    first_text = "Please add duplicate-aware Request capture to the operator workflow."
    second_text = "Please add duplicate aware Request capture in the operator workflow."
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    original = _accepted_capture(tenant, authority, operator, first_text)

    duplicate_command = RequestCapture(uuid4(), "ctower", second_text)
    duplicate = _capture(authority, operator, duplicate_command)
    assert isinstance(duplicate, RequestCaptureResult)
    assert duplicate.acknowledgement == (
        f"captured as {duplicate.reference}, resembles {original.reference} (NEW), linked — "
        "say same to merge."
    )
    assert duplicate.resemblance is not None
    assert duplicate.resemblance.other_request_id == original.request_id
    assert duplicate.resemblance.other_reference == original.reference
    assert duplicate.resemblance.other_state == "NEW"
    assert duplicate.resemblance.algorithm_ref == "ctower.local-hashed-subword/v1"

    _accept_and_assert_resemblance_persistence(
        tenant, authority, operator, duplicate_command, duplicate, original, second_text, first_text
    )
    before_merge = authority.list(
        operator, project_key="ctower", telemetry=_telemetry(operator, uuid4())
    )
    assert not isinstance(before_merge, RecordProblem)
    rows = {row.request_id: row for row in before_merge.rows}
    assert rows[original.request_id].triage == "UNTRIAGED"
    assert rows[duplicate.request_id].triage == "UNTRIAGED"
    assert rows[original.request_id].resemblances[0].other_request_id == duplicate.request_id
    assert rows[duplicate.request_id].resemblances[0].other_request_id == original.request_id
    assert rows[original.request_id].merge_provenance is None
    assert rows[duplicate.request_id].merge_provenance is None
    _assert_request_version(tenant, original.request_id, 1)

    same_command_id = uuid4()
    same_headers = {
        "Authorization": f"Bearer {tenant.operator_credential}",
        "Idempotency-Key": str(same_command_id),
        **telemetry_headers(same_command_id),
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        pending_same = client.post(
            f"/v1/requests/{duplicate.request_id}/same",
            headers=same_headers,
            json={"expected_version": 1},
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        accepted_same = client.post(
            f"/v1/requests/{duplicate.request_id}/same",
            headers=same_headers,
            json={"expected_version": 1},
        )
    assert pending_same.status_code == HTTP_PENDING
    assert accepted_same.status_code == HTTP_OK
    assert pending_same.json()["operation"] == accepted_same.json()["operation"] == "same"
    after_merge = authority.list(
        operator, project_key="ctower", telemetry=_telemetry(operator, uuid4())
    )
    assert not isinstance(after_merge, RecordProblem)
    merged_row = next(row for row in after_merge.rows if row.request_id == duplicate.request_id)
    provenance = merged_row.merge_provenance
    assert merged_row.triage == "DUPLICATE"
    assert provenance is not None
    assert provenance.trigger == "operator_same"
    assert provenance.merge_wording == "same"
    assert provenance.duplicate_content == second_text
    assert provenance.canonical_content == first_text
    assert provenance.duplicate_created_at == merged_row.created_at
    assert provenance.canonical_created_at == rows[original.request_id].created_at
    assert merged_row.resemblances[0].other_request_id == original.request_id
    print(
        "REAL_REQUEST_DUPLICATE_ACK"
        f" acknowledgement={duplicate.acknowledgement!r}"
        f" merge={accepted_same.json()['operation']}:{merged_row.triage}"
        f" provenance={provenance.duplicate_reference}->{provenance.canonical_reference}"
    )


def test_unrelated_capture_stays_unlinked_and_same_refuses_without_a_link(
    tenant: TenantFixture,
) -> None:
    """AC-REQ-09/10: low resemblance is silent and cannot be merged by `same`."""

    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    _accepted_capture(tenant, authority, operator, "Improve Request capture acknowledgements.")
    unrelated = _accepted_capture(
        tenant, authority, operator, "Replace the office coffee grinder next Thursday."
    )

    assert unrelated.resemblance is None
    assert unrelated.acknowledgement == f"captured as {unrelated.reference}."
    refused = authority.same(
        operator,
        RequestSame(uuid4(), unrelated.request_id, 1),
        telemetry=_telemetry(operator, uuid4()),
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "request-same-forbidden"


def _assert_request_version(tenant: TenantFixture, request_id: UUID, expected: int) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        version = connection.execute(
            "SELECT version FROM requests WHERE request_id = %s", (request_id,)
        ).fetchone()
    assert version == (expected,)


def _accept_and_assert_resemblance_persistence(
    tenant: TenantFixture,
    authority: Requests,
    actor: Actor,
    command: RequestCapture,
    source: RequestCaptureResult,
    candidate: RequestCaptureResult,
    source_text: str,
    candidate_text: str,
) -> None:
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    assert _capture(authority, actor, command) == source
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        persisted_link = connection.execute(
            """
            SELECT source_embedding_digest, candidate_embedding_digest
            FROM request_resemblance_links
            WHERE tenant_id = %s AND source_request_id = %s AND candidate_request_id = %s
            """,
            (tenant.tenant_id, source.request_id, candidate.request_id),
        ).fetchone()
    assert persisted_link == (embed(source_text).digest, embed(candidate_text).digest)


def test_request_capture_ack_replay_and_authoritative_list(tenant: TenantFixture) -> None:
    """INV-81/82/84/85: one custody act, honest ACK, permanent R, no Ticket."""

    command_id = uuid4()
    headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        pending = client.post(
            "/v1/requests",
            headers=headers,
            json={"project_key": "ctower", "text": "Keep this operator intent visible."},
        )
        hidden = client.get(
            "/v1/requests",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
            params={"project_key": "ctower"},
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        replay = client.post(
            "/v1/requests",
            headers=headers,
            json={"project_key": "ctower", "text": "Keep this operator intent visible."},
        )
        visible = client.get(
            "/v1/requests",
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
            params={"project_key": "ctower"},
        )

    first = cast(dict[str, object], pending.json())
    second = cast(dict[str, object], replay.json())
    assert pending.status_code == HTTP_PENDING
    assert first["durability_state"] == "durability_pending"
    assert first["accepted_position"] is None
    assert hidden.status_code == HTTP_OK
    assert hidden.json()["rows"] == []
    assert replay.status_code == HTTP_CREATED
    assert second["durability_state"] == "accepted"
    assert isinstance(second["accepted_position"], int)
    assert second["request_id"] == first["request_id"]
    assert second["request_number"] == first["request_number"]
    assert second["reference"] == f"R{first['request_number']}"
    assert second["submitted_by"] == str(tenant.commander_id)
    assert second["owner_id"] == str(tenant.commander_id)
    rows = visible.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["state"] == "NEW"
    assert rows[0]["triage"] == "UNTRIAGED"
    assert rows[0]["priority"] == "P2"
    assert rows[0]["priority_default"] is True
    assert rows[0]["proof_coverage"] == 0
    assert rows[0]["project_key"] == "ctower"
    assert rows[0]["freshness"] == second["accepted_position"]
    _assert_capture_storage(tenant)
    print(
        "REAL_REQUEST_ACK"
        f" first={pending.status_code}:{first['durability_state']}"
        f" replay={replay.status_code}:{second['durability_state']}"
        f" reference={second['reference']} rows={len(rows)}"
    )


def test_request_list_hides_pending_change_facts_until_offhost_acceptance(
    tenant: TenantFixture,
) -> None:
    """OR-01/07: a pending mutation cannot rewrite an accepted list row or freshness."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    captured = _accepted_capture(tenant, authority, actor, "Accepted projection boundary")
    before = authority.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))
    assert not isinstance(before, RecordProblem)
    pending = authority.prioritize(
        actor,
        RequestPriority(uuid4(), captured.request_id, 1, "P0", "pending operator impact"),
        telemetry=_telemetry(actor, uuid4()),
    )
    assert isinstance(pending, RequestChangeResult)
    hidden = authority.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))
    assert not isinstance(hidden, RecordProblem)

    assert before.rows[0].priority == hidden.rows[0].priority == "P2"
    assert before.rows[0].freshness == hidden.rows[0].freshness

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    visible = authority.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))
    assert not isinstance(visible, RecordProblem)
    assert visible.rows[0].priority == "P0"
    assert visible.rows[0].freshness > hidden.rows[0].freshness


def test_bound_humans_use_exact_project_grants_and_are_addressable_owners(
    tenant: TenantFixture,
) -> None:
    """OR-01/05/07: human roles use binding grants, never principal-kind fleet shortcuts."""

    record = PostgresRecord(tenant.database.runtime_dsn)
    machine_operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    human_operator = _bound_human(record, tenant, machine_operator, "operator")
    accepted = _accepted_capture(tenant, authority, human_operator, "Human operator capture")

    assert accepted.submitted_by == human_operator.principal_id
    assert accepted.owner_id == human_operator.principal_id
    denied = authority.capture(
        human_operator,
        RequestCapture(uuid4(), "manibo", "Foreign project capture"),
        telemetry=_telemetry(human_operator, uuid4()),
    )
    assert isinstance(denied, RecordProblem)
    assert denied.code == "project-scope-denied"

    viewer = _bound_human(record, tenant, machine_operator, "viewer")
    visible = authority.list(viewer, project_key="ctower", telemetry=_telemetry(viewer, uuid4()))
    assert not isinstance(visible, RecordProblem)
    assert visible.rows[0].request_id == accepted.request_id


def _assert_capture_storage(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        tickets = cast(tuple[int], connection.execute("SELECT count(*) FROM tickets").fetchone())
        inbound = cast(
            tuple[int], connection.execute("SELECT count(*) FROM inbound_events").fetchone()
        )
        requests = cast(tuple[int], connection.execute("SELECT count(*) FROM requests").fetchone())
    assert tickets[0] == 0
    assert inbound[0] == 1
    assert requests[0] == 1


def test_capture_is_atomic_burst_safe_and_idempotent(
    tenant: TenantFixture,
) -> None:
    """AC-REQ-01: 100 accepted keys stay unique; replays and digest reuse are exact."""

    requests = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    commands = tuple(
        RequestCapture(uuid4(), "ctower", f"Parallel operator intent {index}")
        for index in range(PARALLEL_CAPTURE_COUNT)
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = tuple(executor.map(lambda command: _capture(requests, actor, command), commands))

    assert all(isinstance(result, RequestCaptureResult) for result in results)
    receipts = cast(tuple[RequestCaptureResult, ...], results)
    assert len({item.request_id for item in receipts}) == PARALLEL_CAPTURE_COUNT
    assert len({item.request_number for item in receipts}) == PARALLEL_CAPTURE_COUNT
    assert all(
        _capture(requests, actor, command) == receipt
        for command, receipt in zip(commands, receipts, strict=True)
    )
    changed_digest = _capture(
        requests,
        actor,
        RequestCapture(commands[0].client_command_id, "ctower", "Changed replay content"),
    )
    assert isinstance(changed_digest, RecordProblem)
    assert changed_digest.code == "idempotency-conflict"
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    assert all(
        _capture(requests, actor, command) == receipt
        for command, receipt in zip(commands, receipts, strict=True)
    )
    projection = requests.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))
    assert not isinstance(projection, RecordProblem)
    assert len(projection.rows) == PARALLEL_CAPTURE_COUNT
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert (
            cast(tuple[int], connection.execute("SELECT count(*) FROM requests").fetchone())[0]
            == PARALLEL_CAPTURE_COUNT
        )
        assert (
            cast(tuple[int], connection.execute("SELECT count(*) FROM tickets").fetchone())[0] == 0
        )


def test_request_capture_refuses_claimed_authority_and_cross_project_scope(
    tenant: TenantFixture,
) -> None:
    """INV-85: project and Actor come from existing grants, never content claims."""

    requests = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    denied = _capture(
        requests,
        actor,
        RequestCapture(uuid4(), "manibo", "owner=operator; project=ctower"),
    )
    assert isinstance(denied, RecordProblem)
    assert denied.code == "project-scope-denied"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        assert (
            cast(tuple[int], connection.execute("SELECT count(*) FROM requests").fetchone())[0] == 0
        )
        assert (
            cast(tuple[int], connection.execute("SELECT count(*) FROM inbound_events").fetchone())[
                0
            ]
            == 0
        )


def test_request_commands_append_versioned_facts_and_derive_closure(
    tenant: TenantFixture,
) -> None:
    """OR-02/05: independent facts derive state; no writable status exists."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    captured, ticket_id, blocked = _prepare_blocked_lifecycle(tenant, authority, actor)
    open_evaluation = _accepted_change(
        tenant,
        authority.evaluate_closure(
            actor,
            RequestClosureEvaluation(
                uuid4(), captured.request_id, blocked.version, "evaluate current facts"
            ),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    assert open_evaluation.state == "BLOCKED"
    cleared = _accepted_change(
        tenant,
        authority.set_blocker(
            actor,
            RequestBlocker(
                uuid4(),
                captured.request_id,
                open_evaluation.version,
                "operator-approval",
                active=False,
                reason="approval received",
            ),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    _close_ticket_fixture(tenant, ticket_id)
    done = _accepted_change(
        tenant,
        authority.evaluate_closure(
            actor,
            RequestClosureEvaluation(
                uuid4(), captured.request_id, cleared.version, "required outcome proven"
            ),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    assert done.state == "DONE"
    projection = authority.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))
    assert not isinstance(projection, RecordProblem)
    assert projection.rows[0].state == "DONE"
    assert projection.rows[0].required_ticket_ids == (ticket_id,)
    assert projection.rows[0].priority == "P1"
    optional_ticket = _accepted_ticket(tenant, actor)
    changed_after_close = _accepted_change(
        tenant,
        authority.relate_ticket(
            actor,
            RequestTicketRelation(
                uuid4(),
                captured.request_id,
                done.version,
                1,
                optional_ticket,
                "optional",
                active=True,
                reason="later decomposition changed the closure denominator",
            ),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    assert changed_after_close.state != "DONE"
    invalidated = authority.list(actor, project_key="ctower", telemetry=_telemetry(actor, uuid4()))
    assert not isinstance(invalidated, RecordProblem)
    assert invalidated.rows[0].state != "DONE"


def _prepare_blocked_lifecycle(
    tenant: TenantFixture, authority: Requests, actor: Actor
) -> tuple[RequestCaptureResult, UUID, RequestChangeResult]:
    captured = _accepted_capture(tenant, authority, actor, "Lifecycle intent")
    ticket_id = _accepted_ticket(tenant, actor)
    prioritized = _accepted_change(
        tenant,
        authority.prioritize(
            actor,
            RequestPriority(uuid4(), captured.request_id, 1, "P1", "operator impact"),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    assert prioritized.version == PRIORITIZED_VERSION
    triaged = _accepted_change(
        tenant,
        authority.triage(
            actor,
            RequestTriage(uuid4(), captured.request_id, prioritized.version, "ACCEPTED"),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    assert triaged.version == TRIAGED_VERSION
    related = _accepted_change(
        tenant,
        authority.relate_ticket(
            actor,
            RequestTicketRelation(
                uuid4(),
                captured.request_id,
                triaged.version,
                1,
                ticket_id,
                "required",
                active=True,
                reason="fulfills intent",
            ),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    assert related.version == RELATED_VERSION
    blocked = _accepted_change(
        tenant,
        authority.set_blocker(
            actor,
            RequestBlocker(
                uuid4(),
                captured.request_id,
                related.version,
                "operator-approval",
                active=True,
                reason="approval pending",
            ),
            telemetry=_telemetry(actor, uuid4()),
        ),
    )
    assert blocked.version == BLOCKED_VERSION
    return captured, ticket_id, blocked


def test_request_triage_owner_relation_and_version_refusals_are_fail_closed(
    tenant: TenantFixture,
) -> None:
    """OR-02/05: invalid authority, stale versions, and relation reuse mutate nothing."""

    authority = Requests(PostgresRequests(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    first, ticket_id, relation = _canonical_request(tenant, authority, commander)
    competing = _accepted_capture(tenant, authority, commander, "Competing intent")
    _assert_ticket_reuse_refused(tenant, authority, commander, competing, ticket_id)
    duplicate = _accepted_capture(tenant, authority, commander, "Repeated intent")
    assert relation.version == RELATED_VERSION

    duplicate_result = _accepted_change(
        tenant,
        authority.triage(
            commander,
            RequestTriage(
                uuid4(), duplicate.request_id, 1, "DUPLICATE", "same outcome", first.request_id
            ),
            telemetry=_telemetry(commander, uuid4()),
        ),
    )
    assert duplicate_result.state == "TRIAGED"
    projection = authority.list(
        commander, project_key="ctower", telemetry=_telemetry(commander, uuid4())
    )
    assert not isinstance(projection, RecordProblem)
    duplicate_row = next(row for row in projection.rows if row.request_id == duplicate.request_id)
    assert duplicate_row.merge_provenance is not None
    assert duplicate_row.merge_provenance.trigger == "commander_triage"
    assert duplicate_row.merge_provenance.merge_wording == "triage DUPLICATE: same outcome"
    assert duplicate_row.merge_provenance.duplicate_content == "Repeated intent"
    assert duplicate_row.merge_provenance.canonical_content == "Canonical intent"
    canonical_rewrite = authority.triage(
        commander,
        RequestTriage(
            uuid4(), first.request_id, relation.version, "DUPLICATE", "cycle", duplicate.request_id
        ),
        telemetry=_telemetry(commander, uuid4()),
    )
    assert isinstance(canonical_rewrite, RecordProblem)
    assert canonical_rewrite.code == "request-triage-forbidden"


def _canonical_request(
    tenant: TenantFixture, authority: Requests, commander: Actor
) -> tuple[RequestCaptureResult, UUID, RequestChangeResult]:
    first = _accepted_capture(tenant, authority, commander, "Canonical intent")
    early = authority.triage(
        commander,
        RequestTriage(uuid4(), first.request_id, 1, "ACCEPTED"),
        telemetry=_telemetry(commander, uuid4()),
    )
    assert isinstance(early, RecordProblem) and early.code == "request-triage-forbidden"
    priority = _accepted_change(
        tenant,
        authority.prioritize(
            commander,
            RequestPriority(uuid4(), first.request_id, 1, "P2", "reviewed default"),
            telemetry=_telemetry(commander, uuid4()),
        ),
    )
    accepted = _accepted_change(
        tenant,
        authority.triage(
            commander,
            RequestTriage(uuid4(), first.request_id, priority.version, "ACCEPTED"),
            telemetry=_telemetry(commander, uuid4()),
        ),
    )
    stale = authority.assign_owner(
        commander,
        RequestOwner(uuid4(), first.request_id, 1, tenant.commander_id, "stale placement"),
        telemetry=_telemetry(commander, uuid4()),
    )
    assert isinstance(stale, RecordProblem) and stale.code == "version-conflict"
    ticket_id = _accepted_ticket(tenant, commander)
    relation = _accepted_change(
        tenant,
        authority.relate_ticket(
            commander,
            RequestTicketRelation(
                uuid4(),
                first.request_id,
                accepted.version,
                1,
                ticket_id,
                "required",
                active=True,
                reason="primary",
            ),
            telemetry=_telemetry(commander, uuid4()),
        ),
    )
    return first, ticket_id, relation


def _assert_ticket_reuse_refused(
    tenant: TenantFixture,
    authority: Requests,
    commander: Actor,
    competing: RequestCaptureResult,
    ticket_id: UUID,
) -> None:
    priority = _accepted_change(
        tenant,
        authority.prioritize(
            commander,
            RequestPriority(uuid4(), competing.request_id, 1, "P2", "reviewed default"),
            telemetry=_telemetry(commander, uuid4()),
        ),
    )
    accepted = _accepted_change(
        tenant,
        authority.triage(
            commander,
            RequestTriage(uuid4(), competing.request_id, priority.version, "ACCEPTED"),
            telemetry=_telemetry(commander, uuid4()),
        ),
    )
    reused = authority.relate_ticket(
        commander,
        RequestTicketRelation(
            uuid4(),
            competing.request_id,
            accepted.version,
            1,
            ticket_id,
            "required",
            active=True,
            reason="not reusable",
        ),
        telemetry=_telemetry(commander, uuid4()),
    )
    assert isinstance(reused, RecordProblem)
    assert reused.code == "request-transition-forbidden"


def _accepted_capture(
    tenant: TenantFixture, authority: Requests, actor: Actor, text: str
) -> RequestCaptureResult:
    command = RequestCapture(uuid4(), "ctower", text)
    result = _capture(authority, actor, command)
    assert isinstance(result, RequestCaptureResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    replay = _capture(authority, actor, command)
    assert isinstance(replay, RequestCaptureResult)
    return replay


def _bound_human(
    record: PostgresRecord,
    tenant: TenantFixture,
    operator: Actor,
    role: str,
) -> Actor:
    subject = f"request-{role}-{uuid4().hex}"
    receipt = record.human_identity.bind_role(
        operator,
        HumanRoleBindingIssue(
            client_command_id=uuid4(),
            display_name=f"Request {role} {uuid4().hex[:8]}",
            oidc_issuer="https://request-acceptance.example.test",
            oidc_subject=subject,
            project_keys=("ctower",),
            role=cast(HumanRole, role),
        ),
        request_digest=hashlib.sha256(subject.encode()).digest(),
        now=datetime.now(UTC),
        telemetry=_telemetry(operator, uuid4()),
    )
    assert not isinstance(receipt, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    resolved = record.human_identity.resolve_role_binding(
        "https://request-acceptance.example.test", subject
    )
    assert resolved is not None
    return resolved[1]


def _accepted_change(tenant: TenantFixture, result: object) -> RequestChangeResult:
    assert isinstance(result, RequestChangeResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return result


def _accepted_ticket(tenant: TenantFixture, actor: Actor) -> UUID:
    command = TicketCommand(
        client_command_id=uuid4(),
        initial_custodian_id=tenant.commander_id,
        priority="P2",
        project_key="ctower",
        source=SourceReference("request-test", f"ticket:{uuid4()}"),
        title="Request fulfillment",
    )
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor, command, telemetry=_telemetry(actor, command.client_command_id)
    )
    assert not isinstance(outcome, RecordProblem)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return outcome.ticket.ticket_id


def _close_ticket_fixture(tenant: TenantFixture, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE lifecycle_episodes SET state = 'closed', closed_at = now()
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        )


def _capture(
    requests: Requests,
    actor: Actor,
    command: RequestCapture,
) -> RequestCaptureResult | RecordProblem:
    return requests.capture(actor, command, telemetry=_telemetry(actor, command.client_command_id))


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )

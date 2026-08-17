"""Real PostgreSQL, API, generated-client, and CLI acceptance for native inbox I1."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from _inbox_cli_roundtrip import RoundTrip as _RoundTrip
from _inbox_cli_roundtrip import _accepted_send as _accepted_cli_send
from _inbox_cli_roundtrip import promote as _promote_cli
from _inbox_cli_roundtrip import roundtrip as _roundtrip
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.server import running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture, provision_seat

from ctower_client import BoardView, CtowerClient
from ctower_kernel.inbox import (
    Inbox,
    InboxAcknowledgeCommand,
    InboxAcknowledgementState,
    InboxAcknowledgeResult,
    InboxPromotionCommand,
    InboxPromotionOutcome,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
    PostgresInbox,
)
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work

__all__: tuple[str, ...] = ()

REPLY_POSITION = 2
_ACCEPTED_STATUS = 201
_DURABILITY_PENDING_STATUS = 202
_NOT_FOUND_STATUS = 404
_ACCEPTED_SEND_STATUS = (_ACCEPTED_STATUS, _DURABILITY_PENDING_STATUS)
_AUTHORED_SEND_FIELDS = (
    "command_id",
    "durability_state",
    "event_ids",
    "from",
    "message_id",
    "position",
    "sent_at",
    "severity",
    "thread_id",
    "thread_version",
    "to",
)
DELIVERY_AND_READ_EVENT_COUNT = 2
CREATE_PROMOTION_EVENT_COUNT = 2


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


@pytest.fixture
def protected_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _MemoryBackend()
    monkeypatch.setattr("ctowerctl.spool._keyring._secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "initial-state"))


def test_native_inbox_cli_roundtrip_and_promotion_links_both_ways(
    tenant: TenantFixture,
    protected_state: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1/V1: promotion without a ticket creates from the head and links both ways."""

    del protected_state
    _qa_id, qa_credential = _provision_qa_seat(tenant)
    roundtrip = _roundtrip(tenant, monkeypatch, tmp_path, qa_credential)
    _assert_roundtrip(roundtrip)
    accepted = _promote_cli(tenant, monkeypatch, tmp_path, roundtrip.thread_id)
    promoted = cast(dict[str, object], accepted["result"])
    ticket_id = UUID(str(promoted["ticket_id"]))
    assert promoted["outcome"] == "ticket_created"
    assert len(cast(list[object], promoted["event_ids"])) == CREATE_PROMOTION_EVENT_COUNT
    _assert_created_ticket(tenant, roundtrip.thread_id, ticket_id)
    _assert_promotion(tenant, roundtrip, promoted, ticket_id)
    _print_transcript(roundtrip, promoted)


def test_inbox_cli_promote_with_ticket_links_existing_ticket_both_ways(
    tenant: TenantFixture,
    protected_state: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2/V2: --ticket preserves the ticket and records the bidirectional context link."""

    del protected_state
    _qa_id, qa_credential = _provision_qa_seat(tenant)
    roundtrip = _roundtrip(tenant, monkeypatch, tmp_path, qa_credential)
    ticket_id = _ticket(tenant)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted = _promote_cli(
        tenant,
        monkeypatch,
        tmp_path,
        roundtrip.thread_id,
        ticket_id=ticket_id,
    )
    promoted = cast(dict[str, object], accepted["result"])
    _assert_promotion(tenant, roundtrip, promoted, ticket_id)
    assert promoted["outcome"] == "ticket_linked"
    assert len(cast(list[object], promoted["event_ids"])) == 1
    _print_transcript(roundtrip, promoted)


def test_native_inbox_authority_replay_refusals_and_recipient_projection(
    tenant: TenantFixture,
) -> None:
    qa_id, _credential = _provision_qa_seat(tenant)
    inbox = Inbox(PostgresInbox(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    qa = Actor(qa_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    command = InboxSendCommand(uuid4(), "qa-agent", "x" * 201)
    first = _invoke_send(inbox, commander, command)
    assert isinstance(first, InboxSendResult)
    assert _invoke_send(inbox, commander, command) == first
    conflict = _invoke_send(
        inbox,
        commander,
        InboxSendCommand(command.client_command_id, "qa-agent", "Changed replay body."),
    )
    _assert_problem(conflict, "idempotency-conflict")
    _assert_problem(
        _invoke_promotion(inbox, commander, first.thread_id, None),
        "inbox-thread-head-invalid",
    )
    _assert_send_refusals(tenant, inbox, commander, first.thread_id)
    _assert_recipient_projection(tenant, inbox, commander, qa, first)


def test_native_inbox_message_round_trip_preserves_severity(
    tenant: TenantFixture,
    protected_state: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del protected_state
    qa_id, _qa_credential = _provision_qa_seat(tenant)
    accepted = _roundtrip_single_send(
        tenant,
        monkeypatch,
        tmp_path,
        severity="P0",
    )
    result = cast(dict[str, object], accepted["result"])
    message_id = UUID(str(result["message_id"]))
    assert result["severity"] == "P0"
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        authority = connection.execute(
            "SELECT severity FROM inbox_messages WHERE tenant_id = %s AND message_id = %s",
            (tenant.tenant_id, message_id),
        ).fetchone()
    assert authority == {"severity": "P0"}
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    read = projections.read_inbox(
        Actor(qa_id, tenant.tenant_id, PrincipalKind.COMMANDER), UUID(str(result["thread_id"]))
    )
    assert read is not None
    assert read.messages[0].severity.value == "P0"


def _roundtrip_single_send(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    severity: str,
) -> dict[str, object]:
    with running_api(
        tenant.database.runtime_dsn,
        projection_dsn=tenant.database.projection_dsn,
    ) as base_url:
        return _accepted_cli_send(
            tenant,
            monkeypatch,
            state=tmp_path / "commander",
            base_url=base_url,
            credential=tenant.commander_credential,
            to="qa-agent",
            text="Severity round-trip.",
            severity=severity,
        )


def _assert_send_refusals(
    tenant: TenantFixture,
    inbox: Inbox,
    commander: Actor,
    thread_id: UUID,
) -> None:
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    cases = (
        (operator, InboxSendCommand(uuid4(), "qa-agent", "No seat."), "inbox-sender-unaddressable"),
        (commander, InboxSendCommand(uuid4(), "qa-agent", ""), "invalid-request"),
        (
            commander,
            InboxSendCommand(uuid4(), "missing-agent", "Missing recipient."),
            "inbox-recipient-not-found",
        ),
        (
            commander,
            InboxSendCommand(uuid4(), "ctower-commander", "Self recipient."),
            "inbox-recipient-self",
        ),
        (
            commander,
            InboxSendCommand(uuid4(), "wrong-agent", "Wrong participant.", thread_id),
            "inbox-thread-participant-mismatch",
        ),
        (
            commander,
            InboxSendCommand(uuid4(), "qa-agent", "Missing thread.", uuid4()),
            "tenant-scope-denied",
        ),
    )
    for actor, command, code in cases:
        _assert_problem(_invoke_send(inbox, actor, command), code)
    provision_seat(tenant, "qa-agent", project_key="other")
    ambiguous = _invoke_send(
        inbox, commander, InboxSendCommand(uuid4(), "qa-agent", "Ambiguous recipient.")
    )
    _assert_problem(ambiguous, "inbox-recipient-ambiguous")


def _assert_recipient_projection(
    tenant: TenantFixture,
    inbox: Inbox,
    commander: Actor,
    qa: Actor,
    first: InboxSendResult,
) -> None:
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    unread = projections.list_inbox(qa, unread=True)
    assert unread.total_unread == 1
    read = projections.read_inbox(qa, first.thread_id)
    assert read is not None and read.read_through_position == 0
    assert projections.list_inbox(qa).total_unread == 1
    acknowledged = _invoke_ack(
        inbox,
        qa,
        InboxAcknowledgeCommand(uuid4(), first.message_id, InboxAcknowledgementState.READ),
    )
    assert isinstance(acknowledged, InboxAcknowledgeResult)
    assert len(acknowledged.event_ids) == DELIVERY_AND_READ_EVENT_COUNT
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    assert projections.list_inbox(qa).total_unread == 0
    state = projections.inbox_read_state(qa, first.thread_id)
    assert state is not None and state.messages[0].state.value == "read"
    _assert_problem(
        _invoke_ack(
            inbox,
            commander,
            InboxAcknowledgeCommand(uuid4(), first.message_id, InboxAcknowledgementState.DELIVERED),
        ),
        "inbox-message-recipient-mismatch",
    )
    _assert_problem(
        _invoke_ack(
            inbox,
            qa,
            InboxAcknowledgeCommand(uuid4(), first.message_id, InboxAcknowledgementState.READ),
        ),
        "inbox-acknowledgement-not-advancing",
    )
    _assert_problem(
        _invoke_ack(
            inbox,
            qa,
            InboxAcknowledgeCommand(uuid4(), uuid4(), InboxAcknowledgementState.READ),
        ),
        "tenant-scope-denied",
    )
    reply = _invoke_send(
        inbox,
        qa,
        InboxSendCommand(uuid4(), "ctower-commander", "Direct reply coverage.", first.thread_id),
    )
    assert isinstance(reply, InboxSendResult) and reply.position == REPLY_POSITION
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    assert projections.list_inbox(commander, unread=True).total_unread == 1
    commander_read = projections.read_inbox(commander, first.thread_id)
    assert commander_read is not None and len(commander_read.messages) == REPLY_POSITION
    _assert_promotion_refusals_and_replay(tenant, inbox, projections, commander, qa, reply)


def _assert_roundtrip(roundtrip: _RoundTrip) -> None:
    assert roundtrip.qa_list["total_unread"] == 1
    acknowledgements = roundtrip.acknowledgements
    initial = cast(list[dict[str, object]], acknowledgements.initial_state["messages"])[0]
    delivered = cast(list[dict[str, object]], acknowledgements.delivered_state["messages"])[0]
    read_state = cast(list[dict[str, object]], acknowledgements.read_state["messages"])[0]
    assert initial["state"] == "sent"
    assert "delivered_event_id" not in initial and "read_event_id" not in initial
    assert cast(dict[str, object], acknowledgements.delivered_ack["result"])["state"] == "delivered"
    assert delivered["state"] == "delivered" and delivered["delivered_event_id"] is not None
    assert "read_event_id" not in delivered
    assert cast(dict[str, object], acknowledgements.read_ack["result"])["state"] == "read"
    assert read_state["state"] == "read"
    assert read_state["delivered_event_id"] == delivered["delivered_event_id"]
    assert read_state["read_event_id"] is not None
    assert acknowledgements.after_ack["total_unread"] == 0
    qa_messages = cast(list[dict[str, object]], roundtrip.qa_read["messages"])
    reply_result = cast(dict[str, object], roundtrip.reply["result"])
    commander_messages = cast(list[dict[str, object]], roundtrip.commander_read["messages"])
    assert qa_messages[0]["text"] == "Please verify the native inbox roundtrip."
    assert roundtrip.qa_read["read_through_position"] == 1
    assert reply_result["position"] == REPLY_POSITION
    assert roundtrip.commander_list["total_unread"] == 1
    assert [item["text"] for item in commander_messages] == [
        "Please verify the native inbox roundtrip.",
        "Verified; the reply is durable.",
    ]


def _assert_promotion(
    tenant: TenantFixture,
    roundtrip: _RoundTrip,
    promoted: dict[str, object],
    ticket_id: UUID,
) -> None:
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    roundtrip.projections.catch_up(tenant.tenant_id)
    board = _api_board(tenant)
    events, subjects, authority_before = _promotion_evidence(
        tenant,
        roundtrip.thread_id,
        UUID(str(cast(list[object], promoted["event_ids"])[0])),
    )
    card = next(item for item in board.cards if item.ticket_id == ticket_id)
    assert card.inbox_thread_ids == (roundtrip.thread_id,)
    assert events == [
        {"kind": "thread.opened", "sequence": 1},
        {"kind": "message.appended", "sequence": 2},
        {"kind": "message.delivered", "sequence": 3},
        {"kind": "message.read", "sequence": 4},
        {"kind": "message.appended", "sequence": 5},
        {"kind": "thread.promoted_to_ticket", "sequence": 6},
    ]
    assert subjects == [
        {"subject_kind": "inbox_thread", "subject_id": roundtrip.thread_id},
        {"subject_kind": "ticket", "subject_id": ticket_id},
    ]
    rebuilt = roundtrip.projections.rebuild(tenant.tenant_id)
    rebuilt_card = next(item for item in rebuilt.cards if item.ticket_id == ticket_id)
    assert rebuilt_card.inbox_thread_ids == (roundtrip.thread_id,)
    authority_after = _authority_counts(tenant, roundtrip.thread_id)
    assert authority_before == authority_after == {"delivery_facts": 2, "messages": 2, "links": 1}


def _assert_created_ticket(tenant: TenantFixture, thread_id: UUID, ticket_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        ticket = connection.execute(
            """
            SELECT title, project_key, source_kind, source_ref, priority,
                   custodian_principal_id, version
            FROM tickets WHERE tenant_id = %s AND ticket_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
        created_events = connection.execute(
            """
            SELECT count(*) AS count FROM events
            WHERE tenant_id = %s AND aggregate_id = %s AND kind = 'ticket.created'
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
    assert ticket == {
        "title": "Please verify the native inbox roundtrip.",
        "project_key": "ctower",
        "source_kind": "inbox",
        "source_ref": f"thread:{thread_id}",
        "priority": "P2",
        "custodian_principal_id": tenant.commander_id,
        "version": 1,
    }
    assert created_events == {"count": 1}


def test_the_send_response_puts_the_authored_field_names_on_the_wire(
    tenant: TenantFixture,
) -> None:
    """A boundary field whose contract name is a Python keyword still ships it.

    ``InboxSendResult.from`` is aliased in the generated model because ``from``
    is a keyword. The durability envelope used to serialize the Python name, so
    the wire carried ``from_`` against an ``additionalProperties: false``
    schema. Both generated clients populate by name as well as by alias, so
    every existing roundtrip accepted it; a strict reader outside them — the
    dogfood surface — is what found it. The assertion is therefore on the raw
    bytes, not on a parsed model.
    """
    _recipient_id, _recipient_credential = provision_seat(tenant, "wire-shape-agent")
    command_id = uuid4()

    with running_api(
        tenant.database.runtime_dsn,
        projection_dsn=tenant.database.projection_dsn,
    ) as base_url:
        response = httpx.post(
            f"{base_url}/v1/inbox/messages",
            headers={
                "Accept": "application/json, application/problem+json",
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Content-Type": "application/json",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
            json={
                "project_key": "ctower",
                "severity": "info",
                "to": "wire-shape-agent",
                "text": "The wire carries the authored names.",
            },
            timeout=30,
        )

    body = cast(dict[str, object], json.loads(response.text))
    assert response.status_code in _ACCEPTED_SEND_STATUS
    assert sorted(body) == sorted(_AUTHORED_SEND_FIELDS)
    assert body["from"] == "ctower-commander"
    assert body["to"] == "wire-shape-agent"
    print("REAL_SEND_WIRE_SHAPE " + json.dumps(sorted(body)))


def test_a_send_is_not_accepted_until_its_durable_receipt_commits(
    tenant: TenantFixture,
) -> None:
    """The two answers a send surface has to tell apart, from the record itself.

    Acceptance means a disaster-recoverable acknowledgement, so an instance
    without one answers a fresh send with the explicit non-accepted state and a
    ``202``. Nothing about that answer's shape says so: it carries the same
    message identity, position and timestamp the accepted answer does, and only
    ``durability_state`` distinguishes a recorded message from one nobody has
    promised to keep. What makes it accepted is the receipt chain, and the same
    command key then replays to that outcome rather than recording a second
    message — which is exactly what a browser send box has to do with an
    unconfirmed message it is still holding.
    """
    _recipient_id, _recipient_credential = provision_seat(tenant, "durability-state-agent")
    command_id = uuid4()
    headers = {
        "Accept": "application/json, application/problem+json",
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Content-Type": "application/json",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }
    request = {
        "project_key": "ctower",
        "severity": "info",
        "to": "durability-state-agent",
        "text": "Not sent until the record says so.",
    }

    with running_api(
        tenant.database.runtime_dsn,
        projection_dsn=tenant.database.projection_dsn,
    ) as base_url:
        unconfirmed = httpx.post(
            f"{base_url}/v1/inbox/messages", headers=headers, json=request, timeout=30
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        replayed = httpx.post(
            f"{base_url}/v1/inbox/messages", headers=headers, json=request, timeout=30
        )

    first = cast(dict[str, object], json.loads(unconfirmed.text))
    second = cast(dict[str, object], json.loads(replayed.text))
    assert unconfirmed.status_code == _DURABILITY_PENDING_STATUS
    assert first["durability_state"] == "durability_pending"
    assert replayed.status_code == _ACCEPTED_STATUS
    assert second["durability_state"] == "accepted"
    # one message replayed, not a second one recorded
    assert second["message_id"] == first["message_id"]
    assert second["position"] == first["position"]
    print(
        f"REAL_SEND_DURABILITY first={unconfirmed.status_code} {first['durability_state']}"
        f" replayed={replayed.status_code} {second['durability_state']}"
        f" message={first['message_id']}"
    )


def _api_board(tenant: TenantFixture) -> BoardView:
    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        return client.get_board(project_key="ctower")


def _promotion_evidence(
    tenant: TenantFixture,
    thread_id: UUID,
    event_id: UUID,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object] | None]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        events = connection.execute(
            """
            SELECT kind, sequence FROM events
            WHERE tenant_id = %s AND aggregate_id = %s ORDER BY sequence
            """,
            (tenant.tenant_id, thread_id),
        ).fetchall()
        subjects = connection.execute(
            """
            SELECT subject_kind, subject_id FROM event_links
            WHERE event_id = %s ORDER BY subject_kind
            """,
            (event_id,),
        ).fetchall()
    return events, subjects, _authority_counts(tenant, thread_id)


def _authority_counts(tenant: TenantFixture, thread_id: UUID) -> dict[str, object] | None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        return connection.execute(
            """
            SELECT (SELECT count(*) FROM inbox_messages WHERE thread_id = %s) AS messages,
                   (SELECT count(*) FROM inbox_ticket_links WHERE thread_id = %s) AS links,
                   (SELECT count(*) FROM inbox_message_delivery_facts WHERE thread_id = %s)
                       AS delivery_facts
            """,
            (thread_id, thread_id, thread_id),
        ).fetchone()


def _print_transcript(roundtrip: _RoundTrip, promoted: dict[str, object]) -> None:
    acknowledgements = roundtrip.acknowledgements
    print(
        "REAL_INBOX_TRANSCRIPT "
        + json.dumps(
            {
                "commander_send": roundtrip.first["result"],
                "qa_list_unread": roundtrip.qa_list,
                "qa_initial_read_state": acknowledgements.initial_state,
                "qa_ack_delivered": acknowledgements.delivered_ack["result"],
                "qa_delivered_read_state": acknowledgements.delivered_state,
                "qa_ack_read": acknowledgements.read_ack["result"],
                "qa_final_read_state": acknowledgements.read_state,
                "qa_list_after_ack": acknowledgements.after_ack,
                "qa_read": roundtrip.qa_read,
                "qa_reply": roundtrip.reply["result"],
                "commander_list_unread": roundtrip.commander_list,
                "commander_read": roundtrip.commander_read,
                "promotion": promoted,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _assert_promotion_refusals_and_replay(
    tenant: TenantFixture,
    inbox: Inbox,
    projections: Projections,
    commander: Actor,
    qa: Actor,
    reply: InboxSendResult,
) -> None:
    ticket_id = _ticket(tenant)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    unavailable_ticket = _invoke_promotion(inbox, commander, reply.thread_id, uuid4())
    _assert_problem(unavailable_ticket, "tenant-scope-denied")
    outsider = _invoke_promotion(
        inbox,
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        reply.thread_id,
        ticket_id,
    )
    _assert_problem(outsider, "tenant-scope-denied")
    create_without_custody = _invoke_promotion(
        inbox,
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        reply.thread_id,
        None,
    )
    _assert_problem(create_without_custody, "unauthorized")
    command_id = uuid4()
    promoted = _invoke_promotion(
        inbox,
        commander,
        reply.thread_id,
        ticket_id,
        command_id=command_id,
    )
    assert isinstance(promoted, InboxPromotionResult)
    assert promoted.outcome is InboxPromotionOutcome.TICKET_LINKED
    replay = _invoke_promotion(
        inbox,
        commander,
        reply.thread_id,
        ticket_id,
        command_id=command_id,
    )
    assert replay == promoted
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    listed = projections.list_inbox(qa)
    assert listed.threads[0].promoted_ticket_id == ticket_id
    already = _invoke_promotion(inbox, commander, reply.thread_id, ticket_id)
    _assert_problem(already, "inbox-already-promoted")
    missing = _invoke_promotion(inbox, commander, uuid4(), ticket_id)
    _assert_problem(missing, "tenant-scope-denied")


def _invoke_send(
    inbox: Inbox,
    actor: Actor,
    command: InboxSendCommand,
) -> InboxSendResult | RecordProblem:
    return inbox.send(
        actor,
        command,
        request_digest=_digest(command.request_payload()),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )


def _invoke_ack(
    inbox: Inbox,
    actor: Actor,
    command: InboxAcknowledgeCommand,
) -> InboxAcknowledgeResult | RecordProblem:
    return inbox.acknowledge(
        actor,
        command,
        request_digest=_digest(command.request_payload()),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )


def _invoke_promotion(
    inbox: Inbox,
    actor: Actor,
    thread_id: UUID,
    ticket_id: UUID | None,
    *,
    command_id: UUID | None = None,
) -> InboxPromotionResult | RecordProblem:
    command = InboxPromotionCommand(command_id or uuid4(), thread_id, ticket_id)
    return inbox.promote(
        actor,
        command,
        request_digest=_digest(command.request_payload()),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )


def _assert_problem(outcome: object, code: str) -> None:
    assert isinstance(outcome, RecordProblem)
    assert outcome.code == code


def _provision_qa_seat(tenant: TenantFixture) -> tuple[UUID, str]:
    return provision_seat(tenant, "qa-agent")


def _ticket(tenant: TenantFixture) -> UUID:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P2",
            project_key="ctower",
            source=SourceReference("inbox", f"promotion:{uuid4()}"),
            title="Promoted inbox thread",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    return outcome.ticket.ticket_id


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).digest()


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )

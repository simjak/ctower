"""Real PostgreSQL, API, generated-client, and CLI acceptance for native inbox I1."""

from __future__ import annotations

import hashlib
import io
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.server import running_api
from support.tenant_fixture import TenantFixture, provision_credential

from ctower_client import BoardView, CtowerClient
from ctower_kernel.inbox import (
    Inbox,
    InboxPromotionCommand,
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
from ctowerctl import main

__all__: tuple[str, ...] = ()

EXIT_SUCCESS = 0
EXIT_TEMPORARY = 75
REPLY_POSITION = 2


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


@dataclass(frozen=True, slots=True)
class _RoundTrip:
    commander_list: dict[str, object]
    commander_read: dict[str, object]
    first: dict[str, object]
    projections: Projections
    qa_list: dict[str, object]
    qa_read: dict[str, object]
    reply: dict[str, object]
    thread_id: UUID


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
    """A1/A2/V1/V2: two agents exchange, read, reply, and promote one thread."""

    del protected_state
    roundtrip = _roundtrip(tenant, monkeypatch, tmp_path)
    _assert_roundtrip(roundtrip)
    promoted, ticket_id = _promote(tenant, roundtrip)
    _assert_promotion(tenant, roundtrip, promoted, ticket_id)
    _print_transcript(roundtrip, promoted)


def test_native_inbox_authority_replay_refusals_and_recipient_projection(
    tenant: TenantFixture,
) -> None:
    qa_id, _credential = _provision_qa_seat(tenant)
    inbox = Inbox(PostgresInbox(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    qa = Actor(qa_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    command = InboxSendCommand(uuid4(), "qa-agent", "Direct authority and replay coverage.")
    first = _invoke_send(inbox, commander, command)
    assert isinstance(first, InboxSendResult)
    assert _invoke_send(inbox, commander, command) == first
    conflict = _invoke_send(
        inbox,
        commander,
        InboxSendCommand(command.client_command_id, "qa-agent", "Changed replay body."),
    )
    _assert_problem(conflict, "idempotency-conflict")
    _assert_send_refusals(tenant, inbox, commander, first.thread_id)
    _assert_recipient_projection(tenant, inbox, commander, qa, first)


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
    _provision_seat(tenant, "qa-agent", project_key="other")
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
    read = projections.read_inbox(qa, first.thread_id, now=datetime.now(UTC))
    assert read is not None and read.read_through_position == 1
    assert projections.list_inbox(qa).total_unread == 0
    reply = _invoke_send(
        inbox,
        qa,
        InboxSendCommand(uuid4(), "ctower-commander", "Direct reply coverage.", first.thread_id),
    )
    assert isinstance(reply, InboxSendResult) and reply.position == REPLY_POSITION
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    assert projections.list_inbox(commander, unread=True).total_unread == 1
    commander_read = projections.read_inbox(commander, first.thread_id, now=datetime.now(UTC))
    assert commander_read is not None and len(commander_read.messages) == REPLY_POSITION
    _assert_promotion_refusals_and_replay(tenant, inbox, projections, commander, qa, reply)


def _roundtrip(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> _RoundTrip:
    _qa_id, qa_credential = _provision_qa_seat(tenant)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    commander_state, qa_state = tmp_path / "commander", tmp_path / "qa"
    with running_api(
        tenant.database.runtime_dsn,
        projection_dsn=tenant.database.projection_dsn,
    ) as base_url:
        first = _accepted_send(
            tenant,
            monkeypatch,
            state=commander_state,
            base_url=base_url,
            credential=tenant.commander_credential,
            to="qa-agent",
            text="Please verify the native inbox roundtrip.",
        )
        first_result = cast(dict[str, object], first["result"])
        thread_id = UUID(str(first_result["thread_id"]))
        projections.catch_up(tenant.tenant_id)
        qa_list = _query(
            monkeypatch,
            qa_state,
            qa_credential,
            ["--base-url", base_url, "inbox", "list", "--unread"],
        )
        qa_read = _query(
            monkeypatch,
            qa_state,
            qa_credential,
            ["--base-url", base_url, "inbox", "read", str(thread_id)],
        )
        reply = _accepted_send(
            tenant,
            monkeypatch,
            state=qa_state,
            base_url=base_url,
            credential=qa_credential,
            to="ctower-commander",
            text="Verified; the reply is durable.",
            thread_id=thread_id,
        )
        projections.catch_up(tenant.tenant_id)
        commander_list, commander_read = _commander_queries(
            tenant, monkeypatch, commander_state, base_url, thread_id
        )
    return _RoundTrip(
        commander_list,
        commander_read,
        first,
        projections,
        qa_list,
        qa_read,
        reply,
        thread_id,
    )


def _commander_queries(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    base_url: str,
    thread_id: UUID,
) -> tuple[dict[str, object], dict[str, object]]:
    listed = _query(
        monkeypatch,
        state,
        tenant.commander_credential,
        ["--base-url", base_url, "inbox", "list", "--unread"],
    )
    read = _query(
        monkeypatch,
        state,
        tenant.commander_credential,
        ["--base-url", base_url, "inbox", "read", str(thread_id)],
    )
    return listed, read


def _assert_roundtrip(roundtrip: _RoundTrip) -> None:
    assert roundtrip.qa_list["total_unread"] == 1
    qa_messages = cast(list[dict[str, object]], roundtrip.qa_read["messages"])
    reply_result = cast(dict[str, object], roundtrip.reply["result"])
    commander_messages = cast(list[dict[str, object]], roundtrip.commander_read["messages"])
    assert qa_messages[0]["text"] == "Please verify the native inbox roundtrip."
    assert reply_result["position"] == REPLY_POSITION
    assert roundtrip.commander_list["total_unread"] == 1
    assert [item["text"] for item in commander_messages] == [
        "Please verify the native inbox roundtrip.",
        "Verified; the reply is durable.",
    ]


def _promote(
    tenant: TenantFixture,
    roundtrip: _RoundTrip,
) -> tuple[InboxPromotionResult, UUID]:
    ticket_id = _ticket(tenant)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    command = InboxPromotionCommand(uuid4(), 3, roundtrip.thread_id, ticket_id)
    promoted = Inbox(PostgresInbox(tenant.database.runtime_dsn)).promote(
        actor,
        command,
        request_digest=_digest(command.request_payload()),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )
    assert isinstance(promoted, InboxPromotionResult)
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    roundtrip.projections.catch_up(tenant.tenant_id)
    return promoted, ticket_id


def _assert_promotion(
    tenant: TenantFixture,
    roundtrip: _RoundTrip,
    promoted: InboxPromotionResult,
    ticket_id: UUID,
) -> None:
    board = _api_board(tenant)
    events, subjects, authority_before = _promotion_evidence(
        tenant, roundtrip.thread_id, promoted.event_id
    )
    card = next(item for item in board.cards if item.ticket_id == ticket_id)
    assert card.inbox_thread_ids == (roundtrip.thread_id,)
    assert events == [
        {"kind": "thread.opened", "sequence": 1},
        {"kind": "message.appended", "sequence": 2},
        {"kind": "message.appended", "sequence": 3},
        {"kind": "thread.promoted_to_ticket", "sequence": 4},
    ]
    assert subjects == [
        {"subject_kind": "inbox_thread", "subject_id": roundtrip.thread_id},
        {"subject_kind": "ticket", "subject_id": ticket_id},
    ]
    rebuilt = roundtrip.projections.rebuild(tenant.tenant_id)
    rebuilt_card = next(item for item in rebuilt.cards if item.ticket_id == ticket_id)
    assert rebuilt_card.inbox_thread_ids == (roundtrip.thread_id,)
    authority_after = _authority_counts(tenant, roundtrip.thread_id)
    assert authority_before == authority_after == {"messages": 2, "links": 1}


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
                   (SELECT count(*) FROM inbox_ticket_links WHERE thread_id = %s) AS links
            """,
            (thread_id, thread_id),
        ).fetchone()


def _print_transcript(roundtrip: _RoundTrip, promoted: InboxPromotionResult) -> None:
    print(
        "REAL_INBOX_TRANSCRIPT "
        + json.dumps(
            {
                "commander_send": roundtrip.first["result"],
                "qa_list_unread": roundtrip.qa_list,
                "qa_read": roundtrip.qa_read,
                "qa_reply": roundtrip.reply["result"],
                "commander_list_unread": roundtrip.commander_list,
                "commander_read": roundtrip.commander_read,
                "promotion": promoted.response_payload(),
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
    unavailable_ticket = _invoke_promotion(
        inbox, commander, reply.thread_id, uuid4(), expected_version=reply.thread_version
    )
    _assert_problem(unavailable_ticket, "tenant-scope-denied")
    outsider = _invoke_promotion(
        inbox,
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        reply.thread_id,
        ticket_id,
        expected_version=reply.thread_version,
    )
    _assert_problem(outsider, "tenant-scope-denied")
    command_id = uuid4()
    promoted = _invoke_promotion(
        inbox,
        commander,
        reply.thread_id,
        ticket_id,
        expected_version=reply.thread_version,
        command_id=command_id,
    )
    assert isinstance(promoted, InboxPromotionResult)
    replay = _invoke_promotion(
        inbox,
        commander,
        reply.thread_id,
        ticket_id,
        expected_version=reply.thread_version,
        command_id=command_id,
    )
    assert replay == promoted
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    listed = projections.list_inbox(qa)
    assert listed.threads[0].promoted_ticket_id == ticket_id
    stale = _invoke_promotion(
        inbox, commander, reply.thread_id, ticket_id, expected_version=reply.thread_version
    )
    _assert_problem(stale, "version-conflict")
    already = _invoke_promotion(
        inbox, commander, reply.thread_id, ticket_id, expected_version=promoted.thread_version
    )
    _assert_problem(already, "inbox-already-promoted")
    missing = _invoke_promotion(inbox, commander, uuid4(), ticket_id, expected_version=1)
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


def _invoke_promotion(
    inbox: Inbox,
    actor: Actor,
    thread_id: UUID,
    ticket_id: UUID,
    *,
    expected_version: int,
    command_id: UUID | None = None,
) -> InboxPromotionResult | RecordProblem:
    command = InboxPromotionCommand(command_id or uuid4(), expected_version, thread_id, ticket_id)
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


def _accepted_send(
    tenant: TenantFixture,
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: Path,
    base_url: str,
    credential: str,
    to: str,
    text: str,
    thread_id: UUID | None = None,
) -> dict[str, object]:
    command_id = uuid4()
    arguments = [
        "--base-url",
        base_url,
        "inbox",
        "send",
        "--command-id",
        str(command_id),
        "--to",
        to,
    ]
    if thread_id is not None:
        arguments.extend(("--thread", str(thread_id)))
    arguments.append(text)
    pending_status, pending = _run(monkeypatch, state, credential, arguments)
    assert pending_status == EXIT_TEMPORARY
    assert pending["state"] == "queued"
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted_status, accepted = _run(monkeypatch, state, credential, arguments)
    assert accepted_status == EXIT_SUCCESS
    assert accepted["state"] == "accepted"
    return accepted


def _query(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    credential: str,
    arguments: list[str],
) -> dict[str, object]:
    status, payload = _run(monkeypatch, state, credential, arguments)
    assert status == EXIT_SUCCESS
    return payload


def _run(
    monkeypatch: pytest.MonkeyPatch,
    state: Path,
    credential: str,
    arguments: list[str],
) -> tuple[int, dict[str, object]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    stdout, stderr = io.StringIO(), io.StringIO()
    status = main(arguments, stdin=io.StringIO(credential + "\n"), stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return status, cast(dict[str, object], json.loads(stdout.getvalue()))


def _provision_qa_seat(tenant: TenantFixture) -> tuple[UUID, str]:
    return _provision_seat(tenant, "qa-agent")


def _provision_seat(
    tenant: TenantFixture,
    seat_key: str,
    *,
    project_key: str = "ctower",
) -> tuple[UUID, str]:
    principal_id, credential = uuid4(), secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'commander', %s, false, %s)
            """,
            (principal_id, tenant.tenant_id, f"Inbox {project_key} {seat_key}", now),
        )
        connection.execute(
            """
            INSERT INTO project_seats (
                principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                principal_id,
                tenant.tenant_id,
                project_key,
                seat_key,
                tenant.operator_id,
                now,
            ),
        )
    provision_credential(tenant.database.admin_dsn, tenant.tenant_id, principal_id, credential)
    return principal_id, credential


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

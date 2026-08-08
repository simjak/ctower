"""Real-PostgreSQL acceptance for the additive mission-control notify bridge."""

from __future__ import annotations

import hashlib
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.server import running_api
from support.tenant_fixture import TenantFixture, provision_credential

from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    InboxNotificationRequest,
    InboxSendRequest,
    InboxSendResult,
)
from ctower_kernel.inbox import Inbox, InboxSendCommand, PostgresInbox
from ctower_kernel.inbox import InboxSendResult as KernelInboxSendResult
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_EXPECTED_COMMAND_EVENTS = 2
_EXPECTED_PAIR_MESSAGES = 2


@dataclass(frozen=True, slots=True)
class _Notification:
    delivery_id: UUID
    to: str
    subject: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.subject}\n\n{self.body}"


def test_notification_ingest_is_idempotent_and_groups_an_unordered_seat_pair(
    tenant: TenantFixture,
) -> None:
    qa_id, qa_credential = _provision_seat(tenant, "qa-agent")
    _designer_id, _designer_credential = _provision_seat(tenant, "designer-agent")
    first_notification = _notification("qa-agent", subject="First handoff")
    reply_notification = _notification("ctower-commander", subject="Reply")
    distinct_notification = _notification("designer-agent", subject="Design handoff")

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as commander_client,
        CtowerClient(base_url, credential=qa_credential) as qa_client,
    ):
        first = _ingest(commander_client, first_notification)
        replay = _ingest(commander_client, first_notification)
        reply = _ingest(qa_client, reply_notification)
        distinct = _ingest(commander_client, distinct_notification)

    assert replay == first
    first_thread = first.thread_id
    assert reply.thread_id == first_thread
    assert distinct.thread_id != first_thread
    assert first.from_ == "ctower-commander"
    assert reply.from_ == "qa-agent"

    trace = _pair_trace(tenant, first_notification.delivery_id, first_thread)
    assert trace["command_events"] == _EXPECTED_COMMAND_EVENTS
    assert trace["message_events"] == 1
    assert trace["messages"] == _EXPECTED_PAIR_MESSAGES
    assert trace["positions"] == [1, 2]
    assert trace["participant_ids"] == sorted([str(tenant.commander_id), str(qa_id)])
    assert trace["message_id"] == str(first.message_id)
    print("REAL_NOTIFY_BRIDGE_DOUBLE_INGEST " + json.dumps(trace, sort_keys=True))


def test_notification_ingest_records_unknown_seat_refusal(
    tenant: TenantFixture,
) -> None:
    notification = _notification("unknown-agent", subject="Unknown destination")

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
        pytest.raises(CtowerProblemError) as raised,
    ):
        _ingest(client, notification)

    assert raised.value.problem.code == "inbox-recipient-not-found"
    refusal = _refusal_trace(tenant, notification.delivery_id)
    assert refusal == {
        "event_count": 0,
        "event_ids": [],
        "problem_code": "inbox-recipient-not-found",
        "status_code": 404,
    }


def test_notification_command_key_cannot_replay_a_standard_inbox_send(
    tenant: TenantFixture,
) -> None:
    _qa_id, _qa_credential = _provision_seat(tenant, "digest-qa")
    command_id = uuid4()
    request = InboxSendRequest(to="digest-qa", text="Domain-separated body.")

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        client.send_inbox_message(request, command_id=command_id)
        with pytest.raises(CtowerProblemError) as raised:
            client.ingest_inbox_notification(
                InboxNotificationRequest(to=request.to, text=request.text),
                command_id=command_id,
            )

    assert raised.value.problem.code == "idempotency-conflict"


def test_concurrent_first_notifications_share_one_pair_thread(tenant: TenantFixture) -> None:
    qa_id, _qa_credential = _provision_seat(tenant, "concurrent-qa")
    inbox = Inbox(PostgresInbox(tenant.database.runtime_dsn))
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    qa = Actor(qa_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    calls = (
        (commander, InboxSendCommand(uuid4(), "concurrent-qa", "First concurrent message.")),
        (qa, InboxSendCommand(uuid4(), "ctower-commander", "Second concurrent message.")),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda item: _ingest_notification(inbox, *item), calls))

    assert all(isinstance(outcome, KernelInboxSendResult) for outcome in outcomes)
    results = cast(tuple[KernelInboxSendResult, KernelInboxSendResult], outcomes)
    assert results[0].thread_id == results[1].thread_id
    assert sorted(result.position for result in results) == [1, 2]


def _notification(to: str, *, subject: str) -> _Notification:
    return _Notification(
        delivery_id=uuid4(),
        to=to,
        subject=subject,
        body="Strict bridge acceptance payload.",
    )


def _ingest(client: CtowerClient, notification: _Notification) -> InboxSendResult:
    return client.ingest_inbox_notification(
        InboxNotificationRequest(to=notification.to, text=notification.text),
        command_id=notification.delivery_id,
    )


def _provision_seat(tenant: TenantFixture, seat_key: str) -> tuple[UUID, str]:
    principal_id, credential = uuid4(), secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, 'commander', %s, false, %s)
            """,
            (principal_id, tenant.tenant_id, f"Inbox seat {seat_key}", now),
        )
        connection.execute(
            """
            INSERT INTO project_seats (
                principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
            ) VALUES (%s, %s, 'ctower', %s, %s, %s)
            """,
            (principal_id, tenant.tenant_id, seat_key, tenant.operator_id, now),
        )
    provision_credential(tenant.database.admin_dsn, tenant.tenant_id, principal_id, credential)
    return principal_id, credential


def _ingest_notification(
    inbox: Inbox,
    actor: Actor,
    command: InboxSendCommand,
) -> KernelInboxSendResult | RecordProblem:
    return inbox.ingest_notification(
        actor,
        command,
        request_digest=hashlib.sha256(
            json.dumps(
                command.request_payload(),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).digest(),
        now=datetime.now(UTC),
        telemetry=_telemetry(),
    )


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


def _pair_trace(
    tenant: TenantFixture,
    command_id: UUID,
    thread_id: UUID,
) -> dict[str, object]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        command = connection.execute(
            """
            SELECT event_ids, response_body FROM command_results
            WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
            """,
            (tenant.tenant_id, tenant.commander_id, command_id),
        ).fetchone()
        events = connection.execute(
            """
            SELECT kind FROM events
            WHERE tenant_id = %s AND client_command_id = %s ORDER BY sequence
            """,
            (tenant.tenant_id, command_id),
        ).fetchall()
        thread = connection.execute(
            """
            SELECT participant_a_id, participant_b_id FROM inbox_threads
            WHERE tenant_id = %s AND thread_id = %s
            """,
            (tenant.tenant_id, thread_id),
        ).fetchone()
        messages = connection.execute(
            """
            SELECT message_id, position FROM inbox_messages
            WHERE tenant_id = %s AND thread_id = %s ORDER BY position
            """,
            (tenant.tenant_id, thread_id),
        ).fetchall()
    assert command is not None and thread is not None
    response = cast(dict[str, object], command["response_body"])
    event_ids = cast(list[UUID], command["event_ids"])
    return {
        "command_events": len(event_ids),
        "message_events": sum(row["kind"] == "message.appended" for row in events),
        "message_id": str(response["message_id"]),
        "messages": len(messages),
        "participant_ids": sorted(
            [str(thread["participant_a_id"]), str(thread["participant_b_id"])]
        ),
        "positions": [row["position"] for row in messages],
    }


def _refusal_trace(tenant: TenantFixture, command_id: UUID) -> dict[str, object]:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT status_code, response_body, event_ids,
                   (SELECT count(*) FROM events
                    WHERE tenant_id = %s AND client_command_id = %s) AS event_count
            FROM command_results
            WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
            """,
            (
                tenant.tenant_id,
                command_id,
                tenant.tenant_id,
                tenant.commander_id,
                command_id,
            ),
        ).fetchone()
    assert row is not None
    response = cast(dict[str, object], row["response_body"])
    return {
        "event_count": row["event_count"],
        "event_ids": row["event_ids"],
        "problem_code": response["code"],
        "status_code": row["status_code"],
    }

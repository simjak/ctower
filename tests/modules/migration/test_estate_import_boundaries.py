"""Boundary vectors for estate-import validation and inbox application."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from ctower_api.estate_import_contracts import _InboxImportPlan
from ctower_api.estate_import_inbox import (
    apply_inbox_plan,
    prepare_inbox_batch,
    prepare_inbox_row,
)
from ctower_api.estate_import_support import (
    _digest_json,
    _inbox_batch_header,
    _manifest_projection,
    _validate_generic_batch_digest,
    _validate_inbox_row,
)
from ctower_kernel.inbox import PostgresInbox
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.inbox_events import InboxParticipant
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


class _Cursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class _Connection:
    def __init__(self, *responses: list[dict[str, object]]) -> None:
        self._responses = iter(responses)

    def execute(self, *_args: object, **_kwargs: object) -> _Cursor:
        return _Cursor(next(self._responses, []))


class _Inbox:
    def __init__(self, send_result: object, acknowledge_result: object) -> None:
        self.send_result = send_result
        self.acknowledge_result = acknowledge_result

    def send(self, *_args: object, **_kwargs: object) -> object:
        return self.send_result

    def acknowledge(self, *_args: object, **_kwargs: object) -> object:
        return self.acknowledge_result


def _actor() -> Actor:
    return Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id="",
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )


def _inbox_row() -> dict[str, object]:
    subject = "Subject"
    body = "Body"
    digest = hashlib.sha256(
        json.dumps({"subject": subject, "body": body}, sort_keys=True).encode()
    ).hexdigest()
    return {
        "message_id": str(uuid4()),
        "source_ref": "inbox.jsonl#1",
        "source_sender": "mapped-sender",
        "source_recipient": "operator",
        "sent_at": "2026-08-15T12:00:00+00:00",
        "subject": subject,
        "body": body,
        "read_state": "read",
        "content_sha256": f"sha256:{digest}",
    }


def _mapped_connection(sender: InboxParticipant, recipient: InboxParticipant) -> _Connection:
    return _Connection(
        [{"principal_id": sender.principal_id, "seat_key": sender.seat_key}],
        [{"principal_id": recipient.principal_id, "seat_key": recipient.seat_key}],
    )


def _mapped_plan(actor: Actor) -> _InboxImportPlan:
    sender = InboxParticipant(uuid4(), "mapped-sender")
    recipient = InboxParticipant(uuid4(), "operator")
    row = _inbox_row()
    plan = prepare_inbox_row(
        cast(Any, _mapped_connection(sender, recipient)),
        actor,
        row,
        uuid4(),
    )
    assert isinstance(plan, _InboxImportPlan)
    assert plan.source_only is False
    assert plan.command is not None
    return plan


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("message_id", "not-a-uuid", "estate-import-row-invalid"),
        ("source_ref", "x" * 513, "estate-import-row-invalid"),
        ("source_sender", "x" * 129, "estate-import-row-invalid"),
        ("subject", "x" * 1025, "estate-import-row-invalid"),
        ("body", "x" * 65537, "estate-import-row-invalid"),
        ("read_state", "archived", "estate-import-row-invalid"),
        ("content_sha256", "sha256:" + "0" * 64, "estate-import-content-mismatch"),
    ],
)
def test_inbox_row_validation_refuses_contract_edges(field: str, value: object, code: str) -> None:
    row = _inbox_row()
    row[field] = value

    result = _validate_inbox_row(row, uuid4())

    assert isinstance(result, RecordProblem)
    assert result.code == code


@pytest.mark.parametrize(
    "artifact",
    [
        {},
        {"batches": [None]},
        {"batches": [{"batch_index": 1, "source_count": 1}]},
        {"batches": [{"batch_index": 0, "source_count": 2}]},
    ],
)
def test_inbox_batch_header_refuses_missing_or_mismatched_declarations(
    artifact: Mapping[str, object],
) -> None:
    result = _inbox_batch_header(artifact, 0, 1, uuid4())

    assert isinstance(result, RecordProblem)
    assert result.code in {"estate-import-batch-invalid", "estate-import-count-mismatch"}


def test_generic_batch_digest_accepts_projection_and_refuses_tampering() -> None:
    row = {
        "source_ref": "state/escapes.jsonl#1",
        "content_sha256": "sha256:" + "1" * 64,
        "natural_key": "escape:one",
        "payload": {"summary": "one"},
    }
    projection = {
        "_disposition": "source_only",
        "content_sha256": row["content_sha256"],
        "source_ref": row["source_ref"],
        "source_seat": "unknown-owner",
        "natural_key": row["natural_key"],
        "target_seat_key": None,
        "payload": row["payload"],
    }
    header = {"batch_digest": _digest_json([projection])}

    assert _validate_generic_batch_digest(header, "company_records", [row], uuid4()) is None
    refused = _validate_generic_batch_digest(
        {"batch_digest": "sha256:" + "0" * 64}, "company_records", [row], uuid4()
    )
    assert isinstance(refused, RecordProblem)
    assert refused.code == "estate-import-batch-digest-mismatch"

    with pytest.raises(ValueError, match="payload"):
        _validate_generic_batch_digest(
            header,
            "company_records",
            [{**row, "payload": "not-a-mapping"}],
            uuid4(),
        )


def test_prepare_inbox_batch_accepts_source_only_rows_and_refuses_duplicates() -> None:
    actor = _actor()
    command_id = uuid4()
    row = _inbox_row()
    first_plan = prepare_inbox_row(cast(Any, _Connection()), actor, row, command_id)
    assert isinstance(first_plan, _InboxImportPlan)
    digest = _digest_json([_manifest_projection(first_plan)])
    artifact = {"batches": [{"batch_index": 0, "source_count": 1, "batch_digest": digest}]}

    prepared = prepare_inbox_batch(cast(Any, _Connection()), actor, artifact, 0, [row], command_id)
    assert isinstance(prepared, tuple)
    assert len(prepared) == 1
    assert prepared[0].source_only is True

    duplicate = prepare_inbox_batch(
        cast(Any, _Connection()),
        actor,
        {"batches": [{"batch_index": 0, "source_count": 2, "batch_digest": digest}]},
        0,
        [row, dict(row)],
        uuid4(),
    )
    assert isinstance(duplicate, RecordProblem)
    assert duplicate.code == "estate-import-duplicate-source"


def test_prepare_inbox_batch_propagates_header_row_and_digest_refusals() -> None:
    actor = _actor()
    command_id = uuid4()
    row = _inbox_row()

    header_problem = prepare_inbox_batch(cast(Any, _Connection()), actor, {}, 0, [row], command_id)
    row_problem = prepare_inbox_batch(
        cast(Any, _Connection()),
        actor,
        {"batches": [{"batch_index": 0, "source_count": 1, "batch_digest": "unused"}]},
        0,
        [{**row, "message_id": "invalid"}],
        command_id,
    )
    digest_problem = prepare_inbox_batch(
        cast(Any, _Connection()),
        actor,
        {"batches": [{"batch_index": 0, "source_count": 1, "batch_digest": "tampered"}]},
        0,
        [row],
        command_id,
    )

    assert isinstance(header_problem, RecordProblem)
    assert header_problem.code == "estate-import-batch-invalid"
    assert isinstance(row_problem, RecordProblem)
    assert row_problem.code == "estate-import-row-invalid"
    assert isinstance(digest_problem, RecordProblem)
    assert digest_problem.code == "estate-import-batch-digest-mismatch"


def test_mapped_inbox_plan_sends_and_acknowledges_with_source_state() -> None:
    actor = _actor()
    command_id = uuid4()
    plan = _mapped_plan(actor)

    result = apply_inbox_plan(
        cast(PostgresInbox, _Inbox(object(), object())),
        cast(Any, _Connection()),
        actor,
        plan,
        command_id=command_id,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        telemetry=_telemetry(actor, command_id),
    )

    assert result is None


def test_mapped_inbox_plan_propagates_send_or_acknowledge_refusals() -> None:
    actor = _actor()
    command_id = uuid4()
    plan = _mapped_plan(actor)
    send_problem = RecordProblem("send-refused", "send", 422, "Send", command_id)
    ack_problem = RecordProblem("ack-refused", "ack", 422, "Ack", command_id)
    common = {
        "connection": cast(Any, _Connection()),
        "actor": actor,
        "plan": plan,
        "command_id": command_id,
        "now": datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        "telemetry": _telemetry(actor, command_id),
    }

    send_result = apply_inbox_plan(cast(PostgresInbox, _Inbox(send_problem, object())), **common)
    ack_result = apply_inbox_plan(cast(PostgresInbox, _Inbox(object(), ack_problem)), **common)

    assert send_result is send_problem
    assert ack_result is ack_problem

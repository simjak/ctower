"""Record Module value behavior through its public Interface."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record import CustodyCommand, RecordProblem, TimelineEvent
from ctower_kernel.record.events import (
    BootstrapCreatedPayload,
    CustodyTransferredPayload,
    EventEnvelope,
    EventKind,
    EventOrigin,
    PoisonDispositionRecordedPayload,
    RoutineOccurrenceRecordedPayload,
    TicketCommentAddedPayload,
    TicketCreatedPayload,
    WorkChangedPayload,
    canonical_event_bytes,
    event_digest,
    ticket_payload_from_mapping,
)
from ctower_kernel.record.inbox_events import (
    InboxMessageAppendedPayload,
    InboxParticipant,
    InboxThreadOpenedPayload,
    InboxThreadPromotedToTicketPayload,
)
from ctower_kernel.record.postgres import PostgresRecord, provision_bootstrap

ROOT = Path(__file__).parents[3]


def test_postgres_adapter_is_owned_by_record_module() -> None:
    assert PostgresRecord.__module__ == "ctower_kernel.record.postgres"


def test_record_event_authority_matches_authored_canonical_vectors() -> None:
    document = json.loads(
        (ROOT / "contracts/domain/events/canonical-vectors.json").read_text(encoding="utf-8")
    )
    vectors = cast(list[dict[str, object]], document["vectors"])

    for vector in vectors:
        mapping = cast(dict[str, object], vector["event"])
        event = _event_from_vector(mapping)
        assert canonical_event_bytes(event).decode() == vector["canonical_json"]
        assert f"sha256:{event_digest(event).hex()}" == vector["event_hash"]


__all__: tuple[str, ...] = ()


def test_version_problem_serializes_stable_rfc_9457_extensions() -> None:
    command_id = uuid4()
    problem = RecordProblem(
        code="version-conflict",
        detail="The ticket changed.",
        status=409,
        title="Ticket version conflict",
        command_id=command_id,
        current_version=7,
    )

    assert problem.response_payload() == {
        "code": "version-conflict",
        "command_id": str(command_id),
        "current_version": 7,
        "detail": "The ticket changed.",
        "status": 409,
        "title": "Ticket version conflict",
        "type": "https://ctower.dev/problems/version-conflict",
    }


def test_custody_command_is_immutable_and_includes_target_aggregate_in_digest_payload() -> None:
    command = CustodyCommand(
        client_command_id=uuid4(),
        expected_version=3,
        from_custodian_id=uuid4(),
        protected_transfer=True,
        reason="Accountable handoff",
        ticket_id=uuid4(),
        to_custodian_id=uuid4(),
    )

    assert command.request_payload()["ticket_id"] == str(command.ticket_id)
    with pytest.raises(FrozenInstanceError):
        command.reason = "rewritten"  # type: ignore[misc]


def test_bootstrap_provision_rejects_capability_above_authored_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_connect(_dsn: str) -> None:
        raise AssertionError("invalid capability reached persistence")

    monkeypatch.setattr("ctower_kernel.record._setup_sql.psycopg.connect", unexpected_connect)

    with pytest.raises(ValueError, match="at most 256 characters"):
        provision_bootstrap(
            "postgresql://unused",
            capability_input=StringIO("x" * 257 + "\n"),
            allowed_origin="127.0.0.1",
            expires_at=datetime.now(UTC),
        )


def test_event_payloads_reject_authored_enum_and_length_violations() -> None:
    with pytest.raises(ValueError, match="priority"):
        TicketCreatedPayload(uuid4(), "P3", "ctower", "source", "ref", "title")
    with pytest.raises(ValueError, match="title"):
        TicketCreatedPayload(uuid4(), "P1", "ctower", "source", "ref", "x" * 201)
    with pytest.raises(ValueError, match="reason"):
        CustodyTransferredPayload(uuid4(), "", uuid4())
    with pytest.raises(ValueError, match="tenant_slug"):
        BootstrapCreatedPayload(uuid4(), "vault", "credential", uuid4(), "vault", uuid4(), "x")


def test_event_envelope_rejects_origin_and_stream_identity_mismatch() -> None:
    aggregate_id = uuid4()
    payload = TicketCreatedPayload(uuid4(), "P1", "ctower", "source", "ref", "title")

    with pytest.raises(ValueError, match="origin"):
        _ticket_event(aggregate_id, payload, origin=EventOrigin.BOOTSTRAP)
    with pytest.raises(ValueError, match="stream"):
        _ticket_event(aggregate_id, payload, stream_id=f"ticket:{uuid4()}")
    with pytest.raises(TypeError, match="requires TicketCreatedPayload"):
        _ticket_event(
            aggregate_id,
            CustodyTransferredPayload(uuid4(), "handoff", uuid4()),
            kind=EventKind.TICKET_CREATED,
        )
    with pytest.raises(TypeError, match="validated EventEnvelope"):
        event_digest(cast(EventEnvelope, {"kind": "invalid"}))


def test_timeline_event_keeps_typed_kind_matched_payload() -> None:
    payload = TicketCreatedPayload(uuid4(), "P1", "ctower", "source", "ref", "title")
    rebuilt = ticket_payload_from_mapping(EventKind.TICKET_CREATED, payload.to_mapping())
    event = TimelineEvent(
        actor_principal_id=uuid4(),
        command_id=uuid4(),
        event_id=uuid4(),
        kind=EventKind.TICKET_CREATED,
        occurred_at=datetime.now(UTC),
        payload=rebuilt,
        sequence=1,
    )

    assert event.response_payload()["payload"] == payload.to_mapping()
    legacy = payload.to_mapping()
    del legacy["project_key"]
    derived = ticket_payload_from_mapping(
        EventKind.TICKET_CREATED,
        legacy,
        legacy_project_key="manibo",
    )
    assert isinstance(derived, TicketCreatedPayload)
    assert derived.project_key == "manibo"
    with pytest.raises(ValueError, match="fields"):
        ticket_payload_from_mapping(
            EventKind.TICKET_CREATED, {**payload.to_mapping(), "extra": "rejected"}
        )
    with pytest.raises(TypeError, match="requires CustodyTransferredPayload"):
        TimelineEvent(
            actor_principal_id=uuid4(),
            command_id=uuid4(),
            event_id=uuid4(),
            kind=EventKind.CUSTODY_TRANSFERRED,
            occurred_at=datetime.now(UTC),
            payload=payload,
            sequence=1,
        )


def _ticket_event(
    aggregate_id: UUID,
    payload: TicketCreatedPayload | CustodyTransferredPayload,
    *,
    kind: EventKind = EventKind.TICKET_CREATED,
    origin: EventOrigin = EventOrigin.API,
    stream_id: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=uuid4(),
        aggregate_id=aggregate_id,
        causation_id=None,
        client_command_id=uuid4(),
        correlation_id=uuid4(),
        event_id=uuid4(),
        kind=kind,
        origin=origin,
        payload=payload,
        prev_hash=bytes(32),
        request_sha256=bytes(32),
        sequence=1,
        server_time=datetime.now(UTC),
        stream_id=stream_id or f"ticket:{aggregate_id}",
        tenant_id=uuid4(),
    )


def _event_from_vector(mapping: dict[str, object]) -> EventEnvelope:
    kind = EventKind(str(mapping["kind"]))
    causation = mapping["causation_id"]
    return EventEnvelope(
        actor_principal_id=UUID(str(mapping["actor_principal_id"])),
        aggregate_id=UUID(str(mapping["aggregate_id"])),
        causation_id=UUID(str(causation)) if causation is not None else None,
        client_command_id=UUID(str(mapping["client_command_id"])),
        correlation_id=UUID(str(mapping["correlation_id"])),
        event_id=UUID(str(mapping["event_id"])),
        kind=kind,
        origin=EventOrigin(str(mapping["origin"])),
        payload=_vector_payload(kind, cast(dict[str, object], mapping["payload"])),
        prev_hash=bytes.fromhex(str(mapping["prev_hash"]).removeprefix("sha256:")),
        request_sha256=bytes.fromhex(str(mapping["request_sha256"]).removeprefix("sha256:")),
        sequence=int(cast(int, mapping["sequence"])),
        server_time=datetime.fromisoformat(str(mapping["server_time"])),
        stream_id=str(mapping["stream_id"]),
        tenant_id=UUID(str(mapping["tenant_id"])),
        schema_version=int(cast(int, mapping["schema_version"])),
    )


def _vector_payload(
    kind: EventKind, payload: dict[str, object]
) -> (
    BootstrapCreatedPayload
    | TicketCreatedPayload
    | CustodyTransferredPayload
    | TicketCommentAddedPayload
    | WorkChangedPayload
    | RoutineOccurrenceRecordedPayload
    | PoisonDispositionRecordedPayload
    | InboxThreadOpenedPayload
    | InboxMessageAppendedPayload
    | InboxThreadPromotedToTicketPayload
):
    if kind is EventKind.BOOTSTRAP_CREATED:
        return BootstrapCreatedPayload(
            UUID(str(payload["commander_id"])),
            str(payload["commander_vault_ref"]),
            str(payload["operator_credential_ref"]),
            UUID(str(payload["operator_id"])),
            str(payload["operator_vault_ref"]),
            UUID(str(payload["tenant_id"])),
            str(payload["tenant_slug"]),
        )
    if kind is EventKind.WORK_CHANGED:
        return WorkChangedPayload(
            operation=str(payload["operation"]),
            ticket_id=UUID(str(payload["ticket_id"])),
            work_version=int(cast(int, payload["work_version"])),
            data=cast(dict[str, object], payload["data"]),
        )
    if kind is EventKind.ROUTINE_OCCURRENCE_RECORDED:
        job_id = payload["job_id"]
        return RoutineOccurrenceRecordedPayload(
            occurrence_id=UUID(str(payload["occurrence_id"])),
            routine_ref=str(payload["routine_ref"]),
            revision_digest=str(payload["revision_digest"]),
            scheduled_for=datetime.fromisoformat(str(payload["scheduled_for"])),
            local_civil_time=str(payload["local_civil_time"]),
            timezone=str(payload["timezone"]),
            utc_offset_seconds=(
                int(cast(int, payload["utc_offset_seconds"]))
                if payload["utc_offset_seconds"] is not None
                else None
            ),
            offset_decision=str(payload["offset_decision"]),
            outcome=str(payload["outcome"]),
            job_id=UUID(str(job_id)) if job_id is not None else None,
        )
    if kind is EventKind.POISON_DISPOSITION_RECORDED:
        return PoisonDispositionRecordedPayload(
            outbox_id=UUID(str(payload["outbox_id"])),
            consumer_key=str(payload["consumer_key"]),
            topic=str(payload["topic"]),
            action=str(payload["action"]),
            reason=str(payload["reason"]),
        )
    if kind in {
        EventKind.INBOX_THREAD_OPENED,
        EventKind.INBOX_MESSAGE_APPENDED,
        EventKind.INBOX_THREAD_PROMOTED_TO_TICKET,
    }:
        return _inbox_vector_payload(kind, payload)
    return ticket_payload_from_mapping(kind, payload)


def _inbox_vector_payload(
    kind: EventKind, payload: dict[str, object]
) -> InboxThreadOpenedPayload | InboxMessageAppendedPayload | InboxThreadPromotedToTicketPayload:
    if kind is EventKind.INBOX_THREAD_OPENED:
        return InboxThreadOpenedPayload(
            _inbox_participant(cast(dict[str, object], payload["opener"])),
            _inbox_participant(cast(dict[str, object], payload["recipient"])),
            UUID(str(payload["thread_id"])),
        )
    if kind is EventKind.INBOX_MESSAGE_APPENDED:
        return InboxMessageAppendedPayload(
            UUID(str(payload["message_id"])),
            int(cast(int, payload["position"])),
            _inbox_participant(cast(dict[str, object], payload["recipient"])),
            _inbox_participant(cast(dict[str, object], payload["sender"])),
            str(payload["text"]),
            UUID(str(payload["thread_id"])),
        )
    if kind is EventKind.INBOX_THREAD_PROMOTED_TO_TICKET:
        return InboxThreadPromotedToTicketPayload(
            UUID(str(payload["thread_id"])), UUID(str(payload["ticket_id"]))
        )
    raise ValueError("not an inbox event kind")


def _inbox_participant(payload: dict[str, object]) -> InboxParticipant:
    return InboxParticipant(UUID(str(payload["principal_id"])), str(payload["seat_key"]))

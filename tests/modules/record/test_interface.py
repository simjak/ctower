"""Record Module value behavior through its public Interface."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record import (
    CustodyCommand,
    ProjectEventCursor,
    ProjectEventPage,
    RecordProblem,
    TimelineEvent,
)
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
    project_event_kinds,
    ticket_payload_from_mapping,
    validate_project_event_payload,
)
from ctower_kernel.record.interface import ProjectEvent
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


def test_project_event_cursor_round_trips_and_rejects_unbound_values() -> None:
    cursor = ProjectEventCursor("bh-loop", 12, 42)

    assert cursor.encode() == "v1:bh-loop:12:42"
    assert ProjectEventCursor.decode(cursor.encode()) == cursor
    for value in (
        "",
        "v2:bh-loop:12:42",
        "v1:BH-loop:12:42",
        "v1:bh-loop:-1:42",
    ):
        with pytest.raises(ValueError, match="malformed"):
            ProjectEventCursor.decode(value)
    with pytest.raises(ValueError, match="record domain"):
        ProjectEventCursor("ctower", 1, 9_223_372_036_854_775_808)
    with pytest.raises(ValueError, match="both be zero or positive"):
        ProjectEventCursor("ctower", 0, 1)


def test_project_event_payload_pairing_is_validated_by_the_catalog() -> None:
    payload = TicketCreatedPayload(uuid4(), "P1", "ctower", "source", "ref", "title")

    validate_project_event_payload(EventKind.TICKET_CREATED, payload)
    with pytest.raises(TypeError, match=r"work\.changed requires WorkChangedPayload"):
        validate_project_event_payload(EventKind.WORK_CHANGED, payload)
    with pytest.raises(ValueError, match="not project-feed scoped"):
        validate_project_event_payload(EventKind.BOOTSTRAP_CREATED, payload)


def test_project_event_and_page_emit_one_strict_cursor_ordered_value() -> None:
    event = _project_event(acceptance_position=2, record_position=7)
    page = ProjectEventPage(
        project_key="ctower",
        events=(event,),
        next_cursor=ProjectEventCursor("ctower", 2, 7),
        has_more=False,
        source_watermark=2,
    )

    assert page.response_payload() == {
        "events": [event.response_payload()],
        "has_more": False,
        "next_cursor": "v1:ctower:2:7",
        "project_key": "ctower",
        "source_watermark": 2,
    }
    with pytest.raises(ValueError, match="not project-feed scoped"):
        replace(event, kind=EventKind.BOOTSTRAP_CREATED)
    with pytest.raises(TypeError, match="requires WorkChangedPayload"):
        replace(event, kind=EventKind.WORK_CHANGED)
    with pytest.raises(ValueError, match="positions and sequence"):
        replace(event, acceptance_position=0)


def test_project_event_page_rejects_invalid_scope_watermark_order_and_cursor() -> None:
    first = _project_event(acceptance_position=1, record_position=7)
    second = _project_event(acceptance_position=2, record_position=9)

    with pytest.raises(ValueError, match="invalid project key"):
        _project_page(first, second, project_key="CTOWER")
    with pytest.raises(ValueError, match="bind the page project"):
        _project_page(first, second, next_cursor=ProjectEventCursor("manibo", 2, 9))
    with pytest.raises(ValueError, match="nonnegative integer"):
        _project_page(first, second, source_watermark=-1)
    with pytest.raises(ValueError, match="strictly cursor ordered"):
        _project_page(first, second, events=(second, first))
    with pytest.raises(ValueError, match="strictly cursor ordered"):
        _project_page(first, second, events=(first, replace(first, event_id=uuid4())))
    with pytest.raises(ValueError, match="cannot precede"):
        _project_page(first, second, source_watermark=1)
    with pytest.raises(ValueError, match="follow the final event"):
        _project_page(first, second, next_cursor=ProjectEventCursor("ctower", 2, 8))


def test_project_event_contract_derives_exact_kind_set_from_authoritative_catalog() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))

    _assert_project_event_kind_parity(document)


@pytest.mark.parametrize("mutation", ("catalog-added", "feed-added"))
def test_project_event_catalog_drift_guard_rejects_mutated_contract_copy(
    mutation: str,
) -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    mutated = deepcopy(document)
    components = cast(dict[str, object], mutated["components"])
    schemas = cast(dict[str, object], components["schemas"])
    event_schema = cast(dict[str, object], schemas["ProjectEvent"])
    union = cast(list[dict[str, str]], event_schema["oneOf"])
    if mutation == "catalog-added":
        union.pop()
    else:
        extra = deepcopy(cast(dict[str, object], schemas["ProjectTicketCreatedEvent"]))
        properties = cast(dict[str, object], extra["properties"])
        properties["kind"] = {"const": "session.recorded"}
        schemas["ProjectSessionRecordedEvent"] = extra
        union.append({"$ref": "#/components/schemas/ProjectSessionRecordedEvent"})

    with pytest.raises(AssertionError, match="project event catalog/contract drift"):
        _assert_project_event_kind_parity(mutated)


def _assert_project_event_kind_parity(document: dict[str, object]) -> None:
    components = cast(dict[str, dict[str, object]], document["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])
    branches = cast(list[dict[str, str]], schemas["ProjectEvent"]["oneOf"])
    contract_kinds = {
        cast(
            str,
            cast(
                dict[str, dict[str, object]],
                schemas[branch["$ref"].removeprefix("#/components/schemas/")]["properties"],
            )["kind"]["const"],
        )
        for branch in branches
    }
    catalog_kinds = {kind.value for kind in project_event_kinds()}
    assert contract_kinds == catalog_kinds, (
        "project event catalog/contract drift: "
        f"catalog={sorted(catalog_kinds)} contract={sorted(contract_kinds)}"
    )


def _project_event(*, acceptance_position: int, record_position: int) -> ProjectEvent:
    ticket_id = uuid4()
    return ProjectEvent(
        acceptance_position=acceptance_position,
        actor_principal_id=uuid4(),
        aggregate_id=ticket_id,
        client_command_id=uuid4(),
        event_id=uuid4(),
        kind=EventKind.TICKET_CREATED,
        occurred_at=datetime.now(UTC),
        payload=TicketCreatedPayload(uuid4(), "P2", "ctower", "test", "ref", "title"),
        record_position=record_position,
        sequence=1,
        stream_id=f"ticket:{ticket_id}",
    )


def _project_page(
    first: ProjectEvent,
    second: ProjectEvent,
    *,
    project_key: str = "ctower",
    events: tuple[ProjectEvent, ...] | None = None,
    next_cursor: ProjectEventCursor | None = None,
    source_watermark: int = 2,
) -> ProjectEventPage:
    return ProjectEventPage(
        project_key=project_key,
        events=events if events is not None else (first, second),
        next_cursor=next_cursor or ProjectEventCursor("ctower", 2, 9),
        has_more=False,
        source_watermark=source_watermark,
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
    return ticket_payload_from_mapping(kind, payload)

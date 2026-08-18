"""Coverage for cross-event aggregate identity refusals.

Every case drives the public `EventEnvelope` constructor, which is the only
authored way in: `__post_init__` derives the expected stream from the aggregate
and then asks each cross-event identity rule. A case therefore states the wrong
aggregate *and* the stream that aggregate implies, so the stream check passes and
the identity rule under test is the one that refuses.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.bootstrap_events import BootstrapCreatedPayload
from ctower_kernel.record.catalog_events import (
    CatalogComponentPublishedPayload,
    CatalogComponentReference,
)
from ctower_kernel.record.credentials import CredentialScope, SeatCredentialIssuedPayload
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    EventPayload,
    RoutineOccurrenceRecordedPayload,
    event_catalog,
)
from ctower_kernel.record.poison_events import PoisonDispositionRecordedPayload
from ctower_kernel.record.session_events import SessionStartedPayload
from ctower_kernel.record.spawn_events import (
    SpawnRecordedPayload,
    SpawnState,
    SpawnTransitionedPayload,
)
from ctower_kernel.record.ticket_events import TicketCommentAddedPayload

__all__: tuple[str, ...] = ()

_NOW = datetime(2026, 8, 18, tzinfo=UTC)
_DIGEST = "sha256:" + "3" * 64
_SUBJECT = UUID("00000000-0000-4000-8000-000000000001")
_FOREIGN = UUID("00000000-0000-4000-8000-0000000000ff")
_TENANT = UUID("00000000-0000-4000-8000-000000000002")


def _authored_origin(kind: EventKind) -> EventOrigin:
    """Take the origin from the catalog so a case never re-types the authored set."""

    entry = next(item for item in event_catalog() if item.kind is kind)
    return min(entry.origins)


def _envelope(
    kind: EventKind,
    payload: EventPayload,
    *,
    aggregate_id: UUID,
    stream_id: str,
    client_command_id: UUID = _SUBJECT,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=uuid4(),
        aggregate_id=aggregate_id,
        causation_id=None,
        client_command_id=client_command_id,
        correlation_id=uuid4(),
        event_id=uuid4(),
        kind=kind,
        origin=_authored_origin(kind),
        payload=payload,
        prev_hash=bytes(32),
        request_sha256=bytes.fromhex("1" * 64),
        sequence=1,
        server_time=_NOW,
        stream_id=stream_id,
        tenant_id=_TENANT,
    )


def _bootstrap() -> BootstrapCreatedPayload:
    return BootstrapCreatedPayload(
        uuid4(), "vault", "credential", uuid4(), "vault", _TENANT, "ctower"
    )


def _comment() -> TicketCommentAddedPayload:
    return TicketCommentAddedPayload(
        body="Independent evidence is attached.",
        comment_id=uuid4(),
        ticket_id=_SUBJECT,
    )


def _catalog() -> CatalogComponentPublishedPayload:
    return CatalogComponentPublishedPayload(
        component=CatalogComponentReference(
            content_digest=_DIGEST,
            key="example.component",
            kind="workflow",
            revision=1,
        ),
        object_version="version-1",
        payload_ref="object:" + _DIGEST,
    )


def _occurrence() -> RoutineOccurrenceRecordedPayload:
    return RoutineOccurrenceRecordedPayload(
        occurrence_id=_SUBJECT,
        routine_ref="ctower.beat.fleet@1",
        revision_digest="sha256:" + "2" * 64,
        scheduled_for=_NOW,
        local_civil_time="2026-08-18T03:00:00",
        timezone="Europe/Vilnius",
        utc_offset_seconds=10800,
        offset_decision="exact",
        outcome="skipped",
        job_id=None,
    )


def _poison() -> PoisonDispositionRecordedPayload:
    return PoisonDispositionRecordedPayload(
        outbox_id=uuid4(),
        consumer_key="projection",
        topic="ticket",
        action="tombstone",
        reason="unparseable payload",
    )


def _credential() -> SeatCredentialIssuedPayload:
    return SeatCredentialIssuedPayload(
        credential_id=_SUBJECT,
        credential_ref="vault://seat/engineer",
        principal_id=uuid4(),
        project_key="ctower",
        scopes=(CredentialScope.CAPTURE,),
        seat_key="engineer",
    )


def _session() -> SessionStartedPayload:
    return SessionStartedPayload(
        branch_ref="feat/r3000-spawn-custody",
        crew_name="engineer-506-rebase",
        harness_ref="claude-code",
        model_ref="claude-opus-5",
        seat_key="engineer",
        session_id=_SUBJECT,
        ticket_id=uuid4(),
        worktree_ref="/srv/projects/ctower/.worktrees/r3000-spawn",
    )


def _spawn_recorded() -> SpawnRecordedPayload:
    return SpawnRecordedPayload(
        spawn_id=_SUBJECT,
        project_key="ctower",
        seat_key="engineer",
        crew_name="mc-engineer-r3000-spawn",
        task_file_ref="coordination/2026-08-18_1350--engineer-506-repair.task.md",
        worktree_path="/srv/projects/ctower/.worktrees/r3000-spawn",
        harness="claude-code",
        model="claude-opus-5",
        effort="high",
        workspace_id=None,
    )


def _spawn_transitioned() -> SpawnTransitionedPayload:
    return SpawnTransitionedPayload(
        spawn_id=_SUBJECT,
        from_state=SpawnState.REQUESTED,
        to_state=SpawnState.ACCEPTED,
        transition_number=1,
        reason="operator GO",
    )


def test_identity_refuses_a_stream_that_does_not_match_its_aggregate() -> None:
    with pytest.raises(ValueError, match="stream"):
        _envelope(
            EventKind.TICKET_COMMENT_ADDED,
            _comment(),
            aggregate_id=_SUBJECT,
            stream_id=f"ticket:{_FOREIGN}",
        )


@pytest.mark.parametrize(
    ("kind", "build", "prefix", "message"),
    (
        (EventKind.TICKET_COMMENT_ADDED, _comment, "ticket", "comment"),
        (EventKind.ROUTINE_OCCURRENCE_RECORDED, _occurrence, "routine-occurrence", "Routine"),
        (EventKind.SEAT_CREDENTIAL_ISSUED, _credential, "seat-credential", "credential"),
        (EventKind.SESSION_STARTED, _session, "session", "session"),
        (EventKind.CATALOG_COMPONENT_PUBLISHED, _catalog, "catalog", "Catalog"),
        (EventKind.BOOTSTRAP_CREATED, _bootstrap, "tenant", "bootstrap"),
        (EventKind.SPAWN_RECORDED, _spawn_recorded, "spawn-record", "spawn"),
        (EventKind.SPAWN_TRANSITIONED, _spawn_transitioned, "spawn-record", "spawn"),
    ),
    ids=(
        "comment",
        "occurrence",
        "credential",
        "session",
        "catalog",
        "bootstrap",
        "spawn-recorded",
        "spawn-transitioned",
    ),
)
def test_identity_refuses_an_aggregate_that_disagrees_with_its_payload(
    kind: EventKind,
    build: Callable[[], EventPayload],
    prefix: str,
    message: str,
) -> None:
    """The aggregate is foreign and the stream follows it, so identity is what refuses."""

    stream_id = (
        f"tenant:{_FOREIGN}:bootstrap"
        if kind is EventKind.BOOTSTRAP_CREATED
        else f"{prefix}:{_FOREIGN}"
    )
    with pytest.raises(ValueError, match=message):
        _envelope(kind, build(), aggregate_id=_FOREIGN, stream_id=stream_id)


def test_identity_refuses_a_poison_aggregate_that_is_not_its_command() -> None:
    with pytest.raises(ValueError, match="poison"):
        _envelope(
            EventKind.POISON_DISPOSITION_RECORDED,
            _poison(),
            aggregate_id=_FOREIGN,
            stream_id=f"poison-disposition:{_FOREIGN}",
            client_command_id=_SUBJECT,
        )


def test_identity_accepts_every_aggregate_that_matches_its_payload() -> None:
    """The passthrough arm of each rule: a rule leaves a payload it does not claim alone."""

    accepted = (
        _envelope(
            EventKind.TICKET_COMMENT_ADDED,
            _comment(),
            aggregate_id=_SUBJECT,
            stream_id=f"ticket:{_SUBJECT}",
        ),
        _envelope(
            EventKind.SESSION_STARTED,
            _session(),
            aggregate_id=_SUBJECT,
            stream_id=f"session:{_SUBJECT}",
        ),
        _envelope(
            EventKind.SEAT_CREDENTIAL_ISSUED,
            _credential(),
            aggregate_id=_SUBJECT,
            stream_id=f"seat-credential:{_SUBJECT}",
        ),
        _envelope(
            EventKind.POISON_DISPOSITION_RECORDED,
            _poison(),
            aggregate_id=_SUBJECT,
            stream_id=f"poison-disposition:{_SUBJECT}",
        ),
        _envelope(
            EventKind.CATALOG_COMPONENT_PUBLISHED,
            _catalog(),
            aggregate_id=_TENANT,
            stream_id=f"catalog:{_TENANT}",
        ),
        _envelope(
            EventKind.ROUTINE_OCCURRENCE_RECORDED,
            _occurrence(),
            aggregate_id=_SUBJECT,
            stream_id=f"routine-occurrence:{_SUBJECT}",
        ),
    )

    assert [event.aggregate_id for event in accepted] == [
        _SUBJECT,
        _SUBJECT,
        _SUBJECT,
        _SUBJECT,
        _TENANT,
        _SUBJECT,
    ]

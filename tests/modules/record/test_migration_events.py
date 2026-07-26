"""Restricted migration event variants reject privilege substitution."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    MigrationChangedPayload,
)

__all__: tuple[str, ...] = ()


def test_migration_event_requires_allowlisted_payload_and_origin() -> None:
    run_id, cutover_id = uuid4(), uuid4()
    payload = MigrationChangedPayload(
        "source_link", run_id, cutover_id, "ctower", "artifact:synthetic"
    )
    event = _event(payload, run_id, EventOrigin.MIGRATION_IMPORTER)

    assert event.kind is EventKind.MIGRATION_CHANGED
    with pytest.raises(ValueError, match="unauthorized origin"):
        _event(payload, run_id, EventOrigin.BOOTSTRAP)
    with pytest.raises(ValueError, match="outside the restricted"):
        MigrationChangedPayload("proof_verdict", run_id, cutover_id, "ctower", "proof")


def _event(payload: MigrationChangedPayload, run_id: UUID, origin: EventOrigin) -> EventEnvelope:
    actor_id, command_id, event_id, tenant_id = uuid4(), uuid4(), uuid4(), uuid4()
    return EventEnvelope(
        actor_principal_id=actor_id,
        aggregate_id=run_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=command_id,
        event_id=event_id,
        kind=EventKind.MIGRATION_CHANGED,
        origin=origin,
        payload=payload,
        prev_hash=bytes(32),
        request_sha256=bytes(32),
        sequence=1,
        server_time=datetime.now(UTC),
        stream_id=f"migration:{run_id}",
        tenant_id=tenant_id,
    )

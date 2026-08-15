"""Morning digest HTTP-source and date boundaries."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from uuid import uuid4

import pytest
from psycopg import OperationalError

from ctower_api import _morning_digest_routes as routes
from ctower_kernel.projections.morning_digest import ReadingState, UnreachedScope
from ctower_kernel.record import Actor, PrincipalKind, Record
from ctower_kernel.record.movement_events import MovementCountList, MovementCountRow
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.requests import Requests
from ctower_kernel.work.rulings import Rulings

__all__: tuple[str, ...] = ()

_MOVEMENT_WATERMARK = 47


class _UnavailableSource:
    def list(self, actor: Actor, *, telemetry: TelemetryContext) -> object:
        del actor, telemetry
        raise OperationalError("source is unavailable")


class _MovementAudit:
    def movement_counts(self, actor: Actor, *, telemetry: TelemetryContext) -> MovementCountList:
        del actor, telemetry
        return MovementCountList(
            rows=(
                MovementCountRow(
                    project_key="ctower",
                    source_stage="capture",
                    stage="frame",
                    occurred_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
                ),
            ),
            watermark=47,
            observed_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
        )


class _MovementRecord:
    event_audit = _MovementAudit()


def test_source_exceptions_become_independent_unknown_readings() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    command_id = uuid4()
    telemetry = TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="1" * 32,
        span_id="2" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )
    observed_at = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)

    request_reading = routes._request_source_reading(
        cast(Requests, _UnavailableSource()), actor, telemetry, observed_at
    )
    ruling_reading = routes._ruling_source_reading(
        cast(Rulings, _UnavailableSource()), actor, telemetry, observed_at
    )

    assert request_reading.state is ReadingState.UNKNOWN
    assert request_reading.unreached == (UnreachedScope("requests", "request-source-unavailable"),)
    assert ruling_reading.state is ReadingState.UNKNOWN
    assert ruling_reading.unreached == (UnreachedScope("rulings", "ruling-source-unavailable"),)


def test_movement_source_reading_uses_the_record_cursor_and_preserves_watermark() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    command_id = uuid4()
    telemetry = TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="1" * 32,
        span_id="2" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )

    reading = routes._movement_source_reading(
        cast(Record, _MovementRecord()), actor, telemetry, datetime.now(UTC)
    )

    assert reading.state is ReadingState.COMPLETE
    assert reading.watermark == _MOVEMENT_WATERMARK
    assert reading.rows[0].project_key == "ctower"


def test_digest_date_refuses_a_non_rfc3339_basic_shape() -> None:
    observed_at = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="full-date"):
        routes._digest_date("20260810", observed_at)


def test_omitted_digest_date_uses_the_vilnius_civil_day() -> None:
    observed_at = datetime(2026, 8, 9, 21, 30, tzinfo=UTC)

    assert routes._digest_date(None, observed_at) == date(2026, 8, 10)

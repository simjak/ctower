"""Morning digest HTTP-source failure boundaries."""

from __future__ import annotations

from datetime import UTC as _UTC
from datetime import datetime as _datetime
from typing import cast as _cast
from uuid import uuid4 as _uuid4

import pytest as _pytest
from psycopg import OperationalError as _OperationalError

from ctower_api import _morning_digest_routes as _routes
from ctower_kernel.projections.morning_digest import ReadingState as _ReadingState
from ctower_kernel.projections.morning_digest import UnreachedScope as _UnreachedScope
from ctower_kernel.record import Actor as _Actor
from ctower_kernel.record import PrincipalKind as _PrincipalKind
from ctower_kernel.telemetry import TelemetryContext as _TelemetryContext
from ctower_kernel.work.requests import Requests as _Requests
from ctower_kernel.work.rulings import Rulings as _Rulings

__all__: tuple[str, ...] = ()


class _UnavailableSource:
    def list(self, actor: _Actor, *, telemetry: _TelemetryContext) -> object:
        del actor, telemetry
        raise _OperationalError("source is unavailable")


def test_source_exceptions_become_independent_unknown_readings() -> None:
    actor = _Actor(_uuid4(), _uuid4(), _PrincipalKind.OPERATOR)
    command_id = _uuid4()
    telemetry = _TelemetryContext(
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
    observed_at = _datetime(2026, 8, 10, 5, 0, tzinfo=_UTC)

    request_reading = _routes._request_source_reading(
        _cast(_Requests, _UnavailableSource()), actor, telemetry, observed_at
    )
    ruling_reading = _routes._ruling_source_reading(
        _cast(_Rulings, _UnavailableSource()), actor, telemetry, observed_at
    )

    assert request_reading.state is _ReadingState.UNKNOWN
    assert request_reading.unreached == (_UnreachedScope("requests", "request-source-unavailable"),)
    assert ruling_reading.state is _ReadingState.UNKNOWN
    assert ruling_reading.unreached == (_UnreachedScope("rulings", "ruling-source-unavailable"),)


def test_digest_date_refuses_a_non_rfc3339_basic_shape() -> None:
    observed_at = _datetime(2026, 8, 10, 5, 0, tzinfo=_UTC)

    with _pytest.raises(ValueError, match="full-date"):
        _routes._digest_date("20260810", observed_at)

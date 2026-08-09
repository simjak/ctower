"""GitLab transport scenarios bound to the shared connector admission harness."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, NoReturn, cast
from uuid import UUID, uuid4

import httpx

from ctower_api.connectors.gitlab import (
    GitLabConnectorConfig,
    GitLabCursor,
    GitLabIssueConnector,
)
from ctower_kernel.integrations import (
    CloseExternalIssue,
    ConnectorAttempt,
    ConnectorCursorToken,
    ConnectorRetryExecutor,
    FetchIssuePage,
    FetchIssuePageResult,
)
from modules.integrations.connector_conformance import (
    CloseObservation,
    ReconciliationOutcome,
    RetryObservation,
    TransportReason,
)

__all__ = ["GitLabOutcomeFixture"]

_DELIVERY_ID = UUID("22222222-2222-4222-8222-222222222222")
_MAX_ATTEMPTS: Literal[4] = 4
_SECOND_ATTEMPT = 2


class _RetryClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class GitLabOutcomeFixture:
    def fetch_status(self, status: int) -> FetchIssuePageResult:
        connector = _connector(
            httpx.MockTransport(lambda request: httpx.Response(status, request=request))
        )
        return connector.fetch_page(_request(), _attempt())

    def close_status(self, status: int) -> CloseObservation:
        marker_reads = 0
        marker_writes = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal marker_reads, marker_writes
            if request.method == "GET":
                marker_reads += 1
                return httpx.Response(200, request=request, json=[])
            marker_writes += 1
            return httpx.Response(status, request=request)

        result = _connector(httpx.MockTransport(handler)).comment_and_close(_command(), _attempt())
        return CloseObservation(result, marker_reads, marker_writes)

    def fetch_transport(self, reason: TransportReason) -> FetchIssuePageResult:
        def handler(request: httpx.Request) -> httpx.Response:
            _raise_transport(reason, request)

        return _connector(httpx.MockTransport(handler)).fetch_page(_request(), _attempt())

    def close_transport(self, reason: TransportReason) -> CloseObservation:
        marker_reads = 0
        marker_writes = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal marker_reads, marker_writes
            if request.method == "GET":
                marker_reads += 1
                return httpx.Response(200, request=request, json=[])
            marker_writes += 1
            _raise_transport(reason, request)

        result = _connector(httpx.MockTransport(handler)).comment_and_close(_command(), _attempt())
        return CloseObservation(result, marker_reads, marker_writes)

    def ambiguous_write(self, outcome: ReconciliationOutcome) -> CloseObservation:
        marker_reads = 0
        marker_writes = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal marker_reads, marker_writes
            if request.method == "GET":
                marker_reads += 1
                if marker_reads == 1:
                    return httpx.Response(200, request=request, json=[])
                if outcome == "inconclusive":
                    raise httpx.RemoteProtocolError("reconciliation reset", request=request)
                notes = [{"body": _command().marker}] if outcome == "found" else []
                return httpx.Response(200, request=request, json=notes)
            if request.method == "POST":
                marker_writes += 1
                raise httpx.ReadError("write response lost", request=request)
            if request.method == "PUT" and outcome == "found":
                return httpx.Response(200, request=request, json={"state": "closed"})
            raise AssertionError(f"unexpected request {request.method} {request.url}")

        result = _connector(httpx.MockTransport(handler)).comment_and_close(_command(), _attempt())
        return CloseObservation(result, marker_reads, marker_writes)

    def retry_sequence(self) -> RetryObservation:
        attempts = 0
        clock = _RetryClock()

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.ReadTimeout("timeout", request=request)
            if attempts == _SECOND_ATTEMPT:
                return httpx.Response(429, request=request)
            if attempts == _MAX_ATTEMPTS - 1:
                return httpx.Response(503, request=request)
            return httpx.Response(200, request=request, json=_provider_issue())

        result = self._retry_fetch(handler, clock, jitter=lambda ceiling: ceiling / 2)
        return RetryObservation(result, attempts, tuple(clock.sleeps), clock.now)

    def retry_exhaustion(self) -> RetryObservation:
        attempts = 0
        clock = _RetryClock()

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, request=request)

        result = self._retry_fetch(handler, clock, jitter=lambda ceiling: ceiling)
        return RetryObservation(result, attempts, tuple(clock.sleeps), clock.now)

    def deadline_exhaustion(self) -> RetryObservation:
        attempts = 0
        timeouts: list[float] = []
        clock = _RetryClock()

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            timeout = cast(dict[str, float], request.extensions["timeout"])["read"]
            timeouts.append(timeout)
            clock.now += timeout
            raise httpx.ReadTimeout("deadline", request=request)

        result = self._retry_fetch(handler, clock, jitter=lambda ceiling: ceiling)
        return RetryObservation(
            result,
            attempts,
            tuple(clock.sleeps),
            clock.now,
            tuple(timeouts),
        )

    @staticmethod
    def _retry_fetch(
        handler: Callable[[httpx.Request], httpx.Response],
        clock: _RetryClock,
        *,
        jitter: Callable[[float], float],
    ) -> FetchIssuePageResult:
        connector = _connector(
            httpx.MockTransport(handler),
            monotonic=clock.monotonic,
        )
        retry = ConnectorRetryExecutor(
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            jitter=jitter,
        )
        return retry.fetch(connector, _request())


def _attempt() -> ConnectorAttempt:
    return ConnectorAttempt(
        attempt_number=1,
        max_attempts=_MAX_ATTEMPTS,
        deadline_remaining_milliseconds=10_000,
    )


def _request() -> FetchIssuePage:
    cursor = GitLabCursor(updated_after=datetime(2026, 8, 8, 8, tzinfo=UTC), page=1)
    return FetchIssuePage(cursor=ConnectorCursorToken(value=cursor.encode()), page_size=50)


def _command() -> CloseExternalIssue:
    return CloseExternalIssue(
        external_ref="gitlab:42:7",
        command_id=_DELIVERY_ID,
        marker=f"<!-- ctower-sync:{_DELIVERY_ID} -->",
        comment="Proof-gated close",
    )


def _provider_issue() -> list[dict[str, object]]:
    return [
        {
            "project_id": 42,
            "iid": 7,
            "title": "Feedback title",
            "description": "Feedback body",
            "labels": ["bug"],
            "author": {"username": "reporter", "name": "Report Person"},
            "state": "opened",
            "web_url": "https://gitlab.example.test/group/project/-/issues/7",
            "updated_at": "2026-08-08T08:01:00Z",
        }
    ]


def _connector(
    handler: httpx.MockTransport,
    *,
    monotonic: Callable[[], float] | None = None,
) -> GitLabIssueConnector:
    return GitLabIssueConnector(
        GitLabConnectorConfig(base_url="https://gitlab.example.test", project_id=42),
        token=str(uuid4()),
        client=httpx.Client(transport=handler),
        monotonic=monotonic or time.monotonic,
    )


def _raise_transport(reason: TransportReason, request: httpx.Request) -> NoReturn:
    if reason == "transport_connect":
        raise httpx.ConnectError("connect failed", request=request)
    if reason == "transport_read":
        raise httpx.ReadError("read failed", request=request)
    raise httpx.RemoteProtocolError("protocol failed", request=request)

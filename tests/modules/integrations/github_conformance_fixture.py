"""GitHub transport scenarios bound to the frozen connector outcome harness."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import timedelta
from typing import NoReturn, cast
from uuid import UUID

import httpx

from ctower_api.connectors.github import GitHubAppAuth, GitHubCursor, GitHubIssueConnector
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
from modules.integrations.github_test_support import (
    Clock,
    MintingTransport,
    connector_config,
    private_key_pem,
)

__all__ = ["GitHubOutcomeFixture"]


class _RetryClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class GitHubOutcomeFixture:
    def fetch_status(self, status: int) -> FetchIssuePageResult:
        return _connector(lambda request: httpx.Response(status, request=request)).fetch_page(
            _request(), _attempt()
        )

    def close_status(self, status: int) -> CloseObservation:
        reads = writes = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal reads, writes
            if request.method == "GET":
                reads += 1
                return httpx.Response(200, request=request, json=[])
            writes += 1
            return httpx.Response(status, request=request)

        result = _connector(handler).comment_and_close(_command(), _attempt())
        return CloseObservation(result, reads, writes)

    def fetch_transport(self, reason: TransportReason) -> FetchIssuePageResult:
        def handler(request: httpx.Request) -> httpx.Response:
            _raise(reason, request)

        return _connector(handler).fetch_page(_request(), _attempt())

    def close_transport(self, reason: TransportReason) -> CloseObservation:
        reads = writes = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal reads, writes
            if request.method == "GET":
                reads += 1
                return httpx.Response(200, request=request, json=[])
            writes += 1
            _raise(reason, request)

        result = _connector(handler).comment_and_close(_command(), _attempt())
        return CloseObservation(result, reads, writes)

    def ambiguous_write(self, outcome: ReconciliationOutcome) -> CloseObservation:
        reads = writes = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal reads, writes
            if request.method == "GET" and request.url.path.endswith("/comments"):
                reads += 1
                if reads == 1:
                    return httpx.Response(200, request=request, json=[])
                if outcome == "inconclusive":
                    raise httpx.RemoteProtocolError("reset", request=request)
                return httpx.Response(
                    200,
                    request=request,
                    json=[{"body": _command().marker}] if outcome == "found" else [],
                )
            if request.method == "POST":
                writes += 1
                raise httpx.ReadError("response lost", request=request)
            if request.method == "PATCH" and outcome == "found":
                return httpx.Response(200, request=request, json={"state": "closed"})
            raise AssertionError(request)

        result = _connector(handler).comment_and_close(_command(), _attempt())
        return CloseObservation(result, reads, writes)

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
            if attempts == _THIRD_ATTEMPT:
                return httpx.Response(503, request=request)
            return httpx.Response(200, request=request, json=[_issue()])

        result = self._retry(handler, clock, jitter=lambda ceiling: ceiling / 2)
        return RetryObservation(result, attempts, tuple(clock.sleeps), clock.now)

    def retry_exhaustion(self) -> RetryObservation:
        attempts = 0
        clock = _RetryClock()

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, request=request)

        result = self._retry(handler, clock, jitter=lambda ceiling: ceiling)
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

        result = self._retry(handler, clock, jitter=lambda ceiling: ceiling)
        return RetryObservation(result, attempts, tuple(clock.sleeps), clock.now, tuple(timeouts))

    @staticmethod
    def _retry(
        handler: Callable[[httpx.Request], httpx.Response],
        clock: _RetryClock,
        *,
        jitter: Callable[[float], float],
    ) -> FetchIssuePageResult:
        retry = ConnectorRetryExecutor(sleep=clock.sleep, monotonic=clock.monotonic, jitter=jitter)
        return retry.fetch(_connector(handler, monotonic=clock.monotonic), _request())


def _connector(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> GitHubIssueConnector:
    clock = Clock()
    config = connector_config()
    mint = MintingTransport(clock)
    auth = GitHubAppAuth(
        config,
        resolve_private_key=lambda _binding, _revision: private_key_pem(),
        client=httpx.Client(transport=httpx.MockTransport(mint.handle)),
        clock=clock,
    )
    auth.installation_token()
    return GitHubIssueConnector(
        config,
        auth=auth,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        monotonic=monotonic,
    )


def _attempt() -> ConnectorAttempt:
    return ConnectorAttempt(
        attempt_number=1, max_attempts=4, deadline_remaining_milliseconds=10_000
    )


def _request() -> FetchIssuePage:
    cursor = GitHubCursor(updated_at=Clock().now - timedelta(days=1), issue_id=0, page=1)
    return FetchIssuePage(cursor=ConnectorCursorToken(value=cursor.encode()), page_size=50)


def _command() -> CloseExternalIssue:
    delivery = UUID("22222222-2222-4222-8222-222222222222")
    return CloseExternalIssue(
        external_ref="github:98765:7",
        command_id=delivery,
        marker=f"<!-- ctower-sync:{delivery} -->",
        comment="Proof-gated close",
    )


def _issue() -> dict[str, object]:
    return {
        "id": 70,
        "number": 7,
        "title": "Feedback",
        "body": "Body",
        "labels": [{"name": "bug"}],
        "user": {"id": 42, "login": "reporter"},
        "state": "open",
        "updated_at": Clock().now.isoformat(),
        "html_url": "https://github.com/ctower/feedback/issues/7",
        "repository_url": "https://api.github.com/repos/ctower/feedback",
    }


def _raise(reason: TransportReason, request: httpx.Request) -> NoReturn:
    if reason == "transport_connect":
        raise httpx.ConnectError("connect", request=request)
    if reason == "transport_read":
        raise httpx.ReadError("read", request=request)
    raise httpx.RemoteProtocolError("protocol", request=request)


_SECOND_ATTEMPT = 2
_THIRD_ATTEMPT = 3

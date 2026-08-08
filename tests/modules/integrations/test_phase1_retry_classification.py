"""Phase-1 fixed retry-classification gate rows from CX-08."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx

from ctower_api.connectors.gitlab import GitLabConnectorConfig, GitLabIssueConnector
from ctower_api.connectors.gitlab.adapter import GitLabCursor
from ctower_kernel.integrations import (
    CloseExternalIssue,
    CloseFailure,
    ConnectorAttempt,
    ConnectorCursorToken,
    FetchFailure,
    FetchIssuePage,
)

__all__: tuple[str, ...] = ()

_PROJECT_ID = 42
_EXTERNAL_REF = "gitlab:42:7"
_COMMAND_ID = UUID("22222222-2222-4222-8222-222222222222")
_RESOLVED_CREDENTIAL = str(UUID("11111111-1111-4111-8111-111111111111"))


def test_phase1_retry_classifies_connect_error() -> None:
    _assert_fetch_classification(httpx.ConnectError, "transport_connect")
    _assert_close_classification(
        httpx.ConnectError,
        "transport_connect",
        expected_disposition="not_written",
    )


def test_phase1_retry_classifies_read_error() -> None:
    _assert_fetch_classification(httpx.ReadError, "transport_read")
    _assert_close_classification(
        httpx.ReadError,
        "transport_read",
        expected_disposition="reconciled_absent",
    )


def test_phase1_retry_classifies_remote_protocol_error() -> None:
    _assert_fetch_classification(httpx.RemoteProtocolError, "transport_protocol")
    _assert_close_classification(
        httpx.RemoteProtocolError,
        "transport_protocol",
        expected_disposition="reconciled_absent",
    )


def _assert_fetch_classification(
    error_type: type[httpx.RequestError], expected_reason: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_type("injected transport failure", request=request)

    connector = _connector(handler)
    result = connector.fetch_page(
        FetchIssuePage(
            cursor=ConnectorCursorToken(
                value=GitLabCursor(
                    updated_after=datetime(2026, 8, 8, 8, tzinfo=UTC),
                    page=1,
                ).encode()
            ),
            page_size=50,
        ),
        ConnectorAttempt(
            attempt_number=1,
            max_attempts=4,
            deadline_remaining_milliseconds=10_000,
        ),
    )

    assert isinstance(result, FetchFailure)
    assert result.kind == "fetch_failure"
    assert result.retry_class == "retryable"
    assert result.reason == expected_reason


def _assert_close_classification(
    error_type: type[httpx.RequestError],
    expected_reason: str,
    *,
    expected_disposition: str,
) -> None:
    post_attempted = False
    note_gets = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal note_gets, post_attempted
        if request.method == "GET" and request.url.path.endswith("/notes"):
            note_gets += 1
            return httpx.Response(200, request=request, json=[])
        if request.method == "POST" and request.url.path.endswith("/notes"):
            post_attempted = True
            raise error_type("injected close transport failure", request=request)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    result = _connector(handler).comment_and_close(
        CloseExternalIssue(
            external_ref=_EXTERNAL_REF,
            command_id=_COMMAND_ID,
            marker=f"<!-- ctower-sync:{_COMMAND_ID} -->",
            comment="Proof-gated close",
        ),
        ConnectorAttempt(
            attempt_number=1,
            max_attempts=4,
            deadline_remaining_milliseconds=10_000,
        ),
    )

    assert post_attempted
    assert note_gets == (1 if error_type is httpx.ConnectError else 2)
    assert isinstance(result, CloseFailure)
    assert result.kind == "close_failure"
    assert result.retry_class == "retryable"
    assert result.reason == expected_reason
    assert result.write_disposition == expected_disposition


def _connector(
    handler: Callable[[httpx.Request], httpx.Response],
) -> GitLabIssueConnector:
    return GitLabIssueConnector(
        GitLabConnectorConfig(
            base_url="https://gitlab.example.test",
            project_id=_PROJECT_ID,
        ),
        token=_RESOLVED_CREDENTIAL,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

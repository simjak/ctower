"""Shared protocol conformance plus GitLab transport-specific boundary proofs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest

from ctower_api.connectors.gitlab import (
    GitLabConnectorConfig,
    GitLabCursor,
    GitLabIssueConnector,
)
from ctower_kernel.integrations import (
    AmbiguousWrite,
    CloseExternalIssue,
    CloseFailure,
    ConnectorAttempt,
    ConnectorCursorToken,
    ConnectorReceipt,
    ConnectorRetryExecutor,
    ExternalIssue,
    ExternalIssuePage,
    FetchFailure,
    FetchIssuePage,
    IssueConnector,
)
from modules.integrations.connector_conformance import run_outcome_conformance
from modules.integrations.gitlab_conformance_fixture import GitLabOutcomeFixture

__all__: tuple[str, ...] = ()

DELIVERY_ID = UUID("22222222-2222-4222-8222-222222222222")
EXPECTED_CLOSE_CALLS = 2
EXPECTED_RETRY_ATTEMPTS = 4
NEXT_PAGE = 2
PAGE_SIZE = 50
MAX_ELAPSED_SECONDS = 10.0


def _attempt(number: int = 1) -> ConnectorAttempt:
    return ConnectorAttempt(
        attempt_number=number,
        max_attempts=4,
        deadline_remaining_milliseconds=10_000,
    )


def _cursor(*, page: int = 1) -> ConnectorCursorToken:
    return ConnectorCursorToken(
        value=GitLabCursor(
            updated_after=datetime(2026, 8, 8, 8, tzinfo=UTC),
            page=page,
        ).encode()
    )


def _request() -> FetchIssuePage:
    return FetchIssuePage(cursor=_cursor(), page_size=50)


def _command() -> CloseExternalIssue:
    return CloseExternalIssue(
        external_ref="gitlab:42:7",
        command_id=DELIVERY_ID,
        marker=f"<!-- ctower-sync:{DELIVERY_ID} -->",
        comment="Proof-gated close",
    )


def _issue() -> ExternalIssue:
    return ExternalIssue(
        connector_kind="gitlab-issue",
        external_ref="gitlab:42:7",
        title="Feedback title",
        description="Feedback body",
        source_labels=("bug",),
        reporter_reference="@reporter",
        reporter_display_name="Report Person",
        external_state="opened",
        display_url="https://gitlab.example.test/group/project/-/issues/7",
        updated_at=datetime(2026, 8, 8, 8, 1, tzinfo=UTC),
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
            "documented_but_unused_field": True,
        }
    ]


def _connector(
    handler: httpx.MockTransport | None = None,
    *,
    token: str | None = None,
    monotonic: object | None = None,
) -> GitLabIssueConnector:
    kwargs: dict[str, object] = {}
    if handler is not None:
        kwargs["client"] = httpx.Client(transport=handler)
    if monotonic is not None:
        kwargs["monotonic"] = monotonic
    return GitLabIssueConnector(
        GitLabConnectorConfig(base_url="https://gitlab.example.test", project_id=42),
        token=token or str(uuid4()),
        **kwargs,  # type: ignore[arg-type]
    )


def run_conformance_suite(connector: IssueConnector) -> None:
    page = connector.fetch_page(_request(), _attempt())
    assert isinstance(page, ExternalIssuePage)
    assert page.issues == (_issue(),)

    first = connector.comment_and_close(_command(), _attempt())
    replay = connector.comment_and_close(_command(), _attempt())
    assert first == ConnectorReceipt(command_id=DELIVERY_ID, comment_created=True)
    assert replay == ConnectorReceipt(command_id=DELIVERY_ID, comment_created=False)


class _FakeConnector:
    def __init__(self) -> None:
        self._delivered: set[UUID] = set()

    def fetch_page(self, request: FetchIssuePage, attempt: ConnectorAttempt) -> ExternalIssuePage:
        assert request.page_size == PAGE_SIZE and attempt.max_attempts == EXPECTED_RETRY_ATTEMPTS
        return ExternalIssuePage(issues=(_issue(),), next_cursor=_cursor(page=2), exhausted=False)

    def comment_and_close(
        self, command: CloseExternalIssue, attempt: ConnectorAttempt
    ) -> ConnectorReceipt:
        assert command.external_ref == "gitlab:42:7" and attempt.attempt_number == 1
        created = command.command_id not in self._delivered
        self._delivered.add(command.command_id)
        return ConnectorReceipt(command_id=command.command_id, comment_created=created)


def test_fake_adapter_passes_conformance() -> None:
    run_conformance_suite(_FakeConnector())


def test_real_http_adapter_passes_conformance_and_bounds_requests() -> None:
    notes: list[str] = []
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path.endswith("/issues"):
            return httpx.Response(200, request=request, json=_provider_issue())
        if request.method == "GET" and request.url.path.endswith("/notes"):
            return httpx.Response(
                200, request=request, json=[{"body": body} for body in reversed(notes)]
            )
        if request.method == "POST" and request.url.path.endswith("/notes"):
            posted = cast(dict[str, str], httpx.Response(200, content=request.read()).json())[
                "body"
            ]
            notes.append(posted)
            return httpx.Response(201, request=request, json={"body": posted})
        if request.method == "PUT" and request.url.path.endswith("/7"):
            return httpx.Response(200, request=request, json={"state": "closed"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    resolved_value = str(uuid4())
    connector = _connector(
        httpx.MockTransport(handler),
        token=resolved_value,
    )
    run_conformance_suite(connector)

    issue_request = requests[0]
    assert issue_request.url.params["per_page"] == "50"
    assert issue_request.url.params["page"] == "1"
    assert issue_request.url.params["updated_after"].startswith("2026-08-08T08:00:00")
    assert len([request for request in requests if request.method == "POST"]) == 1
    assert len([request for request in requests if request.method == "PUT"]) == EXPECTED_CLOSE_CALLS
    assert all(request.headers["private-token"] == resolved_value for request in requests)


@pytest.mark.parametrize(
    "payload",
    [
        {"not": "an array"},
        _provider_issue() * 51,
        [{**_provider_issue()[0], "labels": "bug"}],
        [{**_provider_issue()[0], "labels": [1]}],
        [{**_provider_issue()[0], "description": 42}],
        [{**_provider_issue()[0], "author": []}],
        [
            {
                **_provider_issue()[0],
                "author": {"username": "not valid", "name": "Report Person"},
            }
        ],
        [{**_provider_issue()[0], "project_id": True}],
        [{**_provider_issue()[0], "project_id": 43}],
        [{**_provider_issue()[0], "title": None}],
        [{**_provider_issue()[0], "updated_at": "not-a-date"}],
        [{**_provider_issue()[0], "updated_at": "2026-08-08T08:01:00"}],
        [{**_provider_issue()[0], "state": "merged"}],
    ],
)
def test_real_adapter_refuses_malformed_issue_list_variants(payload: object) -> None:
    connector = _connector(
        httpx.MockTransport(lambda request: httpx.Response(200, request=request, json=payload))
    )

    result = connector.fetch_page(_request(), _attempt())

    assert result == FetchFailure(retry_class="terminal", reason="invalid_payload")


def test_real_adapter_rejects_malformed_provider_payload() -> None:
    payload = [{**_provider_issue()[0], "project_id": "42"}]
    connector = _connector(
        httpx.MockTransport(lambda request: httpx.Response(200, request=request, json=payload))
    )

    result = connector.fetch_page(_request(), _attempt())

    assert result == FetchFailure(retry_class="terminal", reason="invalid_payload")


def test_real_adapter_advances_only_the_bounded_provider_page() -> None:
    connector = _connector(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers={"X-Next-Page": "2"},
                json=_provider_issue(),
            )
        )
    )

    result = connector.fetch_page(_request(), _attempt())

    assert isinstance(result, ExternalIssuePage)
    assert GitLabCursor.decode(result.next_cursor).page == NEXT_PAGE
    assert not result.exhausted


@pytest.mark.parametrize(
    "base_url",
    [
        "http://gitlab.example.test",
        "https:///missing-host",
        "https://gitlab.example.test?query=forbidden",
        "https://gitlab.example.test#fragment-forbidden",
        "https://user@gitlab.example.test",
    ],
)
def test_real_adapter_refuses_non_origin_base_urls(base_url: str) -> None:
    with pytest.raises(ValueError, match="base URL"):
        GitLabConnectorConfig(base_url=base_url, project_id=42)


@pytest.mark.parametrize("token", ["", "x" * 2049])
def test_real_adapter_refuses_missing_or_unbounded_credentials(token: str) -> None:
    with pytest.raises(ValueError, match="credential"):
        GitLabIssueConnector(
            GitLabConnectorConfig(base_url="https://gitlab.example.test", project_id=42),
            token=token,
        )


def test_real_adapter_closes_only_the_client_it_owns() -> None:
    with _connector() as owned:
        owned_client = owned._client
    assert owned_client.is_closed

    external_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    )
    connector = GitLabIssueConnector(
        GitLabConnectorConfig(base_url="https://gitlab.example.test", project_id=42),
        token=str(uuid4()),
        client=external_client,
    )
    connector.close()
    assert not external_client.is_closed
    external_client.close()


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Next-Page": "not-numeric"},
        {"X-Next-Page": "1"},
        {"Link": '<https://gitlab.example.test/issues?page=next>; rel="next"'},
        {"Link": '<https://gitlab.example.test/issues?page=1>; rel="next"'},
    ],
)
def test_real_adapter_refuses_nonadvancing_pagination(headers: dict[str, str]) -> None:
    connector = _connector(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, request=request, headers=headers, json=_provider_issue()
            )
        )
    )

    result = connector.fetch_page(_request(), _attempt())

    assert result == FetchFailure(retry_class="terminal", reason="invalid_payload")


def test_real_adapter_accepts_link_pagination_and_ignores_unrelated_links() -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                headers={"Link": '<https://gitlab.example.test/issues?page=2>; rel="next"'},
                json=_provider_issue(),
            ),
            httpx.Response(
                200,
                headers={"Link": '<https://gitlab.example.test/issues?page=2>; rel="prev"'},
                json=_provider_issue(),
            ),
        ]
    )
    connector = _connector(httpx.MockTransport(lambda _request: next(responses)))

    first = connector.fetch_page(_request(), _attempt())
    second = connector.fetch_page(_request(), _attempt())

    assert isinstance(first, ExternalIssuePage)
    assert isinstance(second, ExternalIssuePage)
    assert GitLabCursor.decode(first.next_cursor).page == NEXT_PAGE
    assert second.exhausted


@pytest.mark.parametrize(
    "status,retry_class,reason",
    [
        (401, "terminal", "authentication"),
        (403, "terminal", "authorization"),
        (400, "terminal", "ordinary_4xx"),
        (429, "retryable", "throttled"),
        (503, "retryable", "provider_5xx"),
    ],
)
def test_real_connector_classifies_provider_statuses(
    status: int, retry_class: str, reason: str
) -> None:
    connector = _connector(
        httpx.MockTransport(lambda request: httpx.Response(status, request=request))
    )

    result = connector.fetch_page(_request(), _attempt())

    assert isinstance(result, FetchFailure)
    assert (result.retry_class, result.reason) == (retry_class, reason)


@pytest.mark.parametrize(
    "status,retry_class,reason,write_disposition,expected_note_gets",
    [
        (401, "terminal", "authentication", "not_written", 1),
        (403, "terminal", "authorization", "not_written", 1),
        (400, "terminal", "ordinary_4xx", "not_written", 1),
        (429, "retryable", "throttled", "reconciled_absent", 2),
        (503, "retryable", "provider_5xx", "reconciled_absent", 2),
    ],
)
def test_real_connector_classifies_close_statuses_and_reconciles_before_retryable(
    status: int,
    retry_class: str,
    reason: str,
    write_disposition: str,
    expected_note_gets: int,
) -> None:
    note_gets = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal note_gets
        if request.method == "GET" and request.url.path.endswith("/notes"):
            note_gets += 1
            return httpx.Response(200, request=request, json=[])
        if request.method == "POST" and request.url.path.endswith("/notes"):
            return httpx.Response(status, request=request)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    result = _connector(httpx.MockTransport(handler)).comment_and_close(_command(), _attempt())

    assert isinstance(result, CloseFailure)
    assert (result.retry_class, result.reason) == (retry_class, reason)
    assert result.write_disposition == write_disposition
    assert note_gets == expected_note_gets


def test_real_adapter_wraps_http_and_non_json_failures() -> None:
    responses = iter(
        [
            httpx.Response(400, json={"message": "failed"}),
            httpx.Response(200, content=b"not-json"),
        ]
    )
    connector = _connector(httpx.MockTransport(lambda _request: next(responses)))

    http_failure = connector.fetch_page(_request(), _attempt())
    json_failure = connector.fetch_page(_request(), _attempt())

    assert http_failure == FetchFailure(retry_class="terminal", reason="ordinary_4xx")
    assert json_failure == FetchFailure(retry_class="terminal", reason="invalid_payload")


class _RetryClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_gitlab_passes_unchanged_shared_outcome_conformance() -> None:
    run_outcome_conformance(GitLabOutcomeFixture())


class _UnexpectedConnectorError(Exception):
    pass


class _EscapingConnector:
    def fetch_page(self, _request: FetchIssuePage, _attempt: ConnectorAttempt) -> ExternalIssuePage:
        raise _UnexpectedConnectorError

    def comment_and_close(
        self, _command: CloseExternalIssue, _attempt: ConnectorAttempt
    ) -> ConnectorReceipt:
        raise _UnexpectedConnectorError


def test_core_converts_escaped_adapter_exceptions_to_terminal_contract_failures() -> None:
    retry = ConnectorRetryExecutor()

    fetch = retry.fetch(_EscapingConnector(), _request())
    close = retry.close(_EscapingConnector(), _command())

    assert fetch == FetchFailure(retry_class="terminal", reason="contract_violation")
    assert close == CloseFailure(
        retry_class="terminal",
        reason="contract_violation",
        write_disposition="not_written",
    )


def test_real_adapter_retries_timeout_429_and_5xx_with_bounded_jitter() -> None:
    attempts = 0
    clock = _RetryClock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        if attempts == NEXT_PAGE:
            return httpx.Response(429, request=request)
        if attempts == EXPECTED_RETRY_ATTEMPTS - 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, request=request, json=_provider_issue())

    connector = _connector(httpx.MockTransport(handler), monotonic=clock.monotonic)
    retry = ConnectorRetryExecutor(
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        jitter=lambda ceiling: ceiling / 2,
    )

    result = retry.fetch(connector, _request())

    assert isinstance(result, ExternalIssuePage)
    assert attempts == EXPECTED_RETRY_ATTEMPTS
    assert clock.sleeps == sorted(clock.sleeps)
    assert len(clock.sleeps) == EXPECTED_RETRY_ATTEMPTS - 1


def test_real_adapter_retry_exhaustion_is_capped() -> None:
    attempts = 0
    clock = _RetryClock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    connector = _connector(httpx.MockTransport(handler), monotonic=clock.monotonic)
    retry = ConnectorRetryExecutor(
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        jitter=lambda ceiling: ceiling,
    )

    result = retry.fetch(connector, _request())

    assert result == FetchFailure(retry_class="retryable", reason="provider_5xx")
    assert attempts == EXPECTED_RETRY_ATTEMPTS
    assert len(clock.sleeps) == EXPECTED_RETRY_ATTEMPTS - 1


def test_real_adapter_retry_deadline_bounds_request_timeouts() -> None:
    clock = _RetryClock()
    timeouts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeout = cast(dict[str, float], request.extensions["timeout"])["read"]
        timeouts.append(timeout)
        clock.now += timeout
        raise httpx.ReadTimeout("deadline", request=request)

    connector = _connector(httpx.MockTransport(handler), monotonic=clock.monotonic)
    retry = ConnectorRetryExecutor(
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        jitter=lambda ceiling: ceiling,
    )

    result = retry.fetch(connector, _request())

    assert result == FetchFailure(retry_class="retryable", reason="timeout")
    assert all(timeout <= MAX_ELAPSED_SECONDS for timeout in timeouts)
    assert clock.now <= MAX_ELAPSED_SECONDS


def test_real_adapter_reconciles_marker_after_ambiguous_note_write() -> None:
    notes: list[str] = []
    note_posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal note_posts
        if request.method == "GET" and request.url.path.endswith("/notes"):
            return httpx.Response(200, request=request, json=[{"body": body} for body in notes])
        if request.method == "POST":
            note_posts += 1
            notes.append(f"Proof-gated close\n\n{_command().marker}")
            raise httpx.ReadTimeout("response lost after write", request=request)
        if request.method == "PUT":
            return httpx.Response(200, request=request, json={"state": "closed"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    result = _connector(httpx.MockTransport(handler)).comment_and_close(_command(), _attempt())

    assert result == ConnectorReceipt(command_id=DELIVERY_ID, comment_created=True)
    assert note_posts == 1


def test_real_connector_returns_reconciled_absent_before_retrying_a_write() -> None:
    gets = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal gets
        if request.method == "GET":
            gets += 1
            return httpx.Response(200, request=request, json=[])
        raise httpx.ReadError("write response lost", request=request)

    result = _connector(httpx.MockTransport(handler)).comment_and_close(_command(), _attempt())

    assert result == CloseFailure(
        retry_class="retryable",
        reason="transport_read",
        write_disposition="reconciled_absent",
    )
    assert gets == NEXT_PAGE


def test_real_connector_returns_ambiguous_write_when_reconciliation_is_inconclusive() -> None:
    gets = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal gets
        if request.method == "GET":
            gets += 1
            if gets == 1:
                return httpx.Response(200, request=request, json=[])
        raise httpx.RemoteProtocolError("connection reset", request=request)

    result = _connector(httpx.MockTransport(handler)).comment_and_close(_command(), _attempt())

    assert result == AmbiguousWrite()
    assert gets == NEXT_PAGE


@pytest.mark.parametrize("notes", [{"not": "an array"}, [{"body": "note"}] * 101])
def test_real_adapter_refuses_unbounded_note_pages(notes: object) -> None:
    connector = _connector(
        httpx.MockTransport(lambda request: httpx.Response(200, request=request, json=notes))
    )

    result = connector.comment_and_close(_command(), _attempt())

    assert result == CloseFailure(
        retry_class="terminal",
        reason="invalid_payload",
        write_disposition="not_written",
    )


def test_real_adapter_refuses_wrong_created_marker_and_unclosed_issue() -> None:
    wrong_marker_responses = iter(
        [
            httpx.Response(200, json=[]),
            httpx.Response(201, json={"body": "marker missing"}),
            httpx.Response(200, json=[]),
        ]
    )
    wrong_marker = _connector(httpx.MockTransport(lambda _request: next(wrong_marker_responses)))

    marker_result = wrong_marker.comment_and_close(_command(), _attempt())

    assert marker_result == CloseFailure(
        retry_class="retryable",
        reason="transport_protocol",
        write_disposition="reconciled_absent",
    )

    unclosed_responses = iter(
        [
            httpx.Response(200, json=[{"body": _command().marker}]),
            httpx.Response(200, json={"state": "opened"}),
            httpx.Response(200, json=[{"body": _command().marker}]),
            httpx.Response(200, json={"state": "opened"}),
        ]
    )
    unclosed = _connector(httpx.MockTransport(lambda _request: next(unclosed_responses)))

    close_result = unclosed.comment_and_close(_command(), _attempt())

    assert close_result == CloseFailure(
        retry_class="retryable",
        reason="transport_protocol",
        write_disposition="reconciled_absent",
    )

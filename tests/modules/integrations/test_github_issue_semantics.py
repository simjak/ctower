"""GH-C08 GitHub Issue mapping, identity, cursor, and delivery controls."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

import httpx

from ctower_api.connectors.github import GitHubAppAuth, GitHubCursor, GitHubIssueConnector
from ctower_kernel.integrations import (
    CloseExternalIssue,
    ConnectorAttempt,
    ConnectorCursorToken,
    ExternalIssuePage,
    FetchIssuePage,
    FetchIssuePageResult,
)
from modules.integrations.github_test_support import (
    Clock,
    MintingTransport,
    connector_config,
    private_key_pem,
)


def test_github_pull_requests_are_excluded() -> None:
    result = _fetch([_issue(7, 70), {**_issue(8, 80), "pull_request": {"url": "x"}}])
    assert result.kind == "page"
    assert [item.external_ref for item in result.issues] == ["github:98765:7"]


def test_github_repository_rename_preserves_identity() -> None:
    before_result = _fetch([_issue(7, 70)])
    after_result = _fetch(
        [_issue(7, 70, owner="renamed", repository="renamed")],
        owner="renamed",
        repository="renamed",
    )
    assert isinstance(before_result, ExternalIssuePage)
    assert isinstance(after_result, ExternalIssuePage)
    before = before_result.issues[0]
    after = after_result.issues[0]
    assert before.external_ref == after.external_ref == "github:98765:7"


def test_github_equal_timestamp_cursor_uses_immutable_tie_breaker() -> None:
    cursor = GitHubCursor(updated_at=Clock().now, issue_id=70, page=1)
    result = _fetch([_issue(7, 70), _issue(8, 80)], cursor=cursor)
    assert isinstance(result, ExternalIssuePage)
    decoded = GitHubCursor.decode(result.next_cursor)
    assert [item.external_ref for item in result.issues] == ["github:98765:8"]
    assert (decoded.issue_id, decoded.updated_at) == (80, Clock().now)


def test_github_comment_and_close_reconciles_exactly_once() -> None:
    marker = "<!-- ctower-sync:22222222-2222-4222-8222-222222222222 -->"
    comments: list[str] = []
    closes = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal closes
        if request.method == "GET" and request.url.path.endswith("/comments"):
            return httpx.Response(
                200, request=request, json=[{"body": value} for value in comments]
            )
        if request.method == "POST":
            body = request.read().decode()
            comments.append(marker)
            return httpx.Response(201, request=request, json={"body": body})
        if request.method == "PATCH":
            closes += 1
            return httpx.Response(200, request=request, json={"state": "closed"})
        raise AssertionError(request)

    connector = _connector(handler)
    command = CloseExternalIssue(
        external_ref="github:98765:7",
        command_id=UUID("22222222-2222-4222-8222-222222222222"),
        marker=marker,
        comment="Proof-gated close",
    )
    first = connector.comment_and_close(command, _attempt())
    second = connector.comment_and_close(command, _attempt())
    assert first.kind == second.kind == "receipt"
    assert len(comments) == 1
    assert closes == _EXPECTED_CLOSE_CALLS


def _fetch(
    values: list[dict[str, object]],
    *,
    cursor: GitHubCursor | None = None,
    owner: str = "ctower",
    repository: str = "feedback",
) -> FetchIssuePageResult:
    connector = _connector(
        lambda request: httpx.Response(200, request=request, json=values),
        owner=owner,
        repository=repository,
    )
    token = cursor or GitHubCursor(updated_at=Clock().now - timedelta(days=1), issue_id=0, page=1)
    return connector.fetch_page(
        FetchIssuePage(cursor=ConnectorCursorToken(value=token.encode()), page_size=50), _attempt()
    )


def _connector(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    owner: str = "ctower",
    repository: str = "feedback",
) -> GitHubIssueConnector:
    clock = Clock()
    config = connector_config().model_copy(
        update={"repository_owner": owner, "repository_name": repository}
    )
    mint = MintingTransport(clock, owner=owner, repository=repository)
    auth = GitHubAppAuth(
        config,
        resolve_private_key=lambda _binding, _revision: private_key_pem(),
        client=httpx.Client(transport=httpx.MockTransport(mint.handle)),
        clock=clock,
    )
    return GitHubIssueConnector(
        config, auth=auth, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _attempt() -> ConnectorAttempt:
    return ConnectorAttempt(
        attempt_number=1, max_attempts=4, deadline_remaining_milliseconds=10_000
    )


def _issue(
    number: int, issue_id: int, *, owner: str = "ctower", repository: str = "feedback"
) -> dict[str, object]:
    return {
        "id": issue_id,
        "number": number,
        "title": f"Issue {number}",
        "body": "Body",
        "labels": [{"name": "bug"}],
        "user": {"id": 42, "login": "reporter"},
        "state": "open",
        "updated_at": Clock().now.isoformat(),
        "html_url": f"https://github.com/{owner}/{repository}/issues/{number}",
        "repository_url": f"https://api.github.com/repos/{owner}/{repository}",
    }


_EXPECTED_CLOSE_CALLS = 2

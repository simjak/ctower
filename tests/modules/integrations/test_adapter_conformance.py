"""Shared conformance suite for every GitLabIssueAdapter implementation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest

from ctower_api.gitlab_adapter import GitLabHttpAdapter
from ctower_kernel.integrations import (
    GitLabCloseCommand,
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssue,
    GitLabIssueAdapter,
    GitLabIssueLink,
    GitLabIssuePage,
    GitLabReporter,
    GitLabSyncBinding,
    GitLabSyncError,
)

DELIVERY_ID = UUID("22222222-2222-4222-8222-222222222222")
PROJECT_ID = 42
ISSUE_IID = 7
EXPECTED_CLOSE_CALLS = 2
NEXT_PAGE = 2


def _binding() -> GitLabSyncBinding:
    return GitLabSyncBinding(
        integration_key="gitlab.feedback",
        revision_id=UUID("22222222-2222-4222-8222-222222222222"),
        revision_digest="sha256:" + "a" * 64,
        project_id=42,
        project_key="ctower",
        initial_custodian_id=UUID("11111111-1111-4111-8111-111111111111"),
        import_updated_after=datetime(2026, 8, 8, 8, tzinfo=UTC),
        page_size=50,
        poll_interval=timedelta(seconds=60),
        label_map=(("bug", "type.bug"),),
    )


def _issue() -> GitLabIssue:
    return GitLabIssue(
        project_id=42,
        iid=7,
        title="Feedback title",
        body="Feedback body",
        labels=("bug",),
        reporter=GitLabReporter("reporter", "Report Person"),
        state="opened",
        web_url="https://gitlab.example.test/group/project/-/issues/7",
        updated_at=datetime(2026, 8, 8, 8, 1, tzinfo=UTC),
    )


def _link() -> GitLabIssueLink:
    return GitLabIssueLink(
        tenant_id=UUID("33333333-3333-4333-8333-333333333333"),
        integration_key="gitlab.feedback",
        revision_digest="sha256:" + "a" * 64,
        project_id=42,
        issue_iid=7,
        ticket_id=UUID("44444444-4444-4444-8444-444444444444"),
        thread_id=UUID("55555555-5555-4555-8555-555555555555"),
        web_url="https://gitlab.example.test/group/project/-/issues/7",
    )


def run_conformance_suite(adapter: GitLabIssueAdapter) -> None:
    cursor = GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0)
    page = adapter.list_issues(_binding(), cursor)
    assert page == GitLabIssuePage((_issue(),), None)

    command = GitLabCloseCommand(DELIVERY_ID, "Proof-gated close")
    first = adapter.comment_and_close(_link(), command)
    replay = adapter.comment_and_close(_link(), command)
    assert first == GitLabCloseReceipt(
        delivery_id=DELIVERY_ID, comment_created=True, issue_closed=True
    )
    assert replay == GitLabCloseReceipt(
        delivery_id=DELIVERY_ID, comment_created=False, issue_closed=True
    )


class _FakeAdapter:
    def __init__(self) -> None:
        self._delivered: set[UUID] = set()

    def list_issues(self, binding: GitLabSyncBinding, cursor: GitLabCursor) -> GitLabIssuePage:
        assert binding.project_id == PROJECT_ID and cursor.page == 1
        return GitLabIssuePage((_issue(),), None)

    def comment_and_close(
        self, link: GitLabIssueLink, command: GitLabCloseCommand
    ) -> GitLabCloseReceipt:
        assert link.issue_iid == ISSUE_IID
        created = command.delivery_id not in self._delivered
        self._delivered.add(command.delivery_id)
        return GitLabCloseReceipt(
            delivery_id=command.delivery_id,
            comment_created=created,
            issue_closed=True,
        )


def test_fake_adapter_passes_conformance() -> None:
    run_conformance_suite(_FakeAdapter())


def test_real_http_adapter_passes_conformance_and_bounds_requests() -> None:
    notes: list[str] = []
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path.endswith("/issues"):
            return httpx.Response(200, json=_provider_issue())
        if request.method == "GET" and request.url.path.endswith("/notes"):
            return httpx.Response(200, json=[{"body": body} for body in reversed(notes)])
        if request.method == "POST" and request.url.path.endswith("/notes"):
            body = str(request.read().decode())
            posted = httpx.Response(200, request=request, content=body).json()["body"]
            notes.append(posted)
            return httpx.Response(201, json={"body": posted})
        if request.method == "PUT" and request.url.path.endswith("/7"):
            return httpx.Response(200, json={"state": "closed"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    resolved_value = str(uuid4())
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=resolved_value, client=client)
    run_conformance_suite(adapter)

    issue_request = requests[0]
    assert issue_request.url.params["per_page"] == "50"
    assert issue_request.url.params["page"] == "1"
    assert issue_request.url.params["updated_after"].startswith("2026-08-08T08:00:00")
    assert len([request for request in requests if request.method == "POST"]) == 1
    assert len([request for request in requests if request.method == "PUT"]) == EXPECTED_CLOSE_CALLS
    assert all(request.headers["private-token"] == resolved_value for request in requests)


def test_real_adapter_rejects_malformed_provider_payload() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json=[{**_provider_issue()[0], "project_id": "42"}]
            )
        )
    )
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)

    with pytest.raises(GitLabSyncError, match="project_id"):
        adapter.list_issues(_binding(), GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0))


def test_real_adapter_advances_only_the_bounded_provider_page() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"X-Next-Page": "2"},
                json=_provider_issue(),
            )
        )
    )
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)

    page = adapter.list_issues(_binding(), GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0))

    assert page.next_page == NEXT_PAGE


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

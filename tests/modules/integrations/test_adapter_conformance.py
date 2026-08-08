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

__all__: tuple[str, ...] = ()

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


@pytest.mark.parametrize(
    "base_url",
    [
        "http://gitlab.example.test",
        "https:///missing-host",
        "https://gitlab.example.test?query=forbidden",
        "https://gitlab.example.test#fragment-forbidden",
    ],
)
def test_real_adapter_refuses_non_origin_base_urls(base_url: str) -> None:
    with pytest.raises(ValueError, match="base URL"):
        GitLabHttpAdapter(base_url, token=str(uuid4()))


@pytest.mark.parametrize("token", ["", "x" * 2049])
def test_real_adapter_refuses_missing_or_unbounded_credentials(token: str) -> None:
    with pytest.raises(ValueError, match="credential"):
        GitLabHttpAdapter("https://gitlab.example.test", token=token)


def test_real_adapter_closes_only_the_client_it_owns() -> None:
    with GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4())) as owned:
        owned_client = owned._client
    assert owned_client.is_closed

    external_client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200))
    )
    adapter = GitLabHttpAdapter(
        "https://gitlab.example.test", token=str(uuid4()), client=external_client
    )
    adapter.close()
    assert not external_client.is_closed
    external_client.close()


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"not": "an array"}, "array"),
        (_provider_issue() * 51, "page bound"),
        ([{**_provider_issue()[0], "labels": "bug"}], "labels"),
        ([{**_provider_issue()[0], "labels": [1]}], "labels"),
        ([{**_provider_issue()[0], "description": 42}], "description"),
        ([{**_provider_issue()[0], "author": []}], "author"),
        ([{**_provider_issue()[0], "project_id": True}], "project_id"),
        ([{**_provider_issue()[0], "title": None}], "title"),
        ([{**_provider_issue()[0], "updated_at": "not-a-date"}], "ISO 8601"),
        ([{**_provider_issue()[0], "updated_at": "2026-08-08T08:01:00"}], "timezone-aware"),
        ([{**_provider_issue()[0], "state": "merged"}], "normalized contract"),
    ],
)
def test_real_adapter_refuses_malformed_issue_list_variants(payload: object, match: str) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    )
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)

    with pytest.raises(GitLabSyncError, match=match):
        adapter.list_issues(_binding(), GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0))


@pytest.mark.parametrize(
    "headers,match",
    [
        ({"X-Next-Page": "not-numeric"}, "X-Next-Page"),
        ({"X-Next-Page": "1"}, "did not advance"),
        ({"Link": '<https://gitlab.example.test/issues?page=next>; rel="next"'}, "numeric"),
        ({"Link": '<https://gitlab.example.test/issues?page=1>; rel="next"'}, "did not advance"),
    ],
)
def test_real_adapter_refuses_nonadvancing_pagination(headers: dict[str, str], match: str) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, headers=headers, json=_provider_issue())
        )
    )
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)

    with pytest.raises(GitLabSyncError, match=match):
        adapter.list_issues(_binding(), GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0))


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
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: next(responses)))
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)
    cursor = GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0)

    assert adapter.list_issues(_binding(), cursor).next_page == NEXT_PAGE
    assert adapter.list_issues(_binding(), cursor).next_page is None


def test_real_adapter_wraps_http_and_non_json_failures() -> None:
    response = httpx.Response(500, json={"message": "failed"})
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: response))
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)
    with pytest.raises(GitLabSyncError, match="GET request failed"):
        adapter.list_issues(_binding(), GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0))

    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not-json"))
    )
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)
    with pytest.raises(GitLabSyncError, match="not JSON"):
        adapter.list_issues(_binding(), GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0))


@pytest.mark.parametrize("notes", [{"not": "an array"}, [{"body": "note"}] * 101])
def test_real_adapter_refuses_unbounded_note_pages(notes: object) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=notes))
    )
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)

    with pytest.raises(GitLabSyncError, match="note-list"):
        adapter.comment_and_close(_link(), GitLabCloseCommand(DELIVERY_ID, "Proof-gated close"))


def test_real_adapter_refuses_wrong_created_marker_and_unclosed_issue() -> None:
    wrong_marker = iter(
        [
            httpx.Response(200, json=[]),
            httpx.Response(201, json={"body": "marker missing"}),
        ]
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: next(wrong_marker)))
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)
    command = GitLabCloseCommand(DELIVERY_ID, "Proof-gated close")
    with pytest.raises(GitLabSyncError, match="wrong delivery marker"):
        adapter.comment_and_close(_link(), command)

    unclosed = iter(
        [
            httpx.Response(200, json=[{"body": command.marker}]),
            httpx.Response(200, json={"state": "opened"}),
        ]
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: next(unclosed)))
    adapter = GitLabHttpAdapter("https://gitlab.example.test", token=str(uuid4()), client=client)
    with pytest.raises(GitLabSyncError, match="closed state"):
        adapter.comment_and_close(_link(), command)

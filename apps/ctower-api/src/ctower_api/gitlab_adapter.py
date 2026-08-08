"""Real HTTP Adapter for the GitLab issue integration Seam."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime
from random import SystemRandom
from types import TracebackType
from typing import Self, cast
from urllib.parse import parse_qs, urlsplit

import httpx

from ctower_kernel.integrations import (
    GitLabCloseCommand,
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssue,
    GitLabIssueLink,
    GitLabIssuePage,
    GitLabReporter,
    GitLabSyncBinding,
    GitLabSyncError,
)

__all__ = ["GitLabHttpAdapter"]

_NEXT_LINK = re.compile(r"<(?P<url>[^>]+)>;\s*rel=\"next\"")
_MAX_CREDENTIAL_LENGTH = 2048
_NOTE_PAGE_SIZE = 100
_MAXIMUM_ATTEMPTS = 4
_MAXIMUM_ELAPSED_SECONDS = 10.0
_INITIAL_BACKOFF_SECONDS = 0.25
_MAXIMUM_BACKOFF_SECONDS = 2.0
_REQUEST_TIMEOUT_SECONDS = 5.0
_TOO_MANY_REQUESTS = 429
_MINIMUM_SERVER_ERROR = 500
_MAXIMUM_SERVER_ERROR = 599
_RANDOM = SystemRandom()


class GitLabHttpAdapter:
    """Call only the bounded GitLab v4 issue and note endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
            raise ValueError("GitLab base URL must be an absolute HTTPS origin")
        if not token or len(token) > _MAX_CREDENTIAL_LENGTH:
            raise ValueError("GitLab credential is unavailable")
        self._base_url = base_url.rstrip("/")
        self._headers = {"PRIVATE-TOKEN": token, "Accept": "application/json"}
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        self._owns_client = client is None
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter or (lambda ceiling: _RANDOM.uniform(ceiling / 2, ceiling))

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def list_issues(self, binding: GitLabSyncBinding, cursor: GitLabCursor) -> GitLabIssuePage:
        response = self._request(
            "GET",
            self._issues_url(binding.project_id),
            params={
                "scope": "all",
                "state": "all",
                "order_by": "updated_at",
                "sort": "asc",
                "updated_after": cursor.updated_after.isoformat(),
                "per_page": str(binding.page_size),
                "page": str(cursor.page),
            },
        )
        payload = _json(response)
        if not isinstance(payload, list):
            raise GitLabSyncError("GitLab issue-list response must be an array")
        if len(payload) > binding.page_size:
            raise GitLabSyncError("GitLab issue-list response exceeded the requested page bound")
        issues = tuple(_issue(item) for item in payload)
        return GitLabIssuePage(issues, _next_page(response.headers, cursor.page))

    def comment_and_close(
        self, link: GitLabIssueLink, command: GitLabCloseCommand
    ) -> GitLabCloseReceipt:
        notes_url = f"{self._issues_url(link.project_id)}/{link.issue_iid}/notes"
        notes = self._list_notes(
            notes_url,
        )
        marker_seen = any(command.marker in _note_body(note) for note in notes)
        if not marker_seen:
            created = self._request(
                "POST",
                notes_url,
                json_body={"body": f"{command.comment}\n\n{command.marker}"},
                reconcile=lambda deadline: self._reconcile_marker(
                    notes_url, command.marker, deadline=deadline
                ),
            )
            if command.marker not in _note_body(_json(created)):
                raise GitLabSyncError("GitLab note creation returned the wrong delivery marker")
        closed = self._request(
            "PUT",
            f"{self._issues_url(link.project_id)}/{link.issue_iid}",
            json_body={"state_event": "close"},
        )
        closed_payload = _mapping(_json(closed), "GitLab issue-close response")
        if closed_payload.get("state") != "closed":
            raise GitLabSyncError("GitLab issue close did not return closed state")
        return GitLabCloseReceipt(
            delivery_id=command.delivery_id,
            comment_created=not marker_seen,
            issue_closed=True,
        )

    def _list_notes(self, notes_url: str, *, deadline: float | None = None) -> list[object]:
        response = self._request(
            "GET",
            notes_url,
            params={
                "per_page": "100",
                "page": "1",
                "sort": "desc",
                "order_by": "created_at",
                "activity_filter": "only_comments",
            },
            deadline=deadline,
        )
        notes = _json(response)
        if not isinstance(notes, list) or len(notes) > _NOTE_PAGE_SIZE:
            raise GitLabSyncError("GitLab note-list response violated the page bound")
        return cast(list[object], notes)

    def _reconcile_marker(
        self, notes_url: str, marker: str, *, deadline: float
    ) -> httpx.Response | None:
        notes = self._list_notes(notes_url, deadline=deadline)
        for note in notes:
            body = _note_body(note)
            if marker in body:
                return httpx.Response(200, json={"body": body})
        return None

    def _issues_url(self, project_id: int) -> str:
        return f"{self._base_url}/api/v4/projects/{project_id}/issues"

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, str] | None = None,
        deadline: float | None = None,
        reconcile: Callable[[float], httpx.Response | None] | None = None,
    ) -> httpx.Response:
        retry_deadline = deadline or (self._monotonic() + _MAXIMUM_ELAPSED_SECONDS)
        last_error: httpx.HTTPError | None = None
        for attempt in range(1, _MAXIMUM_ATTEMPTS + 1):
            remaining = retry_deadline - self._monotonic()
            if remaining <= 0:
                break
            try:
                response = self._client.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    json=json_body,
                    timeout=max(0.001, min(_REQUEST_TIMEOUT_SECONDS, remaining)),
                )
                response.raise_for_status()
            except httpx.HTTPError as error:
                last_error = error
                reconciled = self._retry_or_reconcile(
                    method,
                    error,
                    deadline=retry_deadline,
                    attempt=attempt,
                    reconcile=reconcile,
                )
                if reconciled is not None:
                    return reconciled
            except ValueError as error:
                raise GitLabSyncError(f"GitLab {method} request failed") from error
            else:
                return response
        raise GitLabSyncError(f"GitLab {method} retry exhausted") from last_error

    def _retry_or_reconcile(
        self,
        method: str,
        error: httpx.HTTPError,
        *,
        deadline: float,
        attempt: int,
        reconcile: Callable[[float], httpx.Response | None] | None,
    ) -> httpx.Response | None:
        if not _retryable(error):
            raise GitLabSyncError(f"GitLab {method} request failed") from error
        if reconcile is not None:
            reconciled = reconcile(deadline)
            if reconciled is not None:
                return reconciled
        if attempt == _MAXIMUM_ATTEMPTS or not self._back_off(deadline, attempt):
            raise GitLabSyncError(f"GitLab {method} retry exhausted") from error
        return None

    def _back_off(self, deadline: float, attempt: int) -> bool:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            return False
        ceiling = min(
            _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
            _MAXIMUM_BACKOFF_SECONDS,
            remaining,
        )
        delay = self._jitter(ceiling)
        if not 0 <= delay <= ceiling:
            raise RuntimeError("GitLab retry jitter escaped its bounded interval")
        self._sleep(delay)
        return self._monotonic() < deadline


def _issue(value: object) -> GitLabIssue:
    payload = _mapping(value, "GitLab issue")
    author = _mapping(payload.get("author"), "GitLab issue author")
    labels = payload.get("labels")
    if not isinstance(labels, list) or any(not isinstance(item, str) for item in labels):
        raise GitLabSyncError("GitLab issue labels must be strings")
    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise GitLabSyncError("GitLab issue description must be text or null")
    project_id = _integer(payload, "project_id")
    iid = _integer(payload, "iid")
    try:
        return GitLabIssue(
            project_id=project_id,
            iid=iid,
            title=_string(payload, "title"),
            body=description or "",
            labels=tuple(sorted(cast(list[str], labels))),
            reporter=GitLabReporter(
                username=_string(author, "username"),
                name=_string(author, "name"),
            ),
            state=_string(payload, "state"),
            web_url=_string(payload, "web_url"),
            updated_at=_datetime(_string(payload, "updated_at")),
        )
    except ValueError as error:
        raise GitLabSyncError("GitLab issue violated the normalized contract") from error


def _next_page(headers: httpx.Headers, current: int) -> int | None:
    header = headers.get("x-next-page")
    if header:
        if not header.isdigit() or int(header) <= current:
            raise GitLabSyncError("GitLab X-Next-Page did not advance")
        return int(header)
    link = headers.get("link")
    if not link:
        return None
    matched = _NEXT_LINK.search(link)
    if matched is None:
        return None
    values = parse_qs(urlsplit(matched.group("url")).query).get("page")
    if values is None or len(values) != 1 or not values[0].isdigit():
        raise GitLabSyncError("GitLab next Link lacks one numeric page")
    page = int(values[0])
    if page <= current:
        raise GitLabSyncError("GitLab next Link did not advance")
    return page


def _json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as error:
        raise GitLabSyncError("GitLab response was not JSON") from error


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise GitLabSyncError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise GitLabSyncError(f"GitLab field {key} must be text")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GitLabSyncError(f"GitLab field {key} must be an integer")
    return value


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise GitLabSyncError("GitLab updated_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GitLabSyncError("GitLab updated_at must be timezone-aware")
    return parsed


def _note_body(value: object) -> str:
    return _string(_mapping(value, "GitLab note"), "body")


def _retryable(error: httpx.HTTPError) -> bool:
    if isinstance(error, httpx.TimeoutException):
        return True
    if not isinstance(error, httpx.HTTPStatusError):
        return False
    status = error.response.status_code
    return status == _TOO_MANY_REQUESTS or _MINIMUM_SERVER_ERROR <= status <= _MAXIMUM_SERVER_ERROR

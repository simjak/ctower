"""GitLab transport, mapping, cursor codec, classification, and reconciliation."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from types import TracebackType
from typing import Literal, Self, cast
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ctower_api.connectors.gitlab.config import GitLabConnectorConfig
from ctower_kernel.integrations import (
    AmbiguousWrite,
    CloseExternalIssue,
    CloseExternalIssueResult,
    CloseFailure,
    ConnectorAttempt,
    ConnectorCursorToken,
    ConnectorReceipt,
    ExternalIssue,
    ExternalIssuePage,
    FailureReason,
    FetchFailure,
    FetchIssuePage,
    FetchIssuePageResult,
    RetryClass,
    WriteDisposition,
)

__all__ = ["GitLabCursor", "GitLabIssueConnector"]

_NEXT_LINK = re.compile(r'<(?P<url>[^>]+)>;\s*rel="next"')
_USERNAME = re.compile(r"^[A-Za-z0-9_.-]{1,255}$")
_CONNECTOR_KIND = "gitlab-issue"
_MAX_CREDENTIAL_LENGTH = 2048
_NOTE_PAGE_SIZE = 100
_TOO_MANY_REQUESTS = 429
_MINIMUM_SERVER_ERROR = 500
_MAXIMUM_SERVER_ERROR = 599
_HTTP_SUCCESS_START = 200
_HTTP_SUCCESS_END = 300
_UNAUTHORIZED = 401
_FORBIDDEN = 403
_EXTERNAL_IDENTITY_PARTS = 3


class _PayloadError(ValueError):
    pass


class GitLabCursor(BaseModel):
    """Provider-owned aware watermark and page encoded into one opaque token."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_: str = Field(default="ctower.gitlab-cursor/v1", alias="schema")
    updated_after: datetime
    page: int = Field(ge=1)

    @model_validator(mode="after")
    def _watermark_is_aware(self) -> GitLabCursor:
        if self.schema_ != "ctower.gitlab-cursor/v1":
            raise ValueError("GitLab cursor schema is unsupported")
        if self.updated_after.tzinfo is None or self.updated_after.utcoffset() is None:
            raise ValueError("GitLab cursor watermark must be timezone-aware")
        return self

    def encode(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def decode(cls, token: ConnectorCursorToken) -> GitLabCursor:
        try:
            return cls.model_validate_json(token.value)
        except ValueError as error:
            raise _PayloadError("GitLab cursor token is invalid") from error


class GitLabIssueConnector:
    """Perform one bounded GitLab issue operation per protocol invocation."""

    def __init__(
        self,
        config: GitLabConnectorConfig,
        *,
        token: str,
        client: httpx.Client | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not token or len(token) > _MAX_CREDENTIAL_LENGTH:
            raise ValueError("GitLab credential is unavailable")
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._headers = {"PRIVATE-TOKEN": token, "Accept": "application/json"}
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        self._owns_client = client is None
        self._monotonic = monotonic
        self._diagnostic: str | None = None

    @property
    def diagnostic(self) -> str | None:
        """Return the last bounded provider diagnostic for operation-level reporting."""

        return self._diagnostic

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

    def fetch_page(
        self, request: FetchIssuePage, attempt: ConnectorAttempt
    ) -> FetchIssuePageResult:
        self._diagnostic = None
        cursor: GitLabCursor
        try:
            cursor = GitLabCursor.decode(request.cursor)
            deadline = self._deadline(attempt)
            response = self._request(
                "GET",
                self._issues_url(),
                deadline=deadline,
                params={
                    "scope": "all",
                    "state": "all",
                    "order_by": "updated_at",
                    "sort": "asc",
                    "updated_after": cursor.updated_after.isoformat(),
                    "per_page": str(request.page_size),
                    "page": str(cursor.page),
                },
            )
            payload = _issue_list(_json(response), request.page_size)
            issues = tuple(
                _issue(item, expected_project=self._config.project_id) for item in payload
            )
            next_page = _next_page(response.headers, cursor.page)
            next_cursor = _next_cursor(cursor, issues, next_page)
            return ExternalIssuePage(
                issues=issues,
                next_cursor=ConnectorCursorToken(value=next_cursor.encode()),
                exhausted=next_page is None,
            )
        except httpx.HTTPError as error:
            self._diagnostic = _safe_http_diagnostic("GET", error)
            retry_class, reason = _classify(error)
            return FetchFailure(retry_class=retry_class, reason=reason)
        except _PayloadError as error:
            self._diagnostic = str(error)
            return FetchFailure(retry_class="terminal", reason="invalid_payload")
        except ValueError as error:
            self._diagnostic = f"GitLab normalized contract failed: {error}"
            return FetchFailure(retry_class="terminal", reason="contract_violation")

    def comment_and_close(
        self, command: CloseExternalIssue, attempt: ConnectorAttempt
    ) -> CloseExternalIssueResult:
        self._diagnostic = None
        try:
            project_id, issue_iid = _external_identity(command.external_ref)
            _require_project(project_id, self._config.project_id)
            deadline = self._deadline(attempt)
            notes_url = f"{self._issues_url()}/{issue_iid}/notes"
            marker_seen = self._marker_present(notes_url, command.marker, deadline=deadline)
        except httpx.HTTPError as error:
            self._diagnostic = _safe_http_diagnostic("close preflight", error)
            return _known_close_failure(error, write_disposition="not_written")
        except _PayloadError as error:
            self._diagnostic = str(error)
            return CloseFailure(
                retry_class="terminal",
                reason="invalid_payload",
                write_disposition="not_written",
            )
        if not marker_seen:
            posted = self._post_marker(notes_url, command, deadline=deadline)
            if isinstance(posted, (CloseFailure, AmbiguousWrite)):
                return posted
            marker_seen = True
            comment_created = True
        else:
            comment_created = False
        return self._close_issue(
            issue_iid,
            notes_url,
            command,
            comment_created=comment_created,
            deadline=deadline,
        )

    def _post_marker(
        self, notes_url: str, command: CloseExternalIssue, *, deadline: float
    ) -> bool | CloseFailure | AmbiguousWrite:
        try:
            response = self._request(
                "POST",
                notes_url,
                deadline=deadline,
                json_body={"body": f"{command.comment}\n\n{command.marker}"},
            )
            _require_created_marker(response, command.marker)
        except httpx.ConnectError as error:
            self._diagnostic = _safe_http_diagnostic("note creation", error)
            return _known_close_failure(error, write_disposition="not_written")
        except httpx.HTTPError as error:
            self._diagnostic = _safe_http_diagnostic("note creation", error)
            return self._reconcile_marker_failure(
                notes_url, command.marker, error=error, deadline=deadline
            )
        except _PayloadError as error:
            self._diagnostic = str(error)
            return self._reconcile_marker_result(
                notes_url,
                command.marker,
                reason="transport_protocol",
                deadline=deadline,
            )
        else:
            return True

    def _reconcile_marker_failure(
        self,
        notes_url: str,
        marker: str,
        *,
        error: httpx.HTTPError,
        deadline: float,
    ) -> bool | CloseFailure | AmbiguousWrite:
        retry_class, reason = _classify(error)
        if retry_class == "terminal":
            return CloseFailure(
                retry_class=retry_class,
                reason=reason,
                write_disposition="not_written",
            )
        return self._reconcile_marker_result(notes_url, marker, reason=reason, deadline=deadline)

    def _reconcile_marker_result(
        self,
        notes_url: str,
        marker: str,
        *,
        reason: FailureReason,
        deadline: float,
    ) -> bool | CloseFailure | AmbiguousWrite:
        reconciled = self._reconcile_marker(notes_url, marker, deadline=deadline)
        if reconciled is True:
            return True
        if reconciled is False:
            return CloseFailure(
                retry_class="retryable",
                reason=reason,
                write_disposition="reconciled_absent",
            )
        return AmbiguousWrite()

    def _close_issue(
        self,
        issue_iid: int,
        notes_url: str,
        command: CloseExternalIssue,
        *,
        comment_created: bool,
        deadline: float,
    ) -> CloseExternalIssueResult:
        try:
            response = self._request(
                "PUT",
                f"{self._issues_url()}/{issue_iid}",
                deadline=deadline,
                json_body={"state_event": "close"},
            )
            _require_closed(response)
        except httpx.ConnectError as error:
            self._diagnostic = _safe_http_diagnostic("issue close", error)
            return _known_close_failure(error, write_disposition="not_written")
        except httpx.HTTPError as error:
            self._diagnostic = _safe_http_diagnostic("issue close", error)
            return self._reconcile_close_failure(
                issue_iid,
                notes_url,
                command,
                comment_created=comment_created,
                error=error,
                deadline=deadline,
            )
        except _PayloadError as error:
            self._diagnostic = str(error)
            return self._reconcile_close_result(
                issue_iid,
                notes_url,
                command,
                comment_created=comment_created,
                reason="transport_protocol",
                deadline=deadline,
            )
        else:
            return ConnectorReceipt(
                command_id=command.command_id,
                comment_created=comment_created,
            )

    def _reconcile_close_failure(
        self,
        issue_iid: int,
        notes_url: str,
        command: CloseExternalIssue,
        *,
        comment_created: bool,
        error: httpx.HTTPError,
        deadline: float,
    ) -> CloseExternalIssueResult:
        retry_class, reason = _classify(error)
        if retry_class == "terminal":
            return CloseFailure(
                retry_class=retry_class,
                reason=reason,
                write_disposition="not_written",
            )
        return self._reconcile_close_result(
            issue_iid,
            notes_url,
            command,
            comment_created=comment_created,
            reason=reason,
            deadline=deadline,
        )

    def _reconcile_close_result(
        self,
        issue_iid: int,
        notes_url: str,
        command: CloseExternalIssue,
        *,
        comment_created: bool,
        reason: FailureReason,
        deadline: float,
    ) -> CloseExternalIssueResult:
        reconciled = self._reconcile_close(issue_iid, notes_url, command.marker, deadline=deadline)
        if reconciled == "closed":
            return ConnectorReceipt(
                command_id=command.command_id,
                comment_created=comment_created,
            )
        if reconciled == "open":
            return CloseFailure(
                retry_class="retryable",
                reason=reason,
                write_disposition="reconciled_absent",
            )
        return AmbiguousWrite()

    def _marker_present(self, notes_url: str, marker: str, *, deadline: float) -> bool:
        response = self._request(
            "GET",
            notes_url,
            deadline=deadline,
            params={
                "per_page": "100",
                "page": "1",
                "sort": "desc",
                "order_by": "created_at",
                "activity_filter": "only_comments",
            },
        )
        notes = _json(response)
        if not isinstance(notes, list) or len(notes) > _NOTE_PAGE_SIZE:
            raise _PayloadError("GitLab note-list response violated the page bound")
        return any(marker in _note_body(note) for note in notes)

    def _reconcile_marker(self, notes_url: str, marker: str, *, deadline: float) -> bool | None:
        try:
            return self._marker_present(notes_url, marker, deadline=deadline)
        except (httpx.HTTPError, _PayloadError):
            return None

    def _reconcile_close(
        self, issue_iid: int, notes_url: str, marker: str, *, deadline: float
    ) -> str | None:
        try:
            if not self._marker_present(notes_url, marker, deadline=deadline):
                return "open"
            response = self._request("GET", f"{self._issues_url()}/{issue_iid}", deadline=deadline)
            state = _mapping(_json(response), "GitLab close reconciliation").get("state")
        except (httpx.HTTPError, _PayloadError):
            return None
        else:
            if state == "closed":
                return "closed"
            return "open" if state == "opened" else None

    def _request(
        self,
        method: str,
        url: str,
        *,
        deadline: float,
        params: dict[str, str] | None = None,
        json_body: dict[str, str] | None = None,
    ) -> httpx.Response:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            request = httpx.Request(method, url)
            raise httpx.TimeoutException("connector attempt deadline elapsed", request=request)
        response = self._client.request(
            method,
            url,
            headers=self._headers,
            params=params,
            json=json_body,
            timeout=max(0.001, remaining),
        )
        response.raise_for_status()
        if not _HTTP_SUCCESS_START <= response.status_code < _HTTP_SUCCESS_END:
            raise _PayloadError("GitLab response status is outside the supported contract")
        return response

    def _deadline(self, attempt: ConnectorAttempt) -> float:
        request_budget_milliseconds = min(5000, attempt.deadline_remaining_milliseconds)
        return self._monotonic() + (request_budget_milliseconds / 1000)

    def _issues_url(self) -> str:
        return f"{self._base_url}/api/v4/projects/{self._config.project_id}/issues"


def _issue(value: object, *, expected_project: int) -> ExternalIssue:
    payload = _mapping(value, "GitLab issue")
    author = _mapping(payload.get("author"), "GitLab issue author")
    labels = payload.get("labels")
    if not isinstance(labels, list) or any(not isinstance(item, str) for item in labels):
        raise _PayloadError("GitLab issue labels must be strings")
    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise _PayloadError("GitLab issue description must be text or null")
    project_id = _integer(payload, "project_id")
    iid = _integer(payload, "iid")
    if project_id != expected_project:
        raise _PayloadError("GitLab issue belongs to another configured project")
    reporter_reference = _reporter_reference(_string(author, "username"))
    external_state = _external_state(_string(payload, "state"))
    try:
        return ExternalIssue(
            connector_kind=_CONNECTOR_KIND,
            external_ref=f"gitlab:{project_id}:{iid}",
            title=_string(payload, "title"),
            description=description or "",
            source_labels=tuple(sorted(cast(list[str], labels))),
            reporter_reference=reporter_reference,
            reporter_display_name=_string(author, "name"),
            external_state=external_state,
            display_url=_string(payload, "web_url"),
            updated_at=_datetime(_string(payload, "updated_at")),
        )
    except _PayloadError:
        raise
    except ValueError as error:
        raise _PayloadError("GitLab issue violated the normalized contract") from error


def _next_cursor(
    cursor: GitLabCursor,
    issues: tuple[ExternalIssue, ...],
    next_page: int | None,
) -> GitLabCursor:
    if next_page is not None:
        return GitLabCursor(updated_after=cursor.updated_after, page=next_page)
    watermark = (
        max(issue.updated_at for issue in issues) + timedelta(microseconds=1)
        if issues
        else cursor.updated_after
    )
    return GitLabCursor(updated_after=watermark, page=1)


def _next_page(headers: httpx.Headers, current: int) -> int | None:
    header = headers.get("x-next-page")
    if header:
        if not header.isdigit() or int(header) <= current:
            raise _PayloadError("GitLab X-Next-Page did not advance")
        return int(header)
    link = headers.get("link")
    if not link:
        return None
    matched = _NEXT_LINK.search(link)
    if matched is None:
        return None
    values = parse_qs(urlsplit(matched.group("url")).query).get("page")
    if values is None or len(values) != 1 or not values[0].isdigit():
        raise _PayloadError("GitLab next Link lacks one numeric page")
    page = int(values[0])
    if page <= current:
        raise _PayloadError("GitLab next Link did not advance")
    return page


def _classify(error: httpx.HTTPError) -> tuple[RetryClass, FailureReason]:
    if isinstance(error, httpx.TimeoutException):
        return "retryable", "timeout"
    if isinstance(error, httpx.RemoteProtocolError):
        return "retryable", "transport_protocol"
    if isinstance(error, httpx.ConnectError):
        return "retryable", "transport_connect"
    if isinstance(error, httpx.ReadError):
        return "retryable", "transport_read"
    if isinstance(error, httpx.HTTPStatusError):
        return _classify_status(error.response.status_code)
    return "terminal", "contract_violation"


def _safe_http_diagnostic(operation: str, error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"GitLab {operation} request failed with status {error.response.status_code}"
    return f"GitLab {operation} failed: {error}"


def _classify_status(status: int) -> tuple[RetryClass, FailureReason]:
    if status == _UNAUTHORIZED:
        return "terminal", "authentication"
    if status == _FORBIDDEN:
        return "terminal", "authorization"
    if status == _TOO_MANY_REQUESTS:
        return "retryable", "throttled"
    if _MINIMUM_SERVER_ERROR <= status <= _MAXIMUM_SERVER_ERROR:
        return "retryable", "provider_5xx"
    return "terminal", "ordinary_4xx"


def _known_close_failure(
    error: httpx.HTTPError, *, write_disposition: WriteDisposition
) -> CloseFailure:
    retry_class, reason = _classify(error)
    return CloseFailure(
        retry_class=retry_class,
        reason=reason,
        write_disposition=write_disposition,
    )


def _external_identity(external_ref: str) -> tuple[int, int]:
    parts = external_ref.split(":")
    if (
        len(parts) != _EXTERNAL_IDENTITY_PARTS
        or parts[0] != "gitlab"
        or not all(value.isdigit() for value in parts[1:])
    ):
        raise _PayloadError("GitLab external reference is invalid")
    project_id, issue_iid = int(parts[1]), int(parts[2])
    if project_id < 1 or issue_iid < 1:
        raise _PayloadError("GitLab external reference is invalid")
    return project_id, issue_iid


def _json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as error:
        raise _PayloadError("GitLab response was not JSON") from error


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise _PayloadError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise _PayloadError(f"GitLab field {key} must be text")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _PayloadError(f"GitLab field {key} must be an integer")
    return value


def _reporter_reference(username: str) -> str:
    if _USERNAME.fullmatch(username) is None:
        raise _PayloadError("GitLab reporter username is outside the supported contract")
    return f"@{username}"


def _external_state(state: str) -> Literal["opened", "closed"]:
    if state not in {"opened", "closed"}:
        raise _PayloadError("GitLab issue violated the normalized contract")
    return cast(Literal["opened", "closed"], state)


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise _PayloadError("GitLab updated_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _PayloadError("GitLab updated_at must be timezone-aware")
    return parsed


def _note_body(value: object) -> str:
    return _string(_mapping(value, "GitLab note"), "body")


def _issue_list(value: object, page_size: int) -> list[object]:
    if not isinstance(value, list):
        raise _PayloadError("GitLab issue-list response must be an array")
    if len(value) > page_size:
        raise _PayloadError("GitLab issue-list response exceeded the requested page bound")
    return cast(list[object], value)


def _require_project(actual: int, expected: int) -> None:
    if actual != expected:
        raise _PayloadError("GitLab close command names another project")


def _require_created_marker(response: httpx.Response, marker: str) -> None:
    if marker not in _note_body(_json(response)):
        raise httpx.RemoteProtocolError(
            "GitLab note creation returned the wrong marker",
            request=response.request,
        )


def _require_closed(response: httpx.Response) -> None:
    if _mapping(_json(response), "GitLab issue-close response").get("state") != "closed":
        raise httpx.RemoteProtocolError(
            "GitLab issue close did not return closed state",
            request=response.request,
        )

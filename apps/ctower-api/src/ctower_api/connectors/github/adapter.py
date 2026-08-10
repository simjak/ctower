"""GitHub Issue transport, strict mapping, cursor ordering, and close reconciliation."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast
from urllib.parse import SplitResult, parse_qs, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ctower_api.connectors.github.auth import (
    GITHUB_API_ORIGIN,
    GITHUB_API_VERSION,
    GitHubAppAuth,
    GitHubAuthError,
)
from ctower_api.connectors.github.config import GitHubConnectorConfig
from ctower_api.connectors.github.fields import (
    ISSUE_FIELDS,
    LABEL_FIELDS,
    PULL_REQUEST_FIELDS,
    USER_FIELDS,
)
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

__all__ = ["GitHubCursor", "GitHubIssueConnector"]

_NEXT_LINK = re.compile(r'<(?P<url>[^>]+)>;\s*rel="next"')
_CONNECTOR_KIND = "github-issue"
_HTTP_SUCCESS_START = 200
_HTTP_SUCCESS_END = 300
_REDIRECT_START = 300
_REDIRECT_END = 400
_UNAUTHORIZED = 401
_FORBIDDEN = 403
_TOO_MANY_REQUESTS = 429
_SERVER_ERROR_START = 500
_SERVER_ERROR_END = 600
_MAX_COLLECTION_ITEMS = 100
_EXTERNAL_REF_PARTS = 3


class _PayloadError(ValueError):
    pass


class GitHubCursor(BaseModel):
    """Provider-owned stable update watermark plus immutable issue-ID tie-breaker."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_: str = Field(default="ctower.github-cursor/v1", alias="schema")
    updated_at: datetime
    issue_id: int = Field(ge=0)
    page: int = Field(ge=1)

    @model_validator(mode="after")
    def _cursor_is_valid(self) -> GitHubCursor:
        if self.schema_ != "ctower.github-cursor/v1":
            raise ValueError("GitHub cursor schema is unsupported")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("GitHub cursor watermark must be timezone-aware")
        return self

    def encode(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def decode(cls, token: ConnectorCursorToken) -> GitHubCursor:
        try:
            return cls.model_validate_json(token.value)
        except ValueError as error:
            raise _PayloadError("GitHub cursor token is invalid") from error


@dataclass(frozen=True, slots=True)
class _IssueRecord:
    issue_id: int
    updated_at: datetime
    issue: ExternalIssue | None


class GitHubIssueConnector:
    """Perform one bounded GitHub Issue operation per frozen seam invocation."""

    def __init__(
        self,
        config: GitHubConnectorConfig,
        *,
        auth: GitHubAppAuth,
        client: httpx.Client | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._auth = auth
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        self._monotonic = monotonic
        self._diagnostic: str | None = None

    @property
    def diagnostic(self) -> str | None:
        return self._diagnostic

    def rotate_private_key(self, *, binding: str, binding_revision: str) -> None:
        """Run the trusted replacement-key proof before reopening provider authentication."""

        self._auth.rotate_private_key(binding=binding, binding_revision=binding_revision)

    def revoke_credentials(self) -> None:
        """Invalidate local authority before the connected provider revocation drill."""

        self._auth.revoke()

    def fetch_page(
        self, request: FetchIssuePage, attempt: ConnectorAttempt
    ) -> FetchIssuePageResult:
        self._diagnostic = None
        try:
            cursor = GitHubCursor.decode(request.cursor)
            response = self._request(
                "GET",
                self._issues_path(),
                deadline=self._deadline(attempt),
                params={
                    "state": "all",
                    "sort": "updated",
                    "direction": "asc",
                    "since": _timestamp(cursor.updated_at),
                    "per_page": str(request.page_size),
                    "page": str(cursor.page),
                },
            )
            values = _issue_list(_json(response), request.page_size)
            records = tuple(
                sorted(
                    (_issue(value, config=self._config) for value in values),
                    key=lambda item: (item.updated_at, item.issue_id),
                )
            )
            filtered = tuple(
                record.issue
                for record in records
                if record.issue is not None
                and (record.updated_at, record.issue_id) > (cursor.updated_at, cursor.issue_id)
            )
            next_page = _next_page(response.headers, cursor.page, self._issues_path())
            next_cursor = _next_cursor(cursor, records, next_page)
            return ExternalIssuePage(
                issues=filtered,
                next_cursor=ConnectorCursorToken(value=next_cursor.encode()),
                exhausted=next_page is None,
            )
        except GitHubAuthError as error:
            self._diagnostic = str(error)
            return FetchFailure(retry_class="terminal", reason="authentication")
        except httpx.HTTPError as error:
            self._diagnostic = _safe_http_diagnostic("issue fetch", error)
            retry_class, reason = _classify(error)
            return FetchFailure(retry_class=retry_class, reason=reason)
        except _PayloadError as error:
            self._diagnostic = str(error)
            return FetchFailure(retry_class="terminal", reason="invalid_payload")
        except ValueError:
            self._diagnostic = "GitHub normalized contract failed"
            return FetchFailure(retry_class="terminal", reason="contract_violation")

    def comment_and_close(
        self, command: CloseExternalIssue, attempt: ConnectorAttempt
    ) -> CloseExternalIssueResult:
        self._diagnostic = None
        try:
            issue_number = _external_identity(command.external_ref, self._config.repository_id)
            deadline = self._deadline(attempt)
            comments_path = f"{self._issues_path()}/{issue_number}/comments"
            marker_seen = self._marker_present(comments_path, command.marker, deadline=deadline)
        except GitHubAuthError as error:
            self._diagnostic = str(error)
            return CloseFailure(
                retry_class="terminal", reason="authentication", write_disposition="not_written"
            )
        except httpx.HTTPError as error:
            self._diagnostic = _safe_http_diagnostic("close preflight", error)
            return _known_close_failure(error, write_disposition="not_written")
        except _PayloadError as error:
            self._diagnostic = str(error)
            return CloseFailure(
                retry_class="terminal", reason="invalid_payload", write_disposition="not_written"
            )
        comment_created = False
        if not marker_seen:
            posted = self._post_marker(comments_path, command, deadline=deadline)
            if isinstance(posted, (CloseFailure, AmbiguousWrite)):
                return posted
            comment_created = True
        return self._close_issue(
            issue_number,
            comments_path,
            command,
            comment_created=comment_created,
            deadline=deadline,
        )

    def _post_marker(
        self, path: str, command: CloseExternalIssue, *, deadline: float
    ) -> bool | CloseFailure | AmbiguousWrite:
        try:
            response = self._request(
                "POST",
                path,
                deadline=deadline,
                json_body={"body": f"{command.comment}\n\n{command.marker}"},
            )
            if command.marker not in _string(_mapping(_json(response), "GitHub comment"), "body"):
                raise httpx.RemoteProtocolError(
                    "GitHub comment response omitted marker", request=response.request
                )
        except httpx.ConnectError as error:
            return _known_close_failure(error, write_disposition="not_written")
        except httpx.HTTPError as error:
            retry_class, reason = _classify(error)
            if retry_class == "terminal":
                return CloseFailure(
                    retry_class=retry_class, reason=reason, write_disposition="not_written"
                )
            return self._reconcile_marker(path, command.marker, reason=reason, deadline=deadline)
        except _PayloadError:
            return self._reconcile_marker(
                path, command.marker, reason="transport_protocol", deadline=deadline
            )
        return True

    def _reconcile_marker(
        self, path: str, marker: str, *, reason: FailureReason, deadline: float
    ) -> bool | CloseFailure | AmbiguousWrite:
        try:
            present = self._marker_present(path, marker, deadline=deadline)
        except (GitHubAuthError, httpx.HTTPError, _PayloadError):
            return AmbiguousWrite()
        if present:
            return True
        return CloseFailure(
            retry_class="retryable", reason=reason, write_disposition="reconciled_absent"
        )

    def _close_issue(
        self,
        issue_number: int,
        comments_path: str,
        command: CloseExternalIssue,
        *,
        comment_created: bool,
        deadline: float,
    ) -> CloseExternalIssueResult:
        try:
            response = self._request(
                "PATCH",
                f"{self._issues_path()}/{issue_number}",
                deadline=deadline,
                json_body={"state": "closed"},
            )
            if _mapping(_json(response), "GitHub close response").get("state") != "closed":
                raise httpx.RemoteProtocolError(
                    "GitHub close response did not confirm closure", request=response.request
                )
        except httpx.ConnectError as error:
            return _known_close_failure(error, write_disposition="not_written")
        except httpx.HTTPError as error:
            retry_class, reason = _classify(error)
            if retry_class == "terminal":
                return CloseFailure(
                    retry_class=retry_class, reason=reason, write_disposition="not_written"
                )
            return self._reconcile_close(
                issue_number,
                comments_path,
                command,
                comment_created=comment_created,
                reason=reason,
                deadline=deadline,
            )
        except _PayloadError:
            return self._reconcile_close(
                issue_number,
                comments_path,
                command,
                comment_created=comment_created,
                reason="transport_protocol",
                deadline=deadline,
            )
        return ConnectorReceipt(command_id=command.command_id, comment_created=comment_created)

    def _reconcile_close(
        self,
        issue_number: int,
        comments_path: str,
        command: CloseExternalIssue,
        *,
        comment_created: bool,
        reason: FailureReason,
        deadline: float,
    ) -> CloseExternalIssueResult:
        try:
            marker = self._marker_present(comments_path, command.marker, deadline=deadline)
            response = self._request(
                "GET", f"{self._issues_path()}/{issue_number}", deadline=deadline
            )
            state = _mapping(_json(response), "GitHub close reconciliation").get("state")
        except (GitHubAuthError, httpx.HTTPError, _PayloadError):
            return AmbiguousWrite()
        if marker and state == "closed":
            return ConnectorReceipt(command_id=command.command_id, comment_created=comment_created)
        if not marker or state == "open":
            return CloseFailure(
                retry_class="retryable", reason=reason, write_disposition="reconciled_absent"
            )
        return AmbiguousWrite()

    def _marker_present(self, path: str, marker: str, *, deadline: float) -> bool:
        response = self._request(
            "GET",
            path,
            deadline=deadline,
            params={"per_page": "100", "page": "1", "sort": "created", "direction": "desc"},
        )
        comments = _json(response)
        if not isinstance(comments, list) or len(comments) > _MAX_COLLECTION_ITEMS:
            raise _PayloadError("GitHub comment-list response violated the page bound")
        return any(marker in _string(_mapping(item, "GitHub comment"), "body") for item in comments)

    def _request(
        self,
        method: str,
        path: str,
        *,
        deadline: float,
        params: dict[str, str] | None = None,
        json_body: dict[str, str] | None = None,
    ) -> httpx.Response:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise httpx.TimeoutException(
                "connector attempt deadline elapsed",
                request=httpx.Request(method, GITHUB_API_ORIGIN),
            )
        url = _pinned_url(path)
        token = self._auth.installation_token().get_secret_value()
        response = self._client.request(
            method,
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "ctower-github-issues",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
            params=params,
            json=json_body,
            timeout=max(0.001, remaining),
            follow_redirects=False,
        )
        if _REDIRECT_START <= response.status_code < _REDIRECT_END:
            raise _PayloadError("GitHub redirect or destination drift was refused")
        response.raise_for_status()
        if not _HTTP_SUCCESS_START <= response.status_code < _HTTP_SUCCESS_END:
            raise _PayloadError("GitHub response status is outside the supported contract")
        return response

    def _issues_path(self) -> str:
        return f"/repos/{self._config.repository_owner}/{self._config.repository_name}/issues"

    def _deadline(self, attempt: ConnectorAttempt) -> float:
        return self._monotonic() + min(5000, attempt.deadline_remaining_milliseconds) / 1000


def _issue(value: object, *, config: GitHubConnectorConfig) -> _IssueRecord:
    payload = _mapping(value, "GitHub issue", allowed=ISSUE_FIELDS)
    issue_id = _integer(payload, "id")
    number = _integer(payload, "number")
    updated_at = _datetime(_string(payload, "updated_at"))
    if "pull_request" in payload and payload["pull_request"] is not None:
        _mapping(payload["pull_request"], "GitHub pull request", allowed=PULL_REQUEST_FIELDS)
        return _IssueRecord(issue_id, updated_at, None)
    user = _mapping(payload.get("user"), "GitHub issue user", allowed=USER_FIELDS)
    labels = _labels(payload.get("labels"))
    body = payload.get("body")
    if body is not None and not isinstance(body, str):
        raise _PayloadError("GitHub issue body must be text or null")
    state = _state(_string(payload, "state"))
    display_url = _string(payload, "html_url")
    repository_url = _string(payload, "repository_url")
    if repository_url != f"{GITHUB_API_ORIGIN}/repos/{config.repository_full_name}":
        raise _PayloadError("GitHub issue belongs to another configured repository")
    try:
        normalized = ExternalIssue(
            connector_kind=_CONNECTOR_KIND,
            external_ref=f"github:{config.repository_id}:{number}",
            title=_string(payload, "title"),
            description=body or "",
            source_labels=tuple(sorted(labels)),
            reporter_reference=f"github-user:{_integer(user, 'id')}",
            reporter_display_name=_string(user, "login"),
            external_state=state,
            updated_at=updated_at,
            display_url=display_url,
        )
    except ValueError as error:
        raise _PayloadError("GitHub issue violated the normalized contract") from error
    return _IssueRecord(issue_id, updated_at, normalized)


def _next_cursor(
    cursor: GitHubCursor, records: tuple[_IssueRecord, ...], next_page: int | None
) -> GitHubCursor:
    if next_page is not None:
        return GitHubCursor(updated_at=cursor.updated_at, issue_id=cursor.issue_id, page=next_page)
    watermark = max(
        ((item.updated_at, item.issue_id) for item in records),
        default=(cursor.updated_at, cursor.issue_id),
    )
    return GitHubCursor(updated_at=watermark[0], issue_id=watermark[1], page=1)


def _next_page(headers: httpx.Headers, current: int, expected_path: str) -> int | None:
    link = headers.get("link")
    if not link:
        return None
    matched = _NEXT_LINK.search(link)
    if matched is None:
        return None
    parsed = urlsplit(matched.group("url"))
    if not _pagination_destination_matches(parsed, expected_path):
        raise _PayloadError("GitHub pagination destination drift was refused")
    return _pagination_page(parsed.query, current)


def _pagination_destination_matches(value: SplitResult, expected_path: str) -> bool:
    return (
        value.scheme == "https"
        and value.hostname == "api.github.com"
        and value.port in {None, 443}
        and value.path == expected_path
    )


def _pagination_page(query: str, current: int) -> int:
    values = parse_qs(query).get("page")
    if values is None or len(values) != 1 or not values[0].isdigit():
        raise _PayloadError("GitHub pagination link lacks one numeric page")
    page = int(values[0])
    if page <= current:
        raise _PayloadError("GitHub pagination link did not advance")
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


def _classify_status(status: int) -> tuple[RetryClass, FailureReason]:
    if status == _UNAUTHORIZED:
        return "terminal", "authentication"
    if status == _FORBIDDEN:
        return "terminal", "authorization"
    if status == _TOO_MANY_REQUESTS:
        return "retryable", "throttled"
    if _SERVER_ERROR_START <= status < _SERVER_ERROR_END:
        return "retryable", "provider_5xx"
    return "terminal", "ordinary_4xx"


def _known_close_failure(
    error: httpx.HTTPError, *, write_disposition: WriteDisposition
) -> CloseFailure:
    retry_class, reason = _classify(error)
    return CloseFailure(retry_class=retry_class, reason=reason, write_disposition=write_disposition)


def _safe_http_diagnostic(operation: str, error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"GitHub {operation} failed with status {error.response.status_code}"
    return f"GitHub {operation} failed with {type(error).__name__}"


def _external_identity(external_ref: str, repository_id: int) -> int:
    parts = external_ref.split(":")
    if (
        len(parts) != _EXTERNAL_REF_PARTS
        or parts[0] != "github"
        or not parts[1].isdigit()
        or not parts[2].isdigit()
        or int(parts[1]) != repository_id
        or int(parts[2]) < 1
    ):
        raise _PayloadError("GitHub external reference is invalid")
    return int(parts[2])


def _pinned_url(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        raise _PayloadError("GitHub destination drift was refused")
    url = httpx.URL(f"{GITHUB_API_ORIGIN}{path}")
    if url.scheme != "https" or url.host != "api.github.com" or url.port not in {None, 443}:
        raise _PayloadError("GitHub destination drift was refused")
    return str(url)


def _mapping(
    value: object,
    label: str,
    *,
    allowed: frozenset[str] | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise _PayloadError(f"{label} must be an object")
    result = cast(dict[str, object], value)
    if allowed is not None and not set(result).issubset(allowed):
        raise _PayloadError(f"{label} contains unsupported fields")
    return result


def _json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as error:
        raise _PayloadError("GitHub response was not JSON") from error


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise _PayloadError(f"GitHub field {key} must be text")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _PayloadError(f"GitHub field {key} must be a positive integer")
    return value


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise _PayloadError("GitHub updated_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _PayloadError("GitHub updated_at must be timezone-aware")
    return parsed


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > _MAX_COLLECTION_ITEMS:
        raise _PayloadError("GitHub issue labels violated the page bound")
    names: list[str] = []
    for item in value:
        label = _mapping(item, "GitHub label", allowed=LABEL_FIELDS)
        names.append(_string(label, "name"))
    if len(set(names)) != len(names):
        raise _PayloadError("GitHub issue labels must be unique")
    return tuple(names)


def _issue_list(value: object, page_size: int) -> list[object]:
    if not isinstance(value, list) or len(value) > page_size:
        raise _PayloadError("GitHub issue-list response violated the page bound")
    return cast(list[object], value)


def _state(value: str) -> Literal["opened", "closed"]:
    if value == "open":
        return "opened"
    if value == "closed":
        return "closed"
    raise _PayloadError("GitHub issue state is unsupported")


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")

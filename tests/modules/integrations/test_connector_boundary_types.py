from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from ctower_api.connectors.gitlab.adapter import GitLabCursor
from ctower_kernel.integrations import (
    AmbiguousWrite,
    CloseExternalIssue,
    CloseExternalIssueResult,
    CloseFailure,
    ConnectorAttempt,
    ConnectorCursorToken,
    ConnectorLabelMapping,
    ConnectorReceipt,
    ConnectorRegistration,
    ExternalIssue,
    ExternalIssuePage,
    FetchFailure,
    FetchIssuePage,
    FetchIssuePageResult,
)

__all__: tuple[str, ...] = ()

_AWARE = datetime(2026, 8, 8, 8, tzinfo=UTC)
_NAIVE = _AWARE.replace(tzinfo=None)
_CORE_ATTEMPT_LIMIT = 4


def _issue(**changes: object) -> ExternalIssue:
    values: dict[str, object] = {
        "connector_kind": "gitlab-issue",
        "external_ref": "gitlab:42:7",
        "title": "Feedback title",
        "description": "Feedback body",
        "source_labels": ("bug",),
        "reporter_reference": "@reporter",
        "reporter_display_name": "Report Person",
        "external_state": "opened",
        "display_url": "https://gitlab.example.test/group/project/-/issues/7",
        "updated_at": _AWARE,
    }
    values.update(changes)
    return ExternalIssue(**values)  # type: ignore[arg-type]


def _registration(**changes: object) -> ConnectorRegistration:
    values: dict[str, object] = {
        "registration_key": "gitlab.feedback",
        "revision_id": UUID("22222222-2222-4222-8222-222222222222"),
        "revision_digest": "sha256:" + "a" * 64,
        "connector_kind": "gitlab-issue",
        "source_display_name": "GitLab",
        "project_key": "ctower",
        "initial_custodian_id": UUID("11111111-1111-4111-8111-111111111111"),
        "initial_cursor": ConnectorCursorToken(
            value=GitLabCursor(updated_after=_AWARE, page=1).encode()
        ),
        "page_size": 50,
        "poll_interval": timedelta(seconds=60),
        "label_map": (ConnectorLabelMapping(source="bug", target="type.bug"),),
    }
    values.update(changes)
    return ConnectorRegistration(**values)  # type: ignore[arg-type]


def test_gitlab_types_reject_unbounded_or_secret_bearing_values() -> None:
    issue = _issue()
    registration = _registration()

    assert issue.external_ref == "gitlab:42:7"
    assert issue.to_mapping()["reporter_reference"] == "@reporter"
    assert registration.label_key("bug") == "type.bug"
    assert "token" not in registration.to_mapping()
    assert "base_url" not in registration.to_mapping()

    boundary_reporter = _issue(reporter_reference="@" + "r" * 255)
    assert len(boundary_reporter.reporter_reference) == len("@" + "r" * 255)
    with pytest.raises(ValidationError):
        _issue(reporter_reference="@" + "r" * 256)


@pytest.mark.parametrize(
    "changes",
    [
        {"connector_kind": "BAD"},
        {"connector_kind": "a" * 65},
        {"external_ref": ""},
        {"external_ref": "x" * 257},
        {"title": ""},
        {"description": "x" * 60_001},
        {"source_labels": tuple(f"label-{index}" for index in range(101))},
        {"source_labels": ("bug", "bug")},
        {"source_labels": ("",)},
        {"reporter_reference": ""},
        {"reporter_display_name": ""},
        {"external_state": ""},
        {"external_state": "done"},
        {"display_url": "http://gitlab.example.test/issues/7"},
        {"updated_at": _NAIVE},
    ],
)
def test_issue_refuses_each_untrusted_boundary_violation(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _issue(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"registration_key": "BAD"},
        {"revision_id": "not-a-uuid"},
        {"revision_digest": "sha256:nope"},
        {"connector_kind": "BAD"},
        {"connector_kind": "a" * 65},
        {"source_display_name": ""},
        {"project_key": "UPPER"},
        {"initial_cursor": "x" * 4097},
        {"page_size": 0},
        {"page_size": 101},
        {"poll_interval": timedelta(seconds=14)},
        {"poll_interval": timedelta(seconds=3601)},
        {
            "label_map": (
                ConnectorLabelMapping(source="bug", target="type.bug"),
                ConnectorLabelMapping(source="bug", target="type.other"),
            )
        },
    ],
)
def test_binding_refuses_each_catalog_boundary_violation(
    changes: dict[str, object],
) -> None:
    with pytest.raises((ValidationError, TypeError)):
        _registration(**changes)


def test_cursor_page_close_and_receipt_values_are_strict_and_serializable() -> None:
    token = ConnectorCursorToken(value=GitLabCursor(updated_after=_AWARE, page=2).encode())
    request = FetchIssuePage(cursor=token, page_size=50)
    attempt = ConnectorAttempt(
        attempt_number=1,
        max_attempts=4,
        deadline_remaining_milliseconds=10_000,
    )
    command_id = uuid4()
    receipt = ConnectorReceipt(command_id=command_id, comment_created=True)

    assert request.cursor == token
    assert attempt.max_attempts == _CORE_ATTEMPT_LIMIT
    assert receipt.issue_closed and receipt.marker_present
    with pytest.raises(ValidationError):
        CloseExternalIssue(
            external_ref="gitlab:42:7",
            command_id=command_id,
            marker="wrong",
            comment="Proof-gated close",
        )


def test_strict_result_unions_are_discriminated_and_operation_specific() -> None:
    fetch_adapter: TypeAdapter[FetchIssuePageResult] = TypeAdapter(FetchIssuePageResult)
    close_adapter: TypeAdapter[CloseExternalIssueResult] = TypeAdapter(CloseExternalIssueResult)
    page = ExternalIssuePage(
        issues=(_issue(),),
        next_cursor=ConnectorCursorToken(
            value=GitLabCursor(updated_after=_AWARE + timedelta(seconds=1), page=1).encode()
        ),
        exhausted=True,
    )
    fetch_failure = FetchFailure(retry_class="retryable", reason="timeout")
    close_failure = CloseFailure(
        retry_class="retryable",
        reason="transport_read",
        write_disposition="reconciled_absent",
    )

    assert fetch_adapter.validate_python(page).kind == "page"
    assert fetch_adapter.validate_python(fetch_failure).kind == "fetch_failure"
    assert close_adapter.validate_python(close_failure).kind == "close_failure"
    assert close_adapter.validate_python(AmbiguousWrite()).kind == "ambiguous_write"
    with pytest.raises(ValidationError):
        fetch_adapter.validate_python(close_failure)
    with pytest.raises(ValidationError):
        close_adapter.validate_python(fetch_failure)


@pytest.mark.parametrize(
    "value",
    [
        {"retry_class": "retryable", "reason": "authentication"},
        {"retry_class": "terminal", "reason": "timeout"},
    ],
)
def test_failure_reason_and_retry_class_are_a_closed_pair(value: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="retry class"):
        FetchFailure.model_validate(value)

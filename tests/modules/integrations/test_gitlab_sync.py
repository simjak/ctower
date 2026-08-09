from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from ctower_kernel.integrations import (
    GitLabCloseCommand,
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssue,
    GitLabIssueLink,
    GitLabIssuePage,
    GitLabReporter,
    GitLabSyncBinding,
)

__all__: tuple[str, ...] = ()

_AWARE = datetime(2026, 8, 8, 8, tzinfo=UTC)
_EVENT_CURSOR = 41
_NAIVE = _AWARE.replace(tzinfo=None)


def _issue(**changes: object) -> GitLabIssue:
    values: dict[str, object] = {
        "project_id": 42,
        "iid": 7,
        "title": "Feedback title",
        "body": "Feedback body",
        "labels": ("bug",),
        "reporter": GitLabReporter("reporter", "Report Person"),
        "state": "opened",
        "web_url": "https://gitlab.example.test/group/project/-/issues/7",
        "updated_at": _AWARE,
    }
    values.update(changes)
    return GitLabIssue(**values)  # type: ignore[arg-type]


def _binding(**changes: object) -> GitLabSyncBinding:
    values: dict[str, object] = {
        "integration_key": "gitlab.feedback",
        "revision_id": UUID("22222222-2222-4222-8222-222222222222"),
        "revision_digest": "sha256:" + "a" * 64,
        "project_id": 42,
        "project_key": "ctower",
        "initial_custodian_id": UUID("11111111-1111-4111-8111-111111111111"),
        "import_updated_after": _AWARE,
        "page_size": 50,
        "poll_interval": timedelta(seconds=60),
        "label_map": (("bug", "type.bug"),),
    }
    values.update(changes)
    return GitLabSyncBinding(**values)  # type: ignore[arg-type]


def test_gitlab_types_reject_unbounded_or_secret_bearing_values() -> None:
    reporter = GitLabReporter(username="reporter", name="Report Person")
    issue = _issue(reporter=reporter)

    assert issue.source_ref == "gitlab:42:7"
    assert issue.to_mapping()["reporter"] == {
        "username": "reporter",
        "name": "Report Person",
    }
    binding = _binding()
    assert binding.label_key("bug") == "type.bug"
    assert "token" not in binding.to_mapping()


def test_gitlab_type_identity_rejects_wrong_project_and_unstable_configuration() -> None:
    try:
        GitLabSyncBinding(
            integration_key="bad",
            revision_id=uuid4(),
            revision_digest="sha256:" + "a" * 64,
            project_id=0,
            project_key="ctower",
            initial_custodian_id=uuid4(),
            import_updated_after=datetime.now(UTC),
            page_size=101,
            poll_interval=timedelta(seconds=1),
            label_map=(),
        )
    except ValueError as error:
        assert "GitLab" in str(error) or "poll" in str(error)
    else:
        raise AssertionError("invalid GitLab binding was accepted")


@pytest.mark.parametrize(
    "username,name",
    [
        ("not a handle", "Report Person"),
        ("reporter", ""),
    ],
)
def test_reporter_refuses_each_invalid_identity_shape(username: str, name: str) -> None:
    with pytest.raises(ValueError, match="reporter"):
        GitLabReporter(username, name)


@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": False},
        {"project_id": 0},
        {"iid": False},
        {"iid": 0},
        {"title": ""},
        {"body": "x" * 60_001},
        {"state": "merged"},
        {"labels": tuple(f"label-{index}" for index in range(101))},
        {"labels": ("bug", "bug")},
        {"labels": ("",)},
        {"labels": ("x" * 256,)},
        {"web_url": "http://gitlab.example.test/issues/7"},
        {"web_url": "https:///issues/7"},
        {"updated_at": _NAIVE},
    ],
)
def test_issue_refuses_each_untrusted_boundary_violation(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="GitLab"):
        _issue(**changes)


@pytest.mark.parametrize(
    "changes,error_type",
    [
        ({"integration_key": "BAD"}, ValueError),
        ({"revision_id": "not-a-uuid"}, TypeError),
        ({"revision_digest": "sha256:nope"}, ValueError),
        ({"project_id": False}, ValueError),
        ({"project_id": 0}, ValueError),
        ({"project_key": "UPPER"}, ValueError),
        ({"import_updated_after": _NAIVE}, ValueError),
        ({"page_size": 0}, ValueError),
        ({"page_size": 101}, ValueError),
        ({"poll_interval": timedelta(seconds=14)}, ValueError),
        ({"poll_interval": timedelta(seconds=3601)}, ValueError),
        ({"label_map": tuple((str(index), "type.bug") for index in range(101))}, ValueError),
        ({"label_map": (("bug", "type.bug"), ("bug", "type.other"))}, ValueError),
        ({"label_map": (("", "type.bug"),)}, ValueError),
        ({"label_map": (("bug", "BAD"),)}, ValueError),
    ],
)
def test_binding_refuses_each_catalog_boundary_violation(
    changes: dict[str, object], error_type: type[Exception]
) -> None:
    with pytest.raises(error_type, match="GitLab"):
        _binding(**changes)


def test_cursor_page_close_and_receipt_values_are_strict_and_serializable() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        GitLabCursor(_NAIVE, 1, 0)
    with pytest.raises(ValueError, match="positions"):
        GitLabCursor(_AWARE, 0, 0)
    with pytest.raises(ValueError, match="positions"):
        GitLabCursor(_AWARE, 1, -1)
    with pytest.raises(ValueError, match="next page"):
        GitLabIssuePage((_issue(),), 1)
    with pytest.raises(ValueError, match="close comment"):
        GitLabCloseCommand(uuid4(), "")
    with pytest.raises(ValueError, match="close comment"):
        GitLabCloseCommand(uuid4(), "   ")

    cursor = GitLabCursor(_AWARE, 2, _EVENT_CURSOR)
    link = GitLabIssueLink(
        uuid4(), "gitlab.feedback", "sha256:" + "a" * 64, 42, 7, uuid4(), uuid4(), "https://x"
    )
    command = GitLabCloseCommand(uuid4(), "Proof-gated close")
    receipt = GitLabCloseReceipt(command.delivery_id, comment_created=True, issue_closed=True)

    assert cursor.to_mapping()["project_event_cursor"] == _EVENT_CURSOR
    assert link.source_ref == "gitlab:42:7"
    assert command.marker in f"marker={command.marker}"
    assert command.to_mapping()["delivery_id"] == str(command.delivery_id)
    assert receipt.to_mapping()["issue_closed"] is True

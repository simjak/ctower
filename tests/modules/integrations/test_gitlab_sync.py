from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ctower_kernel.integrations import GitLabIssue, GitLabReporter, GitLabSyncBinding


def test_gitlab_types_reject_unbounded_or_secret_bearing_values() -> None:
    reporter = GitLabReporter(username="reporter", name="Report Person")
    issue = GitLabIssue(
        project_id=42,
        iid=7,
        title="Feedback title",
        body="Feedback body",
        labels=("bug",),
        reporter=reporter,
        state="opened",
        web_url="https://gitlab.example.test/group/project/-/issues/7",
        updated_at=datetime(2026, 8, 8, 8, tzinfo=UTC),
    )

    assert issue.source_ref == "gitlab:42:7"
    assert issue.to_mapping()["reporter"] == {
        "username": "reporter",
        "name": "Report Person",
    }
    binding = GitLabSyncBinding(
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

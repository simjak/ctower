"""Strict GitHub REST response allowlists."""

from __future__ import annotations

ISSUE_FIELDS = frozenset(
    {
        "active_lock_reason",
        "assignee",
        "assignees",
        "author_association",
        "body",
        "closed_at",
        "closed_by",
        "comments",
        "comments_url",
        "created_at",
        "events_url",
        "html_url",
        "id",
        "labels",
        "labels_url",
        "locked",
        "milestone",
        "node_id",
        "number",
        "performed_via_github_app",
        "pinned_comment",
        "pull_request",
        "reactions",
        "repository_url",
        "state",
        "state_reason",
        "sub_issues_summary",
        "timeline_url",
        "title",
        "type",
        "updated_at",
        "url",
        "user",
    }
)
USER_FIELDS = frozenset(
    {
        "avatar_url",
        "events_url",
        "followers_url",
        "following_url",
        "gists_url",
        "gravatar_id",
        "html_url",
        "id",
        "login",
        "node_id",
        "organizations_url",
        "received_events_url",
        "repos_url",
        "site_admin",
        "starred_url",
        "subscriptions_url",
        "type",
        "url",
        "user_view_type",
    }
)
LABEL_FIELDS = frozenset({"color", "default", "description", "id", "name", "node_id", "url"})
PULL_REQUEST_FIELDS = frozenset({"diff_url", "html_url", "merged_at", "patch_url", "url"})

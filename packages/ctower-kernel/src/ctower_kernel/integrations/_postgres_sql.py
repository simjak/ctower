"""PostgreSQL persistence behind the GitLab integration Store Interface."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.integrations.interface import (
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssue,
    GitLabIssueLink,
    GitLabReporter,
    GitLabSyncBinding,
    GitLabSyncError,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def claim(
    dsn: str, actor: Actor, binding: GitLabSyncBinding, *, now: datetime
) -> GitLabCursor | None:
    due = now + binding.poll_interval
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            INSERT INTO integration_gitlab_sync_progress (
                tenant_id, integration_key, component_revision_id, revision_digest,
                gitlab_project_id, updated_after, page, project_event_cursor,
                next_poll_at, consecutive_failures
            )
            SELECT %s, %s, %s, %s, %s, %s, 1, 0, %s, 0
            WHERE EXISTS (
                SELECT 1
                FROM company_bundle_active AS active
                JOIN company_bundle_members AS member
                  ON member.tenant_id = active.tenant_id
                 AND member.bundle_revision_id = active.bundle_revision_id
                JOIN catalog_component_revisions AS revision
                  ON revision.tenant_id = member.tenant_id
                 AND revision.component_revision_id = member.component_revision_id
                JOIN catalog_components AS component
                  ON component.tenant_id = revision.tenant_id
                 AND component.component_id = revision.component_id
                WHERE active.tenant_id = %s
                  AND revision.component_revision_id = %s
                  AND revision.content_digest = %s
                  AND component.kind = 'integration'
                  AND component.component_key = %s
            )
            ON CONFLICT DO NOTHING
            """,
            (
                actor.tenant_id,
                binding.integration_key,
                binding.revision_id,
                _digest_bytes(binding.revision_digest),
                binding.project_id,
                binding.import_updated_after,
                now,
                actor.tenant_id,
                binding.revision_id,
                _digest_bytes(binding.revision_digest),
                binding.integration_key,
            ),
        )
        row = connection.execute(
            """
            UPDATE integration_gitlab_sync_progress AS progress
            SET next_poll_at = %s, claimed_at = %s, completed_at = NULL
            WHERE progress.tenant_id = %s
              AND progress.integration_key = %s
              AND progress.component_revision_id = %s
              AND progress.revision_digest = %s
              AND progress.gitlab_project_id = %s
              AND progress.next_poll_at <= %s
              AND EXISTS (
                  SELECT 1
                  FROM company_bundle_active AS active
                  JOIN company_bundle_members AS member
                    ON member.tenant_id = active.tenant_id
                   AND member.bundle_revision_id = active.bundle_revision_id
                  WHERE active.tenant_id = progress.tenant_id
                    AND member.component_revision_id = progress.component_revision_id
              )
            RETURNING updated_after, page, project_event_cursor
            """,
            (
                due,
                now,
                actor.tenant_id,
                binding.integration_key,
                binding.revision_id,
                _digest_bytes(binding.revision_digest),
                binding.project_id,
                now,
            ),
        ).fetchone()
    return _cursor(row) if row is not None else None


def issue_link(
    dsn: str, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
) -> GitLabIssueLink | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT tenant_id, integration_key, source_revision_digest,
                gitlab_project_id, issue_iid, ticket_id, thread_id, web_url
            FROM integration_gitlab_issue_links
            WHERE tenant_id = %s AND integration_key = %s
              AND gitlab_project_id = %s AND issue_iid = %s
            """,
            (actor.tenant_id, binding.integration_key, binding.project_id, issue_iid),
        ).fetchone()
    return _link(row) if row is not None else None


def ticket_link(
    dsn: str, actor: Actor, binding: GitLabSyncBinding, ticket_id: UUID
) -> GitLabIssueLink | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT tenant_id, integration_key, source_revision_digest,
                gitlab_project_id, issue_iid, ticket_id, thread_id, web_url
            FROM integration_gitlab_issue_links
            WHERE tenant_id = %s AND integration_key = %s AND ticket_id = %s
            """,
            (actor.tenant_id, binding.integration_key, ticket_id),
        ).fetchone()
    return _link(row) if row is not None else None


def latest_issue(
    dsn: str, actor: Actor, binding: GitLabSyncBinding, issue_iid: int
) -> GitLabIssue | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT gitlab_project_id, issue_iid, title, body, labels,
                reporter_username, reporter_name, issue_state, web_url,
                source_updated_at
            FROM integration_gitlab_issue_observations
            WHERE tenant_id = %s AND integration_key = %s
              AND gitlab_project_id = %s AND issue_iid = %s
            ORDER BY source_updated_at DESC, observed_at DESC, payload_digest DESC
            LIMIT 1
            """,
            (actor.tenant_id, binding.integration_key, binding.project_id, issue_iid),
        ).fetchone()
    return _issue(row) if row is not None else None


def record_issue(
    dsn: str,
    actor: Actor,
    binding: GitLabSyncBinding,
    issue: GitLabIssue,
    *,
    ticket_id: UUID,
    thread_id: UUID,
    observed_at: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            INSERT INTO integration_gitlab_issue_links (
                tenant_id, integration_key, source_component_revision_id,
                source_revision_digest, gitlab_project_id, issue_iid,
                ticket_id, thread_id, web_url, linked_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                actor.tenant_id,
                binding.integration_key,
                binding.revision_id,
                _digest_bytes(binding.revision_digest),
                issue.project_id,
                issue.iid,
                ticket_id,
                thread_id,
                issue.web_url,
                observed_at,
            ),
        )
        row = connection.execute(
            """
            SELECT tenant_id, integration_key, source_revision_digest,
                gitlab_project_id, issue_iid, ticket_id, thread_id, web_url
            FROM integration_gitlab_issue_links
            WHERE tenant_id = %s AND integration_key = %s
              AND gitlab_project_id = %s AND issue_iid = %s
            """,
            (actor.tenant_id, binding.integration_key, issue.project_id, issue.iid),
        ).fetchone()
        expected = GitLabIssueLink(
            actor.tenant_id,
            binding.integration_key,
            binding.revision_digest,
            issue.project_id,
            issue.iid,
            ticket_id,
            thread_id,
            issue.web_url,
        )
        if row is None or _link(row) != expected:
            raise GitLabSyncError("GitLab issue already has a different custody link")
        _record_observation(connection, actor, binding, issue, observed_at=observed_at)


def record_observation(
    dsn: str,
    actor: Actor,
    binding: GitLabSyncBinding,
    issue: GitLabIssue,
    *,
    observed_at: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        _record_observation(connection, actor, binding, issue, observed_at=observed_at)


def delivered(dsn: str, actor: Actor, binding: GitLabSyncBinding, event_id: UUID) -> bool:
    del binding
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT 1 FROM integration_gitlab_close_deliveries
            WHERE tenant_id = %s AND event_id = %s
            """,
            (actor.tenant_id, event_id),
        ).fetchone()
    return row is not None


def record_delivery(
    dsn: str,
    actor: Actor,
    binding: GitLabSyncBinding,
    link: GitLabIssueLink,
    receipt: GitLabCloseReceipt,
    *,
    delivered_at: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            INSERT INTO integration_gitlab_close_deliveries (
                tenant_id, integration_key, component_revision_id,
                gitlab_project_id, issue_iid, ticket_id, event_id,
                comment_created, issue_closed, delivered_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                actor.tenant_id,
                binding.integration_key,
                binding.revision_id,
                link.project_id,
                link.issue_iid,
                link.ticket_id,
                receipt.delivery_id,
                receipt.comment_created,
                receipt.issue_closed,
                delivered_at,
            ),
        )
        row = connection.execute(
            """
            SELECT gitlab_project_id, issue_iid, ticket_id, event_id,
                comment_created, issue_closed
            FROM integration_gitlab_close_deliveries
            WHERE tenant_id = %s AND event_id = %s
            """,
            (actor.tenant_id, receipt.delivery_id),
        ).fetchone()
        expected = (
            link.project_id,
            link.issue_iid,
            link.ticket_id,
            receipt.delivery_id,
            receipt.comment_created,
            receipt.issue_closed,
        )
        actual = (
            (
                int(cast(int, row["gitlab_project_id"])),
                int(cast(int, row["issue_iid"])),
                cast(UUID, row["ticket_id"]),
                cast(UUID, row["event_id"]),
                bool(row["comment_created"]),
                bool(row["issue_closed"]),
            )
            if row is not None
            else None
        )
        if actual != expected:
            raise GitLabSyncError("GitLab close event already has a different delivery receipt")


def complete(
    dsn: str,
    actor: Actor,
    binding: GitLabSyncBinding,
    cursor: GitLabCursor,
    *,
    now: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        result = connection.execute(
            """
            UPDATE integration_gitlab_sync_progress
            SET updated_after = %s, page = %s, project_event_cursor = %s,
                consecutive_failures = 0, completed_at = %s
            WHERE tenant_id = %s AND integration_key = %s
              AND component_revision_id = %s
              AND updated_after <= %s
              AND project_event_cursor <= %s
            """,
            (
                cursor.updated_after,
                cursor.page,
                cursor.project_event_cursor,
                now,
                actor.tenant_id,
                binding.integration_key,
                binding.revision_id,
                cursor.updated_after,
                cursor.project_event_cursor,
            ),
        )
        if result.rowcount != 1:
            raise GitLabSyncError("GitLab cursor completion was stale or unavailable")


def fail(dsn: str, actor: Actor, binding: GitLabSyncBinding, *, now: datetime) -> None:
    retry_seconds = min(int(binding.poll_interval.total_seconds()) * 2, 3600)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            UPDATE integration_gitlab_sync_progress
            SET next_poll_at = %s,
                consecutive_failures = LEAST(consecutive_failures + 1, 8)
            WHERE tenant_id = %s AND integration_key = %s
              AND component_revision_id = %s
            """,
            (
                now + timedelta(seconds=retry_seconds),
                actor.tenant_id,
                binding.integration_key,
                binding.revision_id,
            ),
        )


def _record_observation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    binding: GitLabSyncBinding,
    issue: GitLabIssue,
    *,
    observed_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO integration_gitlab_issue_observations (
            tenant_id, integration_key, component_revision_id,
            gitlab_project_id, issue_iid, payload_digest, title, body, labels,
            reporter_username, reporter_name, issue_state, web_url,
            source_updated_at, observed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            actor.tenant_id,
            binding.integration_key,
            binding.revision_id,
            issue.project_id,
            issue.iid,
            _issue_digest(issue),
            issue.title,
            issue.body,
            list(issue.labels),
            issue.reporter.username,
            issue.reporter.name,
            issue.state,
            issue.web_url,
            issue.updated_at,
            observed_at,
        ),
    )


def _cursor(row: dict[str, object]) -> GitLabCursor:
    return GitLabCursor(
        cast(datetime, row["updated_after"]),
        int(cast(int, row["page"])),
        int(cast(int, row["project_event_cursor"])),
    )


def _link(row: dict[str, object]) -> GitLabIssueLink:
    return GitLabIssueLink(
        cast(UUID, row["tenant_id"]),
        str(row["integration_key"]),
        "sha256:" + bytes(cast(bytes, row["source_revision_digest"])).hex(),
        int(cast(int, row["gitlab_project_id"])),
        int(cast(int, row["issue_iid"])),
        cast(UUID, row["ticket_id"]),
        cast(UUID, row["thread_id"]),
        str(row["web_url"]),
    )


def _issue(row: dict[str, object]) -> GitLabIssue:
    return GitLabIssue(
        project_id=int(cast(int, row["gitlab_project_id"])),
        iid=int(cast(int, row["issue_iid"])),
        title=str(row["title"]),
        body=str(row["body"]),
        labels=tuple(cast(list[str], row["labels"])),
        reporter=GitLabReporter(
            username=str(row["reporter_username"]),
            name=str(row["reporter_name"]),
        ),
        state=str(row["issue_state"]),
        web_url=str(row["web_url"]),
        updated_at=cast(datetime, row["source_updated_at"]),
    )


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _issue_digest(issue: GitLabIssue) -> bytes:
    return hashlib.sha256(
        json.dumps(
            issue.to_mapping(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    ).digest()

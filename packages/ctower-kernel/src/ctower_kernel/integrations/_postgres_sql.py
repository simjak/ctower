"""PostgreSQL persistence behind the provider-neutral ConnectorStore Interface."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.integrations.interface import (
    ConnectorClaim,
    ConnectorCursorToken,
    ConnectorLink,
    ConnectorReceipt,
    ConnectorRegistration,
    ConnectorSyncError,
    ExternalIssue,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def claim(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    *,
    owner_id: UUID,
    now: datetime,
) -> ConnectorClaim | None:
    expires_at = now + (registration.poll_interval * 2)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            INSERT INTO connector_sync_progress (
                tenant_id, connector_registration_key, registration_revision_id,
                revision_digest, cursor_token, project_event_cursor,
                next_poll_at, consecutive_failures
            )
            SELECT %s, %s, %s, %s, %s, 0, %s, 0
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
                registration.registration_key,
                registration.revision_id,
                _digest_bytes(registration.revision_digest),
                registration.initial_cursor.value,
                now,
                actor.tenant_id,
                registration.revision_id,
                _digest_bytes(registration.revision_digest),
                registration.registration_key,
            ),
        )
        row = connection.execute(
            """
            UPDATE connector_sync_progress AS progress
            SET claim_owner = %s, claim_fence = claim_fence + 1,
                claim_expires_at = %s, claimed_at = %s, completed_at = NULL
            WHERE progress.tenant_id = %s
              AND progress.connector_registration_key = %s
              AND progress.registration_revision_id = %s
              AND progress.revision_digest = %s
              AND progress.next_poll_at <= %s
              AND (progress.claim_owner IS NULL OR progress.claim_expires_at <= %s)
              AND EXISTS (
                  SELECT 1
                  FROM company_bundle_active AS active
                  JOIN company_bundle_members AS member
                    ON member.tenant_id = active.tenant_id
                   AND member.bundle_revision_id = active.bundle_revision_id
                  WHERE active.tenant_id = progress.tenant_id
                    AND member.component_revision_id = progress.registration_revision_id
              )
            RETURNING cursor_token, project_event_cursor,
                claim_owner, claim_fence, claim_expires_at
            """,
            (
                owner_id,
                expires_at,
                now,
                actor.tenant_id,
                registration.registration_key,
                registration.revision_id,
                _digest_bytes(registration.revision_digest),
                now,
                now,
            ),
        ).fetchone()
    return _claim(row) if row is not None else None


def active_revision_id(
    dsn: str,
    actor: Actor,
    *,
    registration_key: str,
    revision_digest: str,
) -> UUID | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT revision.component_revision_id
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
              AND component.kind = 'integration'
              AND component.component_key = %s
              AND revision.content_digest = %s
            """,
            (actor.tenant_id, registration_key, _digest_bytes(revision_digest)),
        ).fetchone()
    return cast(UUID, row["component_revision_id"]) if row is not None else None


def issue_link(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    external_ref: str,
) -> ConnectorLink | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT tenant_id, connector_registration_key, source_revision_digest,
                connector_kind, external_ref, ticket_id, thread_id, display_url
            FROM connector_issue_links
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND external_ref = %s
            """,
            (actor.tenant_id, registration.registration_key, external_ref),
        ).fetchone()
    return _link(row) if row is not None else None


def ticket_link(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    ticket_id: UUID,
) -> ConnectorLink | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT tenant_id, connector_registration_key, source_revision_digest,
                connector_kind, external_ref, ticket_id, thread_id, display_url
            FROM connector_issue_links
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND ticket_id = %s
            """,
            (actor.tenant_id, registration.registration_key, ticket_id),
        ).fetchone()
    return _link(row) if row is not None else None


def latest_issue(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    external_ref: str,
) -> ExternalIssue | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT connector_kind, external_ref, title, description, source_labels,
                reporter_reference, reporter_display_name, external_state,
                display_url, source_updated_at
            FROM connector_issue_observations
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND external_ref = %s
            ORDER BY source_updated_at DESC, observed_at DESC, payload_digest DESC
            LIMIT 1
            """,
            (actor.tenant_id, registration.registration_key, external_ref),
        ).fetchone()
    return _issue(row) if row is not None else None


def record_issue(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    issue: ExternalIssue,
    *,
    ticket_id: UUID,
    thread_id: UUID,
    observed_at: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            INSERT INTO connector_issue_links (
                tenant_id, connector_registration_key,
                source_registration_revision_id, source_revision_digest,
                connector_kind, external_ref, ticket_id, thread_id,
                display_url, linked_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                actor.tenant_id,
                registration.registration_key,
                registration.revision_id,
                _digest_bytes(registration.revision_digest),
                issue.connector_kind,
                issue.external_ref,
                ticket_id,
                thread_id,
                issue.display_url,
                observed_at,
            ),
        )
        row = connection.execute(
            """
            SELECT tenant_id, connector_registration_key, source_revision_digest,
                connector_kind, external_ref, ticket_id, thread_id, display_url
            FROM connector_issue_links
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND external_ref = %s
            """,
            (actor.tenant_id, registration.registration_key, issue.external_ref),
        ).fetchone()
        expected = ConnectorLink(
            tenant_id=actor.tenant_id,
            registration_key=registration.registration_key,
            revision_digest=registration.revision_digest,
            connector_kind=issue.connector_kind,
            external_ref=issue.external_ref,
            ticket_id=ticket_id,
            thread_id=thread_id,
            display_url=issue.display_url,
        )
        if row is None or _link(row) != expected:
            raise ConnectorSyncError("external reference already has a different custody link")
        _record_observation(connection, actor, registration, issue, observed_at=observed_at)


def record_observation(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    issue: ExternalIssue,
    *,
    observed_at: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        _record_observation(connection, actor, registration, issue, observed_at=observed_at)


def delivered(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    command_id: UUID,
) -> bool:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT 1 FROM connector_close_deliveries
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND command_id = %s
            """,
            (actor.tenant_id, registration.registration_key, command_id),
        ).fetchone()
    return row is not None


def record_delivery(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    link: ConnectorLink,
    receipt: ConnectorReceipt,
    *,
    delivered_at: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            """
            INSERT INTO connector_close_deliveries (
                tenant_id, connector_registration_key, registration_revision_id,
                connector_kind, external_ref, ticket_id, command_id,
                marker_present, comment_created, issue_closed, delivered_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                actor.tenant_id,
                registration.registration_key,
                registration.revision_id,
                link.connector_kind,
                link.external_ref,
                link.ticket_id,
                receipt.command_id,
                receipt.marker_present,
                receipt.comment_created,
                receipt.issue_closed,
                delivered_at,
            ),
        )
        row = connection.execute(
            """
            SELECT connector_kind, external_ref, ticket_id, command_id,
                marker_present, comment_created, issue_closed
            FROM connector_close_deliveries
            WHERE tenant_id = %s AND command_id = %s
            """,
            (actor.tenant_id, receipt.command_id),
        ).fetchone()
        expected = (
            link.connector_kind,
            link.external_ref,
            link.ticket_id,
            receipt.command_id,
            True,
            receipt.comment_created,
            True,
        )
        actual = (
            (
                str(row["connector_kind"]),
                str(row["external_ref"]),
                cast(UUID, row["ticket_id"]),
                cast(UUID, row["command_id"]),
                bool(row["marker_present"]),
                bool(row["comment_created"]),
                bool(row["issue_closed"]),
            )
            if row is not None
            else None
        )
        if actual != expected:
            raise ConnectorSyncError("close command already has a different delivery receipt")


def complete(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    claim: ConnectorClaim,
    cursor: ConnectorCursorToken,
    project_event_cursor: int,
    *,
    now: datetime,
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        result = connection.execute(
            """
            UPDATE connector_sync_progress
            SET cursor_token = %s, project_event_cursor = %s,
                next_poll_at = %s, consecutive_failures = 0,
                claim_owner = NULL, claim_expires_at = NULL, completed_at = %s
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND registration_revision_id = %s
              AND claim_owner = %s AND claim_fence = %s
              AND claim_expires_at > %s
              AND project_event_cursor <= %s
            """,
            (
                cursor.value,
                project_event_cursor,
                now + registration.poll_interval,
                now,
                actor.tenant_id,
                registration.registration_key,
                registration.revision_id,
                claim.owner_id,
                claim.fence,
                now,
                project_event_cursor,
            ),
        )
        if result.rowcount != 1:
            raise ConnectorSyncError("connector cursor completion was stale or unavailable")


def fail(
    dsn: str,
    actor: Actor,
    registration: ConnectorRegistration,
    claim: ConnectorClaim,
    *,
    now: datetime,
) -> None:
    poll_seconds = int(registration.poll_interval.total_seconds())
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        result = connection.execute(
            """
            UPDATE connector_sync_progress AS progress
            SET next_poll_at = %s + make_interval(
                    secs => LEAST(
                        %s * power(2, LEAST(progress.consecutive_failures + 1, 8)),
                        3600
                    )::double precision
                ),
                consecutive_failures = LEAST(progress.consecutive_failures + 1, 8),
                claim_owner = NULL, claim_expires_at = NULL
            WHERE tenant_id = %s AND connector_registration_key = %s
              AND registration_revision_id = %s
              AND claim_owner = %s AND claim_fence = %s
              AND claim_expires_at > %s
            """,
            (
                now,
                poll_seconds,
                actor.tenant_id,
                registration.registration_key,
                registration.revision_id,
                claim.owner_id,
                claim.fence,
                now,
            ),
        )
        if result.rowcount != 1:
            raise ConnectorSyncError("connector cursor failure was stale, expired, or unavailable")


def _record_observation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    registration: ConnectorRegistration,
    issue: ExternalIssue,
    *,
    observed_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO connector_issue_observations (
            tenant_id, connector_registration_key, registration_revision_id,
            connector_kind, external_ref, payload_digest, title, description,
            source_labels, reporter_reference, reporter_display_name,
            external_state, display_url, source_updated_at, observed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            actor.tenant_id,
            registration.registration_key,
            registration.revision_id,
            issue.connector_kind,
            issue.external_ref,
            _issue_digest(issue),
            issue.title,
            issue.description,
            list(issue.source_labels),
            issue.reporter_reference,
            issue.reporter_display_name,
            issue.external_state,
            issue.display_url,
            issue.updated_at,
            observed_at,
        ),
    )


def _claim(row: dict[str, object]) -> ConnectorClaim:
    return ConnectorClaim(
        cursor=ConnectorCursorToken(value=str(row["cursor_token"])),
        project_event_cursor=int(cast(int, row["project_event_cursor"])),
        owner_id=cast(UUID, row["claim_owner"]),
        fence=int(cast(int, row["claim_fence"])),
        expires_at=cast(datetime, row["claim_expires_at"]),
    )


def _link(row: dict[str, object]) -> ConnectorLink:
    return ConnectorLink(
        tenant_id=cast(UUID, row["tenant_id"]),
        registration_key=str(row["connector_registration_key"]),
        revision_digest="sha256:" + bytes(cast(bytes, row["source_revision_digest"])).hex(),
        connector_kind=str(row["connector_kind"]),
        external_ref=str(row["external_ref"]),
        ticket_id=cast(UUID, row["ticket_id"]),
        thread_id=cast(UUID, row["thread_id"]),
        display_url=str(row["display_url"]),
    )


def _issue(row: dict[str, object]) -> ExternalIssue:
    return ExternalIssue(
        connector_kind=str(row["connector_kind"]),
        external_ref=str(row["external_ref"]),
        title=str(row["title"]),
        description=str(row["description"]),
        source_labels=tuple(cast(list[str], row["source_labels"])),
        reporter_reference=str(row["reporter_reference"]),
        reporter_display_name=str(row["reporter_display_name"]),
        external_state=cast(Literal["opened", "closed"], str(row["external_state"])),
        display_url=str(row["display_url"]),
        updated_at=cast(datetime, row["source_updated_at"]),
    )


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))


def _issue_digest(issue: ExternalIssue) -> bytes:
    return hashlib.sha256(
        json.dumps(
            issue.to_mapping(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    ).digest()

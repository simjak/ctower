"""PostgreSQL implementation of the provider-neutral ConnectorStore."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.integrations import _postgres_sql
from ctower_kernel.integrations.interface import (
    ConnectorClaim,
    ConnectorCursorToken,
    ConnectorLink,
    ConnectorReceipt,
    ConnectorRegistration,
    ExternalIssue,
)
from ctower_kernel.record import Actor

__all__ = ["PostgresConnectorStore"]


class PostgresConnectorStore:
    """Persist immutable custody/receipts plus mutable bounded sync progress."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def claim(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        *,
        owner_id: UUID,
        now: datetime,
    ) -> ConnectorClaim | None:
        return _postgres_sql.claim(self._dsn, actor, registration, owner_id=owner_id, now=now)

    def active_revision_id(
        self,
        actor: Actor,
        *,
        registration_key: str,
        revision_digest: str,
    ) -> UUID | None:
        return _postgres_sql.active_revision_id(
            self._dsn,
            actor,
            registration_key=registration_key,
            revision_digest=revision_digest,
        )

    def issue_link(
        self, actor: Actor, registration: ConnectorRegistration, external_ref: str
    ) -> ConnectorLink | None:
        return _postgres_sql.issue_link(self._dsn, actor, registration, external_ref)

    def ticket_link(
        self, actor: Actor, registration: ConnectorRegistration, ticket_id: UUID
    ) -> ConnectorLink | None:
        return _postgres_sql.ticket_link(self._dsn, actor, registration, ticket_id)

    def latest_issue(
        self, actor: Actor, registration: ConnectorRegistration, external_ref: str
    ) -> ExternalIssue | None:
        return _postgres_sql.latest_issue(self._dsn, actor, registration, external_ref)

    def record_issue(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        ticket_id: UUID,
        thread_id: UUID,
        observed_at: datetime,
    ) -> None:
        _postgres_sql.record_issue(
            self._dsn,
            actor,
            registration,
            issue,
            ticket_id=ticket_id,
            thread_id=thread_id,
            observed_at=observed_at,
        )

    def record_observation(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        observed_at: datetime,
    ) -> None:
        _postgres_sql.record_observation(
            self._dsn, actor, registration, issue, observed_at=observed_at
        )

    def delivered(
        self, actor: Actor, registration: ConnectorRegistration, command_id: UUID
    ) -> bool:
        return _postgres_sql.delivered(self._dsn, actor, registration, command_id)

    def record_delivery(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        link: ConnectorLink,
        receipt: ConnectorReceipt,
        *,
        delivered_at: datetime,
    ) -> None:
        _postgres_sql.record_delivery(
            self._dsn,
            actor,
            registration,
            link,
            receipt,
            delivered_at=delivered_at,
        )

    def complete(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        claim: ConnectorClaim,
        cursor: ConnectorCursorToken,
        project_event_cursor: int,
        *,
        now: datetime,
    ) -> None:
        _postgres_sql.complete(
            self._dsn,
            actor,
            registration,
            claim,
            cursor,
            project_event_cursor,
            now=now,
        )

    def fail(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        claim: ConnectorClaim,
        *,
        now: datetime,
    ) -> None:
        _postgres_sql.fail(self._dsn, actor, registration, claim, now=now)

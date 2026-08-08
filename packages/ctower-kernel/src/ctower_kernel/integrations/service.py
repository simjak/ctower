"""Bounded GitLab issue ingestion and proof-gated close delivery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ctower_kernel.board_context.labels import ApplyLabelCommand
from ctower_kernel.integrations.interface import (
    GitLabCloseCommand,
    GitLabCursor,
    GitLabIntegrationStore,
    GitLabIssue,
    GitLabIssueAdapter,
    GitLabIssueLink,
    GitLabSyncBatch,
    GitLabSyncBinding,
    GitLabSyncError,
)
from ctower_kernel.record import Actor, AuditEvent, RecordProblem
from ctower_kernel.record.comments import TicketCommentCommand
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.intake import (
    InboundSource,
    IntakeCommandResult,
    IntakeIntent,
    IntakeSubmitCommand,
    IntakeTaint,
)
from ctower_kernel.record.project_events import ProjectEventPage
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["GitLabIssueSync"]

_SOURCE_KIND = "gitlab-issue"
_MAX_COMMENT_BODY = 4000


class _Intake(Protocol):
    def submit(
        self, actor: Actor, command: IntakeSubmitCommand, *, telemetry: TelemetryContext
    ) -> IntakeCommandResult | RecordProblem: ...


class _CommentWriter(Protocol):
    def add_comment(
        self,
        actor: Actor,
        command: TicketCommentCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> object | RecordProblem: ...


class _EventAudit(Protocol):
    def project_events(
        self,
        actor: Actor,
        project_key: str,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> ProjectEventPage | RecordProblem: ...


class _BoardContext(Protocol):
    def apply_label(
        self,
        actor: Actor,
        command: ApplyLabelCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> object | RecordProblem: ...


class GitLabIssueSync:
    """Process at most one GitLab page and one ctower event page per due tick."""

    def __init__(
        self,
        adapter: GitLabIssueAdapter,
        store: GitLabIntegrationStore,
        intake: _Intake,
        comments: _CommentWriter,
        event_audit: _EventAudit,
        board_context: _BoardContext,
        *,
        clock: Callable[[], datetime] | None = None,
        claim_owner: UUID | None = None,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._intake = intake
        self._comments = comments
        self._event_audit = event_audit
        self._board_context = board_context
        self._clock = clock or (lambda: datetime.now(UTC))
        self._claim_owner = claim_owner or uuid4()

    def tick(self, actor: Actor, binding: GitLabSyncBinding) -> GitLabSyncBatch:
        now = self._clock()
        claim = self._store.claim(actor, binding, owner_id=self._claim_owner, now=now)
        if claim is None:
            return GitLabSyncBatch(claimed=False)
        cursor = claim.cursor
        try:
            page = self._adapter.list_issues(binding, cursor)
            created = 0
            updated = 0
            for issue in page.issues:
                _require_bound_project(issue, binding)
                issue_created, issue_updated = self._sync_issue(actor, binding, issue, now=now)
                created += int(issue_created)
                updated += int(issue_updated)
            event_cursor, closures = self._deliver_project_events(actor, binding, cursor, now=now)
            completed = GitLabCursor(
                updated_after=_next_watermark(cursor, page.issues, page.next_page),
                page=page.next_page or 1,
                project_event_cursor=event_cursor,
            )
            self._store.complete(actor, binding, claim, completed, now=self._clock())
            return GitLabSyncBatch(
                claimed=True,
                issues_seen=len(page.issues),
                tickets_created=created,
                ticket_updates=updated,
                closures_delivered=closures,
            )
        except Exception:
            self._store.fail(actor, binding, claim, now=self._clock())
            raise

    def _sync_issue(
        self, actor: Actor, binding: GitLabSyncBinding, issue: GitLabIssue, *, now: datetime
    ) -> tuple[bool, bool]:
        previous = self._store.latest_issue(actor, binding, issue.iid)
        link = self._store.issue_link(actor, binding, issue.iid)
        if previous is not None and _issue_digest(previous) == _issue_digest(issue):
            if link is None:
                raise GitLabSyncError("GitLab observation has no custody link")
            self._apply_labels(actor, binding, issue, link.ticket_id, now=now)
            return False, False
        if link is None:
            command_id = _id(actor, binding, f"intake:{issue.source_ref}")
            outcome = self._intake.submit(
                actor,
                IntakeSubmitCommand(
                    client_command_id=command_id,
                    project_key=binding.project_key,
                    source=InboundSource(_SOURCE_KIND, issue.source_ref),
                    content=_initial_content(issue),
                    intent=IntakeIntent.CREATE_TICKET,
                    taint=IntakeTaint.EXTERNAL_UNTRUSTED,
                    initial_custodian_id=binding.initial_custodian_id,
                    priority="P2",
                    title=issue.title,
                ),
                telemetry=_telemetry(actor, command_id),
            )
            result = _require_result(outcome, "GitLab intake")
            if result.ticket_id is None:
                raise GitLabSyncError("GitLab intake returned no ticket")
            self._store.record_issue(
                actor,
                binding,
                issue,
                ticket_id=result.ticket_id,
                thread_id=result.thread_id,
                observed_at=now,
            )
            self._apply_labels(actor, binding, issue, result.ticket_id, now=now)
            return True, False
        self._apply_labels(actor, binding, issue, link.ticket_id, now=now)
        command_id = _id(actor, binding, f"update:{link.ticket_id}:{_issue_digest(issue)}")
        comment = TicketCommentCommand(command_id, link.ticket_id, _update_comment(previous, issue))
        comment_outcome = self._comments.add_comment(
            actor,
            comment,
            request_digest=_digest(comment.request_payload()),
            now=now,
            telemetry=_telemetry(actor, command_id, ticket_id=link.ticket_id),
        )
        if (
            isinstance(comment_outcome, RecordProblem)
            and comment_outcome.code == "ticket-comment-ineligible"
            and issue.state == "closed"
        ):
            # The provider's reflection of our proof-gated close arrives on the next
            # issue page. Terminal ctower tickets correctly refuse new comments; retain
            # the provider observation so the same reflection cannot poison every poll.
            self._store.record_observation(actor, binding, issue, observed_at=now)
            return False, False
        _require_result(comment_outcome, "GitLab update comment")
        self._store.record_observation(actor, binding, issue, observed_at=now)
        return False, True

    def _apply_labels(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        issue: GitLabIssue,
        ticket_id: UUID,
        *,
        now: datetime,
    ) -> None:
        for source_label in issue.labels:
            label_key = binding.label_key(source_label)
            if label_key is None:
                continue
            command_id = _id(actor, binding, f"label:{ticket_id}:{label_key}")
            command = ApplyLabelCommand(command_id, ticket_id, label_key)
            outcome = self._board_context.apply_label(
                actor,
                command,
                request_digest=_digest(command.request_payload()),
                now=now,
                telemetry=_telemetry(actor, command_id, ticket_id=ticket_id),
            )
            if isinstance(outcome, RecordProblem) and outcome.code == "durability_pending":
                continue
            _require_result(outcome, f"GitLab label {source_label!r}")

    def _deliver_project_events(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        cursor: GitLabCursor,
        *,
        now: datetime,
    ) -> tuple[int, int]:
        command_id = _id(actor, binding, f"project-events:{cursor.project_event_cursor}")
        outcome = self._event_audit.project_events(
            actor,
            binding.project_key,
            cursor=cursor.project_event_cursor,
            limit=100,
            telemetry=_telemetry(actor, command_id),
        )
        page = _require_result(outcome, "ctower project event read")
        event_cursor = cursor.project_event_cursor
        delivered = 0
        for event in page.events:
            if _is_proof_gated_close(event):
                link = self._store.ticket_link(
                    actor, binding, UUID(str(event.payload["ticket_id"]))
                )
                if link is not None and not self._store.delivered(actor, binding, event.event_id):
                    self._deliver_close(actor, binding, link, event, now=now)
                    delivered += 1
            event_cursor = max(event_cursor, event.record_position)
        return event_cursor, delivered

    def _deliver_close(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        link: GitLabIssueLink,
        event: AuditEvent,
        *,
        now: datetime,
    ) -> None:
        command = GitLabCloseCommand(
            delivery_id=event.event_id,
            comment=(
                f"ctower ticket {link.ticket_id} completed through its current-proof gate.\n\n"
                f"Canonical close event: {event.event_id}"
            ),
        )
        receipt = self._adapter.comment_and_close(link, command)
        if receipt.delivery_id != event.event_id or not receipt.issue_closed:
            raise GitLabSyncError("GitLab close Adapter returned an invalid receipt")
        self._store.record_delivery(actor, binding, link, receipt, delivered_at=now)


def _require_result[T](value: T | RecordProblem, operation: str) -> T:
    if isinstance(value, RecordProblem):
        raise GitLabSyncError(f"{operation} refused: {value.code}")
    return value


def _require_bound_project(issue: GitLabIssue, binding: GitLabSyncBinding) -> None:
    if issue.project_id != binding.project_id:
        raise GitLabSyncError("GitLab Adapter returned an issue from another project")


def _is_proof_gated_close(event: AuditEvent) -> bool:
    return (
        event.kind is EventKind.WORKFLOW_CHANGED
        and event.payload.get("operation") == "resolve_close"
        and event.payload.get("lifecycle_facts") == ["resolved", "closed"]
        and isinstance(event.payload.get("ticket_id"), str)
    )


def _next_watermark(
    cursor: GitLabCursor, issues: tuple[GitLabIssue, ...], next_page: int | None
) -> datetime:
    if next_page is not None or not issues:
        return cursor.updated_after
    return max(issue.updated_at for issue in issues) + timedelta(microseconds=1)


def _initial_content(issue: GitLabIssue) -> str:
    header = (
        f"GitLab reporter: {issue.reporter.name} (@{issue.reporter.username})\n"
        f"GitLab issue: {issue.web_url}\n"
        f"GitLab labels: {', '.join(issue.labels) if issue.labels else '(none)'}\n\n"
    )
    return header + (issue.body or "(No GitLab description.)")


def _update_comment(previous: GitLabIssue | None, issue: GitLabIssue) -> str:
    changed = _changed_issue_fields(previous, issue)
    prefix = f"GitLab issue updated: {issue.web_url}\n\n"
    body = prefix + "\n\n".join(changed)
    if len(body) <= _MAX_COMMENT_BODY:
        return body
    suffix = "\n\n[GitLab update truncated; follow the source link for the complete body.]"
    return body[: _MAX_COMMENT_BODY - len(suffix)] + suffix


def _changed_issue_fields(previous: GitLabIssue | None, issue: GitLabIssue) -> list[str]:
    if previous is None:
        return [
            f"Title: {issue.title}",
            f"State: {issue.state}",
            f"Labels: {_labels_text(issue.labels)}",
            f"Reporter: {issue.reporter.name} (@{issue.reporter.username})",
            f"Body:\n{_body_text(issue.body)}",
        ]
    changed: list[str] = []
    if previous.title != issue.title:
        changed.append(f"Title: {issue.title}")
    if previous.state != issue.state:
        changed.append(f"State: {issue.state}")
    if previous.labels != issue.labels:
        changed.append(f"Labels: {_labels_text(issue.labels)}")
    if previous.reporter != issue.reporter:
        changed.append(f"Reporter: {issue.reporter.name} (@{issue.reporter.username})")
    if previous.body != issue.body:
        changed.append(f"Body:\n{_body_text(issue.body)}")
    return changed


def _labels_text(labels: tuple[str, ...]) -> str:
    return ", ".join(labels) if labels else "(none)"


def _body_text(body: str) -> str:
    return body or "(No GitLab description.)"


def _issue_digest(issue: GitLabIssue) -> str:
    return "sha256:" + hashlib.sha256(_canonical(issue.to_mapping())).hexdigest()


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(_canonical(payload)).digest()


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _id(actor: Actor, binding: GitLabSyncBinding, purpose: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"ctower:gitlab:v1:{actor.tenant_id}:{binding.revision_digest}:{purpose}",
    )


def _telemetry(
    actor: Actor, command_id: UUID, *, ticket_id: UUID | None = None
) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=command_id.hex,
        span_id=command_id.hex[:16],
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
        ticket_id=str(ticket_id) if ticket_id is not None else None,
    )

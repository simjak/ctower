"""Provider-neutral bounded issue synchronization and close delivery."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from random import SystemRandom
from types import TracebackType
from typing import Literal, Protocol, Self, TypeVar
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ctower_kernel.board_context.labels import ApplyLabelCommand
from ctower_kernel.integrations.interface import (
    AmbiguousWrite,
    CloseExternalIssue,
    CloseExternalIssueResult,
    CloseFailure,
    ConnectorAttempt,
    ConnectorCursorToken,
    ConnectorLink,
    ConnectorRegistration,
    ConnectorStore,
    ConnectorSyncBatch,
    ConnectorSyncError,
    ExternalIssue,
    ExternalIssuePage,
    FetchFailure,
    FetchIssuePage,
    FetchIssuePageResult,
    IssueConnector,
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

__all__ = ["ConnectorRetryExecutor", "IssueConnectorService"]

_MAX_ATTEMPTS: Literal[4] = 4
_MAX_ELAPSED_SECONDS = 10.0
_INITIAL_BACKOFF_SECONDS = 0.25
_MAX_BACKOFF_SECONDS = 2.0
_MAX_COMMENT_BODY = 4000
_MAX_INTAKE_CONTENT = 65_536
_RANDOM = SystemRandom()
_T = TypeVar("_T", FetchIssuePageResult, CloseExternalIssueResult)


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


class _ConnectorContractBoundary:
    """Convert every ordinary escaped adapter exception into a typed terminal result."""

    def __init__(self) -> None:
        self.failed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> bool:
        if error_type is None or not issubclass(error_type, Exception):
            return False
        self.failed = True
        return True


class ConnectorRetryExecutor:
    """Own the one bounded attempt/deadline/backoff/jitter policy for connector core."""

    def __init__(
        self,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter or (lambda ceiling: _RANDOM.uniform(ceiling / 2, ceiling))

    def fetch(self, connector: IssueConnector, request: FetchIssuePage) -> FetchIssuePageResult:
        return self._execute(
            lambda attempt: connector.fetch_page(request, attempt),
            contract_failure=lambda: FetchFailure(
                retry_class="terminal", reason="contract_violation"
            ),
        )

    def close(
        self, connector: IssueConnector, command: CloseExternalIssue
    ) -> CloseExternalIssueResult:
        return self._execute(
            lambda attempt: connector.comment_and_close(command, attempt),
            contract_failure=lambda: CloseFailure(
                retry_class="terminal",
                reason="contract_violation",
                write_disposition="not_written",
            ),
        )

    def _execute(
        self,
        invoke: Callable[[ConnectorAttempt], _T],
        *,
        contract_failure: Callable[[], _T],
    ) -> _T:
        deadline = self._monotonic() + _MAX_ELAPSED_SECONDS
        last: _T | None = None
        for attempt_number in range(1, _MAX_ATTEMPTS + 1):
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            attempt = ConnectorAttempt(
                attempt_number=attempt_number,
                max_attempts=_MAX_ATTEMPTS,
                deadline_remaining_milliseconds=max(1, min(10_000, int(remaining * 1000))),
            )
            boundary = _ConnectorContractBoundary()
            with boundary:
                last = invoke(attempt)
            if boundary.failed or last is None:
                return contract_failure()
            if not _retryable(last) or attempt_number == _MAX_ATTEMPTS:
                return last
            if not self._back_off(deadline, attempt_number):
                return last
        return last if last is not None else contract_failure()

    def _back_off(self, deadline: float, attempt_number: int) -> bool:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            return False
        ceiling = min(
            _INITIAL_BACKOFF_SECONDS * (2 ** (attempt_number - 1)),
            _MAX_BACKOFF_SECONDS,
            remaining,
        )
        delay = self._jitter(ceiling)
        if not 0 <= delay <= ceiling:
            raise RuntimeError("connector retry jitter escaped its bounded interval")
        self._sleep(delay)
        return self._monotonic() < deadline


class IssueConnectorService:
    """Process at most one connector page and one ctower event page per due tick."""

    def __init__(
        self,
        connector: IssueConnector,
        store: ConnectorStore,
        intake: _Intake,
        comments: _CommentWriter,
        event_audit: _EventAudit,
        board_context: _BoardContext,
        *,
        clock: Callable[[], datetime] | None = None,
        claim_owner: UUID | None = None,
        retry: ConnectorRetryExecutor | None = None,
    ) -> None:
        self._connector = connector
        self._store = store
        self._intake = intake
        self._comments = comments
        self._event_audit = event_audit
        self._board_context = board_context
        self._clock = clock or (lambda: datetime.now(UTC))
        self._claim_owner = claim_owner or uuid4()
        self._retry = retry or ConnectorRetryExecutor()

    def tick(self, actor: Actor, registration: ConnectorRegistration) -> ConnectorSyncBatch:
        now = self._clock()
        claim = self._store.claim(actor, registration, owner_id=self._claim_owner, now=now)
        if claim is None:
            return ConnectorSyncBatch(claimed=False)
        try:
            page = self._fetch_page(registration, claim.cursor)
            _require_cursor_advance(page, claim.cursor)
            created, updated = self._sync_page(actor, registration, page, now=now)
            event_cursor, closures = self._deliver_project_events(
                actor, registration, claim.project_event_cursor, now=now
            )
            self._store.complete(
                actor,
                registration,
                claim,
                page.next_cursor,
                event_cursor,
                now=self._clock(),
            )
            return ConnectorSyncBatch(
                claimed=True,
                issues_seen=len(page.issues),
                tickets_created=created,
                ticket_updates=updated,
                closures_delivered=closures,
            )
        except Exception:
            self._store.fail(actor, registration, claim, now=self._clock())
            raise

    def _fetch_page(
        self, registration: ConnectorRegistration, cursor: ConnectorCursorToken
    ) -> ExternalIssuePage:
        result = self._retry.fetch(
            self._connector,
            FetchIssuePage(cursor=cursor, page_size=registration.page_size),
        )
        if isinstance(result, FetchFailure):
            raise ConnectorSyncError(
                f"connector fetch failed: {result.retry_class}:{result.reason}"
            )
        if len(result.issues) > registration.page_size:
            raise ConnectorSyncError("connector page exceeded its requested bound")
        if any(issue.connector_kind != registration.connector_kind for issue in result.issues):
            raise ConnectorSyncError("connector returned an issue of another kind")
        refs = tuple(issue.external_ref for issue in result.issues)
        if len(set(refs)) != len(refs):
            raise ConnectorSyncError("connector page repeated an external reference")
        return result

    def _sync_page(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        page: ExternalIssuePage,
        *,
        now: datetime,
    ) -> tuple[int, int]:
        created = 0
        updated = 0
        for issue in page.issues:
            issue_created, issue_updated = self._sync_issue(actor, registration, issue, now=now)
            created += int(issue_created)
            updated += int(issue_updated)
        return created, updated

    def _sync_issue(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        now: datetime,
    ) -> tuple[bool, bool]:
        previous = self._store.latest_issue(actor, registration, issue.external_ref)
        link = self._store.issue_link(actor, registration, issue.external_ref)
        if link is not None and link.connector_kind != registration.connector_kind:
            raise ConnectorSyncError("connector custody link belongs to another kind")
        if previous is not None and _issue_digest(previous) == _issue_digest(issue):
            if link is None:
                raise ConnectorSyncError("connector observation has no custody link")
            self._apply_labels(actor, registration, issue, link.ticket_id, now=now)
            return False, False
        if link is None:
            return self._create_issue(actor, registration, issue, now=now), False
        self._apply_labels(actor, registration, issue, link.ticket_id, now=now)
        return False, self._update_issue(actor, registration, issue, previous, link, now=now)

    def _create_issue(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        now: datetime,
    ) -> bool:
        command_id = _id(actor, registration, f"intake:{issue.external_ref}")
        outcome = self._intake.submit(
            actor,
            IntakeSubmitCommand(
                client_command_id=command_id,
                project_key=registration.project_key,
                source=InboundSource(registration.connector_kind, issue.external_ref),
                content=_initial_content(issue, registration.source_display_name),
                intent=IntakeIntent.CREATE_TICKET,
                taint=IntakeTaint.EXTERNAL_UNTRUSTED,
                initial_custodian_id=registration.initial_custodian_id,
                priority="P2",
                title=issue.title,
            ),
            telemetry=_telemetry(actor, command_id),
        )
        result = _require_result(outcome, "connector intake")
        if result.ticket_id is None:
            raise ConnectorSyncError("connector intake returned no ticket")
        self._store.record_issue(
            actor,
            registration,
            issue,
            ticket_id=result.ticket_id,
            thread_id=result.thread_id,
            observed_at=now,
        )
        self._apply_labels(actor, registration, issue, result.ticket_id, now=now)
        return True

    def _update_issue(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        previous: ExternalIssue | None,
        link: ConnectorLink,
        *,
        now: datetime,
    ) -> bool:
        command_id = _id(actor, registration, f"update:{link.ticket_id}:{_issue_digest(issue)}")
        comment = TicketCommentCommand(
            command_id,
            link.ticket_id,
            _update_comment(previous, issue, registration.source_display_name),
        )
        outcome = self._comments.add_comment(
            actor,
            comment,
            request_digest=_digest(comment.request_payload()),
            now=now,
            telemetry=_telemetry(actor, command_id, ticket_id=link.ticket_id),
        )
        if (
            isinstance(outcome, RecordProblem)
            and outcome.code == "ticket-comment-ineligible"
            and issue.external_state == "closed"
        ):
            # A provider reflection of ctower's proof-gated close reaches the next
            # issue page after the terminal ticket correctly refuses comments.
            self._store.record_observation(actor, registration, issue, observed_at=now)
            return False
        _require_result(outcome, "connector update comment")
        self._store.record_observation(actor, registration, issue, observed_at=now)
        return True

    def _apply_labels(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        issue: ExternalIssue,
        ticket_id: UUID,
        *,
        now: datetime,
    ) -> None:
        for source_label in issue.source_labels:
            label_key = registration.label_key(source_label)
            if label_key is None:
                continue
            command_id = _id(actor, registration, f"label:{ticket_id}:{label_key}")
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
            _require_result(outcome, f"connector label {source_label!r}")

    def _deliver_project_events(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        event_cursor: int,
        *,
        now: datetime,
    ) -> tuple[int, int]:
        command_id = _id(actor, registration, f"project-events:{event_cursor}")
        outcome = self._event_audit.project_events(
            actor,
            registration.project_key,
            cursor=event_cursor,
            limit=100,
            telemetry=_telemetry(actor, command_id),
        )
        page = _require_result(outcome, "ctower project event read")
        delivered = 0
        for event in page.events:
            if _is_proof_gated_close(event):
                link = self._store.ticket_link(
                    actor, registration, UUID(str(event.payload["ticket_id"]))
                )
                if link is not None and link.connector_kind != registration.connector_kind:
                    raise ConnectorSyncError("connector custody link belongs to another kind")
                if link is not None and not self._store.delivered(
                    actor, registration, event.event_id
                ):
                    self._deliver_close(actor, registration, link, event, now=now)
                    delivered += 1
            event_cursor = max(event_cursor, event.record_position)
        return event_cursor, delivered

    def _deliver_close(
        self,
        actor: Actor,
        registration: ConnectorRegistration,
        link: ConnectorLink,
        event: AuditEvent,
        *,
        now: datetime,
    ) -> None:
        command = CloseExternalIssue(
            external_ref=link.external_ref,
            command_id=event.event_id,
            marker=f"<!-- ctower-sync:{event.event_id} -->",
            comment=(
                f"ctower ticket {link.ticket_id} completed through its current-proof gate.\n\n"
                f"Canonical close event: {event.event_id}"
            ),
        )
        result = self._retry.close(self._connector, command)
        if isinstance(result, (CloseFailure, AmbiguousWrite)):
            raise ConnectorSyncError(f"connector close failed: {result.kind}")
        if result.command_id != event.event_id:
            raise ConnectorSyncError("connector returned a receipt for another command")
        self._store.record_delivery(actor, registration, link, result, delivered_at=now)


def _retryable(result: object) -> bool:
    return isinstance(result, (FetchFailure, CloseFailure)) and result.retry_class == "retryable"


def _require_result[T](value: T | RecordProblem, operation: str) -> T:
    if isinstance(value, RecordProblem):
        raise ConnectorSyncError(f"{operation} refused: {value.code}")
    return value


def _require_cursor_advance(page: ExternalIssuePage, prior: ConnectorCursorToken) -> None:
    if page.next_cursor == prior and (page.issues or not page.exhausted):
        raise ConnectorSyncError("connector page neither advanced its cursor nor exhausted")


def _is_proof_gated_close(event: AuditEvent) -> bool:
    return (
        event.kind is EventKind.WORKFLOW_CHANGED
        and event.payload.get("operation") == "resolve_close"
        and event.payload.get("lifecycle_facts") == ["resolved", "closed"]
        and isinstance(event.payload.get("ticket_id"), str)
    )


def _initial_content(issue: ExternalIssue, source_name: str) -> str:
    header = (
        f"{source_name} reporter: {issue.reporter_display_name} ({issue.reporter_reference})\n"
        f"{source_name} issue: {issue.display_url}\n"
        f"{source_name} labels: "
        f"{', '.join(issue.source_labels) if issue.source_labels else '(none)'}\n\n"
    )
    content = header + (issue.description or f"(No {source_name} description.)")
    if len(content) <= _MAX_INTAKE_CONTENT:
        return content
    suffix = f"\n\n[{source_name} intake truncated; follow the source link for the complete body.]"
    return content[: _MAX_INTAKE_CONTENT - len(suffix)] + suffix


def _update_comment(
    previous: ExternalIssue | None,
    issue: ExternalIssue,
    source_name: str,
) -> str:
    changed = _changed_issue_fields(previous, issue)
    body = f"{source_name} issue updated: {issue.display_url}\n\n" + "\n\n".join(changed)
    if len(body) <= _MAX_COMMENT_BODY:
        return body
    suffix = f"\n\n[{source_name} update truncated; follow the source link for the complete body.]"
    return body[: _MAX_COMMENT_BODY - len(suffix)] + suffix


def _changed_issue_fields(previous: ExternalIssue | None, issue: ExternalIssue) -> list[str]:
    if previous is None:
        return _all_issue_fields(issue)
    changed: list[str] = []
    comparisons = (
        ("Title", previous.title, issue.title),
        ("State", previous.external_state, issue.external_state),
        ("Labels", previous.source_labels, issue.source_labels),
        (
            "Reporter",
            f"{previous.reporter_display_name} ({previous.reporter_reference})",
            f"{issue.reporter_display_name} ({issue.reporter_reference})",
        ),
        ("Body", previous.description, issue.description),
    )
    for label, old, new in comparisons:
        if old != new:
            changed.append(f"{label}:\n{new}" if label == "Body" else f"{label}: {new}")
    return changed


def _all_issue_fields(issue: ExternalIssue) -> list[str]:
    return [
        f"Title: {issue.title}",
        f"State: {issue.external_state}",
        f"Labels: {', '.join(issue.source_labels) if issue.source_labels else '(none)'}",
        f"Reporter: {issue.reporter_display_name} ({issue.reporter_reference})",
        f"Body:\n{issue.description or '(No external description.)'}",
    ]


def _issue_digest(issue: ExternalIssue) -> str:
    return "sha256:" + hashlib.sha256(_canonical(issue.to_mapping())).hexdigest()


def _digest(payload: dict[str, object]) -> bytes:
    return hashlib.sha256(_canonical(payload)).digest()


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _id(actor: Actor, registration: ConnectorRegistration, purpose: str) -> UUID:
    connector_family = registration.connector_kind.removesuffix("-issue")
    return uuid5(
        NAMESPACE_URL,
        f"ctower:{connector_family}:v1:{actor.tenant_id}:{registration.revision_digest}:{purpose}",
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

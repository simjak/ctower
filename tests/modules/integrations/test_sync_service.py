from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from ctower_kernel.board_context.labels import ApplyLabelCommand
from ctower_kernel.integrations import (
    CloseExternalIssue,
    ConnectorAttempt,
    ConnectorClaim,
    ConnectorCursorToken,
    ConnectorLabelMapping,
    ConnectorLink,
    ConnectorReceipt,
    ConnectorRegistration,
    ConnectorSyncError,
    ExternalIssue,
    ExternalIssuePage,
    FetchIssuePage,
    IssueConnectorService,
)
from ctower_kernel.record import Actor, AuditEvent, PrincipalKind, RecordProblem
from ctower_kernel.record.comments import TicketCommentCommand
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.intake import (
    IntakeCommandResult,
    IntakeOutcome,
    IntakeSubmitCommand,
)
from ctower_kernel.record.project_events import ProjectEventPage
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_PAGE_SIZE = 50
_MAX_ATTEMPTS = 4
_MAX_INTAKE_CONTENT = 65_536
_PROJECT_EVENT_LIMIT = 100

TENANT_ID = UUID("33333333-3333-4333-8333-333333333333")
ACTOR_ID = UUID("11111111-1111-4111-8111-111111111111")
TICKET_ID = UUID("44444444-4444-4444-8444-444444444444")
THREAD_ID = UUID("55555555-5555-4555-8555-555555555555")


def _actor() -> Actor:
    return Actor(ACTOR_ID, TENANT_ID, PrincipalKind.COMMANDER)


def _registration() -> ConnectorRegistration:
    return ConnectorRegistration(
        registration_key="gitlab.feedback",
        revision_id=UUID("22222222-2222-4222-8222-222222222222"),
        revision_digest="sha256:" + "a" * 64,
        connector_kind="gitlab-issue",
        source_display_name="GitLab",
        project_key="ctower",
        initial_custodian_id=ACTOR_ID,
        initial_cursor=ConnectorCursorToken(value="cursor-0"),
        page_size=50,
        poll_interval=timedelta(seconds=60),
        label_map=(ConnectorLabelMapping(source="bug", target="type.bug"),),
    )


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
        "updated_at": datetime(2026, 8, 8, 8, 1, tzinfo=UTC),
    }
    values.update(changes)
    return ExternalIssue(**values)  # type: ignore[arg-type]


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class _Connector:
    def __init__(self, issue: ExternalIssue | None) -> None:
        self.issue = issue
        self.fetch_calls = 0
        self.closes: list[CloseExternalIssue] = []

    def fetch_page(self, request: FetchIssuePage, attempt: ConnectorAttempt) -> ExternalIssuePage:
        assert request.page_size == _PAGE_SIZE and attempt.max_attempts == _MAX_ATTEMPTS
        self.fetch_calls += 1
        return ExternalIssuePage(
            issues=(self.issue,) if self.issue is not None else (),
            next_cursor=ConnectorCursorToken(value=f"cursor-{self.fetch_calls}"),
            exhausted=True,
        )

    def comment_and_close(
        self, command: CloseExternalIssue, attempt: ConnectorAttempt
    ) -> ConnectorReceipt:
        assert attempt.attempt_number == 1
        self.closes.append(command)
        return ConnectorReceipt(command_id=command.command_id, comment_created=True)


class _PageConnector(_Connector):
    def __init__(self, page: ExternalIssuePage) -> None:
        super().__init__(None)
        self.page = page

    def fetch_page(self, request: FetchIssuePage, attempt: ConnectorAttempt) -> ExternalIssuePage:
        assert request.page_size == _PAGE_SIZE and attempt.max_attempts == _MAX_ATTEMPTS
        self.fetch_calls += 1
        return self.page


class _Store:
    def __init__(self) -> None:
        self.cursor = ConnectorCursorToken(value="cursor-0")
        self.event_cursor = 0
        self.next_due = datetime.min.replace(tzinfo=UTC)
        self.issue: ExternalIssue | None = None
        self.link: ConnectorLink | None = None
        self.deliveries: set[UUID] = set()
        self.failures = 0
        self.fence = 0
        self.active_claim: ConnectorClaim | None = None

    def claim(
        self,
        _actor: Actor,
        registration: ConnectorRegistration,
        *,
        owner_id: UUID,
        now: datetime,
    ) -> ConnectorClaim | None:
        if now < self.next_due or (
            self.active_claim is not None and self.active_claim.expires_at > now
        ):
            return None
        self.fence += 1
        self.active_claim = ConnectorClaim(
            cursor=self.cursor,
            project_event_cursor=self.event_cursor,
            owner_id=owner_id,
            fence=self.fence,
            expires_at=now + (registration.poll_interval * 2),
        )
        return self.active_claim

    def issue_link(
        self, _actor: Actor, _registration: ConnectorRegistration, external_ref: str
    ) -> ConnectorLink | None:
        return (
            self.link if self.link is not None and self.link.external_ref == external_ref else None
        )

    def ticket_link(
        self, _actor: Actor, _registration: ConnectorRegistration, ticket_id: UUID
    ) -> ConnectorLink | None:
        return self.link if self.link is not None and self.link.ticket_id == ticket_id else None

    def latest_issue(
        self, _actor: Actor, _registration: ConnectorRegistration, external_ref: str
    ) -> ExternalIssue | None:
        return (
            self.issue
            if self.issue is not None and self.issue.external_ref == external_ref
            else None
        )

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
        del observed_at
        candidate = ConnectorLink(
            tenant_id=actor.tenant_id,
            registration_key=registration.registration_key,
            revision_digest=registration.revision_digest,
            connector_kind=issue.connector_kind,
            external_ref=issue.external_ref,
            ticket_id=ticket_id,
            thread_id=thread_id,
            display_url=issue.display_url,
        )
        if self.link is not None:
            assert self.link == candidate
        self.link = candidate
        self.issue = issue

    def record_observation(
        self,
        _actor: Actor,
        _registration: ConnectorRegistration,
        issue: ExternalIssue,
        *,
        observed_at: datetime,
    ) -> None:
        del observed_at
        self.issue = issue

    def delivered(
        self, _actor: Actor, _registration: ConnectorRegistration, command_id: UUID
    ) -> bool:
        return command_id in self.deliveries

    def record_delivery(
        self,
        _actor: Actor,
        _registration: ConnectorRegistration,
        _link: ConnectorLink,
        receipt: ConnectorReceipt,
        *,
        delivered_at: datetime,
    ) -> None:
        del delivered_at
        self.deliveries.add(receipt.command_id)

    def complete(
        self,
        _actor: Actor,
        registration: ConnectorRegistration,
        claim: ConnectorClaim,
        cursor: ConnectorCursorToken,
        project_event_cursor: int,
        *,
        now: datetime,
    ) -> None:
        assert self.active_claim == claim
        self.cursor = cursor
        self.event_cursor = project_event_cursor
        self.next_due = now + registration.poll_interval
        self.active_claim = None

    def fail(
        self,
        _actor: Actor,
        _registration: ConnectorRegistration,
        claim: ConnectorClaim,
        *,
        now: datetime,
    ) -> None:
        del now
        assert self.active_claim == claim
        self.active_claim = None
        self.failures += 1


class _Intake:
    def __init__(self) -> None:
        self.commands: list[IntakeSubmitCommand] = []

    def submit(
        self,
        _actor: Actor,
        command: IntakeSubmitCommand,
        *,
        telemetry: TelemetryContext,
    ) -> IntakeCommandResult:
        del telemetry
        self.commands.append(command)
        return IntakeCommandResult(
            command.client_command_id,
            (uuid4(), uuid4()),
            uuid4(),
            IntakeOutcome.TICKET_CREATED,
            "ctower",
            command.source,
            THREAD_ID,
            1,
            ticket_id=TICKET_ID,
            ticket_version=1,
        )


class _Comments:
    def __init__(self) -> None:
        self.commands: list[TicketCommentCommand] = []

    def add_comment(
        self,
        _actor: Actor,
        command: TicketCommentCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> object | RecordProblem:
        del request_digest, now, telemetry
        self.commands.append(command)
        return object()


class _RefusingComments(_Comments):
    def add_comment(
        self,
        actor: Actor,
        command: TicketCommentCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> RecordProblem:
        super().add_comment(
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        return RecordProblem(
            "ticket-comment-ineligible",
            "Terminal ticket comment refused",
            409,
            "Terminal ticket comment refused",
        )


class _Board:
    def __init__(self) -> None:
        self.commands: list[ApplyLabelCommand] = []

    def apply_label(
        self,
        _actor: Actor,
        command: ApplyLabelCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> object | RecordProblem:
        del request_digest, now, telemetry
        self.commands.append(command)
        return object()


class _Events:
    def __init__(self) -> None:
        self.events: tuple[AuditEvent, ...] = ()

    def project_events(
        self,
        _actor: Actor,
        project_key: str,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> ProjectEventPage | RecordProblem:
        assert limit == _PROJECT_EVENT_LIMIT
        del cursor, telemetry
        return ProjectEventPage(project_key, self.events, None)


def _service(
    connector: _Connector,
    store: _Store,
    intake: _Intake,
    comments: _Comments,
    events: _Events,
    board: _Board,
    clock: _Clock,
) -> IssueConnectorService:
    return IssueConnectorService(connector, store, intake, comments, events, board, clock=clock)


def test_real_issue_shape_creates_one_source_link_and_maps_feedback_fields() -> None:
    clock = _Clock()
    connector, store, intake, comments, events, board = (
        _Connector(_issue()),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )

    batch = _service(connector, store, intake, comments, events, board, clock).tick(
        _actor(), _registration()
    )

    assert batch.tickets_created == 1 and batch.issues_seen == 1
    command = intake.commands[0]
    assert command.title == "Feedback title"
    assert command.source.kind == "gitlab-issue"
    assert command.source.ref == "gitlab:42:7"
    assert "Report Person (@reporter)" in command.content
    assert "Feedback body" in command.content
    assert store.link is not None and store.link.ticket_id == TICKET_ID
    assert len(board.commands) == 1
    assert comments.commands == []


def test_due_cursor_prevents_polling_storm_and_turns_updates_into_comments() -> None:
    clock = _Clock()
    connector, store, intake, comments, events, board = (
        _Connector(_issue()),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(connector, store, intake, comments, events, board, clock)
    service.tick(_actor(), _registration())

    assert not service.tick(_actor(), _registration()).claimed
    assert connector.fetch_calls == 1
    clock.now += timedelta(seconds=60)
    connector.issue = _issue().model_copy(
        update={
            "description": "Updated feedback body",
            "external_state": "closed",
            "updated_at": clock.now,
        }
    )
    batch = service.tick(_actor(), _registration())

    assert batch.ticket_updates == 1 and batch.tickets_created == 0
    assert len(intake.commands) == 1 and len(comments.commands) == 1
    assert "State: closed" in comments.commands[0].body
    assert "Updated feedback body" in comments.commands[0].body


def test_reporter_display_name_change_produces_gitlab_update_copy() -> None:
    clock = _Clock()
    connector, store, intake, comments, events, board = (
        _Connector(_issue()),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(connector, store, intake, comments, events, board, clock)
    service.tick(_actor(), _registration())
    clock.now += timedelta(seconds=60)
    connector.issue = _issue(
        reporter_display_name="Renamed Reporter",
        updated_at=clock.now,
    )

    batch = service.tick(_actor(), _registration())

    assert batch.ticket_updates == 1
    assert comments.commands[0].body.startswith("GitLab issue updated:")
    assert "Reporter: Renamed Reporter (@reporter)" in comments.commands[0].body


def test_open_provider_update_does_not_swallow_terminal_ticket_refusal() -> None:
    previous = _issue()
    store = _Store()
    store.issue = previous
    store.link = _link(connector_kind="gitlab-issue")
    updated = previous.model_copy(
        update={"description": "Reopened provider change", "updated_at": _Clock().now}
    )

    with pytest.raises(ConnectorSyncError, match="ticket-comment-ineligible"):
        _service(
            _Connector(updated),
            store,
            _Intake(),
            _RefusingComments(),
            _Events(),
            _Board(),
            _Clock(),
        ).tick(_actor(), _registration())

    assert store.failures == 1 and store.issue == previous


def test_closed_provider_reflection_records_observation_after_terminal_refusal() -> None:
    previous = _issue()
    reflected = previous.model_copy(update={"external_state": "closed", "updated_at": _Clock().now})
    store = _Store()
    store.issue = previous
    store.link = _link(connector_kind="gitlab-issue")

    batch = _service(
        _Connector(reflected),
        store,
        _Intake(),
        _RefusingComments(),
        _Events(),
        _Board(),
        _Clock(),
    ).tick(_actor(), _registration())

    assert batch.ticket_updates == 0 and store.failures == 0
    assert store.issue == reflected


def test_maximum_normalized_issue_is_bounded_to_work_intake_limit() -> None:
    labels = tuple(f"{index:03d}" + "x" * 252 for index in range(100))
    issue = _issue(
        description="d" * 60_000,
        source_labels=labels,
        reporter_reference="@" + "r" * 255,
        reporter_display_name="n" * 255,
        display_url="https://example.test/" + "u" * 2_000,
    )
    clock = _Clock()
    intake = _Intake()

    batch = _service(
        _Connector(issue), _Store(), intake, _Comments(), _Events(), _Board(), clock
    ).tick(_actor(), _registration())

    assert batch.tickets_created == 1
    assert len(intake.commands[0].content) == _MAX_INTAKE_CONTENT
    assert intake.commands[0].content.startswith("GitLab reporter:")
    assert intake.commands[0].content.endswith(
        "[GitLab intake truncated; follow the source link for the complete body.]"
    )


def test_page_bound_violation_fails_before_intake_side_effects() -> None:
    page = ExternalIssuePage(
        issues=tuple(_issue() for _ in range(_PAGE_SIZE + 1)),
        next_cursor=ConnectorCursorToken(value="cursor-1"),
        exhausted=True,
    )
    store, intake = _Store(), _Intake()

    with pytest.raises(ConnectorSyncError, match="requested bound"):
        _service(
            _PageConnector(page), store, intake, _Comments(), _Events(), _Board(), _Clock()
        ).tick(_actor(), _registration())

    assert store.failures == 1 and intake.commands == []


def test_nonadvancing_nonexhausted_empty_page_fails_before_side_effects() -> None:
    page = ExternalIssuePage(
        issues=(),
        next_cursor=ConnectorCursorToken(value="cursor-0"),
        exhausted=False,
    )
    store, intake = _Store(), _Intake()

    with pytest.raises(ConnectorSyncError, match="neither advanced"):
        _service(
            _PageConnector(page), store, intake, _Comments(), _Events(), _Board(), _Clock()
        ).tick(_actor(), _registration())

    assert store.failures == 1 and intake.commands == []


def test_only_proof_gated_close_event_comments_and_closes_linked_gitlab_issue_once() -> None:
    clock = _Clock()
    connector, store, intake, comments, events, board = (
        _Connector(_issue()),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(connector, store, intake, comments, events, board, clock)
    service.tick(_actor(), _registration())
    close_event = _close_event()
    events.events = (close_event,)
    connector.issue = None
    clock.now += timedelta(seconds=60)

    batch = service.tick(_actor(), _registration())

    assert batch.closures_delivered == 1 and len(connector.closes) == 1
    assert connector.closes[0].command_id == close_event.event_id
    clock.now += timedelta(seconds=60)
    assert service.tick(_actor(), _registration()).closures_delivered == 0
    assert len(connector.closes) == 1


def test_adapter_cannot_return_an_issue_from_another_project() -> None:
    clock = _Clock()
    connector, store, intake, comments, events, board = (
        _Connector(_issue(connector_kind="other-issue")),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(connector, store, intake, comments, events, board, clock)

    with pytest.raises(ConnectorSyncError, match="another kind"):
        service.tick(_actor(), _registration())

    assert store.failures == 1 and intake.commands == []


def test_linked_issue_from_another_connector_kind_fails_closed() -> None:
    store = _Store()
    store.link = _link(connector_kind="other-issue")
    intake = _Intake()

    with pytest.raises(ConnectorSyncError, match="custody link belongs to another kind"):
        _service(
            _Connector(_issue()), store, intake, _Comments(), _Events(), _Board(), _Clock()
        ).tick(_actor(), _registration())

    assert store.failures == 1 and intake.commands == []


def test_outbound_close_never_crosses_connector_kind_custody() -> None:
    store = _Store()
    store.link = _link(connector_kind="other-issue")
    connector = _Connector(None)
    events = _Events()
    events.events = (_close_event(),)

    with pytest.raises(ConnectorSyncError, match="custody link belongs to another kind"):
        _service(connector, store, _Intake(), _Comments(), events, _Board(), _Clock()).tick(
            _actor(), _registration()
        )

    assert store.failures == 1 and connector.closes == []


def _link(*, connector_kind: str) -> ConnectorLink:
    return ConnectorLink(
        tenant_id=TENANT_ID,
        registration_key="gitlab.feedback",
        revision_digest="sha256:" + "a" * 64,
        connector_kind=connector_kind,
        external_ref="gitlab:42:7",
        ticket_id=TICKET_ID,
        thread_id=THREAD_ID,
        display_url="https://gitlab.example.test/group/project/-/issues/7",
    )


def _close_event() -> AuditEvent:
    event_id = UUID("66666666-6666-4666-8666-666666666666")
    return AuditEvent(
        actor_principal_id=ACTOR_ID,
        command_id=uuid4(),
        event_hash="sha256:" + "b" * 64,
        event_id=event_id,
        kind=EventKind.WORKFLOW_CHANGED,
        occurred_at=datetime(2026, 8, 8, 8, 3, tzinfo=UTC),
        payload={
            "operation": "resolve_close",
            "ticket_id": str(TICKET_ID),
            "workflow_ref": "ctower.workflow@1",
            "workflow_version": 4,
            "stage": "closed",
            "lifecycle_facts": ["resolved", "closed"],
        },
        record_position=41,
        sequence=4,
        stream_id=f"workflow:{TICKET_ID}",
    )

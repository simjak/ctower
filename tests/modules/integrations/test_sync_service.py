from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from ctower_kernel.board_context.labels import ApplyLabelCommand
from ctower_kernel.integrations import (
    GitLabCloseCommand,
    GitLabCloseReceipt,
    GitLabCursor,
    GitLabIssue,
    GitLabIssueLink,
    GitLabIssuePage,
    GitLabIssueSync,
    GitLabReporter,
    GitLabSyncBinding,
    GitLabSyncError,
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

TENANT_ID = UUID("33333333-3333-4333-8333-333333333333")
ACTOR_ID = UUID("11111111-1111-4111-8111-111111111111")
TICKET_ID = UUID("44444444-4444-4444-8444-444444444444")
THREAD_ID = UUID("55555555-5555-4555-8555-555555555555")
EVENT_PAGE_SIZE = 100


def _actor() -> Actor:
    return Actor(ACTOR_ID, TENANT_ID, PrincipalKind.COMMANDER)


def _binding() -> GitLabSyncBinding:
    return GitLabSyncBinding(
        integration_key="gitlab.feedback",
        revision_id=UUID("22222222-2222-4222-8222-222222222222"),
        revision_digest="sha256:" + "a" * 64,
        project_id=42,
        project_key="ctower",
        initial_custodian_id=ACTOR_ID,
        import_updated_after=datetime(2026, 8, 8, 8, tzinfo=UTC),
        page_size=50,
        poll_interval=timedelta(seconds=60),
        label_map=(("bug", "type.bug"),),
    )


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
        "updated_at": datetime(2026, 8, 8, 8, 1, tzinfo=UTC),
    }
    values.update(changes)
    return GitLabIssue(**values)  # type: ignore[arg-type]


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 8, 8, 2, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class _Adapter:
    def __init__(self, issue: GitLabIssue | None) -> None:
        self.issue = issue
        self.list_calls = 0
        self.closes: list[tuple[GitLabIssueLink, GitLabCloseCommand]] = []

    def list_issues(self, _binding: GitLabSyncBinding, _cursor: GitLabCursor) -> GitLabIssuePage:
        self.list_calls += 1
        return GitLabIssuePage((self.issue,) if self.issue is not None else (), None)

    def comment_and_close(
        self, link: GitLabIssueLink, command: GitLabCloseCommand
    ) -> GitLabCloseReceipt:
        self.closes.append((link, command))
        return GitLabCloseReceipt(
            delivery_id=command.delivery_id,
            comment_created=True,
            issue_closed=True,
        )


class _Store:
    def __init__(self) -> None:
        self.cursor = GitLabCursor(datetime(2026, 8, 8, 8, tzinfo=UTC), 1, 0)
        self.next_due = datetime.min.replace(tzinfo=UTC)
        self.issue: GitLabIssue | None = None
        self.link: GitLabIssueLink | None = None
        self.deliveries: set[UUID] = set()
        self.failures = 0

    def claim(
        self, _actor: Actor, binding: GitLabSyncBinding, *, now: datetime
    ) -> GitLabCursor | None:
        if now < self.next_due:
            return None
        self.next_due = now + binding.poll_interval
        return self.cursor

    def issue_link(
        self, _actor: Actor, _binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssueLink | None:
        return self.link if self.link is not None and self.link.issue_iid == issue_iid else None

    def ticket_link(
        self, _actor: Actor, _binding: GitLabSyncBinding, ticket_id: UUID
    ) -> GitLabIssueLink | None:
        return self.link if self.link is not None and self.link.ticket_id == ticket_id else None

    def latest_issue(
        self, _actor: Actor, _binding: GitLabSyncBinding, issue_iid: int
    ) -> GitLabIssue | None:
        return self.issue if self.issue is not None and self.issue.iid == issue_iid else None

    def record_issue(
        self,
        actor: Actor,
        binding: GitLabSyncBinding,
        issue: GitLabIssue,
        *,
        ticket_id: UUID,
        thread_id: UUID,
        observed_at: datetime,
    ) -> None:
        del observed_at
        candidate = GitLabIssueLink(
            actor.tenant_id,
            binding.integration_key,
            binding.revision_digest,
            issue.project_id,
            issue.iid,
            ticket_id,
            thread_id,
            issue.web_url,
        )
        if self.link is not None:
            assert self.link == candidate
        self.link = candidate
        self.issue = issue

    def record_observation(
        self,
        _actor: Actor,
        _binding: GitLabSyncBinding,
        issue: GitLabIssue,
        *,
        observed_at: datetime,
    ) -> None:
        del observed_at
        self.issue = issue

    def delivered(self, _actor: Actor, _binding: GitLabSyncBinding, event_id: UUID) -> bool:
        return event_id in self.deliveries

    def record_delivery(
        self,
        _actor: Actor,
        _binding: GitLabSyncBinding,
        _link: GitLabIssueLink,
        receipt: GitLabCloseReceipt,
        *,
        delivered_at: datetime,
    ) -> None:
        del delivered_at
        self.deliveries.add(receipt.delivery_id)

    def complete(
        self,
        _actor: Actor,
        _binding: GitLabSyncBinding,
        cursor: GitLabCursor,
        *,
        now: datetime,
    ) -> None:
        del now
        self.cursor = cursor

    def fail(self, _actor: Actor, _binding: GitLabSyncBinding, *, now: datetime) -> None:
        del now
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
        source = command.source
        return IntakeCommandResult(
            command.client_command_id,
            (uuid4(), uuid4()),
            uuid4(),
            IntakeOutcome.TICKET_CREATED,
            "ctower",
            source,
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
        assert limit == EVENT_PAGE_SIZE
        del cursor, telemetry
        return ProjectEventPage(project_key, self.events, None)


def _service(
    adapter: _Adapter,
    store: _Store,
    intake: _Intake,
    comments: _Comments,
    events: _Events,
    board: _Board,
    clock: _Clock,
) -> GitLabIssueSync:
    return GitLabIssueSync(adapter, store, intake, comments, events, board, clock=clock)


def test_real_issue_shape_creates_one_source_link_and_maps_feedback_fields() -> None:
    clock = _Clock()
    adapter, store, intake, comments, events, board = (
        _Adapter(_issue()),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(adapter, store, intake, comments, events, board, clock)

    batch = service.tick(_actor(), _binding())

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
    adapter, store, intake, comments, events, board = (
        _Adapter(_issue()),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(adapter, store, intake, comments, events, board, clock)
    service.tick(_actor(), _binding())

    assert not service.tick(_actor(), _binding()).claimed
    assert adapter.list_calls == 1
    clock.now += timedelta(seconds=60)
    adapter.issue = replace(
        _issue(),
        body="Updated feedback body",
        state="closed",
        updated_at=clock.now,
    )
    batch = service.tick(_actor(), _binding())

    assert batch.ticket_updates == 1 and batch.tickets_created == 0
    assert len(intake.commands) == 1
    assert len(comments.commands) == 1
    comment = comments.commands[0]
    assert "State: closed" in comment.body
    assert "Updated feedback body" in comment.body


def test_only_proof_gated_close_event_comments_and_closes_linked_gitlab_issue_once() -> None:
    clock = _Clock()
    adapter, store, intake, comments, events, board = (
        _Adapter(_issue()),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(adapter, store, intake, comments, events, board, clock)
    service.tick(_actor(), _binding())
    close_event = _close_event()
    events.events = (close_event,)
    adapter.issue = None
    clock.now += timedelta(seconds=60)

    batch = service.tick(_actor(), _binding())

    assert batch.closures_delivered == 1
    assert len(adapter.closes) == 1
    link, command = adapter.closes[0]
    assert link.ticket_id == TICKET_ID
    assert command.delivery_id == close_event.event_id
    assert "current-proof gate" in command.comment
    clock.now += timedelta(seconds=60)
    assert service.tick(_actor(), _binding()).closures_delivered == 0
    assert len(adapter.closes) == 1


def test_adapter_cannot_return_an_issue_from_another_project() -> None:
    clock = _Clock()
    adapter, store, intake, comments, events, board = (
        _Adapter(_issue(project_id=43)),
        _Store(),
        _Intake(),
        _Comments(),
        _Events(),
        _Board(),
    )
    service = _service(adapter, store, intake, comments, events, board, clock)

    with pytest.raises(GitLabSyncError, match="another project"):
        service.tick(_actor(), _binding())

    assert store.failures == 1 and intake.commands == []


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

"""Typed, cursorable, project-scoped accepted-event feed evidence for #186."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from support.acceptance import accept_command, accept_pending_commands
from support.server import running_api, start_and_admit
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_client import (
    AssignmentChangeRequest,
    CtowerClient,
    CtowerProblemError,
    FreezeCriteriaRequest,
    MutableAssignmentKind,
    Priority,
    PriorityChangeRequest,
    ProjectEvent,
    ProjectProofChangedEvent,
    ProjectTicketCreatedEvent,
    ProjectWorkChangedEvent,
    ProjectWorkflowChangedEvent,
    ProofCriterion,
    RelationKind,
    RelationRequest,
    SourceReference,
    TicketCreateRequest,
)
from ctower_client import Problem as HttpProblem
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_CONTENT = 422


def test_typed_cursor_feed_replays_to_the_same_board_card(tenant: TenantFixture) -> None:
    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        created = client.create_ticket(
            _ticket_request(tenant, "ctower", "feed-replay"),
            command_id=uuid4(),
        )
        ticket_id = created.ticket.ticket_id
        client.change_ticket_priority(
            ticket_id,
            PriorityChangeRequest(
                expected_version=1,
                priority=Priority.P1,
                reason="Typed feed replay evidence",
            ),
            command_id=uuid4(),
        )
        client.change_ticket_assignment(
            ticket_id,
            AssignmentChangeRequest(
                assignment_kind=MutableAssignmentKind.CURRENT_ASSIGNEE,
                expected_version=2,
                reason="Typed feed replay owner",
                to_principal_id=tenant.operator_id,
            ),
            command_id=uuid4(),
        )

        pending = client.list_project_events("ctower", limit=1)
        assert pending.events == ()
        assert pending.next_cursor == "v1:ctower:0:0"
        assert pending.source_watermark == 0

        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
        events, watermark, final_cursor = _all_events(client, "ctower")
        board = client.get_board(project_key="ctower")
        terminal = client.list_project_events("ctower", cursor=final_cursor, limit=1)
    direct = _direct_event_page(tenant, "ctower")
    invalid = _direct_event_page(tenant, "ctower", cursor="malformed")
    refused = _direct_event_page(tenant, "manibo", cursor=final_cursor)

    assert direct.status_code == HTTP_OK
    assert [event["kind"] for event in direct.json()["events"]] == [
        "ticket.created",
        "work.changed",
        "work.changed",
    ]
    assert invalid.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert invalid.json()["code"] == "validation-error"
    assert refused.status_code == HTTP_NOT_FOUND
    assert refused.json()["code"] == "project-scope-denied"
    assert [event.kind for event in events] == [
        "ticket.created",
        "work.changed",
        "work.changed",
    ]
    assert [(event.acceptance_position, event.record_position) for event in events] == sorted(
        (event.acceptance_position, event.record_position) for event in events
    )
    assert all(event.acceptance_position <= watermark for event in events)
    assert _fold_board_card(events) == board.cards[0].model_dump(mode="json")
    assert terminal.events == ()
    assert terminal.next_cursor == final_cursor
    assert terminal.source_watermark == watermark


def test_acceptance_cursor_does_not_skip_a_late_lower_record_position(
    tenant: TenantFixture,
) -> None:
    first_command, second_command = uuid4(), uuid4()
    with (
        running_api(tenant.database.runtime_dsn) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        first_ticket = client.create_ticket(
            _ticket_request(tenant, "ctower", "accepted-later"),
            command_id=first_command,
        ).ticket.ticket_id
        second_ticket = client.create_ticket(
            _ticket_request(tenant, "ctower", "accepted-first"),
            command_id=second_command,
        ).ticket.ticket_id
        accept_command(
            tenant.database.admin_dsn,
            tenant.tenant_id,
            tenant.commander_id,
            second_command,
        )
        first_page = client.list_project_events("ctower", limit=10)
        accept_command(
            tenant.database.admin_dsn,
            tenant.tenant_id,
            tenant.commander_id,
            first_command,
        )
        second_page = client.list_project_events(
            "ctower",
            cursor=first_page.next_cursor,
            limit=10,
        )

    assert [event.aggregate_id for event in first_page.events] == [second_ticket]
    assert [event.aggregate_id for event in second_page.events] == [first_ticket]
    assert first_page.events[0].record_position > second_page.events[0].record_position
    assert first_page.events[0].acceptance_position < second_page.events[0].acceptance_position


def test_linked_workflow_aggregate_uses_its_ticket_project_scope(
    tenant: TenantFixture,
) -> None:
    with (
        running_api(tenant.database.runtime_dsn) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        ticket_id = client.create_ticket(
            _ticket_request(tenant, "ctower", "linked-workflow"),
            command_id=uuid4(),
        ).ticket.ticket_id
        start_and_admit(client, ticket_id)
        client.freeze_proof_criteria(
            ticket_id,
            FreezeCriteriaRequest(
                expected_version=0,
                candidate_digest="sha256:" + "a" * 64,
                criteria=(
                    ProofCriterion(
                        key="artifact-current",
                        description="Artifact evidence matches the current candidate.",
                        candidate_dependent=True,
                        requires_verdict=True,
                    ),
                ),
            ),
            command_id=uuid4(),
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        events, _, _ = _all_events(client, "ctower")
    direct = _direct_event_page(tenant, "ctower")

    workflow_event = next(
        event for event in events if isinstance(event, ProjectWorkflowChangedEvent)
    )
    assert workflow_event.aggregate_id != ticket_id
    assert workflow_event.payload.ticket_id == ticket_id
    assert any(isinstance(event, ProjectProofChangedEvent) for event in events)
    assert "workflow.changed" in {event["kind"] for event in direct.json()["events"]}
    assert "proof.changed" in {event["kind"] for event in direct.json()["events"]}


def test_related_foreign_ticket_link_does_not_duplicate_source_event_into_project(
    tenant: TenantFixture,
) -> None:
    with (
        running_api(tenant.database.runtime_dsn) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        source = client.create_ticket(
            _ticket_request(tenant, "ctower", "relation-source"),
            command_id=uuid4(),
        ).ticket.ticket_id
        target = client.create_ticket(
            _ticket_request(tenant, "manibo", "relation-target"),
            command_id=uuid4(),
        ).ticket.ticket_id
        client.add_ticket_relation(
            source,
            RelationRequest(
                expected_version=1,
                reason="Cross-project scope regression",
                relation_kind=RelationKind.DEPENDS_ON,
                target_ticket_id=target,
            ),
            command_id=uuid4(),
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        source_events, _, _ = _all_events(client, "ctower")
        target_events, _, _ = _all_events(client, "manibo")

    assert any(isinstance(event, ProjectWorkChangedEvent) for event in source_events)
    assert not any(isinstance(event, ProjectWorkChangedEvent) for event in target_events)


@pytest.mark.parametrize(
    ("left", "right"),
    (
        pytest.param("ctower", "manibo", id="ctower-to-manibo"),
        pytest.param("ctower", "bh-loop", id="ctower-to-bh-loop"),
        pytest.param("manibo", "bh-loop", id="manibo-to-bh-loop"),
    ),
)
def test_project_cursor_reuse_is_a_named_refusal(
    tenant: TenantFixture,
    left: str,
    right: str,
) -> None:
    with (
        running_api(tenant.database.runtime_dsn) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        client.create_ticket(
            _ticket_request(tenant, left, f"{left}-cursor"),
            command_id=uuid4(),
        )
        client.create_ticket(
            _ticket_request(tenant, right, f"{right}-cursor"),
            command_id=uuid4(),
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        cursor = client.list_project_events(left, limit=1).next_cursor

        with pytest.raises(CtowerProblemError) as refused:
            client.list_project_events(right, cursor=cursor, limit=1)

    assert cast(HttpProblem, refused.value.problem).status == HTTP_NOT_FOUND
    assert refused.value.problem.code == "project-scope-denied"


def _ticket_request(
    tenant: TenantFixture,
    project_key: str,
    suffix: str,
) -> TicketCreateRequest:
    return TicketCreateRequest(
        initial_custodian_id=tenant.commander_id,
        priority=Priority.P2,
        project_key=project_key,
        source=SourceReference(kind="test", ref=f"test:{suffix}:{uuid4()}"),
        title=f"Typed event feed {suffix}",
    )


def _all_events(
    client: CtowerClient,
    project_key: str,
) -> tuple[tuple[ProjectEvent, ...], int, str]:
    cursor: str | None = None
    events: list[ProjectEvent] = []
    while True:
        page = client.list_project_events(project_key, cursor=cursor, limit=1)
        assert page.project_key == project_key
        events.extend(page.events)
        cursor = page.next_cursor
        if not page.has_more:
            return tuple(events), page.source_watermark, cursor


def _direct_event_page(
    tenant: TenantFixture,
    project_key: str,
    *,
    cursor: str | None = None,
) -> Response:
    parameters = {"limit": "100"}
    if cursor is not None:
        parameters["cursor"] = cursor
    with TestClient(create_app(PostgresRecord(tenant.database.runtime_dsn))) as client:
        return cast(
            Response,
            client.get(
                f"/v1/projects/{project_key}/events",
                params=parameters,
                headers={
                    "Authorization": f"Bearer {tenant.commander_credential}",
                    **telemetry_headers(),
                },
            ),
        )


def _fold_board_card(events: tuple[ProjectEvent, ...]) -> dict[str, Any]:
    state: dict[str, Any] | None = None
    for event in events:
        if isinstance(event, ProjectTicketCreatedEvent):
            state = {
                "activity_class": None,
                "assignee_id": None,
                "blocker_opened_at": None,
                "blocker_reason": None,
                "custodian_id": str(event.payload.custodian_id),
                "delivery_facts": [],
                "lane": "backlog",
                "priority": event.payload.priority.value,
                "project_key": event.payload.project_key,
                "risk": None,
                "stage_key": None,
                "stage_label": None,
                "ticket_id": str(event.aggregate_id),
                "title": event.payload.title,
                "underlying_lane": None,
                "version": 1,
            }
        elif isinstance(event, ProjectWorkChangedEvent):
            _fold_work_event(state, event)
    assert state is not None
    return state


def _fold_work_event(
    state: dict[str, Any] | None,
    event: ProjectWorkChangedEvent,
) -> None:
    assert state is not None
    state["version"] = event.payload.work_version
    if event.payload.operation == "priority_changed":
        state["priority"] = event.payload.data.to_priority.value
    elif event.payload.operation == "assignment_changed":
        state["assignee_id"] = str(event.payload.data.to_principal_id)

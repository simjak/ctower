"""AC-PORT-06: three mutually disjoint Board rows, cross-proven by the Board
projection and by an independent fold over the CT-I1-012 project event feed.

The feed fold never calls the Board's own query function — it derives ticket
membership purely from raw `ticket.created` events read off
`GET /v1/projects/{project_key}/events`, so a replay bug that only the Board's
own fold would hide cannot pass this file silently.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from itertools import permutations
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from support.acceptance import accept_pending_commands
from support.catalog import (
    FileSchemas,
    MemoryObjectStore,
    actor_for,
    apply_initial_bundle,
    minimal_bundle,
)
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import CatalogProblem, CompanyBundle, PostgresCatalog
from ctower_kernel.projections import BoardQuery, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()

HTTP_ACCEPTED = 202
HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE_ENTITY = 422
PROHIBITED_CODE = "prohibited-data-class"
_RECONNECT_FIRST_PAGE_SIZE = 2
_PROJECTS = ("ctower", "manibo", "bh-loop")

# One canary per class — see test_manibo_ordinary_intake.py, the file that established
# this pattern for these five stable class names.
_PROBES: tuple[tuple[str, str, str], ...] = (
    (
        "credential_material",
        "manibo",
        "manibo-feed-canary-1af0 rotate the runner: password = notarealsecret",
    ),
    (
        "production_customer_data",
        "manibo",
        "manibo-feed-canary-2b31 the customer export from the production tenant reproduces it",
    ),
    (
        "phi_hipaa_covered",
        "bh-loop",
        "bhloop-feed-canary-3c42 the patient could not complete the clinical intake form",
    ),
    (
        "pii_beyond_staff_identity",
        "bh-loop",
        "bhloop-feed-canary-4d53 reporter SSN 123-45-6789 was pasted into the issue body",
    ),
    (
        "live_incident_indicator",
        "ctower",
        "ctower-feed-canary-5e64 SEV-1 declared on the ingest path, still an active incident",
    ),
)


def test_three_projects_prove_disjoint_boards_via_independent_feed_replay(
    tenant: TenantFixture,
) -> None:
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        tickets = {
            project: _created_ticket_id(_submit_intake(client, tenant, project, f"{project}-R201"))
            for project in _PROJECTS
        }
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    projections.catch_up(tenant.tenant_id)
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    boards: dict[str, set[UUID]] = {}
    for project in _PROJECTS:
        board = projections.board(actor, BoardQuery(project_key=project))
        assert not isinstance(board, RecordProblem), board
        boards[project] = {card.ticket_id for card in board.cards}

    # AC-PORT-06: exactly one ticket per project, three mutually disjoint Board rows.
    for project in _PROJECTS:
        assert boards[project] == {tickets[project]}
    assert boards["ctower"].isdisjoint(boards["manibo"])
    assert boards["ctower"].isdisjoint(boards["bh-loop"])
    assert boards["manibo"].isdisjoint(boards["bh-loop"])

    # CT-I1-012: the feed independently replays the same per-project ticket set.
    with _client(tenant) as client:
        feeds = {project: _drain_feed(client, tenant, project) for project in _PROJECTS}
    replayed = {project: _fold_ticket_ids(events) for project, events in feeds.items()}
    assert replayed == boards


def test_feed_reconnect_after_a_page_boundary_neither_gaps_nor_duplicates(
    tenant: TenantFixture,
) -> None:
    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        created = [
            _created_ticket_id(_submit_intake(client, tenant, "ctower", f"ctower-R{300 + index}"))
            for index in range(5)
        ]
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    with _client(tenant) as client:
        full = _drain_feed(client, tenant, "ctower", limit=100)
        # Simulate a dropped connection: read the first page, discard the client,
        # and reconnect with a fresh page at the exact cursor the first page named.
        first_page = _get_events(
            client, tenant, "ctower", cursor=0, limit=_RECONNECT_FIRST_PAGE_SIZE
        )
        assert first_page.status_code == HTTP_OK
        body = first_page.json()
        assert len(body["events"]) == _RECONNECT_FIRST_PAGE_SIZE
        resumed = _drain_feed(client, tenant, "ctower", start_cursor=body["next_cursor"])

    reconnected = [*body["events"], *resumed]
    full_ids = [event["event_id"] for event in full]
    reconnected_ids = [event["event_id"] for event in reconnected]
    assert reconnected_ids == full_ids  # no gap, no duplicate, same order
    assert len(set(full_ids)) == len(full_ids)
    assert _fold_ticket_ids(full) == set(created)


def test_the_feed_carries_more_than_ticket_created(tenant: TenantFixture) -> None:
    """A `work.changed` priority mutation reaches the feed alongside `ticket.created`."""

    _apply_portfolio_bundle(tenant)
    with _client(tenant) as client:
        ticket_id = _created_ticket_id(_submit_intake(client, tenant, "ctower", "ctower-R401"))
        changed = client.post(
            f"/v1/tickets/{ticket_id}/priority",
            json={"expected_version": 1, "priority": "P1", "reason": "feed contract probe"},
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(uuid4()),
                **telemetry_headers(),
            },
        )
        assert changed.status_code == HTTP_ACCEPTED, changed.text
        page = _get_events(client, tenant, "ctower", cursor=0, limit=50)

    assert page.status_code == HTTP_OK, page.text
    assert [event["kind"] for event in page.json()["events"]] == [
        "ticket.created",
        "work.changed",
    ]


def test_all_three_project_pairs_refuse_a_foreign_feed_read(tenant: TenantFixture) -> None:
    # No CompanyBundle needed: seat-credential issuance grants the project scope
    # directly, matching test_seat_credentials.py's own six-pair precedent.
    credentials = {project: secrets.token_urlsafe(32) for project in _PROJECTS}
    tickets: dict[str, UUID] = {}

    with _client(tenant) as client:
        for project in _PROJECTS:
            tickets[project] = _issue_seat_and_ticket(client, tenant, project, credentials[project])

        refusals = {
            (source, target): cast(
                Response,
                client.get(
                    f"/v1/projects/{target}/events",
                    params={"cursor": 0, "limit": 50},
                    headers={
                        "Authorization": f"Bearer {credentials[source]}",
                        **telemetry_headers(),
                    },
                ),
            )
            for source, target in permutations(_PROJECTS, 2)
        }

    assert {
        pair: (response.status_code, response.json().get("code"))
        for pair, response in refusals.items()
    } == dict.fromkeys(refusals, (HTTP_FORBIDDEN, "project-scope-denied"))
    # Every refusal disclosed zero rows — the problem body carries no `events` key at all.
    assert all("events" not in response.json() for response in refusals.values())

    # Each seat still reads its OWN project's feed and sees only its own ticket's stream.
    with _client(tenant) as client:
        for project in _PROJECTS:
            own = cast(
                Response,
                client.get(
                    f"/v1/projects/{project}/events",
                    params={"cursor": 0, "limit": 50},
                    headers={
                        "Authorization": f"Bearer {credentials[project]}",
                        **telemetry_headers(),
                    },
                ),
            )
            assert own.status_code == HTTP_OK, own.text
            stream_ids = {event["stream_id"] for event in own.json()["events"]}
            assert stream_ids == {f"ticket:{tickets[project]}"}


@pytest.mark.parametrize(("prohibited_class", "project_key", "content"), _PROBES)
def test_no_prohibited_class_reaches_a_feed_payload(
    tenant: TenantFixture,
    prohibited_class: str,
    project_key: str,
    content: str,
) -> None:
    _apply_portfolio_bundle(tenant)
    canary = content.split(" ", 1)[0]

    with _client(tenant) as client:
        # A control ticket first, so the feed is non-empty and the scan is real.
        _created_ticket_id(_submit_intake(client, tenant, project_key, f"{project_key}-R501"))
        refused = client.post(
            "/v1/intake",
            json={
                "content": content,
                "initial_custodian_id": str(tenant.commander_id),
                "intent": "create_ticket",
                "priority": "P2",
                "project_key": project_key,
                "source": {"kind": "mission-control-request", "ref": f"feed-canary-{uuid4()}"},
                "title": "Portfolio backlog item",
            },
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(uuid4()),
                **telemetry_headers(),
            },
        )
        page = _get_events(client, tenant, project_key, cursor=0, limit=50)

    assert refused.status_code == HTTP_UNPROCESSABLE_ENTITY, refused.text
    assert refused.json()["code"] == PROHIBITED_CODE
    assert refused.json()["prohibited_classes"] == [prohibited_class]
    assert page.status_code == HTTP_OK, page.text
    assert canary not in json.dumps(page.json(), ensure_ascii=False)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        residue = connection.execute(
            "SELECT count(*) FROM events WHERE tenant_id = %s AND payload::text LIKE %s",
            (tenant.tenant_id, f"%{canary}%"),
        ).fetchone()
    assert residue is not None and residue[0] == 0


def _issue_seat_and_ticket(
    client: TestClient, tenant: TenantFixture, project: str, credential: str
) -> UUID:
    """Issue one project-seat credential and one ticket custodied by its principal."""

    issued = client.post(
        "/v1/admin/seat-credentials",
        json={
            "credential_digest": f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}",
            "credential_ref": f"secret-ref:test/{project}/feed-pair-prober",
            "display_name": (
                "Ctower Commander" if project == "ctower" else f"{project.title()} Feed Prober"
            ),
            "project_key": project,
            "scopes": ["capture", "transition", "evidence"],
            "seat_key": (
                "ctower-commander" if project == "ctower" else f"{project}-feed-pair-prober"
            ),
        },
        headers={
            "Authorization": f"Bearer {tenant.operator_credential}",
            "Idempotency-Key": str(uuid4()),
            **telemetry_headers(),
        },
    )
    assert issued.status_code == HTTP_ACCEPTED, issued.text
    principal_id = UUID(issued.json()["principal_id"])
    created = client.post(
        "/v1/tickets",
        json={
            "initial_custodian_id": str(principal_id),
            "priority": "P2",
            "source": {"kind": "feed-pair", "ref": project},
            "title": f"{project} feed pair target",
        },
        headers={
            "Authorization": f"Bearer {tenant.operator_credential}",
            "Idempotency-Key": str(uuid4()),
            **telemetry_headers(),
        },
    )
    assert created.status_code == HTTP_ACCEPTED, created.text
    return UUID(created.json()["ticket"]["ticket_id"])


def _client(tenant: TenantFixture) -> TestClient:
    record = PostgresRecord(tenant.database.runtime_dsn)
    return TestClient(
        create_app(
            record,
            work=Work(record, writer=PostgresWork(tenant.database.runtime_dsn)),
        ),
        client=("127.0.0.1", 51000),
    )


def _apply_portfolio_bundle(tenant: TenantFixture) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
    )
    bundle = _tenant_bundle()
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem), plan
    apply_initial_bundle(catalog, actor, bundle)


def _tenant_bundle() -> CompanyBundle:
    bundle = minimal_bundle()
    return bundle.model_copy(
        update={
            "company": bundle.company.model_copy(
                update={"key": "ctower", "display_name": "Ctower"}
            ),
            "resources": tuple(
                resource.model_copy(
                    update={
                        "component": resource.component.model_copy(
                            update={
                                "scope": resource.component.scope.model_copy(
                                    update={"tenant": "ctower"}
                                )
                            }
                        )
                    }
                )
                for resource in bundle.resources
            ),
        }
    )


def _submit_intake(
    client: TestClient,
    tenant: TenantFixture,
    project_key: str,
    source_ref: str,
) -> Response:
    command_id = uuid4()
    return cast(
        Response,
        client.post(
            "/v1/intake",
            json={
                "content": f"Create {project_key} scoped work",
                "initial_custodian_id": str(tenant.commander_id),
                "intent": "create_ticket",
                "priority": "P2",
                "project_key": project_key,
                "source": {"kind": "mission-control-request", "ref": source_ref},
                "title": f"{project_key} board fold ticket",
            },
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        ),
    )


def _created_ticket_id(response: Response) -> UUID:
    assert response.status_code == HTTP_ACCEPTED, response.text
    return UUID(str(response.json()["ticket_id"]))


def _get_events(
    client: TestClient,
    tenant: TenantFixture,
    project_key: str,
    *,
    cursor: int,
    limit: int,
) -> Response:
    # The operator principal carries no per-project grant to check (INV-69) —
    # matching the disjointness proof, which reads every project as operator.
    return cast(
        Response,
        client.get(
            f"/v1/projects/{project_key}/events",
            params={"cursor": cursor, "limit": limit},
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                **telemetry_headers(),
            },
        ),
    )


def _drain_feed(
    client: TestClient,
    tenant: TenantFixture,
    project_key: str,
    *,
    start_cursor: int = 0,
    limit: int = 1,
) -> list[dict[str, Any]]:
    """Page to exhaustion with a deliberately small default limit."""

    events: list[dict[str, Any]] = []
    cursor: int | None = start_cursor
    while cursor is not None:
        response = _get_events(client, tenant, project_key, cursor=cursor, limit=limit)
        assert response.status_code == HTTP_OK, response.text
        body = response.json()
        events.extend(body["events"])
        cursor = body["next_cursor"]
    return events


def _fold_ticket_ids(events: list[dict[str, Any]]) -> set[UUID]:
    """Independently reconstruct Board ticket membership from raw feed events.

    `ticket.created`'s payload carries no `ticket_id` (it IS the event's own
    aggregate) — the ticket identity is the `ticket:<uuid>` stream_id instead.
    """

    return {
        UUID(str(event["stream_id"]).removeprefix("ticket:"))
        for event in events
        if event["kind"] == "ticket.created"
    }

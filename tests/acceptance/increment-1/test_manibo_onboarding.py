"""The manibo onboarding journey, end to end, on one disposable stack.

Every other manibo file in this suite starts after somebody has already made manibo
real. This one proves the making, in the order an operator actually performs it:

1. the CompanyBundle is what turns `manibo` into a Project this record accepts work
   for, and what carries the authored `MNB` prefix (D30 keeps the roster configured,
   never coded);
2. the seat credential — not the bundle — is what mints an address, so the same
   compose that answers `inbox-recipient-not-found` before issuance is accepted
   after it;
3. the first ticket that seat captures through the sanctioned capture route wears
   `MNB-1`, and the number is the Project's own;
4. it reaches manibo's Board and never ctower's; and
5. it reaches no Board at all until durability is accepted *and* the projection has
   folded, which is why a surface may never render a pending write as a done one.

The refusal cells ride along on the same stack: the manibo seat cannot capture into
ctower, cannot read ctower's Board, and cannot mint a P0 that only an operator may.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from support.acceptance import accept_pending_commands
from support.catalog import activate_project_prefixes
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.inbox import Inbox, PostgresInbox
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_ACCEPTED = 201
HTTP_PENDING = 202
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
_ACCEPTED_SEND = (HTTP_ACCEPTED, HTTP_PENDING)

_CTOWER = "ctower"
_MANIBO = "manibo"
_MANIBO_SEAT = "manibo-commander"
_CAPTURE_SCOPES = ("capture", "transition", "evidence")
_COMPOSED_TEXT = "Welcome to manibo on ctower."


@dataclass(frozen=True, slots=True)
class _Seat:
    """One issued project seat: the identity, and the secret only this test holds."""

    principal_id: UUID
    credential: str


def test_the_onboarding_journey_lands_one_manibo_ticket_on_manibos_board_alone(
    tenant: TenantFixture,
) -> None:
    """Bundle, seat, capture, Board — the whole journey against one real database."""

    activate_project_prefixes(tenant.database.runtime_dsn, tenant.tenant_id, tenant.operator_id)
    assert _declared_projects(tenant) >= {_CTOWER, _MANIBO}
    assert _authored_prefixes(tenant)[_MANIBO] == "MNB"

    with _client(tenant) as client:
        seat = _issue_seat(client, tenant, project_key=_MANIBO, seat_key=_MANIBO_SEAT)
        captured = _capture(client, seat.credential, seat.principal_id, "Manibo onboarding item")
        # Read the Board through the same credential before anything is accepted:
        # the write exists in the authority and is nowhere in a read model yet.
        unaccepted = _board(client, seat.credential, _MANIBO)

    ticket_id = UUID(str(captured.json()["ticket"]["ticket_id"]))
    assert captured.status_code == HTTP_PENDING, captured.text
    assert captured.json()["ticket"]["display_key"] == "MNB-1"
    assert captured.json()["ticket"]["durability_state"] == "durability_pending"
    assert unaccepted.status_code == HTTP_OK, unaccepted.text
    assert unaccepted.json()["cards"] == []

    _accept_and_fold(tenant)

    with _client(tenant) as client:
        manibo_board = _board(client, seat.credential, _MANIBO)
        ctower_board = _board(client, tenant.commander_credential, _CTOWER)
        addressed = client.get(
            f"/v1/tickets/{captured.json()['ticket']['display_key']}",
            params={"project_key": _MANIBO},
            headers=_bearer(seat.credential),
        )

    assert [card["display_key"] for card in manibo_board.json()["cards"]] == ["MNB-1"]
    assert [card["ticket_id"] for card in manibo_board.json()["cards"]] == [str(ticket_id)]
    assert {card["project_key"] for card in manibo_board.json()["cards"]} == {_MANIBO}
    assert ctower_board.status_code == HTTP_OK, ctower_board.text
    assert str(ticket_id) not in {card["ticket_id"] for card in ctower_board.json()["cards"]}
    # The display key is an address, not a label: the same key reaches the ticket.
    assert addressed.status_code == HTTP_OK, addressed.text
    assert addressed.json()["ticket_id"] == str(ticket_id)


def test_the_seat_credential_and_not_the_bundle_is_what_mints_a_manibo_address(
    tenant: TenantFixture,
) -> None:
    """An applied bundle names Projects; only an issued seat can be written to.

    The compose control's closed world is `project_seats`, and a bundle writes none.
    So the identical request that answers by the record's own stable refusal name
    before issuance is accepted after it, and the address then appears in the very
    list the picker offers.
    """

    activate_project_prefixes(tenant.database.runtime_dsn, tenant.tenant_id, tenant.operator_id)

    with _client(tenant) as client:
        unminted = _compose(client, tenant.commander_credential, _MANIBO_SEAT)
        seat = _issue_seat(client, tenant, project_key=_MANIBO, seat_key=_MANIBO_SEAT)
        opened = _compose(client, tenant.commander_credential, _MANIBO_SEAT)
        offered = client.get(
            "/v1/inbox/correspondents", headers=_bearer(tenant.commander_credential)
        )

    assert (unminted.status_code, unminted.json()["code"]) == (
        HTTP_NOT_FOUND,
        "inbox-recipient-not-found",
    )
    assert opened.status_code in _ACCEPTED_SEND, opened.text
    assert offered.status_code == HTTP_OK, offered.text
    assert (_MANIBO, _MANIBO_SEAT) in {
        (item["project_key"], item["seat_key"]) for item in offered.json()["correspondents"]
    }
    assert seat.principal_id == _seat_principal(tenant, _MANIBO, _MANIBO_SEAT)

    _accept_and_fold(tenant)

    with _client(tenant) as client:
        thread = client.get(
            f"/v1/inbox/threads/{opened.json()['thread_id']}",
            headers=_bearer(seat.credential),
        )

    assert thread.status_code == HTTP_OK, thread.text
    assert sorted(thread.json()["participants"]) == ["ctower-commander", _MANIBO_SEAT]
    assert [message["text"] for message in thread.json()["messages"]] == [_COMPOSED_TEXT]


def test_a_foreign_project_seat_cannot_ask_which_addresses_manibo_has(
    tenant: TenantFixture,
) -> None:
    """The Inbox is a tenant-wide transport; the *narrowed* address list is not.

    Naming a Project asks a scoped question, and the record answers it only for a
    Project the asking principal actually holds. A ctower-only seat is refused by
    name rather than answered empty, so "manibo has no addresses" and "manibo is
    not yours to ask about" can never look alike.
    """

    activate_project_prefixes(tenant.database.runtime_dsn, tenant.tenant_id, tenant.operator_id)

    with _client(tenant) as client:
        _issue_seat(client, tenant, project_key=_MANIBO, seat_key=_MANIBO_SEAT)
        ctower_seat = _issue_seat(client, tenant, project_key=_CTOWER, seat_key="ctower-reviewer")
        narrowed = client.get(
            "/v1/inbox/correspondents",
            params={"project_key": _MANIBO},
            headers=_bearer(ctower_seat.credential),
        )
        own = client.get(
            "/v1/inbox/correspondents",
            params={"project_key": _CTOWER},
            headers=_bearer(ctower_seat.credential),
        )

    assert (narrowed.status_code, narrowed.json()["code"]) == (
        HTTP_FORBIDDEN,
        "project-scope-denied",
    )
    assert "correspondents" not in narrowed.json()
    assert own.status_code == HTTP_OK, own.text
    assert {item["project_key"] for item in own.json()["correspondents"]} == {_CTOWER}


def test_the_manibo_seat_captures_only_into_manibo_and_reads_only_manibos_board(
    tenant: TenantFixture,
) -> None:
    """Two halves of one law: a seat writes where it sits, and reads where it sits."""

    activate_project_prefixes(tenant.database.runtime_dsn, tenant.tenant_id, tenant.operator_id)

    with _client(tenant) as client:
        seat = _issue_seat(client, tenant, project_key=_MANIBO, seat_key=_MANIBO_SEAT)
        foreign_project = _capture(
            client,
            seat.credential,
            seat.principal_id,
            "Captured into a project this seat does not hold",
            project_key=_CTOWER,
        )
        foreign_custodian = _capture(
            client,
            seat.credential,
            tenant.commander_id,
            "Custody placed on somebody else's Commander",
        )
        foreign_board = _board(client, seat.credential, _CTOWER)

    assert (foreign_project.status_code, foreign_project.json()["code"]) == (
        HTTP_NOT_FOUND,
        "tenant-scope-denied",
    )
    assert (foreign_custodian.status_code, foreign_custodian.json()["code"]) == (
        HTTP_FORBIDDEN,
        "unauthorized",
    )
    assert (foreign_board.status_code, foreign_board.json()["code"]) == (
        HTTP_FORBIDDEN,
        "project-scope-denied",
    )
    assert "cards" not in foreign_board.json()
    assert _ticket_count(tenant) == 0


def test_p0_is_refused_to_the_manibo_seat_and_minted_only_through_the_operator(
    tenant: TenantFixture,
) -> None:
    """P0 is operator authority, and the refusal costs the Project no number.

    The refused capture must not consume `MNB-1`: a display sequence that advanced
    on refusals would hand the Project's first real item a number nobody can explain.
    """

    activate_project_prefixes(tenant.database.runtime_dsn, tenant.tenant_id, tenant.operator_id)

    with _client(tenant) as client:
        seat = _issue_seat(client, tenant, project_key=_MANIBO, seat_key=_MANIBO_SEAT)
        refused = _capture(
            client, seat.credential, seat.principal_id, "Seat-minted P0", priority="P0"
        )
        minted = _capture(
            client,
            tenant.operator_credential,
            seat.principal_id,
            "Operator-minted P0",
            priority="P0",
        )

    assert (refused.status_code, refused.json()["code"]) == (HTTP_FORBIDDEN, "unauthorized")
    assert "operator" in refused.json()["detail"]
    assert minted.status_code == HTTP_PENDING, minted.text
    assert minted.json()["ticket"]["display_key"] == "MNB-1"
    assert minted.json()["ticket"]["priority"] == "P0"


def _client(tenant: TenantFixture) -> TestClient:
    return TestClient(_app(tenant), client=("127.0.0.1", 51000))


def _app(tenant: TenantFixture) -> FastAPI:
    """Compose exactly the surfaces the journey crosses: capture, Board, Inbox."""

    runtime_dsn = tenant.database.runtime_dsn
    record = PostgresRecord(runtime_dsn)
    return create_app(
        record,
        work=Work(record, writer=PostgresWork(runtime_dsn)),
        projections=Projections(PostgresProjections(tenant.database.projection_dsn)),
        inbox=Inbox(PostgresInbox(runtime_dsn)),
    )


def _issue_seat(
    client: TestClient,
    tenant: TenantFixture,
    *,
    project_key: str,
    seat_key: str,
) -> _Seat:
    """Issue one project-seat credential the way the operator onboarding flow does."""

    credential = secrets.token_urlsafe(32)
    response = client.post(
        "/v1/admin/seat-credentials",
        json={
            "credential_digest": f"sha256:{hashlib.sha256(credential.encode()).hexdigest()}",
            "credential_ref": f"secret-ref:test/{project_key}/{seat_key}",
            # The display name is a tenant-unique human identity, so it is derived
            # from the seat rather than the Project: two seats cannot share one.
            "display_name": seat_key.replace("-", " ").title(),
            "project_key": project_key,
            "scopes": list(_CAPTURE_SCOPES),
            "seat_key": seat_key,
        },
        headers=_bearer(tenant.operator_credential, command_id=uuid4()),
    )
    assert response.status_code == HTTP_PENDING, response.text
    return _Seat(UUID(str(response.json()["principal_id"])), credential)


def _capture(
    client: TestClient,
    credential: str,
    custodian_id: UUID,
    title: str,
    *,
    priority: str = "P2",
    project_key: str | None = None,
) -> Response:
    """Capture one ticket through the sanctioned `ticket capture` route."""

    body: dict[str, object] = {
        "initial_custodian_id": str(custodian_id),
        "priority": priority,
        "source": {"kind": "mission-control-request", "ref": f"onboarding:{uuid4()}"},
        "title": title,
    }
    if project_key is not None:
        body["project_key"] = project_key
    return cast(
        Response,
        client.post("/v1/tickets", json=body, headers=_bearer(credential, command_id=uuid4())),
    )


def _compose(client: TestClient, credential: str, to: str) -> Response:
    """Open a thread to one project-qualified address, the compose control's request."""

    command_id = uuid4()
    return cast(
        Response,
        client.post(
            "/v1/inbox/notifications",
            json={
                "project_key": _MANIBO,
                "severity": "info",
                "text": _COMPOSED_TEXT,
                "to": to,
            },
            headers=_bearer(credential, command_id=command_id),
        ),
    )


def _board(client: TestClient, credential: str, project_key: str) -> Response:
    return cast(
        Response,
        client.get("/v1/board", params={"project_key": project_key}, headers=_bearer(credential)),
    )


def _bearer(credential: str, *, command_id: UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {credential}", **telemetry_headers(command_id)}
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers


def _accept_and_fold(tenant: TenantFixture) -> None:
    """Accept every pending command, then fold — the only order a read may trust."""

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)


def _declared_projects(tenant: TenantFixture) -> set[str]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT project_key FROM project_delivery_checkpoint_definitions
            WHERE tenant_id = %s
            """,
            (tenant.tenant_id,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _authored_prefixes(tenant: TenantFixture) -> dict[str, str]:
    """Read the active bundle's Project prefixes, keyed the way capture resolves them."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT split_part(component.component_key, '.', 1) AS project_key,
                revision.project_prefix
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
            WHERE active.tenant_id = %s AND component.kind = 'project'
              AND revision.project_prefix IS NOT NULL
            """,
            (tenant.tenant_id,),
        ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _seat_principal(tenant: TenantFixture, project_key: str, seat_key: str) -> UUID:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT principal_id FROM project_seats
            WHERE tenant_id = %s AND project_key = %s AND seat_key = %s
            """,
            (tenant.tenant_id, project_key, seat_key),
        ).fetchone()
    if row is None:
        raise AssertionError("the issued seat registered no addressable identity")
    return cast(UUID, row[0])


def _ticket_count(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM tickets WHERE tenant_id = %s", (tenant.tenant_id,)
        ).fetchone()
    if row is None:
        raise AssertionError("ticket count query returned no row")
    return int(cast(int, row[0]))

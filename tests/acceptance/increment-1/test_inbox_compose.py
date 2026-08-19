"""Real PostgreSQL acceptance for opening a new inbox thread from a chosen seat.

The compose control on `/inbox` asks two things of the record that the reply
path never has to: who may be written to at all, and where a message to somebody
you have no thread with lands. Both are the record's answers, so both are proved
here against a real database and the real composed API rather than against the
surface that renders them.
"""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from support.acceptance import accept_pending_commands
from support.server import running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture, provision_seat

from ctower_client import CtowerClient, CtowerProblemError, Problem
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections

__all__: tuple[str, ...] = ()

_ACCEPTED_STATUS = 201
_DURABILITY_PENDING_STATUS = 202
_UNPROCESSABLE_STATUS = 422
_NOT_FOUND_STATUS = 404
_ACCEPTED_SEND_STATUS = (_ACCEPTED_STATUS, _DURABILITY_PENDING_STATUS)


def _compose(
    base_url: str,
    credential: str,
    to: str,
    text: str,
    *,
    project_key: str = "ctower",
) -> httpx.Response:
    """Ask the record to open — or continue — this credential's thread with one seat.

    This is the compose control's whole request: the project-qualified address,
    informational severity, and words. There is no sender field and no thread
    field, so what comes back is the record's own answer about both.
    """

    command_id = uuid4()
    return httpx.post(
        f"{base_url}/v1/inbox/notifications",
        headers={
            "Accept": "application/json, application/problem+json",
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(command_id),
            **telemetry_headers(command_id),
        },
        json={"project_key": project_key, "severity": "info", "to": to, "text": text},
        timeout=30,
    )


def _refusal_code(response: httpx.Response) -> str:
    return str(cast(dict[str, object], json.loads(response.text))["code"])


def test_the_addressable_seats_are_the_ones_a_new_thread_can_be_opened_to(
    tenant: TenantFixture,
) -> None:
    """The picker's closed world, and the command's, are the same world.

    A compose control has to offer somebody before a thread exists, so unlike
    the send box it cannot read its recipient back from a thread. What it reads
    instead is this list — the registered project seats — and the value of that
    is only real if the list and the command agree: every seat listed here can
    be opened a thread to, and a seat that is not listed is refused by the
    record's own stable name rather than quietly creating an identity.
    """
    _director_id, _director_credential = provision_seat(tenant, "director")
    commander = tenant.commander_credential

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=commander) as client,
    ):
        listed = client.list_inbox_correspondents()
        opened = _compose(base_url, commander, "director", "Opened from the compose control.")
        stranger = _compose(base_url, commander, "unregistered-seat", "Nobody holds this address.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
        thread_id = UUID(str(cast(dict[str, object], json.loads(opened.text))["thread_id"]))
        read_back = client.read_inbox_thread(thread_id)

    addressable = [item.seat_key for item in listed.correspondents]
    assert listed.sender == "ctower-commander"
    assert "director" in addressable
    assert "ctower-commander" not in addressable
    assert opened.status_code in _ACCEPTED_SEND_STATUS
    # the same closed world, from the other side: an address nobody holds is
    # refused by name, and no seat identity is invented to receive it
    assert stranger.status_code == _NOT_FOUND_STATUS
    assert _refusal_code(stranger) == "inbox-recipient-not-found"
    assert sorted(read_back.participants) == ["ctower-commander", "director"]
    assert [message.text for message in read_back.messages] == ["Opened from the compose control."]
    print(
        "REAL_COMPOSE_CLOSED_WORLD listed=" + json.dumps(addressable) + f" thread={thread_id}"
        f" unknown={stranger.status_code}"
    )


def test_composing_twice_to_one_seat_stays_one_pair_grouped_thread(
    tenant: TenantFixture,
) -> None:
    """Two composes to the same seat are one conversation, not two.

    The thread a compose opens is derived from the unordered seat pair, so the
    second message joins the thread the first one opened — including the thread
    the notification mirror already opened for that pair. A control that minted
    a fresh thread per send would scatter one correspondent's conversation
    across as many threads as the operator pressed the button.
    """
    _director_id, _director_credential = provision_seat(tenant, "director")

    def compose(base_url: str, text: str) -> dict[str, object]:
        response = _compose(base_url, tenant.commander_credential, "director", text)
        assert response.status_code in _ACCEPTED_SEND_STATUS
        return cast(dict[str, object], json.loads(response.text))

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
    ):
        first = compose(base_url, "The first thing I had to say.")
        second = compose(base_url, "The second thing, in the same conversation.")
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
        thread_id = UUID(str(first["thread_id"]))
        read_back = client.read_inbox_thread(thread_id)

    assert second["thread_id"] == first["thread_id"]
    assert second["message_id"] != first["message_id"]
    assert [message.text for message in read_back.messages] == [
        "The first thing I had to say.",
        "The second thing, in the same conversation.",
    ]
    print(f"REAL_COMPOSE_PAIR_GROUPED thread={thread_id} messages={len(read_back.messages)}")


def test_the_offered_addresses_are_the_accepted_ones_inside_this_seats_grant(
    tenant: TenantFixture,
) -> None:
    """Every address the list offers is one the command accepts — and no other Project's.

    The list withholds four classes, and each is withheld for a reason the reader
    can act on. Three are mirrors of a command refusal: a seat key two seats share
    refuses as ambiguous, the reader's own seat refuses as self, and a reader
    holding no seat can address nobody. The fourth is the grant: a Project this
    principal holds no grant on is not its to enumerate, so the roster of `apex`
    is absent from a `ctower` seat's picker under INV-69.

    That fourth class is deliberately *not* a mirror. The comms plane stays
    tenant-wide, so the foreign compose below is still accepted; what the picker
    stops doing is disclosing who is there. Discovery and delivery answer two
    different questions, and only discovery is a Project-scoped read.
    """

    provision_seat(tenant, "director")
    provision_seat(tenant, "shared-seat")
    provision_seat(tenant, "shared-seat", project_key="apex")
    commander, unseated = tenant.commander_credential, tenant.operator_credential

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=commander) as client,
        CtowerClient(base_url, credential=unseated) as seatless_client,
    ):
        listed = client.list_inbox_correspondents()
        opened = {
            (item.project_key, item.seat_key): _compose(
                base_url,
                commander,
                item.seat_key,
                "Opened from the list.",
                project_key=item.project_key,
            )
            for item in listed.correspondents
        }
        foreign = _compose(
            base_url,
            commander,
            "shared-seat",
            "Which project?",
            project_key="apex",
        )
        unknown = _compose(
            base_url,
            commander,
            "unregistered-seat",
            "Nobody holds this address.",
            project_key="apex",
        )
        mine = _compose(base_url, commander, listed.sender, "Writing to myself.")
        seatless = seatless_client.list_inbox_correspondents()
        seatless_send = _compose(base_url, unseated, "director", "No seat of my own.")

    assert sorted(opened) == [
        ("ctower", "director"),
        ("ctower", "shared-seat"),
    ]
    assert all(response.status_code in _ACCEPTED_SEND_STATUS for response in opened.values())
    # the grant bounds discovery, not delivery: the address this list withholds is
    # still deliverable, so the picker narrows without the transport changing
    assert foreign.status_code in _ACCEPTED_SEND_STATUS
    assert unknown.status_code == _NOT_FOUND_STATUS
    assert _refusal_code(unknown) == "inbox-recipient-not-found"
    assert mine.status_code == _UNPROCESSABLE_STATUS
    assert _refusal_code(mine) == "inbox-recipient-self"
    # a principal with no seat of its own can address nobody, and is offered nobody
    assert seatless.correspondents == ()
    assert seatless_send.status_code == _UNPROCESSABLE_STATUS
    assert _refusal_code(seatless_send) == "inbox-sender-unaddressable"


def test_naming_a_project_on_the_address_list_answers_only_within_this_seats_grant(
    tenant: TenantFixture,
) -> None:
    """Narrowing the picker to one Project is a scoped read, so it answers under INV-69.

    Naming a Project asks for a subset of what the unnarrowed list already bounds
    to this principal's grants, so the two answers agree about `ctower` and neither
    of them mentions `apex`. They differ in how they say so: the unnarrowed list
    leaves a foreign Project out, while naming one is refused by its own name
    rather than quietly answered empty, so "no addresses there" and "not yours to
    ask about" never look alike.
    """

    _director_id, director = provision_seat(tenant, "director")
    provision_seat(tenant, "shared-seat")
    provision_seat(tenant, "shared-seat", project_key="apex")

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=director) as client,
    ):
        listed = client.list_inbox_correspondents()
        narrowed = client.list_inbox_correspondents(project_key="ctower")
        with pytest.raises(CtowerProblemError) as refusal:
            client.list_inbox_correspondents(project_key="apex")

    offered = [(item.project_key, item.seat_key) for item in listed.correspondents]
    problem = cast(Problem, refusal.value.problem)
    assert ("apex", "shared-seat") not in offered
    assert [(item.project_key, item.seat_key) for item in narrowed.correspondents] == [
        address for address in offered if address[0] == "ctower"
    ]
    assert {item.project_key for item in narrowed.correspondents} == {"ctower"}
    assert (problem.status, problem.code) == (403, "project-scope-denied")
    print(
        "REAL_PROJECT_SCOPED_ADDRESSES "
        f"offered={len(offered)} narrowed={len(narrowed.correspondents)} refused=apex"
    )


def test_the_unnarrowed_address_list_answers_only_within_this_seats_grant(
    tenant: TenantFixture,
) -> None:
    """The closing cell of ticket bf20e6b6: naming no Project still names this seat's.

    `list_inbox_correspondents` used to select every `project_seats` row in the
    tenant and evaluate no grant, so a seat holding one Project's grant was handed
    the rosters of Projects it may not read — and it escaped the INV-69 inventory
    only because its signature names no scope.

    This cell asks the unnarrowed list the question INV-69 asks every other
    Project-scoped read: answer within this principal's own grants. A `ctower`
    seat is never told that `apex` has an engineer in it, and the record's own
    grant — not the request's shape — is what decides that.
    """

    _director_id, director = provision_seat(tenant, "director")
    provision_seat(tenant, "apex-engineer", project_key="apex")

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=director) as client,
    ):
        listed = client.list_inbox_correspondents()

    offered = [(item.project_key, item.seat_key) for item in listed.correspondents]
    print("REAL_UNNARROWED_ADDRESSES offered=" + json.dumps(offered))
    assert ("apex", "apex-engineer") not in offered
    assert {project_key for project_key, _seat_key in offered} <= {"ctower"}


def test_unrestricted_operator_authority_still_reaches_every_registered_project(
    tenant: TenantFixture,
) -> None:
    """The grant bounds the listing; unrestricted authority is bounded by nothing.

    Binding the unnarrowed listing to the caller's grant must not quietly turn the
    operator's own view into one project's. An operator seated in `ctower` is still
    answered for `apex`, because its authority reaches every project the tenant has
    registered a seat in — the same answer the chokepoint gives when that operator
    names `apex` outright.
    """

    provision_seat(tenant, "director")
    provision_seat(tenant, "apex-engineer", project_key="apex")
    _operator_id, operator = provision_seat(tenant, "fleet-operator", kind="operator")

    with (
        running_api(
            tenant.database.runtime_dsn,
            projection_dsn=tenant.database.projection_dsn,
        ) as base_url,
        CtowerClient(base_url, credential=operator) as client,
    ):
        listed = client.list_inbox_correspondents()

    offered = [(item.project_key, item.seat_key) for item in listed.correspondents]
    print("REAL_OPERATOR_ADDRESSES offered=" + json.dumps(offered))
    assert listed.sender == "fleet-operator"
    assert ("apex", "apex-engineer") in offered
    assert ("ctower", "director") in offered

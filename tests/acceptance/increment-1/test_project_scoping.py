"""Three-project Board read-isolation evidence for #185."""

from __future__ import annotations

from typing import cast

from support.project_scoping import _assert_pair_disjoint, _scoped_projection_fixture
from support.tenant_fixture import TenantFixture

from ctower_kernel.projections import BoardQuery
from ctower_kernel.record import RecordProblem


def test_manibo_and_ctower_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "manibo", "ctower")


def test_foreign_project_projection_reads_are_refused(tenant: TenantFixture) -> None:
    projections, scoped_actor, _operator, _manibo_ticket = _scoped_projection_fixture(tenant)

    foreign_board = projections.board(scoped_actor, BoardQuery(project_key="ctower"))
    foreign_cards = getattr(foreign_board, "cards", ())
    assert isinstance(cast(object, foreign_board), RecordProblem), (
        f"HTTP 200 with foreign card(s)={len(foreign_cards)}: {foreign_board.response_payload()}"
    )

    foreign_delivery = projections.project_delivery(scoped_actor, "ctower")
    foreign_rows = getattr(foreign_delivery, "rows", ())
    assert isinstance(cast(object, foreign_delivery), RecordProblem), (
        f"HTTP 200 with foreign delivery row(s)={len(foreign_rows)}: "
        f"{foreign_delivery.response_payload() if foreign_delivery is not None else None}"
    )


def test_granted_project_projection_reads_still_work(tenant: TenantFixture) -> None:
    projections, scoped_actor, operator, manibo_ticket = _scoped_projection_fixture(tenant)

    granted_board = projections.board(scoped_actor, BoardQuery(project_key="manibo"))
    assert not isinstance(granted_board, RecordProblem), granted_board
    assert {card.ticket_id for card in granted_board.cards} == {manibo_ticket}

    granted_delivery = projections.project_delivery(scoped_actor, "manibo")
    assert granted_delivery is not None
    assert not isinstance(granted_delivery, RecordProblem), granted_delivery
    assert granted_delivery.project_key == "manibo"

    operator_board = projections.board(operator, BoardQuery(project_key="ctower"))
    assert not isinstance(cast(object, operator_board), RecordProblem), (
        operator_board.response_payload()
    )


def test_bhloop_and_ctower_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "bh-loop", "ctower")


def test_manibo_and_bhloop_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "manibo", "bh-loop")

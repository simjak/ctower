"""Three-project Board read-isolation evidence for #185."""

from __future__ import annotations

from typing import cast

from support.project_scoping import (
    HTTP_FORBIDDEN,
    _assert_pair_disjoint,
    _scoped_projection_fixture,
)
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


def test_portfolio_board_reads_are_operator_only(tenant: TenantFixture) -> None:
    """Four persisted cells: own Project, foreign Project, and both portfolio reads."""

    projections, scoped_actor, operator, manibo_ticket = _scoped_projection_fixture(tenant)

    own = projections.board(scoped_actor, BoardQuery(project_key="manibo"))
    foreign = projections.board(scoped_actor, BoardQuery(project_key="ctower"))
    operator_portfolio = projections.portfolio_board(operator)
    scoped_portfolio = projections.portfolio_board(scoped_actor)

    assert not isinstance(own, RecordProblem), own
    assert {card.ticket_id for card in own.cards} == {manibo_ticket}
    assert isinstance(cast(object, foreign), RecordProblem), _project_keys(foreign)
    assert not isinstance(operator_portfolio, RecordProblem), operator_portfolio
    assert _project_keys(operator_portfolio) == ("ctower", "manibo")
    assert isinstance(scoped_portfolio, RecordProblem), (
        "a project-scoped non-operator received the portfolio Board: "
        f"projects={_project_keys(scoped_portfolio)}"
    )
    assert scoped_portfolio.code == "project-scope-denied"
    assert scoped_portfolio.status == HTTP_FORBIDDEN


def _project_keys(view: object) -> tuple[str, ...]:
    return tuple(sorted({str(card.project_key) for card in getattr(view, "cards", ())}))


def test_bhloop_and_ctower_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "bh-loop", "ctower")


def test_manibo_and_bhloop_boards_are_disjoint(tenant: TenantFixture) -> None:
    _assert_pair_disjoint(tenant, "manibo", "bh-loop")

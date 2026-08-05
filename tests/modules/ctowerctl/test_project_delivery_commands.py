"""Generic Project Delivery parser and renderer behavior."""

from __future__ import annotations

import argparse
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from ctower_client.models import (
    ProjectDeliveryAssignedSeatAssignment,
    ProjectDeliveryCriteria,
    ProjectDeliveryRow,
    ProjectDeliverySeat,
    ProjectDeliverySlot,
    ProjectDeliverySurfaceDeclaration,
    ProjectDeliveryUnassignedSeatAssignment,
    ProjectDeliveryView,
    SeatCatalogRevision,
    SurfaceDeclarationState,
    SurfaceEnvironmentsField,
    SurfaceIdentityField,
)
from ctowerctl import _migration_commands, interface
from ctowerctl._parser import parse_arguments
from modules.migration._import_vectors import ZERO_DIGEST

__all__: tuple[str, ...] = ()

_NOW = datetime(2026, 7, 25, 12, tzinfo=UTC)


def test_project_delivery_parser_accepts_authored_generic_project_keys() -> None:
    assert _parse_delivery("quarterly-close").project_key == "quarterly-close"
    assert _parse_delivery("a" * 64).project_key == "a" * 64


@pytest.mark.parametrize("project_key", ("my.project", "a" * 100))
def test_project_delivery_parser_refuses_keys_outside_the_authored_contract(
    project_key: str,
) -> None:
    with pytest.raises(ValueError, match="project_key"):
        _parse_delivery(project_key)


def test_project_delivery_renderer_accepts_a_second_project_fixture() -> None:
    view = _ledger_delivery_view()
    rendered = _migration_commands.delivery_text(view)

    assert "company=ledger-co project=quarterly-close" in rendered
    assert all(column in rendered for column in ("CHECKPOINT", "CRITERIA", "SLOTS", "UNRESOLVED"))
    assert "Q3-close.2" in rendered
    assert "2/3" in rendered
    assert "1/3" in rendered
    assert "approval-receipt,archive-proof" in rendered
    assert "ledger:close-run-27,archive:quarter-2026-q3" in rendered
    assert "slot_unfilled:approval-receipt" in rendered

    stream = io.StringIO()
    interface.write_result(_json_arguments(), view, stream)
    payload = json.loads(stream.getvalue())
    assert payload["company_key"] == "ledger-co"
    assert payload["project_key"] == "quarterly-close"
    assert payload["rows"][0]["checkpoint_key"] == "Q3-close.2"
    assert payload["rows"][0]["qualifying_stage_slots_filled"] == 1


def _parse_delivery(project_key: str) -> argparse.Namespace:
    return parse_arguments(
        [
            "--base-url",
            "https://ctower.example",
            "project",
            "delivery",
            "query",
            project_key,
        ]
    )


def _json_arguments() -> argparse.Namespace:
    return argparse.Namespace(
        cli_name="project delivery query",
        project_key="quarterly-close",
        output="json",
    )


def _ledger_delivery_view() -> ProjectDeliveryView:
    return ProjectDeliveryView(
        schema_id="ctower.project-delivery/v1",
        company_key="ledger-co",
        project_key="quarterly-close",
        source_record_position=27,
        projection_record_position=27,
        reconciled_at=_NOW,
        freshness_due_at=_NOW + timedelta(hours=1),
        projection_semantic_digest=ZERO_DIGEST,
        rebuild_generation=1,
        rows=(_ledger_delivery_row(),),
    )


def _undeclared_surface() -> ProjectDeliverySurfaceDeclaration:
    undeclared = SurfaceIdentityField(state=SurfaceDeclarationState.UNDECLARED, identity=None)
    return ProjectDeliverySurfaceDeclaration(
        landing_boundary=undeclared,
        non_production_environments=SurfaceEnvironmentsField(
            state=SurfaceDeclarationState.UNDECLARED, environments=()
        ),
        externally_effective_outcome=undeclared,
    )


def _ledger_delivery_row() -> ProjectDeliveryRow:
    return ProjectDeliveryRow(
        checkpoint_key="Q3-close.2",
        checkpoint_label="Quarter close approval",
        headline_state="blocked",
        underlying_maturity="verified",
        outcome="The quarter close is approved and archived",
        accountable_owner="controller",
        criteria=ProjectDeliveryCriteria(proven=2, declared=3),
        delivery_surface=_undeclared_surface(),
        qualifying_stage_slots_filled=1,
        qualifying_stage_slots_required=3,
        qualifying_stage_unfilled_or_unknown_slot_keys=("approval-receipt", "archive-proof"),
        qualifying_stage_slots=_ledger_delivery_slots(),
        source_watermark=27,
        projection_watermark=27,
        freshness="fresh",
        confidence="STATE_UNKNOWN",
        health="STATE_UNKNOWN",
        durability="STATE_UNKNOWN",
        recovery="STATE_UNKNOWN",
        data_class="STATE_UNKNOWN",
        semantic_digest=ZERO_DIGEST,
        reconciled_at=_NOW,
        freshness_due_at=_NOW + timedelta(hours=1),
        rebuild_generation=1,
        source_ids=("ledger:close-run-27", "archive:quarter-2026-q3"),
        derivation_reasons=(
            "slot_unfilled:approval-receipt",
            "slot_unknown:archive-proof",
            "underlying_maturity:verified",
        ),
    )


def _ledger_delivery_slots() -> tuple[ProjectDeliverySlot, ...]:
    unassigned = ProjectDeliveryUnassignedSeatAssignment(state="unassigned")
    return (
        ProjectDeliverySlot(
            slot_key="close-ledger",
            state="filled",
            assigned_seat=ProjectDeliveryAssignedSeatAssignment(
                state="assigned", seat=_seat("controller", "Controller")
            ),
            signing_seat=_seat("reviewer", "Reviewer"),
        ),
        ProjectDeliverySlot(
            slot_key="approval-receipt",
            state="unfilled",
            assigned_seat=unassigned,
            signing_seat=None,
        ),
        ProjectDeliverySlot(
            slot_key="archive-proof",
            state="unknown",
            assigned_seat=unassigned,
            signing_seat=None,
        ),
    )


def _seat(key: str, label: str) -> ProjectDeliverySeat:
    return ProjectDeliverySeat(
        seat_key=key,
        seat_label=label,
        catalog_revision=SeatCatalogRevision(
            catalog_key="fixture.delivery-seats",
            revision=1,
            content_digest=ZERO_DIGEST,
        ),
    )

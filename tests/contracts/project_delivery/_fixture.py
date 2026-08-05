"""Cross-domain Project Delivery contract fixtures."""

from __future__ import annotations

from typing import Final

__all__ = ["DIGEST", "project_delivery_row", "project_delivery_view"]

DIGEST: Final = "sha256:" + ("0" * 64)


def project_delivery_row() -> dict[str, object]:
    """Return one accounting checkpoint with incomplete qualifying-stage proof."""

    return {
        "checkpoint_key": "Q3-close.2",
        "checkpoint_label": "Quarter close approval",
        "headline_state": "blocked",
        "underlying_maturity": "verified",
        "outcome": "The quarter close is approved and archived",
        "accountable_owner": "controller",
        "criteria": {"proven": 2, "declared": 3},
        "delivery_surface": _undeclared_surface(),
        "qualifying_stage_slots_filled": 1,
        "qualifying_stage_slots_required": 3,
        "qualifying_stage_unfilled_or_unknown_slot_keys": [
            "approval-receipt",
            "archive-proof",
        ],
        "qualifying_stage_slots": _seat_slots(),
        "source_watermark": 27,
        "projection_watermark": 27,
        "freshness": "fresh",
        "confidence": "STATE_UNKNOWN",
        "health": "STATE_UNKNOWN",
        "durability": "STATE_UNKNOWN",
        "recovery": "STATE_UNKNOWN",
        "data_class": "STATE_UNKNOWN",
        "semantic_digest": DIGEST,
        "reconciled_at": "2026-07-25T12:00:00Z",
        "freshness_due_at": "2026-07-25T13:00:00Z",
        "rebuild_generation": 1,
        "source_ids": ["ledger:close-run-27", "archive:quarter-2026-q3"],
        "derivation_reasons": [
            "slot_unfilled:approval-receipt",
            "slot_unknown:archive-proof",
            "underlying_maturity:verified",
        ],
    }


def _undeclared_surface() -> dict[str, object]:
    undeclared_identity = {"state": "undeclared", "identity": None}
    return {
        "landing_boundary": undeclared_identity,
        "non_production_environments": {"state": "undeclared", "environments": []},
        "externally_effective_outcome": undeclared_identity,
    }


def _seat_slots() -> list[dict[str, object]]:
    return [
        {
            "slot_key": "ledger-posted",
            "state": "filled",
            "assigned_seat": {
                "state": "assigned",
                "seat": {
                    "seat_key": "preparer",
                    "seat_label": "Preparer",
                    "catalog_revision": {
                        "catalog_key": "ledger.delivery-seats",
                        "revision": 1,
                        "content_digest": DIGEST,
                    },
                },
            },
            "signing_seat": {
                "seat_key": "approver",
                "seat_label": "Approver",
                "catalog_revision": {
                    "catalog_key": "ledger.delivery-seats",
                    "revision": 1,
                    "content_digest": DIGEST,
                },
            },
        },
        {
            "slot_key": "approval-receipt",
            "state": "unfilled",
            "assigned_seat": {
                "state": "assigned",
                "seat": {
                    "seat_key": "approver",
                    "seat_label": "Approver",
                    "catalog_revision": {
                        "catalog_key": "ledger.delivery-seats",
                        "revision": 1,
                        "content_digest": DIGEST,
                    },
                },
            },
            "signing_seat": None,
        },
        {
            "slot_key": "archive-proof",
            "state": "unknown",
            "assigned_seat": {"state": "unassigned"},
            "signing_seat": None,
        },
    ]


def project_delivery_view(
    row: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return a non-ctower project view with a configurable checkpoint key."""

    return {
        "schema": "ctower.project-delivery/v1",
        "company_key": "ledger-co",
        "project_key": "quarterly-close",
        "source_record_position": 27,
        "projection_record_position": 27,
        "reconciled_at": "2026-07-25T12:00:00Z",
        "freshness_due_at": "2026-07-25T13:00:00Z",
        "projection_semantic_digest": DIGEST,
        "rebuild_generation": 1,
        "rows": [row or project_delivery_row()],
    }

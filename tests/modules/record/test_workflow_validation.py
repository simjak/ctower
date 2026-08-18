"""Kernel record policy for enriched workflow transition provenance."""

from __future__ import annotations

from uuid import UUID

from ctower_kernel.record.events import WorkflowChangedPayload

__all__: tuple[str, ...] = ()


_TICKET_ID = UUID("00000000-0000-7000-8000-000000000001")


def test_pre_enrichment_transition_payload_is_legal_to_reconstruct_on_read() -> None:
    payload = WorkflowChangedPayload(
        operation="transition",
        ticket_id=_TICKET_ID,
        workflow_ref="fixture.workflow@1",
        workflow_version=1,
        stage="frame",
        lifecycle_facts=(),
    )

    assert payload.source_stage == ""
    assert payload.evaluation_ref == ""

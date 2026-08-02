"""Strict decoding for catalog-selected project event payloads."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from ctower_kernel.record.events import (
    EventKind,
    ProjectEventPayload,
    ProofChangedPayload,
    WorkflowChangedPayload,
    ticket_payload_from_mapping,
)
from ctower_kernel.record.work_events import WorkChangedPayload

__all__: tuple[str, ...] = ()


def project_event_payload_from_mapping(
    kind: EventKind,
    payload: Mapping[str, object],
    *,
    legacy_project_key: str,
) -> ProjectEventPayload:
    """Rebuild one strict project-feed payload selected by catalog kind."""

    if kind in {
        EventKind.TICKET_CREATED,
        EventKind.CUSTODY_TRANSFERRED,
        EventKind.TICKET_COMMENT_ADDED,
    }:
        return ticket_payload_from_mapping(
            kind,
            payload,
            legacy_project_key=legacy_project_key,
        )
    if kind is EventKind.WORK_CHANGED:
        return _work_payload(payload)
    if kind is EventKind.PROOF_CHANGED:
        return _proof_payload(payload)
    if kind is EventKind.WORKFLOW_CHANGED:
        return _workflow_payload(payload)
    raise ValueError(f"{kind.value} is not project-feed scoped by the event catalog")


def _work_payload(payload: Mapping[str, object]) -> WorkChangedPayload:
    _require_fields(payload, {"data", "operation", "ticket_id", "work_version"})
    data = payload["data"]
    if not isinstance(data, Mapping):
        raise TypeError("Work event data must be an object")
    return WorkChangedPayload(
        operation=_string(payload["operation"], "operation"),
        ticket_id=_uuid(payload["ticket_id"], "ticket_id"),
        work_version=_integer(payload["work_version"], "work_version"),
        data=data,
    )


def _proof_payload(payload: Mapping[str, object]) -> ProofChangedPayload:
    _require_fields(
        payload,
        {
            "candidate_digest",
            "invalidated_evidence_ids",
            "invalidated_verdict_ids",
            "operation",
            "proof_version",
            "ticket_id",
        },
    )
    return ProofChangedPayload(
        operation=_string(payload["operation"], "operation"),
        ticket_id=_uuid(payload["ticket_id"], "ticket_id"),
        proof_version=_integer(payload["proof_version"], "proof_version"),
        candidate_digest=_string(payload["candidate_digest"], "candidate_digest"),
        invalidated_evidence_ids=_uuid_tuple(
            payload["invalidated_evidence_ids"], "invalidated_evidence_ids"
        ),
        invalidated_verdict_ids=_uuid_tuple(
            payload["invalidated_verdict_ids"], "invalidated_verdict_ids"
        ),
    )


def _workflow_payload(payload: Mapping[str, object]) -> WorkflowChangedPayload:
    _require_fields(
        payload,
        {
            "lifecycle_facts",
            "operation",
            "stage",
            "ticket_id",
            "workflow_ref",
            "workflow_version",
        },
    )
    lifecycle = payload["lifecycle_facts"]
    if not isinstance(lifecycle, list):
        raise TypeError("lifecycle_facts must be an array")
    return WorkflowChangedPayload(
        operation=_string(payload["operation"], "operation"),
        ticket_id=_uuid(payload["ticket_id"], "ticket_id"),
        workflow_ref=_string(payload["workflow_ref"], "workflow_ref"),
        workflow_version=_integer(payload["workflow_version"], "workflow_version"),
        stage=_string(payload["stage"], "stage"),
        lifecycle_facts=tuple(_string(item, "lifecycle_facts item") for item in lifecycle),
    )


def _require_fields(payload: Mapping[str, object], expected: set[str]) -> None:
    if set(payload) != expected:
        raise ValueError("event payload fields do not match the authored variant")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _uuid(value: object, label: str) -> UUID:
    return UUID(_string(value, label))


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    return value


def _uuid_tuple(value: object, label: str) -> tuple[UUID, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be an array")
    return tuple(_uuid(item, f"{label} item") for item in value)

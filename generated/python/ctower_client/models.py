"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:c7720459fe13da7954fd47531b54db7cee8e84b2df15c9a18ed354c1f0f768d3
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BootstrapReceipt",
    "BootstrapRequest",
    "CustodyTransferRequest",
    "CustodyTransferredPayload",
    "DurabilityState",
    "Priority",
    "Problem",
    "SourceReference",
    "TicketCommandResult",
    "TicketCreateRequest",
    "TicketCreatedPayload",
    "TicketResource",
    "TimelineEvent",
    "TimelineResponse",
]


class _BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)


class DurabilityState(StrEnum):
    DURABILITY_PENDING = "durability_pending"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class SourceReference(_BoundaryModel):
    kind: Annotated[str, Field(min_length=1, max_length=64)]
    ref: Annotated[str, Field(min_length=1, max_length=256)]


class BootstrapRequest(_BoundaryModel):
    commander_name: Annotated[str, Field(min_length=1, max_length=120)]
    commander_vault_ref: Annotated[str, Field(pattern=r"^vault-ref:[a-z0-9/_-]+$")]
    operator_credential_ref: Annotated[str, Field(pattern=r"^credential-ref:[a-z0-9/_-]+$")]
    operator_name: Annotated[str, Field(min_length=1, max_length=120)]
    operator_vault_ref: Annotated[str, Field(pattern=r"^vault-ref:[a-z0-9/_-]+$")]
    tenant_name: Annotated[str, Field(min_length=1, max_length=120)]
    tenant_slug: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}$")]


class BootstrapReceipt(_BoundaryModel):
    command_id: UUID
    commander_id: UUID
    durability_state: DurabilityState
    event_ids: tuple[UUID, ...]
    operator_id: UUID
    receipt_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    tenant_id: UUID


class TicketCreateRequest(_BoundaryModel):
    initial_custodian_id: UUID
    priority: Priority
    source: SourceReference
    title: Annotated[str, Field(min_length=1, max_length=200)]


class CustodyTransferRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    from_custodian_id: UUID
    protected_transfer: bool
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    to_custodian_id: UUID


class TicketResource(_BoundaryModel):
    created_at: datetime
    custodian_id: UUID
    durability_state: DurabilityState
    priority: Priority
    source: SourceReference
    ticket_id: UUID
    title: str
    version: Annotated[int, Field(ge=1)]


class TicketCommandResult(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: tuple[UUID, ...]
    ticket: TicketResource


class TicketCreatedPayload(_BoundaryModel):
    custodian_id: UUID
    priority: Priority
    source: SourceReference
    title: str


class CustodyTransferredPayload(_BoundaryModel):
    from_custodian_id: UUID
    reason: str
    to_custodian_id: UUID


class TimelineEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_id: UUID
    kind: Literal["ticket.created", "ticket.custody_transferred"]
    occurred_at: datetime
    payload: TicketCreatedPayload | CustodyTransferredPayload
    sequence: Annotated[int, Field(ge=1)]


class TimelineResponse(_BoundaryModel):
    durability_state: DurabilityState
    events: tuple[TimelineEvent, ...]
    ticket_id: UUID


class Problem(_BoundaryModel):
    code: Literal[
        "bootstrap-consumed",
        "bootstrap-expired",
        "bootstrap-origin",
        "idempotency-conflict",
        "tenant-scope-denied",
        "unauthorized",
        "version-conflict",
    ]
    command_id: UUID | None = None
    current_version: Annotated[int, Field(ge=1)] | None = None
    detail: str
    status: Annotated[int, Field(ge=400, le=599)]
    title: str
    type_uri: str = Field(alias="type", serialization_alias="type")

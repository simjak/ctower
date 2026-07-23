"""Private strict encrypted-payload schemas for spool recovery and replay."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ctowerctl.spool._redaction import JsonObject

__all__ = [
    "AcceptedReceipt",
    "CommandEnvelope",
    "CompactionAnchor",
    "Disposition",
    "Head",
    "Metadata",
    "QuarantineReceipt",
]


class _DiskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Metadata(_DiskPayload):
    format_version: Literal[1]
    spool_uuid: str
    key_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    origin_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Head(_DiskPayload):
    format_version: Literal[1]
    sequence: Annotated[int, Field(ge=0)]
    record_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CommandEnvelope(_DiskPayload):
    schema_version: Literal[1]
    operation_id: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9]{0,127}$")]
    path_parameters: JsonObject
    request_body: JsonObject
    command_id: str
    origin_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    enqueued_at: str
    expires_at: str
    semantic_request_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class AcceptedReceipt(_DiskPayload):
    schema_version: Literal[1]
    command_sequence: Annotated[int, Field(ge=1)]
    command_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    command_id: str
    status_code: Annotated[int, Field(ge=200, le=299)]
    durability_state: Literal["accepted"]
    response: JsonObject | None
    response_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    event_ids: tuple[str, ...]
    acceptance_position: str | None
    accepted_at: str


class QuarantineReceipt(_DiskPayload):
    schema_version: Literal[1]
    command_sequence: Annotated[int, Field(ge=1)]
    command_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    reason_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    response_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    quarantined_at: str


class Disposition(_DiskPayload):
    schema_version: Literal[1]
    command_sequence: Annotated[int, Field(ge=1)]
    command_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    action: Literal["retry", "discard"]
    reason_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    recorded_at: str


class CompactionAnchor(_DiskPayload):
    schema_version: Literal[1]
    covered_from: Annotated[int, Field(ge=1)]
    covered_through: Annotated[int, Field(ge=1)]
    terminal_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    created_at: str

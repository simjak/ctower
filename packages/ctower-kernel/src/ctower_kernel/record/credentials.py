"""Typed project-seat credential commands, receipts, and event payloads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

__all__ = [
    "CredentialScope",
    "SeatCredentialIssue",
    "SeatCredentialIssuedPayload",
    "SeatCredentialReceipt",
    "SeatCredentialRevocation",
    "SeatCredentialRevokedPayload",
]

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_SEAT_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_DIGEST_BYTES = 32
_MAX_CREDENTIAL_REF = 512
_MAX_DISPLAY_NAME = 120
_MAX_REASON = 500


class CredentialScope(StrEnum):
    """The only mutation capabilities a project-seat bearer may receive."""

    CAPTURE = "capture"
    TRANSITION = "transition"
    EVIDENCE = "evidence"


@dataclass(frozen=True, slots=True)
class SeatCredentialIssue:
    """Operator request to bind one digest/reference to a stable project seat."""

    client_command_id: UUID
    credential_digest: bytes
    credential_ref: str
    display_name: str
    project_key: str
    scopes: tuple[CredentialScope, ...]
    seat_key: str

    def __post_init__(self) -> None:
        _validate_issue_authority(self)
        _validate_issue_contract(self)
        _validate_issue_scopes(self)

    def request_payload(self) -> dict[str, object]:
        """Return canonical semantics without bearer plaintext."""

        return {
            "credential_digest": f"sha256:{self.credential_digest.hex()}",
            "credential_ref": self.credential_ref,
            "display_name": self.display_name,
            "project_key": self.project_key,
            "scopes": [scope.value for scope in self.scopes],
            "seat_key": self.seat_key,
        }


@dataclass(frozen=True, slots=True)
class SeatCredentialRevocation:
    """Operator request to revoke one exact issued credential."""

    client_command_id: UUID
    credential_id: UUID
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.credential_id, UUID):
            raise TypeError("seat credential revocation IDs must be UUIDs")
        if not 1 <= len(self.reason) <= _MAX_REASON:
            raise ValueError("seat credential revocation reason is outside the authored contract")

    def request_payload(self) -> dict[str, object]:
        return {
            "credential_id": str(self.credential_id),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SeatCredentialReceipt:
    """Public receipt for one issuance or revocation event."""

    command_id: UUID
    credential_id: UUID
    event_ids: tuple[UUID, ...]
    principal_id: UUID
    project_key: str
    scopes: tuple[CredentialScope, ...]
    seat_key: str
    state: Literal["active", "revoked"]

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "credential_id": str(self.credential_id),
            "durability_state": "durability_pending",
            "event_ids": [str(event_id) for event_id in self.event_ids],
            "principal_id": str(self.principal_id),
            "project_key": self.project_key,
            "scopes": [scope.value for scope in self.scopes],
            "seat_key": self.seat_key,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class SeatCredentialIssuedPayload:
    """Canonical secret-free issuance event payload."""

    credential_id: UUID
    credential_ref: str
    principal_id: UUID
    project_key: str
    scopes: tuple[CredentialScope, ...]
    seat_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.credential_id, UUID) or not isinstance(self.principal_id, UUID):
            raise TypeError("seat credential event IDs must be UUIDs")
        if not 1 <= len(self.credential_ref) <= _MAX_CREDENTIAL_REF:
            raise ValueError("seat credential reference is outside the event contract")
        if _PROJECT_KEY.fullmatch(self.project_key) is None:
            raise ValueError("seat credential event project is invalid")
        if _SEAT_KEY.fullmatch(self.seat_key) is None:
            raise ValueError("seat credential event seat is invalid")
        if not self.scopes or len(set(self.scopes)) != len(self.scopes):
            raise ValueError("seat credential event scopes must be nonempty and unique")

    def to_mapping(self) -> dict[str, object]:
        return {
            "credential_id": str(self.credential_id),
            "credential_ref": self.credential_ref,
            "principal_id": str(self.principal_id),
            "project_key": self.project_key,
            "scopes": [scope.value for scope in self.scopes],
            "seat_key": self.seat_key,
        }


@dataclass(frozen=True, slots=True)
class SeatCredentialRevokedPayload:
    """Canonical revocation event payload without credential material."""

    credential_id: UUID
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.credential_id, UUID):
            raise TypeError("revoked credential ID must be a UUID")
        if not 1 <= len(self.reason) <= _MAX_REASON:
            raise ValueError("revocation reason is outside the event contract")

    def to_mapping(self) -> dict[str, object]:
        return {
            "credential_id": str(self.credential_id),
            "reason": self.reason,
        }


def _validate_issue_authority(command: SeatCredentialIssue) -> None:
    if not isinstance(command.client_command_id, UUID):
        raise TypeError("seat credential command ID must be a UUID")
    if (
        not isinstance(command.credential_digest, bytes)
        or len(command.credential_digest) != _DIGEST_BYTES
    ):
        raise ValueError("seat credential digest must contain exactly 32 bytes")


def _validate_issue_contract(command: SeatCredentialIssue) -> None:
    if not 1 <= len(command.credential_ref) <= _MAX_CREDENTIAL_REF:
        raise ValueError("seat credential reference is outside the authored contract")
    if not 1 <= len(command.display_name) <= _MAX_DISPLAY_NAME:
        raise ValueError("seat display name is outside the authored contract")
    if _PROJECT_KEY.fullmatch(command.project_key) is None:
        raise ValueError("seat project key is outside the authored contract")
    if _SEAT_KEY.fullmatch(command.seat_key) is None:
        raise ValueError("seat key is outside the authored contract")


def _validate_issue_scopes(command: SeatCredentialIssue) -> None:
    if not command.scopes or len(set(command.scopes)) != len(command.scopes):
        raise ValueError("seat credential scopes must be nonempty and unique")
    if not all(isinstance(scope, CredentialScope) for scope in command.scopes):
        raise TypeError("seat credential scopes must use the authored enum")

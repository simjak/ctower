"""Small public Interface for atomic Record commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

__all__ = ["BootstrapCommand", "BootstrapReceipt", "BootstrapRecord", "RecordProblem"]


@dataclass(frozen=True, slots=True)
class BootstrapCommand:
    """Validated first-tenant values entering the trusted kernel."""

    client_command_id: UUID
    commander_name: str
    commander_vault_ref: str
    operator_credential_ref: str
    operator_name: str
    operator_vault_ref: str
    tenant_name: str
    tenant_slug: str

    def request_payload(self) -> dict[str, str]:
        """Return the cross-process body without transport authority."""

        payload = asdict(self)
        payload.pop("client_command_id")
        return {str(key): str(value) for key, value in payload.items()}


@dataclass(frozen=True, slots=True)
class BootstrapReceipt:
    """Committed first-tenant receipt returned on success and exact replay."""

    command_id: UUID
    commander_id: UUID
    event_ids: tuple[UUID, ...]
    operator_id: UUID
    receipt_digest: str
    tenant_id: UUID

    def response_payload(self) -> dict[str, object]:
        """Return the exact authoritative HTTP response shape."""

        return {
            "command_id": str(self.command_id),
            "commander_id": str(self.commander_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "operator_id": str(self.operator_id),
            "receipt_digest": self.receipt_digest,
            "tenant_id": str(self.tenant_id),
        }


@dataclass(frozen=True, slots=True)
class RecordProblem:
    """Stable RFC 9457 failure with no partial Record mutation."""

    code: str
    detail: str
    status: int
    title: str
    command_id: UUID | None = None

    def response_payload(self) -> dict[str, object]:
        """Return a minimal RFC 9457 object."""

        payload: dict[str, object] = {
            "code": self.code,
            "detail": self.detail,
            "status": self.status,
            "title": self.title,
            "type": f"https://ctower.dev/problems/{self.code}",
        }
        if self.command_id is not None:
            payload["command_id"] = str(self.command_id)
        return payload


class BootstrapRecord(Protocol):
    """Record authority needed by the one-use Access ceremony."""

    def bootstrap_first_tenant(
        self,
        command: BootstrapCommand,
        *,
        capability_digest: bytes,
        request_digest: bytes,
        origin: str,
        now: datetime,
    ) -> BootstrapReceipt | RecordProblem:
        """Atomically commit or refuse one first-tenant command."""

        ...

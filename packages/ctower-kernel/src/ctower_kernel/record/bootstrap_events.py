"""Strict first-tenant bootstrap event payload."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = ["BootstrapCreatedPayload"]


@dataclass(frozen=True, slots=True)
class BootstrapCreatedPayload:
    commander_id: UUID
    commander_vault_ref: str
    operator_credential_ref: str
    operator_id: UUID
    operator_vault_ref: str
    tenant_id: UUID
    tenant_slug: str

    def __post_init__(self) -> None:
        _require_uuid_fields(
            self,
            ("commander_id", "operator_id", "tenant_id"),
        )
        _bounded("commander_vault_ref", self.commander_vault_ref, minimum=1)
        _bounded("operator_credential_ref", self.operator_credential_ref, minimum=1)
        _bounded("operator_vault_ref", self.operator_vault_ref, minimum=1)
        _bounded("tenant_slug", self.tenant_slug, minimum=2, maximum=63)

    def to_mapping(self) -> dict[str, object]:
        return {
            "commander_id": str(self.commander_id),
            "commander_vault_ref": self.commander_vault_ref,
            "operator_credential_ref": self.operator_credential_ref,
            "operator_id": str(self.operator_id),
            "operator_vault_ref": self.operator_vault_ref,
            "tenant_id": str(self.tenant_id),
            "tenant_slug": self.tenant_slug,
        }


def _bounded(label: str, value: object, *, minimum: int, maximum: int | None = None) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise ValueError(f"{label} is outside the authored event contract")


def _require_uuid_fields(value: object, names: tuple[str, ...]) -> None:
    for name in names:
        if not isinstance(getattr(value, name), UUID):
            raise TypeError(f"{name} must be a UUID")

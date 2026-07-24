"""Real-Postgres CompanyBundle support without provider or network dependencies."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from ruamel.yaml import YAML

from ctower_kernel.catalog import CompanyBundle
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.objects import StoredObject
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.telemetry import TelemetryContext

ROOT = Path(__file__).parents[4]

__all__ = [
    "FileSchemas",
    "MemoryObjectStore",
    "actor_for",
    "minimal_bundle",
    "telemetry_for",
]


class FileSchemas:
    def __init__(self) -> None:
        self._schemas = _load_schemas()

    def schema_for(self, schema_ref: str) -> dict[str, JsonValue] | None:
        return self._schemas.get(schema_ref)


class MemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        del tenant_id
        self.objects[artifact_digest] = content
        now = datetime(2026, 7, 24, tzinfo=UTC)
        return StoredObject(
            artifact_digest=artifact_digest,
            object_key="catalog/" + artifact_digest,
            object_version="version-1",
            ciphertext_sha256="sha256:" + "1" * 64,
            key_reference=key_reference,
            key_version="version-1",
            wrapped_key_sha256="sha256:" + "2" * 64,
            uploaded_at=now,
            verified_at=now,
        )

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        del tenant_id
        return self.objects[receipt.artifact_digest]

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        del tenant_id
        self.objects.pop(receipt.artifact_digest)


def minimal_bundle() -> CompanyBundle:
    raw = cast(
        dict[str, JsonValue],
        YAML(typ="safe", pure=True).load(
            (ROOT / "company/company.bundle.yaml").read_text(encoding="utf-8")
        ),
    )
    return CompanyBundle.model_validate_json(json.dumps(raw))


def actor_for(tenant_id: UUID, principal_id: UUID) -> Actor:
    return Actor(
        principal_id=principal_id,
        tenant_id=tenant_id,
        kind=PrincipalKind.OPERATOR,
    )


def telemetry_for(actor: Actor, command_id: UUID) -> TelemetryContext:
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="1" * 32,
        span_id="2" * 16,
        trace_flags=1,
        correlation_id=str(command_id),
        causation_id=str(command_id),
        tenant_id=str(actor.tenant_id),
        actor_id=str(actor.principal_id),
        command_id=str(command_id),
    )


def _load_schemas() -> dict[str, dict[str, JsonValue]]:
    schemas: dict[str, dict[str, JsonValue]] = {}
    for path in (ROOT / "contracts").rglob("*.schema.json"):
        raw = cast(dict[str, JsonValue], json.loads(path.read_text(encoding="utf-8")))
        properties = raw.get("properties")
        if not isinstance(properties, dict):
            continue
        schema_field = properties.get("schema")
        if not isinstance(schema_field, dict):
            continue
        schema_ref = schema_field.get("const")
        if isinstance(schema_ref, str):
            schemas[schema_ref] = raw
    return schemas

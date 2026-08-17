"""Real-Postgres CompanyBundle support without provider or network dependencies."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from ruamel.yaml import YAML

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.catalog.interface import BundleActionKind, JsonValue
from ctower_kernel.objects import ObjectIntegrityError, StoredObject
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.telemetry import TelemetryContext

ROOT = Path(__file__).parents[4]

__all__ = [
    "FileSchemas",
    "InterruptingObjectStore",
    "MemoryObjectStore",
    "SimulatedProcessLoss",
    "activate_project_prefixes",
    "actor_for",
    "apply_initial_bundle",
    "assert_command_replay_precedes_adapters",
    "assert_locked_plan_refusals_precede_adapters",
    "assert_removal_refusal_precedes_adapters",
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
        self.receipts: dict[str, StoredObject] = {}
        self.put_attempts = 0
        self.read_attempts = 0
        self.erase_attempts = 0
        self.write_count = 0

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        del tenant_id
        self.put_attempts += 1
        existing = self.receipts.get(artifact_digest)
        if existing is not None:
            if self.objects[artifact_digest] != content:
                raise ObjectIntegrityError("existing immutable object bytes differ")
            if existing.key_reference != key_reference:
                raise ObjectIntegrityError("existing immutable object receipt differs")
            return existing
        self.objects[artifact_digest] = content
        now = datetime(2026, 7, 24, tzinfo=UTC)
        receipt = StoredObject(
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
        self.receipts[artifact_digest] = receipt
        self.write_count += 1
        return receipt

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        del tenant_id
        self.read_attempts += 1
        return self.objects[receipt.artifact_digest]

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        del tenant_id
        self.erase_attempts += 1
        self.objects.pop(receipt.artifact_digest)
        self.receipts.pop(receipt.artifact_digest)


class SimulatedProcessLoss(BaseException):
    """A process disappears after its final external payload write."""


class InterruptingObjectStore(MemoryObjectStore):
    def __init__(self, interrupt_after: int) -> None:
        super().__init__()
        self.interrupt_after = interrupt_after
        self.armed = True

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        receipt = super().put_verified(
            tenant_id,
            artifact_digest,
            content,
            key_reference=key_reference,
        )
        if self.armed and self.write_count == self.interrupt_after:
            self.armed = False
            raise SimulatedProcessLoss
        return receipt


def activate_project_prefixes(runtime_dsn: str, tenant_id: UUID, operator_id: UUID) -> None:
    """Materialize the authored Project prefixes so capture assigns a real display key."""

    catalog = PostgresCatalog(
        runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 8, 17, tzinfo=UTC),
    )
    apply_initial_bundle(catalog, actor_for(tenant_id, operator_id), minimal_bundle())


def apply_initial_bundle(
    catalog: PostgresCatalog,
    actor: Actor,
    bundle: CompanyBundle,
) -> tuple[CompanyBundleApply, CompanyBundleCommandResult]:
    first_plan = catalog.plan(actor, bundle)
    assert not isinstance(first_plan, CatalogProblem)
    command_id = uuid4()
    command = CompanyBundleApply(
        client_command_id=command_id,
        bundle=bundle,
        expected_active_version=0,
        plan_digest=first_plan.plan_digest,
    )
    first = catalog.apply(
        actor,
        command,
        telemetry=telemetry_for(actor, command_id),
    )
    assert isinstance(first, CompanyBundleCommandResult)
    return command, first


def assert_command_replay_precedes_adapters(
    catalog: PostgresCatalog,
    actor: Actor,
    command: CompanyBundleApply,
    first: CompanyBundleCommandResult,
    store: MemoryObjectStore,
) -> None:
    calls = _adapter_calls(store)
    replay = catalog.apply(
        actor,
        command,
        telemetry=telemetry_for(actor, command.client_command_id),
    )
    assert _adapter_calls(store) == calls
    assert replay == first
    conflicting = catalog.apply(
        actor,
        command.model_copy(update={"expected_active_version": 1}),
        telemetry=telemetry_for(actor, command.client_command_id),
    )
    assert _adapter_calls(store) == calls
    assert isinstance(conflicting, CatalogProblem)
    assert conflicting.code == "idempotency-conflict"


def assert_locked_plan_refusals_precede_adapters(
    catalog: PostgresCatalog,
    actor: Actor,
    bundle: CompanyBundle,
    store: MemoryObjectStore,
) -> None:
    changed = bundle.model_copy(
        update={"company": bundle.company.model_copy(update={"display_name": "Ctower changed"})}
    )
    changed_plan = catalog.plan(actor, changed)
    assert not isinstance(changed_plan, CatalogProblem)
    writes = _write_calls(store)
    stale_id, invalid_id = uuid4(), uuid4()
    stale = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=stale_id,
            bundle=changed,
            expected_active_version=0,
            plan_digest=changed_plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, stale_id),
    )
    assert _write_calls(store) == writes
    assert isinstance(stale, CatalogProblem)
    assert stale.code == "bundle-base-conflict"
    invalid_plan = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=invalid_id,
            bundle=changed,
            expected_active_version=1,
            plan_digest="sha256:" + "0" * 64,
        ),
        telemetry=telemetry_for(actor, invalid_id),
    )
    assert _write_calls(store) == writes
    assert isinstance(invalid_plan, CatalogProblem)
    assert invalid_plan.code == "bundle-plan-mismatch"


def assert_removal_refusal_precedes_adapters(
    catalog: PostgresCatalog,
    actor: Actor,
    bundle: CompanyBundle,
    store: MemoryObjectStore,
) -> None:
    removal = bundle.model_copy(
        update={
            "resources": tuple(
                resource
                for resource in bundle.resources
                if resource.component.key != "local.process"
            )
        }
    )
    removal_plan = catalog.plan(actor, removal)
    assert not isinstance(removal_plan, CatalogProblem)
    assert BundleActionKind.DEPRECATE in {action.kind for action in removal_plan.actions}
    writes = _write_calls(store)
    removal_id = uuid4()
    unsupported = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=removal_id,
            bundle=removal,
            expected_active_version=1,
            plan_digest=removal_plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, removal_id),
    )
    assert _write_calls(store) == writes
    assert isinstance(unsupported, CatalogProblem)
    assert unsupported.code == "bundle-compatibility-refused"


def _adapter_calls(store: MemoryObjectStore) -> tuple[int, int, int, int]:
    return (
        store.put_attempts,
        store.read_attempts,
        store.erase_attempts,
        store.write_count,
    )


def _write_calls(store: MemoryObjectStore) -> tuple[int, int]:
    return store.put_attempts, store.write_count


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

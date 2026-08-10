"""Catalog-pinned static composition for provider-neutral issue connectors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from ctower_api.connectors import CONNECTOR_REGISTRATIONS
from ctower_api.connectors.registry import RuntimeConnectorRegistration
from ctower_client import CompanyBundleExportResult, ComponentKind
from ctower_kernel.board_context import BoardContextFacts
from ctower_kernel.board_context.postgres import PostgresBoardContextFacts
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import (
    ConnectorRegistration,
    ConnectorSyncBatch,
    IssueConnector,
    IssueConnectorService,
)
from ctower_kernel.integrations.postgres import PostgresConnectorStore
from ctower_kernel.record import Actor
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Intake

__all__ = ["ConnectorLoop", "build_active_connector_loops", "build_connector_loop"]


@dataclass(frozen=True, slots=True)
class ConnectorLoop:
    """One standing service pinned to one immutable connector registration."""

    service: IssueConnectorService
    actor: Actor
    registration: ConnectorRegistration

    def tick(self) -> ConnectorSyncBatch:
        return self.service.tick(self.actor, self.registration)


def build_active_connector_loops(
    catalog_export: CompanyBundleExportResult,
    *,
    actor: Actor,
    runtime_dsn: str,
    resolve_secret: Callable[[str], str],
) -> tuple[ConnectorLoop, ...]:
    """Compose every supported active registration independently."""

    runtime_bindings = {
        item.name
        for item in catalog_export.bundle.secret_binding_refs
        if item.reference_class == "runtime-binding"
    }
    store = PostgresConnectorStore(runtime_dsn)
    loops: list[ConnectorLoop] = []
    for resource in catalog_export.bundle.resources:
        component = resource.component
        payload = resource.payload
        if component.kind is not ComponentKind.INTEGRATION:
            continue
        adapter_kind = payload.get("adapter")
        if not isinstance(adapter_kind, str):
            continue
        factory = CONNECTOR_REGISTRATIONS.get(adapter_kind)
        if factory is None:
            raise RuntimeError(f"active connector adapter is unsupported: {adapter_kind}")
        if component.schema_ref != factory.schema_ref:
            raise RuntimeError("active connector schema does not match its static registration")
        if payload.get("key") != component.key:
            raise RuntimeError("active connector payload key does not match its Catalog component")
        runtime = _pinned_runtime(
            actor,
            store,
            registration_key=component.key,
            revision_digest=component.content_digest,
            payload=payload,
            parse=factory.from_catalog,
        )
        if runtime.token_binding not in runtime_bindings:
            raise RuntimeError("active connector credential binding is not declared for deployment")
        loops.append(
            build_connector_loop(
                runtime,
                connector=runtime.build(resolve_secret),
                actor=actor,
                runtime_dsn=runtime_dsn,
            )
        )
    if not loops:
        raise RuntimeError("deployment requires at least one active issue connector")
    return tuple(loops)


def _pinned_runtime(
    actor: Actor,
    store: PostgresConnectorStore,
    *,
    registration_key: str,
    revision_digest: str,
    payload: dict[str, object],
    parse: Callable[..., RuntimeConnectorRegistration],
) -> RuntimeConnectorRegistration:
    revision_id = store.active_revision_id(
        actor,
        registration_key=registration_key,
        revision_digest=revision_digest,
    )
    if revision_id is None:
        raise RuntimeError("active connector Catalog revision identity is unavailable")
    runtime = parse(
        cast(dict[str, JsonValue], payload),
        revision_id=revision_id,
        revision_digest=revision_digest,
    )
    registration = runtime.registration
    if (
        registration.registration_key != registration_key
        or registration.revision_id != revision_id
        or registration.revision_digest != revision_digest
    ):
        raise RuntimeError("connector parser changed its pinned Catalog identity")
    return runtime


def build_connector_loop(
    runtime: RuntimeConnectorRegistration,
    *,
    connector: IssueConnector,
    actor: Actor,
    runtime_dsn: str,
) -> ConnectorLoop:
    """Compose one adapter with only public kernel Interfaces."""

    record = PostgresRecord(runtime_dsn)
    service = IssueConnectorService(
        connector,
        PostgresConnectorStore(runtime_dsn),
        Intake(record),
        record,
        record.event_audit,
        BoardContextFacts(PostgresBoardContextFacts(runtime_dsn)),
    )
    return ConnectorLoop(service, actor, runtime.registration)

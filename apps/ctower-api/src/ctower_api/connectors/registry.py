"""Closed first-party connector registry; no dynamic loading or entry points."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from ctower_api.connectors.github.registration import GitHubRuntimeRegistration
from ctower_api.connectors.gitlab.registration import GitLabRuntimeRegistration
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import ConnectorRegistration, IssueConnector

__all__ = ["CONNECTOR_REGISTRATIONS", "ConnectorFactory", "RuntimeConnectorRegistration"]


class RuntimeConnectorRegistration(Protocol):
    @property
    def token_binding(self) -> str: ...

    @property
    def registration(self) -> ConnectorRegistration: ...

    def build(self, resolve_secret: Callable[[str], str]) -> IssueConnector: ...


class _RegistrationParser(Protocol):
    def __call__(
        self,
        payload: dict[str, JsonValue],
        *,
        revision_id: UUID,
        revision_digest: str,
    ) -> RuntimeConnectorRegistration: ...


@dataclass(frozen=True, slots=True)
class ConnectorFactory:
    """One statically registered, typed Catalog-to-runtime parser."""

    adapter_kind: str
    schema_ref: str
    from_catalog: _RegistrationParser


def _closed_registry(*factories: ConnectorFactory) -> Mapping[str, ConnectorFactory]:
    kinds = tuple(factory.adapter_kind for factory in factories)
    schemas = tuple(factory.schema_ref for factory in factories)
    if len(set(kinds)) != len(kinds):
        raise RuntimeError("connector registry repeats an adapter kind")
    if len(set(schemas)) != len(schemas):
        raise RuntimeError("connector registry repeats a schema identifier")
    return MappingProxyType({factory.adapter_kind: factory for factory in factories})


CONNECTOR_REGISTRATIONS: Mapping[str, ConnectorFactory] = _closed_registry(
    ConnectorFactory(
        adapter_kind=GitLabRuntimeRegistration.adapter_kind,
        schema_ref=GitLabRuntimeRegistration.schema_ref,
        from_catalog=GitLabRuntimeRegistration.from_catalog,
    ),
    ConnectorFactory(
        adapter_kind=GitHubRuntimeRegistration.adapter_kind,
        schema_ref=GitHubRuntimeRegistration.schema_ref,
        from_catalog=GitHubRuntimeRegistration.from_catalog,
    ),
)

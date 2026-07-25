"""Postgres Adapter for the universal Catalog and CompanyBundle authority."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.catalog._canonical import canonical_bytes
from ctower_kernel.catalog._postgres_apply import apply_bundle
from ctower_kernel.catalog._postgres_read import load_active_catalog, tenant_key
from ctower_kernel.catalog.interface import (
    BundleValidation,
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    CompanyBundleExport,
    CompanyBundlePlan,
    SchemaCatalog,
)
from ctower_kernel.catalog.object_interface import CatalogObjectError
from ctower_kernel.catalog.service import CatalogPayloadStager, CatalogPolicy
from ctower_kernel.objects import ObjectStore
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.transaction import recover_ambiguous_commit
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__ = ["PostgresCatalog"]

_SERIALIZATION_ATTEMPTS = 3


class PostgresCatalog:
    """Authenticated Catalog policy plus serializable immutable persistence."""

    def __init__(
        self,
        dsn: str,
        schemas: SchemaCatalog,
        store: ObjectStore,
        *,
        key_reference: str,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._dsn = dsn
        self._policy = CatalogPolicy(schemas)
        self._store = store
        self._stager = CatalogPayloadStager(store, key_reference=key_reference)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def validate(self, actor: Actor, bundle: CompanyBundle) -> BundleValidation | CatalogProblem:
        """Validate against local authored contracts without Catalog writes."""

        key = self._tenant_key(actor)
        if isinstance(key, CatalogProblem):
            return key
        return self._policy.validate(key, bundle)

    def plan(self, actor: Actor, bundle: CompanyBundle) -> CompanyBundlePlan | CatalogProblem:
        """Plan against one exact active bundle without Catalog writes."""

        key = self._tenant_key(actor)
        if isinstance(key, CatalogProblem):
            return key
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            connection.execute("SET ROLE ctower_svc")
            try:
                active = load_active_catalog(
                    connection,
                    actor.tenant_id,
                    key,
                    self._store,
                )
            except CatalogObjectError:
                return _recovery_problem()
        return self._policy.plan(
            key,
            bundle,
            active.active if active is not None else None,
        )

    def apply(
        self,
        actor: Actor,
        command: CompanyBundleApply,
        *,
        telemetry: TelemetryContext,
    ) -> CompanyBundleCommandResult | CatalogProblem:
        """Authorize and lock the exact command before any payload write."""

        authorized = _authorize_apply(actor, command)
        if authorized is not None:
            return authorized
        key = self._tenant_key(actor)
        if isinstance(key, CatalogProblem):
            return key
        request_digest = hashlib.sha256(canonical_bytes(command.request_payload())).digest()
        outcome = self._apply_with_serialization_retry(
            actor,
            key,
            command,
            request_digest=request_digest,
            telemetry=telemetry,
        )
        self._telemetry.emit(
            "catalog.apply_company_bundle",
            telemetry,
            outcome="error" if isinstance(outcome, CatalogProblem) else "ok",
            reason=outcome.code if isinstance(outcome, CatalogProblem) else "committed",
        )
        return outcome

    def export(self, actor: Actor) -> CompanyBundleExport | CatalogProblem:
        """Export one exact active semantic bundle plus separate server metadata."""

        key = self._tenant_key(actor)
        if isinstance(key, CatalogProblem):
            return key
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            connection.execute("SET ROLE ctower_svc")
            try:
                active = load_active_catalog(
                    connection,
                    actor.tenant_id,
                    key,
                    self._store,
                )
            except CatalogObjectError:
                return _recovery_problem()
        if active is None:
            return CatalogProblem(
                code="bundle-not-active",
                detail="No active CompanyBundle exists for this tenant.",
                status=404,
                title="Bundle unavailable",
            )
        value = active.active
        return CompanyBundleExport(
            active_version=value.version,
            bundle=value.bundle,
            bundle_digest=value.bundle_digest,
            activated_at=value.activated_at,
            actor_principal_id=value.actor_principal_id,
            command_id=value.command_id,
            checks=value.checks,
        )

    def _apply_with_serialization_retry(
        self,
        actor: Actor,
        tenant_slug: str,
        command: CompanyBundleApply,
        *,
        request_digest: bytes,
        telemetry: TelemetryContext,
    ) -> CompanyBundleCommandResult | CatalogProblem:
        for attempt in range(_SERIALIZATION_ATTEMPTS):
            try:
                return recover_ambiguous_commit(
                    lambda: apply_bundle(
                        self._dsn,
                        actor,
                        tenant_slug,
                        command,
                        self._policy,
                        self._stager,
                        self._store,
                        request_digest=request_digest,
                        now=self._clock(),
                        telemetry=telemetry,
                    )
                )
            except psycopg.errors.SerializationFailure:
                if attempt + 1 == _SERIALIZATION_ATTEMPTS:
                    return CatalogProblem(
                        code="bundle-base-conflict",
                        detail="CompanyBundle apply lost a concurrent serialization race.",
                        status=409,
                        title="Bundle base conflict",
                        command_id=command.client_command_id,
                    )
        raise AssertionError("bounded serialization loop did not return")

    def _tenant_key(self, actor: Actor) -> str | CatalogProblem:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            connection.execute("SET ROLE ctower_svc")
            key = tenant_key(connection, actor.tenant_id)
        if key is not None:
            return key
        return CatalogProblem(
            code="tenant-scope-denied",
            detail="Catalog tenant authority is unavailable.",
            status=404,
            title="Catalog unavailable",
        )


def _recovery_problem(command_id: UUID | None = None) -> CatalogProblem:
    return CatalogProblem(
        code="bundle-recovery-unavailable",
        detail="Catalog payload staging or read-back is unavailable.",
        status=503,
        title="Bundle recovery unavailable",
        command_id=command_id,
    )


def _authorize_apply(
    actor: Actor,
    command: CompanyBundleApply,
) -> CatalogProblem | None:
    if actor.kind is PrincipalKind.OPERATOR:
        return None
    return CatalogProblem(
        code="unauthorized",
        detail="CompanyBundle apply requires operator or platform-administrator authority.",
        status=403,
        title="CompanyBundle apply forbidden",
        command_id=command.client_command_id,
    )

"""Authoritative Catalog and Project Delivery setup for migration reconciliation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID, uuid4

import psycopg

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.objects import ObjectIntegrityError, StoredObject
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.telemetry import TelemetryContext
from modules.catalog.support import FileSchemas

from ._checkpoint_fixture import checkpoint_keys, checkpoint_resource
from ._postgres import Database

__all__ = ["materialize_checkpoint_truth", "refresh_checkpoint_truth"]


class _MemoryObjectStore:
    def __init__(self, now: datetime) -> None:
        self._now = now
        self._objects: dict[str, bytes] = {}
        self._receipts: dict[str, StoredObject] = {}

    def put_verified(
        self,
        tenant_id: UUID,
        artifact_digest: str,
        content: bytes,
        *,
        key_reference: str,
    ) -> StoredObject:
        del tenant_id
        existing = self._receipts.get(artifact_digest)
        if existing is not None:
            if self._objects[artifact_digest] != content:
                raise ObjectIntegrityError("existing immutable object bytes differ")
            return existing
        receipt = StoredObject(
            artifact_digest=artifact_digest,
            object_key=f"catalog/{artifact_digest}",
            object_version="version-1",
            ciphertext_sha256=f"sha256:{'1' * 64}",
            key_reference=key_reference,
            key_version="version-1",
            wrapped_key_sha256=f"sha256:{'2' * 64}",
            uploaded_at=self._now,
            verified_at=self._now,
        )
        self._objects[artifact_digest] = content
        self._receipts[artifact_digest] = receipt
        return receipt

    def read_verified(self, tenant_id: UUID, receipt: StoredObject) -> bytes:
        del tenant_id
        return self._objects[receipt.artifact_digest]

    def erase(self, tenant_id: UUID, receipt: StoredObject) -> None:
        del tenant_id
        self._objects.pop(receipt.artifact_digest, None)
        self._receipts.pop(receipt.artifact_digest, None)


def materialize_checkpoint_truth(
    database: Database,
    *,
    now: datetime,
    outcome_overrides: Mapping[str, str] | None = None,
) -> None:
    actor = Actor(database.operator_id, database.tenant_id, PrincipalKind.OPERATOR)
    catalog = PostgresCatalog(
        database.runtime_dsn,
        FileSchemas(),
        _MemoryObjectStore(now),
        key_reference="vault:catalog-key",
        clock=lambda: now,
    )
    bundle = _checkpoint_bundle(outcome_overrides or {})
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem)
    command_id = uuid4()
    applied = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=bundle,
            expected_active_version=0,
            plan_digest=plan.plan_digest,
        ),
        telemetry=_telemetry(actor, command_id),
    )
    assert isinstance(applied, CompanyBundleCommandResult)
    refresh_checkpoint_truth(database, now=now)


def refresh_checkpoint_truth(database: Database, *, now: datetime) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(record_position), 0) FROM events WHERE tenant_id = %s",
            (database.tenant_id,),
        ).fetchone()
        assert row is not None and int(row[0]) > 0
        connection.execute(
            """
            INSERT INTO outbox_consumer_cursors (
                consumer_key, tenant_id, topic, generation, acceptance_position,
                health, detail, blocked_outbox_id, updated_at
            ) VALUES (
                'board_projection', %s, 'record.events', 1, %s,
                'CURRENT', 'migration-module', NULL, %s
            )
            ON CONFLICT (consumer_key, tenant_id, topic) DO UPDATE
            SET acceptance_position = EXCLUDED.acceptance_position,
                health = EXCLUDED.health, detail = EXCLUDED.detail,
                blocked_outbox_id = NULL, updated_at = EXCLUDED.updated_at
            """,
            (database.tenant_id, int(row[0]), now),
        )
    affected = Projections(PostgresProjections(database.projection_dsn)).reconcile_project_delivery(
        database.tenant_id, now=now
    )
    assert affected in {0, len(checkpoint_keys())}


def _checkpoint_bundle(outcome_overrides: Mapping[str, str]) -> CompanyBundle:
    resources = [
        checkpoint_resource(
            checkpoint_key,
            outcome=outcome_overrides.get(checkpoint_key),
        )
        for checkpoint_key in checkpoint_keys()
    ]
    return CompanyBundle.model_validate_json(
        json.dumps(
            {
                "schema": "ctower.company-bundle/v1",
                "company": {"key": "ctower", "display_name": "ctower"},
                "resources": resources,
                "assignments": [],
                "secret_binding_refs": [],
            }
        )
    )


def _telemetry(actor: Actor, command_id: UUID) -> TelemetryContext:
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

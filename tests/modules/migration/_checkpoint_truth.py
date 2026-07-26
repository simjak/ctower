"""Authoritative Catalog and Project Delivery setup for migration reconciliation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import rfc8785

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.objects import ObjectIntegrityError, StoredObject
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.telemetry import TelemetryContext
from modules.catalog.support import FileSchemas

from ._postgres import Database

__all__ = ["materialize_checkpoint_truth", "refresh_checkpoint_truth"]
_ROOT = Path(__file__).parents[3]
_CHECKPOINT_COUNT = 14


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


def materialize_checkpoint_truth(database: Database, *, now: datetime) -> None:
    actor = Actor(database.operator_id, database.tenant_id, PrincipalKind.OPERATOR)
    catalog = PostgresCatalog(
        database.runtime_dsn,
        FileSchemas(),
        _MemoryObjectStore(now),
        key_reference="vault:catalog-key",
        clock=lambda: now,
    )
    bundle = _checkpoint_bundle()
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
    assert affected in {0, _CHECKPOINT_COUNT}


def _checkpoint_bundle() -> CompanyBundle:
    vectors = cast(
        dict[str, object],
        json.loads(
            (_ROOT / "contracts/domain/project-delivery/project-delivery-vectors.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    resources = [
        _checkpoint_resource(checkpoint_key, vectors)
        for checkpoint_key in cast(list[str], vectors["checkpoint_keys"])
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


def _checkpoint_resource(checkpoint_key: str, vectors: dict[str, object]) -> JsonValue:
    criterion_keys = (
        cast(list[str], vectors["i1_7_criteria"])
        if checkpoint_key == "I1.7"
        else ["declared-outcome"]
    )
    key = checkpoint_key.casefold().replace(".", "-")
    payload: JsonValue = {
        "schema": "ctower.checkpoint/v1",
        "key": f"ctower.{key}",
        "checkpoint_key": checkpoint_key,
        "display_name": f"ctower checkpoint {checkpoint_key}",
        "outcome": f"ctower establishes the declared {checkpoint_key} outcome",
        "accountable_owner": "ctower-operator",
        "criteria": [
            {
                "key": criterion,
                "description": f"Current proof for {criterion}",
                "required": True,
                "evidence_policy_refs": [],
            }
            for criterion in criterion_keys
        ],
        "dependency_refs": [],
    }
    digest = f"sha256:{hashlib.sha256(rfc8785.dumps(payload)).hexdigest()}"
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": "checkpoint",
            "key": f"ctower.{key}",
            "scope": {"tenant": "ctower", "project": "ctower"},
            "revision": 1,
            "content_digest": digest,
            "schema_ref": "ctower.checkpoint/v1",
            "lifecycle": "published",
            "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
            "provenance": [
                {
                    "kind": "reviewed-contract",
                    "source": "SPEC#project-delivery-projection",
                    "digest": digest,
                }
            ],
            "payload_ref": f"object:{digest}",
        },
        "payload": payload,
    }


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

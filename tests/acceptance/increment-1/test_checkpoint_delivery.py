"""Checkpoint Catalog materialization and Project Delivery acceptance evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import rfc8785
from support.catalog import FileSchemas, MemoryObjectStore, actor_for, telemetry_for
from support.tenant_fixture import TenantFixture

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).parents[3]
_CHECKPOINT_COUNT = 14


def test_checkpoint_bundle_materializes_all_14_definitions_atomically_and_replays(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = _catalog(tenant)
    bundle = _checkpoint_bundle()
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem)
    command_id = uuid4()
    command = CompanyBundleApply(
        client_command_id=command_id,
        bundle=bundle,
        expected_active_version=0,
        plan_digest=plan.plan_digest,
    )

    applied = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))
    counts = _checkpoint_counts(tenant.database.admin_dsn)
    replayed = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))
    partial = catalog.validate(
        actor,
        bundle.model_copy(update={"resources": bundle.resources[:-1]}),
    )

    assert isinstance(applied, CompanyBundleCommandResult)
    assert replayed == applied
    assert counts == (14, 19, 14)
    assert _checkpoint_counts(tenant.database.admin_dsn) == counts
    assert isinstance(partial, CatalogProblem)
    assert partial.code == "bundle-reference-invalid"


def test_project_delivery_heartbeat_poison_and_rebuild_are_deterministic(
    tenant: TenantFixture,
) -> None:
    _apply_checkpoint_bundle(tenant)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    now = datetime.now(UTC)

    first_count = projections.reconcile_project_delivery(tenant.tenant_id, now=now)
    first = projections.project_delivery(actor, "ctower")
    unchanged = projections.reconcile_project_delivery(
        tenant.tenant_id, now=now + timedelta(minutes=30)
    )
    heartbeat_count = projections.reconcile_project_delivery(
        tenant.tenant_id, now=now + timedelta(hours=2)
    )
    heartbeat = projections.project_delivery(actor, "ctower")
    _poison_project_delivery_source(tenant)
    poison_count = projections.reconcile_project_delivery(
        tenant.tenant_id, now=now + timedelta(hours=2, minutes=1)
    )
    poisoned = projections.project_delivery(actor, "ctower")
    _recover_project_delivery_source(tenant)
    rebuild_count = projections.rebuild_project_delivery(
        tenant.tenant_id, now=now + timedelta(hours=2, minutes=2)
    )
    rebuilt = projections.project_delivery(actor, "ctower")

    assert first is not None and heartbeat is not None
    assert poisoned is not None and rebuilt is not None
    assert (first_count, unchanged, heartbeat_count, poison_count, rebuild_count) == (
        14,
        0,
        14,
        14,
        14,
    )
    first_semantics = tuple(row.semantic_digest for row in first.rows)
    assert len(first_semantics) == _CHECKPOINT_COUNT
    assert tuple(row.semantic_digest for row in heartbeat.rows) == first_semantics
    assert {row.health for row in poisoned.rows} == {"STATE_UNKNOWN"}
    assert tuple(row.semantic_digest for row in rebuilt.rows) == first_semantics
    assert rebuilt.rebuild_generation == 1


def _checkpoint_bundle() -> CompanyBundle:
    vectors = json.loads(
        (_ROOT / "contracts/domain/project-delivery/project-delivery-vectors.json").read_text(
            encoding="utf-8"
        )
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


def _checkpoint_resource(checkpoint_key: str, vectors: object) -> JsonValue:
    typed_vectors = cast(dict[str, object], vectors)
    criterion_keys = (
        cast(list[str], typed_vectors["i1_7_criteria"])
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
    digest = _digest(payload)
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


def _digest(payload: JsonValue) -> str:
    return f"sha256:{hashlib.sha256(rfc8785.dumps(payload)).hexdigest()}"


def _catalog(tenant: TenantFixture) -> PostgresCatalog:
    return PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 7, 24, tzinfo=UTC),
    )


def _apply_checkpoint_bundle(tenant: TenantFixture) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = _catalog(tenant)
    bundle = _checkpoint_bundle()
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem)
    command_id = uuid4()
    result = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=bundle,
            expected_active_version=0,
            plan_digest=plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, command_id),
    )
    assert isinstance(result, CompanyBundleCommandResult)


def _poison_project_delivery_source(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT outbox_id FROM outbox WHERE tenant_id = %s ORDER BY outbox_id LIMIT 1",
            (tenant.tenant_id,),
        ).fetchone()
        assert row is not None
        connection.execute(
            """
            INSERT INTO outbox_consumer_cursors (
                consumer_key, tenant_id, topic, generation, acceptance_position,
                health, detail, blocked_outbox_id, updated_at
            ) VALUES (
                'board_projection', %s, 'record.events', 1, 0,
                'STATE_UNKNOWN', 'synthetic-poison', %s, %s
            )
            """,
            (tenant.tenant_id, row[0], datetime.now(UTC)),
        )


def _recover_project_delivery_source(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE outbox_consumer_cursors
            SET health = 'CURRENT', detail = 'synthetic-recovery',
                blocked_outbox_id = NULL, updated_at = %s
            WHERE consumer_key = 'board_projection' AND tenant_id = %s
              AND topic = 'record.events'
            """,
            (datetime.now(UTC), tenant.tenant_id),
        )


def _checkpoint_counts(dsn: str) -> tuple[int, int, int]:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM project_delivery_checkpoint_definitions),
                (SELECT count(*) FROM project_delivery_exit_criteria),
                (SELECT count(DISTINCT event_id)
                 FROM project_delivery_checkpoint_definitions)
            """
        ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])

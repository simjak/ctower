"""Project Delivery checkpoint completeness stays project-local (issue 201)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
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

_DECLARATION = "declaration"

# project_key -> ordered checkpoint_keys, each a bare declaration-only checkpoint.
_MULTI_PROJECT_CHECKPOINTS: dict[str, tuple[str, ...]] = {
    "ctower": ("fx-ctower-1", "fx-ctower-2"),
    "manibo": ("fx-manibo-1", "fx-manibo-2"),
}


def test_checkpoint_completeness_is_project_local_across_a_materialization_gap(
    tenant: TenantFixture,
) -> None:
    """Issue 201: one project's own checkpoint completeness never reads another
    project's materialization state, in either direction — erasing one of
    `manibo`'s checkpoint definitions must never mark `ctower`'s untouched,
    fully-materialized rows `source_incomplete`."""

    now = datetime.now(UTC)
    _apply_multi_project_checkpoints(tenant, now=now)
    _advance_source_cursor(tenant, now=now)

    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    affected = projections.reconcile_project_delivery(tenant.tenant_id, now=now)
    assert affected == sum(len(keys) for keys in _MULTI_PROJECT_CHECKPOINTS.values())

    ctower_before = projections.project_delivery(operator, "ctower")
    manibo_before = projections.project_delivery(operator, "manibo")
    assert ctower_before is not None and manibo_before is not None
    assert {row.checkpoint_key for row in ctower_before.rows} == {"fx-ctower-1", "fx-ctower-2"}
    assert {row.checkpoint_key for row in manibo_before.rows} == {"fx-manibo-1", "fx-manibo-2"}
    assert all("source_incomplete" not in row.derivation_reasons for row in ctower_before.rows)
    assert all("source_incomplete" not in row.derivation_reasons for row in manibo_before.rows)

    # Simulate a real materialization gap: `manibo`'s second checkpoint stays part of
    # the active bundle (its publish event is untouched), but its
    # `project_delivery_checkpoint_definitions` row disappears, exactly as it would if
    # `materialize_checkpoints` had never run for it. Only a real Postgres superuser
    # connection can do this: the definitions/criteria tables refuse ordinary
    # UPDATE/DELETE by an immutability trigger.
    _erase_checkpoint_definition(tenant, project_key="manibo", checkpoint_key="fx-manibo-2")

    later = datetime.now(UTC)
    projections.reconcile_project_delivery(tenant.tenant_id, now=later)
    ctower_after = projections.project_delivery(operator, "ctower")
    assert ctower_after is not None
    assert {row.checkpoint_key for row in ctower_after.rows} == {"fx-ctower-1", "fx-ctower-2"}
    assert all("source_incomplete" not in row.derivation_reasons for row in ctower_after.rows), (
        "manibo's missing checkpoint definition must never mark ctower's rows source_incomplete"
    )


def _apply_multi_project_checkpoints(tenant: TenantFixture, *, now: datetime) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: now,
    )
    resources = [
        _minimal_checkpoint_resource(project_key, checkpoint_key)
        for project_key, checkpoint_keys in _MULTI_PROJECT_CHECKPOINTS.items()
        for checkpoint_key in checkpoint_keys
    ]
    bundle = CompanyBundle.model_validate_json(
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
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem), plan
    command_id = uuid4()
    applied = catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=bundle,
            expected_active_version=0,
            plan_digest=plan.plan_digest,
        ),
        telemetry=telemetry_for(actor, command_id),
    )
    assert isinstance(applied, CompanyBundleCommandResult), applied


def _minimal_checkpoint_resource(project_key: str, checkpoint_key: str) -> JsonValue:
    slug = checkpoint_key.casefold().replace(".", "-")
    payload: JsonValue = {
        "schema": "ctower.checkpoint/v1",
        "key": f"fixture.{slug}",
        "checkpoint_key": checkpoint_key,
        "display_name": f"{project_key} checkpoint {checkpoint_key}",
        "outcome": f"{project_key} establishes the declared {checkpoint_key} outcome",
        "accountable_owner": f"{project_key}-operator",
        "criteria": [
            {
                "key": _DECLARATION,
                "description": f"The declared {checkpoint_key} outcome",
                "required": True,
                "evidence_policy_refs": [],
            }
        ],
        "dependency_refs": [],
    }
    digest = f"sha256:{hashlib.sha256(rfc8785.dumps(payload)).hexdigest()}"
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": "checkpoint",
            "key": f"fixture.{slug}",
            "scope": {"tenant": "ctower", "project": project_key},
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


def _advance_source_cursor(tenant: TenantFixture, *, now: datetime) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(record_position), 0) FROM events WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
        assert row is not None and int(row[0]) > 0
        connection.execute(
            """
            INSERT INTO outbox_consumer_cursors (
                consumer_key, tenant_id, topic, generation, acceptance_position,
                health, detail, blocked_outbox_id, updated_at
            ) VALUES (
                'board_projection', %s, 'record.events', 1, %s,
                'CURRENT', 'project-delivery-completeness', NULL, %s
            )
            ON CONFLICT (consumer_key, tenant_id, topic) DO UPDATE
            SET acceptance_position = EXCLUDED.acceptance_position,
                health = EXCLUDED.health, detail = EXCLUDED.detail,
                blocked_outbox_id = NULL, updated_at = EXCLUDED.updated_at
            """,
            (tenant.tenant_id, int(row[0]), now),
        )


def _erase_checkpoint_definition(
    tenant: TenantFixture, *, project_key: str, checkpoint_key: str
) -> None:
    """Delete one checkpoint's definition/criteria rows as a live superuser would
    only ever do by mistake: the immutability trigger refuses this for every
    ordinary role, so the fixture disables it for exactly this one statement."""

    with psycopg.connect(tenant.database.admin_dsn, autocommit=True) as connection:
        definition = connection.execute(
            """
            SELECT checkpoint_definition_id FROM project_delivery_checkpoint_definitions
            WHERE tenant_id = %s AND project_key = %s AND checkpoint_key = %s
            """,
            (tenant.tenant_id, project_key, checkpoint_key),
        ).fetchone()
        assert definition is not None
        definition_id = definition[0]
        connection.execute(
            "ALTER TABLE project_delivery_exit_criteria "
            "DISABLE TRIGGER project_delivery_exit_criteria_immutable"
        )
        connection.execute(
            "ALTER TABLE project_delivery_checkpoint_definitions "
            "DISABLE TRIGGER project_delivery_checkpoint_definitions_immutable"
        )
        try:
            connection.execute(
                "DELETE FROM project_delivery_exit_criteria WHERE checkpoint_definition_id = %s",
                (definition_id,),
            )
            connection.execute(
                "DELETE FROM project_delivery_checkpoint_definitions "
                "WHERE checkpoint_definition_id = %s",
                (definition_id,),
            )
        finally:
            connection.execute(
                "ALTER TABLE project_delivery_exit_criteria "
                "ENABLE TRIGGER project_delivery_exit_criteria_immutable"
            )
            connection.execute(
                "ALTER TABLE project_delivery_checkpoint_definitions "
                "ENABLE TRIGGER project_delivery_checkpoint_definitions_immutable"
            )

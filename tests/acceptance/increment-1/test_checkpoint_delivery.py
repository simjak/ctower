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


def test_checkpoint_bundle_materializes_all_14_definitions_atomically_and_replays(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = _catalog(tenant)
    prior_bundle = _checkpoint_bundle(prior=True)
    _apply_checkpoint_bundle(tenant, catalog=catalog, bundle=prior_bundle)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    initial_source = _record_watermark(tenant)
    _set_project_delivery_source(tenant, acceptance_position=initial_source)
    assert projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC)) == len(
        prior_bundle.resources
    )
    prior_view = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        "ctower",
    )
    assert prior_view is not None
    assert len(prior_view.rows) == len(prior_bundle.resources)

    bundle = _checkpoint_bundle(mutated=True)
    plan = catalog.plan(actor, bundle)
    assert not isinstance(plan, CatalogProblem)
    command_id = uuid4()
    command = CompanyBundleApply(
        client_command_id=command_id,
        bundle=bundle,
        expected_active_version=1,
        plan_digest=plan.plan_digest,
    )

    applied = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))
    replayed = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))
    configured_count = len(bundle.resources)

    assert isinstance(applied, CompanyBundleCommandResult)
    assert replayed == applied
    source = _record_watermark(tenant)
    _set_project_delivery_source(tenant, acceptance_position=source)
    affected = projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC))
    view = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        "ctower",
    )
    assert view is not None
    configured_keys = {str(resource.payload["checkpoint_key"]) for resource in bundle.resources}
    assert {row.checkpoint_key for row in view.rows} == configured_keys
    assert len(view.rows) == configured_count
    assert affected == configured_count
    assert configured_count == len(prior_view.rows) + 1
    renamed = next(row for row in view.rows if row.checkpoint_key == "I1.9")
    prior = next(row for row in prior_view.rows if row.checkpoint_key == "I1.9")
    assert prior.checkpoint_label == "ctower checkpoint I1.9"
    assert renamed.checkpoint_label == "Renamed fixture checkpoint"
    assert renamed.qualifying_stage_unfilled_or_unknown_slot_keys == ("declared-outcome",)


def test_project_delivery_missing_lagging_poison_and_rebuild_are_deterministic(
    tenant: TenantFixture,
) -> None:
    _apply_checkpoint_bundle(tenant)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    now = datetime.now(UTC)

    missing_count = projections.reconcile_project_delivery(tenant.tenant_id, now=now)
    missing = projections.project_delivery(actor, "ctower")
    source = _record_watermark(tenant)
    _set_project_delivery_source(tenant, acceptance_position=source)
    recovery_count = projections.reconcile_project_delivery(
        tenant.tenant_id, now=now + timedelta(minutes=1)
    )
    recovered = projections.project_delivery(actor, "ctower")
    _set_project_delivery_source(tenant, acceptance_position=source - 1)
    lagging_count = projections.reconcile_project_delivery(
        tenant.tenant_id, now=now + timedelta(minutes=2)
    )
    lagging = projections.project_delivery(actor, "ctower")
    _poison_project_delivery_source(tenant)
    poison_count = projections.reconcile_project_delivery(
        tenant.tenant_id, now=now + timedelta(minutes=3)
    )
    poisoned = projections.project_delivery(actor, "ctower")
    _set_project_delivery_source(tenant, acceptance_position=source)
    rebuild_count = projections.rebuild_project_delivery(
        tenant.tenant_id, now=now + timedelta(minutes=4)
    )
    rebuilt = projections.project_delivery(actor, "ctower")

    assert missing is not None and recovered is not None
    assert lagging is not None and poisoned is not None and rebuilt is not None
    assert (
        missing_count,
        recovery_count,
        lagging_count,
        poison_count,
        rebuild_count,
    ) == (14, 14, 14, 0, 14)
    assert {row.health for row in missing.rows} == {"STATE_UNKNOWN"}
    recovered_semantics = tuple(row.semantic_digest for row in recovered.rows)
    assert len(recovered_semantics) == len(_checkpoint_bundle().resources)
    assert {row.health for row in lagging.rows} == {"STATE_UNKNOWN"}
    assert {row.health for row in poisoned.rows} == {"STATE_UNKNOWN"}
    assert tuple(row.semantic_digest for row in rebuilt.rows) == recovered_semantics
    assert rebuilt.rebuild_generation == 1


def _checkpoint_bundle(
    *,
    mutated: bool = False,
    prior: bool = False,
) -> CompanyBundle:
    vectors = cast(
        dict[str, object],
        json.loads(
            (_ROOT / "contracts/domain/project-delivery/project-delivery-vectors.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    if mutated or prior:
        keys = cast(list[str], vectors["checkpoint_keys"])
        configured = cast(
            dict[str, list[str]],
            vectors["configured_checkpoint_criteria"],
        )
        checkpoint_keys = ["I1.9", *keys[1:-1]]
        if mutated:
            checkpoint_keys.append("I2.9")
        vectors = {
            **vectors,
            "checkpoint_keys": checkpoint_keys,
            "configured_checkpoint_criteria": {
                "I1.9": configured[keys[0]],
                **{key: configured[key] for key in keys[1:-1]},
                **({"I2.9": configured[keys[-1]]} if mutated else {}),
            },
            "checkpoint_labels": ({"I1.9": "Renamed fixture checkpoint"} if mutated else {}),
        }
    resources = [
        _checkpoint_resource(checkpoint_key, vectors)
        for checkpoint_key in cast(list[str], vectors["checkpoint_keys"])
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
    if not mutated:
        return bundle
    previous = next(
        item.component.reference()
        for item in _checkpoint_bundle(prior=True).resources
        if item.component.key == "ctower.i1-9"
    )
    superseding_resources = tuple(
        item.model_copy(
            update={
                "component": item.component.model_copy(
                    update={"revision": 2, "supersedes": previous}
                )
            }
        )
        if item.component.key == "ctower.i1-9"
        else item
        for item in bundle.resources
    )
    return bundle.model_copy(update={"resources": superseding_resources})


def _checkpoint_resource(checkpoint_key: str, vectors: object) -> JsonValue:
    typed_vectors = cast(dict[str, object], vectors)
    configured = cast(dict[str, object], typed_vectors["configured_checkpoint_criteria"])
    criterion_keys = cast(list[str], configured[checkpoint_key])
    labels = cast(dict[str, str], typed_vectors.get("checkpoint_labels", {}))
    key = checkpoint_key.casefold().replace(".", "-")
    payload: JsonValue = {
        "schema": "ctower.checkpoint/v1",
        "key": f"ctower.{key}",
        "checkpoint_key": checkpoint_key,
        "display_name": labels.get(
            checkpoint_key,
            f"ctower checkpoint {checkpoint_key}",
        ),
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


def _apply_checkpoint_bundle(
    tenant: TenantFixture,
    *,
    catalog: PostgresCatalog | None = None,
    bundle: CompanyBundle | None = None,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    selected_catalog = catalog or _catalog(tenant)
    selected_bundle = bundle or _checkpoint_bundle()
    plan = selected_catalog.plan(actor, selected_bundle)
    assert not isinstance(plan, CatalogProblem)
    command_id = uuid4()
    result = selected_catalog.apply(
        actor,
        CompanyBundleApply(
            client_command_id=command_id,
            bundle=selected_bundle,
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
        result = connection.execute(
            """
            UPDATE outbox_consumer_cursors
            SET health = 'STATE_UNKNOWN', detail = 'synthetic-poison',
                blocked_outbox_id = %s, updated_at = %s
            WHERE consumer_key = 'board_projection' AND tenant_id = %s
              AND topic = 'record.events'
            """,
            (row[0], datetime.now(UTC), tenant.tenant_id),
        )
        assert result.rowcount == 1


def _set_project_delivery_source(
    tenant: TenantFixture,
    *,
    acceptance_position: int,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO outbox_consumer_cursors (
                consumer_key, tenant_id, topic, generation, acceptance_position,
                health, detail, blocked_outbox_id, updated_at
            ) VALUES (
                'board_projection', %s, 'record.events', 1, %s,
                'CURRENT', 'synthetic-recovery', NULL, %s
            )
            ON CONFLICT (consumer_key, tenant_id, topic) DO UPDATE
            SET acceptance_position = EXCLUDED.acceptance_position,
                health = EXCLUDED.health, detail = EXCLUDED.detail,
                blocked_outbox_id = NULL, updated_at = EXCLUDED.updated_at
            """,
            (tenant.tenant_id, acceptance_position, datetime.now(UTC)),
        )


def _record_watermark(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(record_position), 0) FROM events WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None and int(row[0]) > 0
    return int(row[0])


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

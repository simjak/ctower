"""Checkpoint Catalog materialization and Project Delivery acceptance evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import rfc8785
from support.catalog import FileSchemas, MemoryObjectStore, actor_for, minimal_bundle, telemetry_for
from support.tenant_fixture import TenantFixture

from ctower_kernel.catalog import (
    CatalogProblem,
    CompanyBundle,
    CompanyBundleApply,
    CompanyBundleCommandResult,
    PostgresCatalog,
)
from ctower_kernel.catalog.interface import CompanyBundleResource, JsonValue
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).parents[3]
# The domain migration 0027 wrote into both checkpoint_key CHECK constraints, and the
# only domain either constraint accepted before 0037 relaxed them to the authored
# contract pattern read from checkpoint.schema.json below.
_SUPERSEDED_INCREMENT_KEY = re.compile(r"^I[12]\.[0-9]+$")
_CROSS_DOMAIN_CHECKPOINT_KEYS = (
    "Q3-close.1",
    "accounting_2026.q3",
    "compliance.2026-h2",
    "4-hiring.close",
)
_CTOWER_CHECKPOINT_CRITERIA = {
    "I1.0": 3,
    "I1.1": 3,
    "I1.2": 3,
    "I1.3": 4,
    "I1.4": 3,
    "I1.5": 2,
    "I1.6": 3,
    "I1.7": 5,
    "I2.1": 3,
    "I2.2": 2,
    "I2.3": 2,
    "I2.4": 2,
    "I2.5": 2,
    "I2.6": 3,
}


def test_reviewed_company_bundle_materializes_ordered_meaningful_delivery_rows(
    tenant: TenantFixture,
) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    catalog = _catalog(tenant)
    bundle = minimal_bundle()

    _apply_checkpoint_bundle(tenant, catalog=catalog, bundle=bundle)
    exported = catalog.export(actor)
    assert not isinstance(exported, CatalogProblem)
    replanned = catalog.plan(actor, exported.bundle)
    assert not isinstance(replanned, CatalogProblem)
    assert replanned.actions == ()

    source = _record_watermark(tenant)
    _set_project_delivery_source(tenant, acceptance_position=source)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    affected = projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC))
    view = projections.project_delivery(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        "ctower",
    )

    assert view is not None
    assert affected == len(_CTOWER_CHECKPOINT_CRITERIA)
    assert tuple(row.checkpoint_key for row in view.rows) == tuple(_CTOWER_CHECKPOINT_CRITERIA)
    assert all("ctower checkpoint" not in row.checkpoint_label.casefold() for row in view.rows)
    assert all("establishes the declared" not in row.outcome.casefold() for row in view.rows)
    for row in view.rows:
        expected = _CTOWER_CHECKPOINT_CRITERIA[row.checkpoint_key]
        assert (row.proven_criteria, row.declared_criteria) == (0, expected)
        assert (
            row.qualifying_stage_slots_filled,
            row.qualifying_stage_slots_required,
        ) == (0, expected)
        assert len(row.qualifying_stage_unfilled_or_unknown_slot_keys) == expected
        assert row.source_ids == (
            f"catalog:ctower.{row.checkpoint_key.casefold().replace('.', '-')}@1",
            "ctower.trust-spine-four-stage.evidence@1",
        )
        assert row.source_watermark == source
        assert row.projection_watermark == source
        assert row.derivation_reasons[-1] == "underlying_maturity:planned"


def test_checkpoint_bundle_materializes_every_definition_and_replays_without_residue(
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
    applied_residue = _checkpoint_counts(tenant.database.admin_dsn)
    replayed = catalog.apply(actor, command, telemetry=telemetry_for(actor, command_id))
    replayed_residue = _checkpoint_counts(tenant.database.admin_dsn)
    configured_count = len(bundle.resources)

    assert isinstance(applied, CompanyBundleCommandResult)
    assert replayed == applied
    # Residue, not a return value: the apply left exactly the definitions and criteria
    # the two bundles publish between them, each on its own publication event, and the
    # replay added none of them a second time.
    assert applied_residue == _expected_residue(prior_bundle, bundle)
    assert replayed_residue == applied_residue
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
    configured = len(_checkpoint_bundle().resources)
    # A poisoned source reconciles no row; every other pass touches the whole
    # authored checkpoint set, whatever size the vectors declare it to be.
    assert (
        missing_count,
        recovery_count,
        lagging_count,
        poison_count,
        rebuild_count,
    ) == (configured, configured, configured, 0, configured)
    assert {row.health for row in missing.rows} == {"STATE_UNKNOWN"}
    recovered_semantics = tuple(row.semantic_digest for row in recovered.rows)
    assert len(recovered_semantics) == configured
    assert {row.health for row in lagging.rows} == {"STATE_UNKNOWN"}
    assert {row.health for row in poisoned.rows} == {"STATE_UNKNOWN"}
    assert tuple(row.semantic_digest for row in rebuilt.rows) == recovered_semantics
    assert rebuilt.rebuild_generation == 1


def test_non_increment_checkpoint_key_materializes_and_projects_end_to_end(
    tenant: TenantFixture,
) -> None:
    """Storage accepts every checkpoint key the authored contract authorizes."""

    contract_pattern = re.compile(_authored_checkpoint_key_pattern())
    assert all(contract_pattern.fullmatch(key) for key in _CROSS_DOMAIN_CHECKPOINT_KEYS)
    assert not any(
        _SUPERSEDED_INCREMENT_KEY.fullmatch(key) for key in _CROSS_DOMAIN_CHECKPOINT_KEYS
    )
    bundle = _cross_domain_checkpoint_bundle()
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)

    _apply_checkpoint_bundle(tenant, bundle=bundle)
    _set_project_delivery_source(tenant, acceptance_position=_record_watermark(tenant))
    affected = projections.reconcile_project_delivery(tenant.tenant_id, now=datetime.now(UTC))
    view = projections.project_delivery(actor, "ctower")

    assert affected == len(_CROSS_DOMAIN_CHECKPOINT_KEYS)
    assert view is not None
    assert {row.checkpoint_key for row in view.rows} == set(_CROSS_DOMAIN_CHECKPOINT_KEYS)
    definitions, rows = _stored_checkpoint_keys(tenant)
    assert definitions == set(_CROSS_DOMAIN_CHECKPOINT_KEYS)
    assert rows == set(_CROSS_DOMAIN_CHECKPOINT_KEYS)


def _authored_checkpoint_key_pattern() -> str:
    contract = cast(
        dict[str, object],
        json.loads(
            (_ROOT / "contracts/components/checkpoint.schema.json").read_text(encoding="utf-8")
        ),
    )
    properties = cast(dict[str, dict[str, str]], contract["properties"])
    return properties["checkpoint_key"]["pattern"]


def _cross_domain_checkpoint_bundle() -> CompanyBundle:
    return _bundle_of(
        {
            "checkpoint_keys": list(_CROSS_DOMAIN_CHECKPOINT_KEYS),
            "configured_checkpoint_criteria": {
                checkpoint_key: ["declared-outcome"]
                for checkpoint_key in _CROSS_DOMAIN_CHECKPOINT_KEYS
            },
        }
    )


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
    bundle = _bundle_of(vectors)
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


def _bundle_of(vectors: dict[str, object]) -> CompanyBundle:
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
    configured = cast(dict[str, object], typed_vectors["configured_checkpoint_criteria"])
    criterion_keys = cast(list[str], configured[checkpoint_key])
    labels = cast(dict[str, str], typed_vectors.get("checkpoint_labels", {}))
    # The component key domain is narrower than the checkpoint key domain, so fold
    # every authored checkpoint-key separator onto the one the component key allows.
    key = checkpoint_key.casefold().replace(".", "-").replace("_", "-")
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


def _stored_checkpoint_keys(tenant: TenantFixture) -> tuple[set[str], set[str]]:
    """Read the two columns migration 0027 constrained, straight from storage."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        definitions = connection.execute(
            """
            SELECT checkpoint_key FROM project_delivery_checkpoint_definitions
            WHERE tenant_id = %s
            """,
            (tenant.tenant_id,),
        ).fetchall()
        rows = connection.execute(
            "SELECT checkpoint_key FROM project_delivery_projection_rows WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchall()
    return {str(row[0]) for row in definitions}, {str(row[0]) for row in rows}


def _expected_residue(
    prior_bundle: CompanyBundle,
    bundle: CompanyBundle,
) -> tuple[int, int, int]:
    """Derive the storage residue both applies must leave, from the bundles themselves.

    A carried-forward component keeps its original publication event, so the second apply
    materializes exactly the resources whose reference the first one never published.
    """

    published = tuple(item.component.reference() for item in prior_bundle.resources)
    added = tuple(item for item in bundle.resources if item.component.reference() not in published)
    definitions = len(prior_bundle.resources) + len(added)
    criteria = _criteria_count(prior_bundle.resources) + _criteria_count(added)
    return definitions, criteria, definitions


def _criteria_count(resources: tuple[CompanyBundleResource, ...]) -> int:
    return sum(
        len(cast(list[object], cast(dict[str, object], item.payload)["criteria"]))
        for item in resources
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

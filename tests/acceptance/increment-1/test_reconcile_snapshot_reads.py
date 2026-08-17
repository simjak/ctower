"""gh#165 D9: reconcile reads the active-checkpoint snapshot exactly once (issue 165)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from unittest.mock import patch
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
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()

_DECLARATION = "declaration"

# The current live portfolio (three project_keys) — the exact shape gh#165's D9
# disposition comment measured: "up to 4 reads of the same ... fact per reconcile
# pass ... 1 global + 1 per active project."
_THREE_PROJECT_CHECKPOINTS: dict[str, tuple[str, ...]] = {
    "ctower": ("fx-ctower-1", "fx-ctower-2"),
    "manibo": ("fx-manibo-1", "fx-manibo-2"),
    "bh-loop": ("fx-bhloop-1", "fx-bhloop-2"),
}


def test_reconcile_reads_the_active_checkpoint_snapshot_exactly_once_for_a_three_project_portfolio(
    tenant: TenantFixture,
) -> None:
    """D9 regression: whatever the active project count, the active-checkpoint
    snapshot (`active_checkpoint_event_ids`'s query, distinguished below by the
    `member_event_ids` fragment unique to it in this module) must be read exactly
    once per reconcile pass — not once globally plus once per project. Counting is
    done at the `psycopg.Connection.execute` boundary (public API), not by importing
    the kernel's private reconcile modules, so this stays outside the architecture
    boundary those modules are private against. The reconcile outcome is also
    checked for full per-project correctness (same-outcome proof) alongside the
    read count."""

    now = datetime.now(UTC)
    _apply_three_project_checkpoints(tenant, now=now)
    _advance_source_cursor(tenant, now=now)

    reads: list[None] = []
    real_execute = psycopg.Connection.execute

    def _counting_execute(
        self: psycopg.Connection[dict[str, object]],
        query: str,
        params: Sequence[object] | Mapping[str, object] | None = None,
    ) -> psycopg.Cursor[dict[str, object]]:
        if isinstance(query, str) and "member_event_ids" in query:
            reads.append(None)
        return real_execute(self, query, params)

    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    with patch.object(psycopg.Connection, "execute", new=_counting_execute):
        affected = projections.reconcile_project_delivery(tenant.tenant_id, now=now)

    assert len(reads) == 1, (
        f"reconcile must read the active-checkpoint snapshot exactly once per pass "
        f"regardless of active project count; observed {len(reads)} reads for "
        f"{len(_THREE_PROJECT_CHECKPOINTS)} active projects"
    )
    assert affected == sum(len(keys) for keys in _THREE_PROJECT_CHECKPOINTS.values())

    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    for project_key, checkpoint_keys in _THREE_PROJECT_CHECKPOINTS.items():
        board = projections.project_delivery(operator, project_key)
        assert not isinstance(board, RecordProblem), board
        assert board is not None
        assert {row.checkpoint_key for row in board.rows} == set(checkpoint_keys)
        assert all("source_incomplete" not in row.derivation_reasons for row in board.rows), (
            f"{project_key}'s rows must be source-complete on the seeded corpus"
        )


def _apply_three_project_checkpoints(tenant: TenantFixture, *, now: datetime) -> None:
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
        for project_key, checkpoint_keys in _THREE_PROJECT_CHECKPOINTS.items()
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
                'CURRENT', 'reconcile-snapshot-reads', NULL, %s
            )
            ON CONFLICT (consumer_key, tenant_id, topic) DO UPDATE
            SET acceptance_position = EXCLUDED.acceptance_position,
                health = EXCLUDED.health, detail = EXCLUDED.detail,
                blocked_outbox_id = NULL, updated_at = EXCLUDED.updated_at
            """,
            (tenant.tenant_id, int(row[0]), now),
        )

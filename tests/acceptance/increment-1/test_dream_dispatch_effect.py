"""Stage-walked nightly dream emission, refusal, and output-custody proof."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import load_routine_revisions
from ctower_api.interface import create_app
from ctower_client import CtowerClient, DreamDispatchConsumeRequest, DreamDispatchEffectList
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime import (
    DreamDispatchConsumeCommand,
    DreamDispatchEffect,
    Routine,
)
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()
_OUTPUT_DIGEST = "sha256:" + "d" * 64
_DREAM_EFFECT_COUNT = 4


def test_nightly_dream_dispatch_stage_walk(tenant: TenantFixture) -> None:
    store, effects = _emit_nightly_effects(tenant)
    _bind_lane(
        tenant,
        tenant.operator_id,
        lane_ref="dream-lane:primary",
        model_ref="gpt-5.6-sol",
        model_family="codex",
        reasoning_effort="max",
        model_tier="hard",
    )
    _assert_named_refusals(store, tenant, effects[0].effect_id)
    consumed = _consume_effects(tenant, store)
    assert all(effect.consumption is not None for effect in consumed.effects)
    assert all(
        effect.consumption.output_digest == _OUTPUT_DIGEST
        for effect in consumed.effects
        if effect.consumption
    )
    _assert_output_custody(tenant)


def _emit_nightly_effects(
    tenant: TenantFixture,
) -> tuple[PostgresRuntime, tuple[DreamDispatchEffect, ...]]:
    root = Path(__file__).parents[3]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    revisions = tuple(
        revision
        for revision in load_routine_revisions(root / "packs")
        if revision.handler_kind == "dream_dispatch"
    )
    now = datetime.now(UTC)
    boundary = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if boundary >= now:
        boundary -= timedelta(days=1)
    future = boundary + timedelta(days=2)
    for revision in revisions:
        runtime.register(tenant.tenant_id, revision, first_fire_at=future)

    assert runtime.scan(tenant.tenant_id).dream_dispatches == ()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE routine_triggers SET next_fire_at = %s WHERE tenant_id = %s",
            (boundary, tenant.tenant_id),
        )
    emitted = runtime.scan(tenant.tenant_id)
    assert len(emitted.dream_dispatches) == _DREAM_EFFECT_COUNT
    assert {effect.spec.project_key for effect in emitted.dream_dispatches} == {
        "manibo",
        "ctower",
        "bh-loop",
        None,
    }
    assert all(
        effect.spec.skill_path == "skills/dreamer/SKILL.md" for effect in emitted.dream_dispatches
    )
    assert all(effect.spec.minimum_model_tier == "hard" for effect in emitted.dream_dispatches)
    assert runtime.scan(tenant.tenant_id).dream_dispatches == ()
    return store, emitted.dream_dispatches


def _consume_effects(tenant: TenantFixture, store: PostgresRuntime) -> DreamDispatchEffectList:
    record = PostgresRecord(tenant.database.runtime_dsn)
    with TestClient(create_app(record, dream_dispatch_runtime=store)) as transport:
        client = CtowerClient(str(transport.base_url), credential=tenant.operator_credential)
        client._http.close()
        client._http = transport
        listed = client.list_dream_dispatch_effects()
        assert len(listed.effects) == _DREAM_EFFECT_COUNT
        commands: list[tuple[UUID, UUID]] = []
        for effect in listed.effects:
            command_id = uuid4()
            receipt = client.consume_dream_dispatch_effect(
                effect.effect_id,
                DreamDispatchConsumeRequest(output_digest=_OUTPUT_DIGEST),
                command_id=command_id,
            )
            assert receipt.effect_id == effect.effect_id
            commands.append((effect.effect_id, command_id))
        replay_effect, replay_command = commands[0]
        replay = client.consume_dream_dispatch_effect(
            replay_effect,
            DreamDispatchConsumeRequest(output_digest=_OUTPUT_DIGEST),
            command_id=replay_command,
        )
        assert replay.effect_id == replay_effect
        consumed = client.list_dream_dispatch_effects()
    return consumed


def _assert_output_custody(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        linked = connection.execute(
            """
            SELECT count(*) AS value
            FROM runtime_dream_dispatch_consumptions AS consumption
            JOIN runtime_dream_dispatch_effects AS effect
              ON effect.effect_id = consumption.effect_id
             AND effect.tenant_id = consumption.tenant_id
            JOIN routine_occurrences AS occurrence
              ON occurrence.occurrence_id = effect.occurrence_id
             AND occurrence.tenant_id = effect.tenant_id
            WHERE effect.tenant_id = %s
              AND consumption.output_digest = %s
              AND consumption.lane_ref = 'dream-lane:primary'
            """,
            (tenant.tenant_id, bytes.fromhex("d" * 64)),
        ).fetchone()
    assert linked is not None and linked["value"] == _DREAM_EFFECT_COUNT


def _assert_named_refusals(store: PostgresRuntime, tenant: TenantFixture, effect_id: UUID) -> None:
    cases = (
        ("unbound", None, "dream-dispatch-lane-unbound"),
        ("excluded", ("gpt-5.6-sol", "claude", "max", "hard"), "dream-dispatch-family-excluded"),
        ("cheap", ("gpt-5.6-sol", "codex", "max", "cheap"), "dream-dispatch-tier-refused"),
        (
            "wrong-model",
            ("cheap-model", "codex", "max", "hard"),
            "dream-dispatch-model-requirement-mismatch",
        ),
    )
    for label, binding, code in cases:
        principal_id = _principal(tenant, label)
        if binding is not None:
            _bind_lane(
                tenant,
                principal_id,
                lane_ref=f"dream-lane:{label}",
                model_ref=binding[0],
                model_family=binding[1],
                reasoning_effort=binding[2],
                model_tier=binding[3],
            )
        outcome = store.consume_dream_dispatch(
            Actor(principal_id, tenant.tenant_id, PrincipalKind.COMMANDER),
            DreamDispatchConsumeCommand(uuid4(), effect_id, _OUTPUT_DIGEST),
        )
        assert isinstance(outcome, RecordProblem) and outcome.code == code


def _principal(tenant: TenantFixture, label: str) -> UUID:
    principal_id = uuid4()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled,
                credential_ref, vault_ref, created_at
            ) VALUES (%s, %s, 'commander', %s, false, NULL, %s, transaction_timestamp())
            """,
            (principal_id, tenant.tenant_id, f"Dream {label}", f"vault:dream/{label}"),
        )
    return principal_id


def _bind_lane(
    tenant: TenantFixture,
    principal_id: UUID,
    *,
    lane_ref: str,
    model_ref: str,
    model_family: str,
    reasoning_effort: str,
    model_tier: str,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            INSERT INTO runtime_dream_lane_bindings (
                tenant_id, principal_id, lane_ref, crew_name, harness_ref,
                model_ref, model_family, reasoning_effort, model_tier,
                binding_source, probe_evidence, bound_at
            ) VALUES (%s, %s, %s, 'dream-r368', 'hermes', %s, %s, %s, %s,
                'mission-control', %s, transaction_timestamp())
            """,
            (
                tenant.tenant_id,
                principal_id,
                lane_ref,
                model_ref,
                model_family,
                reasoning_effort,
                model_tier,
                "sha256:" + "e" * 64,
            ),
        )

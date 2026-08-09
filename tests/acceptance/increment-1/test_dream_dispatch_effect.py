"""Stage-walked nightly dream emission, refusal, and output-custody proof."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import permutations
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import load_routine_revisions
from ctower_api.interface import create_app
from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    DreamDispatchConsumeRequest,
    DreamDispatchEffectList,
    DreamLaneBindRequest,
    Problem,
)
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
_PROJECTS = ("ctower", "manibo", "bh-loop")


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
    ctower_effect = next(effect for effect in effects if effect.spec.project_key == "ctower")
    _assert_named_refusals(store, tenant, ctower_effect.effect_id, project_key="ctower")
    consumed = _consume_effects(tenant, store)
    assert all(effect.consumption is not None for effect in consumed.effects)
    assert all(
        effect.consumption.output_digest == _OUTPUT_DIGEST
        for effect in consumed.effects
        if effect.consumption
    )
    _assert_output_custody(tenant)


def test_dream_dispatch_list_and_consumption_are_bound_to_persisted_project_scope(
    tenant: TenantFixture,
) -> None:
    store, effects = _emit_nightly_effects(tenant)
    project_effects = {
        effect.spec.project_key: effect for effect in effects if effect.spec.scope_kind == "project"
    }
    fleet_effect = next(effect for effect in effects if effect.spec.scope_kind == "fleet")
    principals = {project: _project_principal(tenant, project) for project in _PROJECTS}
    _bind_project_lanes(tenant, principals)
    _assert_scoped_lists(store, tenant, effects, principals)
    _assert_cross_scope_refusals(store, tenant, project_effects, fleet_effect, principals)
    project_commands = _consume_authorized_effects(
        store, tenant, project_effects, fleet_effect, principals
    )
    _assert_replay_and_terminal_refusals(
        store, tenant, project_effects, project_commands, principals
    )


def test_operator_binding_is_immutable_refuses_nonoperators_and_enables_consumption(
    tenant: TenantFixture,
) -> None:
    store, effects = _emit_nightly_effects(tenant)
    record = PostgresRecord(tenant.database.runtime_dsn)
    command_id = uuid4()
    request = DreamLaneBindRequest(
        lane_ref="dream-lane:writer-r2881-dream",
        crew_name="writer-r2881-dream",
        harness_ref="codex",
        model_ref="gpt-5.6-sol",
        reasoning_effort="max",
        fallback_model_ref="qwen3.8-max",
        model_tier="hard",
    )
    with TestClient(create_app(record, dream_dispatch_runtime=store)) as transport:
        operator = _client(transport, tenant.operator_credential)
        receipt = operator.bind_dream_lane(request, command_id=command_id)
        replay = operator.bind_dream_lane(request, command_id=command_id)
        assert replay == receipt
        with pytest.raises(CtowerProblemError) as duplicate:
            operator.bind_dream_lane(request, command_id=uuid4())
        duplicate_problem = cast(Problem, duplicate.value.problem)
        assert (duplicate_problem.status, duplicate_problem.code) == (
            409,
            "dream-lane-already-bound",
        )
        commander = _client(transport, tenant.commander_credential)
        with pytest.raises(CtowerProblemError) as refusal:
            commander.bind_dream_lane(request, command_id=uuid4())
        refusal_problem = cast(Problem, refusal.value.problem)
        assert (refusal_problem.status, refusal_problem.code) == (
            403,
            "dream-lane-binding-operator-required",
        )
        for effect in effects:
            consumed = operator.consume_dream_dispatch_effect(
                effect.effect_id,
                DreamDispatchConsumeRequest(output_digest=_OUTPUT_DIGEST),
                command_id=uuid4(),
            )
            assert consumed.effect_id == effect.effect_id

    assert receipt.principal_id == tenant.operator_id
    assert receipt.lane_ref == "dream-lane:writer-r2881-dream"
    _assert_dream_lane_binding(tenant, command_id)
    immutability_states = _assert_dream_lane_binding_is_immutable(tenant)
    recorded = _assert_output_custody(
        tenant,
        lane_ref="dream-lane:writer-r2881-dream",
        crew_name="writer-r2881-dream",
        harness_ref="codex",
    )
    print(
        "TEST-POSTGRES binding_rows=1 binding_events=1 "
        "operator_bind=accepted replay=same distinct_bind=dream-lane-already-bound "
        "non_operator=dream-lane-binding-operator-required "
        f"update_sqlstate={immutability_states[0]} delete_sqlstate={immutability_states[1]} "
        f"generated_consume_requests={len(effects)} recorded_consumptions={recorded}"
    )


def test_operator_recovers_wrong_binding_with_a_new_versioned_lane(
    tenant: TenantFixture,
) -> None:
    store, effects = _emit_nightly_effects(tenant)
    record = PostgresRecord(tenant.database.runtime_dsn)
    wrong = DreamLaneBindRequest(
        lane_ref="dream-lane:writer-r2881-dream",
        crew_name="writer-r2881-wrong",
        harness_ref="codex",
        model_ref="gpt-5.6-sol",
        reasoning_effort="max",
        fallback_model_ref="qwen3.8-max",
        model_tier="hard",
    )
    corrected_same_lane = wrong.model_copy(update={"crew_name": "writer-r2881-dream"})
    recovered = corrected_same_lane.model_copy(
        update={"lane_ref": "dream-lane:writer-r2881-dream.v2"}
    )

    with TestClient(create_app(record, dream_dispatch_runtime=store)) as transport:
        operator = _client(transport, tenant.operator_credential)
        operator.bind_dream_lane(wrong, command_id=uuid4())
        with pytest.raises(CtowerProblemError) as duplicate:
            operator.bind_dream_lane(corrected_same_lane, command_id=uuid4())
        duplicate_problem = cast(Problem, duplicate.value.problem)
        assert (duplicate_problem.status, duplicate_problem.code) == (
            409,
            "dream-lane-already-bound",
        )
        recovery = operator.bind_dream_lane(recovered, command_id=uuid4())
        consumed = operator.consume_dream_dispatch_effect(
            effects[0].effect_id,
            DreamDispatchConsumeRequest(output_digest=_OUTPUT_DIGEST),
            command_id=uuid4(),
        )

    assert recovery.lane_ref == "dream-lane:writer-r2881-dream.v2"
    assert consumed.effect_id == effects[0].effect_id
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        bindings = connection.execute(
            """
            SELECT lane_ref, crew_name
            FROM runtime_dream_lane_bindings
            WHERE tenant_id = %s AND principal_id = %s
            ORDER BY bound_at, lane_ref
            """,
            (tenant.tenant_id, tenant.operator_id),
        ).fetchall()
        consumption = connection.execute(
            """
            SELECT lane_ref, crew_name
            FROM runtime_dream_dispatch_consumptions
            WHERE tenant_id = %s AND effect_id = %s
            """,
            (tenant.tenant_id, effects[0].effect_id),
        ).fetchone()
    assert [(row["lane_ref"], row["crew_name"]) for row in bindings] == [
        ("dream-lane:writer-r2881-dream", "writer-r2881-wrong"),
        ("dream-lane:writer-r2881-dream.v2", "writer-r2881-dream"),
    ]
    assert consumption is not None
    assert (consumption["lane_ref"], consumption["crew_name"]) == (
        "dream-lane:writer-r2881-dream.v2",
        "writer-r2881-dream",
    )


def _bind_project_lanes(tenant: TenantFixture, principals: dict[str, UUID]) -> None:
    for project, principal_id in principals.items():
        _bind_lane(
            tenant,
            principal_id,
            lane_ref=f"dream-lane:{project}",
            model_ref="gpt-5.6-sol",
            model_family="codex",
            reasoning_effort="max",
            model_tier="hard",
        )


def _assert_scoped_lists(
    store: PostgresRuntime,
    tenant: TenantFixture,
    effects: tuple[DreamDispatchEffect, ...],
    principals: dict[str, UUID],
) -> None:
    operator_effects = store.list_dream_dispatches(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    )
    assert {effect.effect_id for effect in operator_effects} == {
        effect.effect_id for effect in effects
    }
    for project, principal_id in principals.items():
        listed = store.list_dream_dispatches(
            Actor(principal_id, tenant.tenant_id, PrincipalKind.COMMANDER)
        )
        assert [(effect.spec.scope_kind, effect.spec.project_key) for effect in listed] == [
            ("project", project)
        ]


def _assert_cross_scope_refusals(
    store: PostgresRuntime,
    tenant: TenantFixture,
    project_effects: dict[str | None, DreamDispatchEffect],
    fleet_effect: DreamDispatchEffect,
    principals: dict[str, UUID],
) -> None:
    for source, target in permutations(_PROJECTS, 2):
        refused = store.consume_dream_dispatch(
            Actor(principals[source], tenant.tenant_id, PrincipalKind.COMMANDER),
            DreamDispatchConsumeCommand(uuid4(), project_effects[target].effect_id, _OUTPUT_DIGEST),
        )
        assert isinstance(refused, RecordProblem) and refused.code == "project-scope-denied"
    for principal_id in principals.values():
        refused = store.consume_dream_dispatch(
            Actor(principal_id, tenant.tenant_id, PrincipalKind.COMMANDER),
            DreamDispatchConsumeCommand(uuid4(), fleet_effect.effect_id, _OUTPUT_DIGEST),
        )
        assert isinstance(refused, RecordProblem) and refused.code == "project-scope-denied"
    assert _consumption_count(tenant) == 0


def _consume_authorized_effects(
    store: PostgresRuntime,
    tenant: TenantFixture,
    project_effects: dict[str | None, DreamDispatchEffect],
    fleet_effect: DreamDispatchEffect,
    principals: dict[str, UUID],
) -> dict[str, DreamDispatchConsumeCommand]:
    project_commands: dict[str, DreamDispatchConsumeCommand] = {}
    for project, principal_id in principals.items():
        command = DreamDispatchConsumeCommand(
            uuid4(), project_effects[project].effect_id, _OUTPUT_DIGEST
        )
        project_commands[project] = command
        receipt = store.consume_dream_dispatch(
            Actor(principal_id, tenant.tenant_id, PrincipalKind.COMMANDER),
            command,
        )
        assert not isinstance(receipt, RecordProblem)
    _bind_lane(
        tenant,
        tenant.operator_id,
        lane_ref="dream-lane:fleet",
        model_ref="gpt-5.6-sol",
        model_family="codex",
        reasoning_effort="max",
        model_tier="hard",
    )
    fleet_receipt = store.consume_dream_dispatch(
        Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR),
        DreamDispatchConsumeCommand(uuid4(), fleet_effect.effect_id, _OUTPUT_DIGEST),
    )
    assert not isinstance(fleet_receipt, RecordProblem)
    assert _consumption_count(tenant) == _DREAM_EFFECT_COUNT
    return project_commands


def _assert_replay_and_terminal_refusals(
    store: PostgresRuntime,
    tenant: TenantFixture,
    project_effects: dict[str | None, DreamDispatchEffect],
    project_commands: dict[str, DreamDispatchConsumeCommand],
    principals: dict[str, UUID],
) -> None:
    ctower_actor = Actor(principals["ctower"], tenant.tenant_id, PrincipalKind.COMMANDER)
    replayed = store.consume_dream_dispatch(ctower_actor, project_commands["ctower"])
    assert not isinstance(replayed, RecordProblem)
    conflicting = store.consume_dream_dispatch(
        ctower_actor,
        DreamDispatchConsumeCommand(
            project_commands["ctower"].client_command_id,
            project_effects["ctower"].effect_id,
            "sha256:" + "e" * 64,
        ),
    )
    assert isinstance(conflicting, RecordProblem) and conflicting.code == "idempotency-conflict"
    already_consumed = store.consume_dream_dispatch(
        ctower_actor,
        DreamDispatchConsumeCommand(uuid4(), project_effects["ctower"].effect_id, _OUTPUT_DIGEST),
    )
    assert (
        isinstance(already_consumed, RecordProblem)
        and already_consumed.code == "dream-dispatch-already-consumed"
    )
    unavailable = store.consume_dream_dispatch(
        ctower_actor,
        DreamDispatchConsumeCommand(uuid4(), uuid4(), _OUTPUT_DIGEST),
    )
    assert (
        isinstance(unavailable, RecordProblem) and unavailable.code == "dream-dispatch-unavailable"
    )
    assert _consumption_count(tenant) == _DREAM_EFFECT_COUNT


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


def _client(transport: TestClient, credential: str) -> CtowerClient:
    client = CtowerClient(str(transport.base_url), credential=credential)
    client._http.close()
    client._http = transport
    return client


def _assert_dream_lane_binding(tenant: TenantFixture, command_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT binding.*, event.kind, event.payload, event.client_command_id,
                   event.correlation_id, outbox.topic,
                   count(*) OVER () AS binding_count
            FROM runtime_dream_lane_bindings AS binding
            JOIN events AS event
              ON event.tenant_id = binding.tenant_id
             AND event.aggregate_id = binding.principal_id
             AND event.kind = 'runtime.dream_lane_bound'
            JOIN outbox
              ON outbox.tenant_id = event.tenant_id
             AND outbox.event_id = event.event_id
            WHERE binding.tenant_id = %s
            """,
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    assert row["binding_count"] == 1
    assert row["principal_id"] == tenant.operator_id
    assert row["crew_name"] == "writer-r2881-dream"
    assert row["harness_ref"] == "codex"
    assert row["model_ref"] == "gpt-5.6-sol"
    assert row["model_family"] == "codex"
    assert row["reasoning_effort"] == "max"
    assert row["model_tier"] == "hard"
    assert row["binding_source"] == "operator-ceremony"
    assert row["client_command_id"] == command_id
    assert row["correlation_id"] == command_id
    assert row["topic"] == "runtime.dream-lane-bindings"
    assert row["payload"] == {
        "binding_source": "operator-ceremony",
        "crew_name": "writer-r2881-dream",
        "fallback_model_ref": "qwen3.8-max",
        "harness_ref": "codex",
        "lane_ref": "dream-lane:writer-r2881-dream",
        "model_family": "codex",
        "model_ref": "gpt-5.6-sol",
        "model_tier": "hard",
        "principal_id": str(tenant.operator_id),
        "probe_evidence": row["probe_evidence"],
        "reasoning_effort": "max",
    }


def _assert_dream_lane_binding_is_immutable(tenant: TenantFixture) -> tuple[str, str]:
    statements = (
        "UPDATE runtime_dream_lane_bindings SET lane_ref = 'dream-lane:changed'",
        "DELETE FROM runtime_dream_lane_bindings",
    )
    sqlstates: list[str] = []
    for statement in statements:
        with (
            psycopg.connect(tenant.database.admin_dsn) as connection,
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState) as refusal,
        ):
            connection.execute(statement)
        assert refusal.value.sqlstate is not None
        sqlstates.append(refusal.value.sqlstate)
    assert len(sqlstates) == len(statements)
    return sqlstates[0], sqlstates[1]


def _assert_output_custody(
    tenant: TenantFixture,
    *,
    lane_ref: str = "dream-lane:primary",
    crew_name: str = "dream-r368",
    harness_ref: str = "hermes",
) -> int:
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
            JOIN events AS event
              ON event.event_id = consumption.event_id
             AND event.tenant_id = consumption.tenant_id
            WHERE effect.tenant_id = %s
              AND consumption.output_digest = %s
              AND consumption.executor_principal_id = %s
              AND consumption.lane_ref = %s
              AND consumption.crew_name = %s
              AND consumption.harness_ref = %s
              AND consumption.model_ref = 'gpt-5.6-sol'
              AND consumption.model_family = 'codex'
              AND consumption.reasoning_effort = 'max'
              AND consumption.model_tier = 'hard'
              AND event.kind = 'runtime.dream_dispatch_consumed'
            """,
            (
                tenant.tenant_id,
                bytes.fromhex("d" * 64),
                tenant.operator_id,
                lane_ref,
                crew_name,
                harness_ref,
            ),
        ).fetchone()
    assert linked is not None and linked["value"] == _DREAM_EFFECT_COUNT
    return int(linked["value"])


def _assert_named_refusals(
    store: PostgresRuntime,
    tenant: TenantFixture,
    effect_id: UUID,
    *,
    project_key: str,
) -> None:
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
        principal_id = _principal(tenant, label, project_key=project_key)
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


def _principal(tenant: TenantFixture, label: str, *, project_key: str | None = None) -> UUID:
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
        if project_key is not None:
            connection.execute(
                """
                INSERT INTO project_seats (
                    principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
                ) VALUES (%s, %s, %s, %s, %s, transaction_timestamp())
                """,
                (
                    principal_id,
                    tenant.tenant_id,
                    project_key,
                    f"dream-{label}",
                    tenant.operator_id,
                ),
            )
    return principal_id


def _project_principal(tenant: TenantFixture, project_key: str) -> UUID:
    if project_key == "ctower":
        return tenant.commander_id
    return _principal(tenant, project_key, project_key=project_key)


def _consumption_count(tenant: TenantFixture) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM runtime_dream_dispatch_consumptions WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


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

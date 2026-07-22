"""Real PostgreSQL 17 evidence for Record's off-host durability authority."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from support.durability_assertions import (
    acceptance_position as _acceptance_position,
)
from support.durability_assertions import (
    add_relation as _add_relation,
)
from support.durability_assertions import (
    assert_ack_without_finalization as _assert_ack_without_finalization,
)
from support.durability_assertions import (
    assert_exact_refusal as _assert_exact_refusal,
)
from support.durability_assertions import (
    assert_no_relation as _assert_no_relation,
)
from support.durability_assertions import (
    assert_one_result_and_ack as _assert_one_result_and_ack,
)
from support.durability_assertions import (
    assert_primary_evidence as _assert_primary_evidence,
)
from support.durability_assertions import (
    assert_primary_loss_boundary as _assert_primary_loss_boundary,
)
from support.durability_assertions import (
    assert_primary_only_result as _assert_primary_only_result,
)
from support.durability_assertions import (
    assert_replay_without_receipt as _assert_replay_without_receipt,
)
from support.durability_assertions import (
    assert_secret_free_telemetry as _assert_secret_free_telemetry,
)
from support.durability_assertions import (
    change_priority as _change_priority,
)
from support.durability_assertions import (
    create_ticket as _create_ticket,
)
from support.durability_assertions import (
    database_now as _database_now,
)
from support.durability_assertions import (
    install_ack_delay as _install_ack_delay,
)
from support.durability_assertions import (
    install_finalization_refusal as _install_finalization_refusal,
)
from support.durability_assertions import (
    remove_ack_delay as _remove_ack_delay,
)
from support.durability_assertions import (
    remove_finalization_refusal as _remove_finalization_refusal,
)
from support.durability_assertions import (
    semantic_without_durability as _semantic_without_durability,
)
from support.durability_assertions import (
    set_mode as _set_mode,
)
from support.durability_assertions import (
    set_target as _set_target,
)
from support.durability_finalization import (
    AmbiguousFinalization as _AmbiguousFinalization,
)
from support.durability_finalization import (
    assert_promoted_replay as _assert_promoted_replay,
)
from support.durability_finalization import (
    assert_receipt_mismatches_are_rejected as _assert_receipt_mismatches_are_rejected,
)
from support.durability_finalization import (
    create_ambiguous_finalization as _create_ambiguous_finalization,
)
from support.durability_health import (
    assert_live_health_faults,
    unreadable_standby_replay_evidence,
)
from support.durability_serialization import assert_subject_serialization
from support.postgres import (
    DatabaseFixture,
    DurabilityPair,
    create_durability_database,
    start_durability_pair,
    stop_durability_pair,
    wait_for_durability_replay_current,
)
from support.tenant_fixture import TenantFixture, create_first_tenant

from ctower_api.interface import create_app
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.record import DurabilityHealth, DurabilityHealthStatus
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()

HTTP_ACCEPTED = 201
HTTP_PENDING = 202
HTTP_CONFLICT = 409
HTTP_OK = 200
BOUND_SECONDS = 8.0
SHA256_BYTES = 32


@dataclass(frozen=True, slots=True)
class _AuthorityFixture:
    pair: DurabilityPair
    database: DatabaseFixture
    pending_only_health: DurabilityHealth
    standby_dsn: str
    tenant: TenantFixture


@pytest.fixture(scope="module")
def authority() -> Iterator[_AuthorityFixture]:
    """Provision one exact named physical standby and leave production defaults untouched."""

    pair = start_durability_pair()
    try:
        database, standby_dsn = create_durability_database(pair)
        tenant = create_first_tenant(database)
        pending_only_health = PostgresRecord(database.runtime_dsn).durability_health(
            now=_database_now(database.admin_dsn)
        )
        with psycopg.connect(database.admin_dsn) as connection:
            connection.execute(
                """
                UPDATE durability_policy_state
                SET policy_ref = 'ctower.cutover-rpo0@1', mode = 'cutover_rpo0',
                    standby_identity = 'ctower_i1_standby', configured_at = clock_timestamp()
                WHERE singleton
                """
            )
        wait_for_durability_replay_current(pair)
        yield _AuthorityFixture(pair, database, pending_only_health, standby_dsn, tenant)
    finally:
        stop_durability_pair(pair)


@pytest.mark.parametrize(
    ("malformed", "reason"),
    [(False, "replay_evidence_unreadable"), (True, "target_evidence_unreadable")],
)
def test_unreadable_standby_replay_evidence_fails_closed(
    authority: _AuthorityFixture, *, malformed: bool, reason: str
) -> None:
    record = PostgresRecord(authority.database.runtime_dsn, standby_dsn=authority.standby_dsn)

    with unreadable_standby_replay_evidence(authority.database.admin_dsn, malformed=malformed):
        health = record.durability_health(now=_database_now(authority.database.admin_dsn))

    assert health.status is DurabilityHealthStatus.DEGRADED
    assert health.reason == reason


def test_named_standby_authority_is_replay_safe_and_fail_closed(
    authority: _AuthorityFixture,
) -> None:
    assert authority.pending_only_health.status is DurabilityHealthStatus.STATE_UNKNOWN
    assert authority.pending_only_health.reason == "pending_only"
    unconfigured = PostgresRecord(authority.database.runtime_dsn).durability_health(
        now=_database_now(authority.database.admin_dsn)
    )
    unavailable = PostgresRecord(
        authority.database.runtime_dsn,
        standby_dsn="postgresql://postgres@127.0.0.1:1/ctower?connect_timeout=1",
    ).durability_health(now=_database_now(authority.database.admin_dsn))
    assert unconfigured.status is DurabilityHealthStatus.STATE_UNKNOWN
    assert unconfigured.reason == "standby_unconfigured"
    assert unavailable.status is DurabilityHealthStatus.DEGRADED
    assert unavailable.reason == "target_not_live"
    captures: list[dict[str, object]] = []
    recorder = TelemetryRecorder(captures.append)
    record = PostgresRecord(
        authority.database.runtime_dsn,
        standby_dsn=authority.standby_dsn,
        telemetry=recorder,
    )
    app = create_app(
        record,
        work=Work(
            record,
            writer=PostgresWork(authority.database.runtime_dsn),
            telemetry=recorder,
        ),
        telemetry=recorder,
    )
    assert_live_health_faults(record, authority.pair, authority.database)

    with (
        TestClient(app, client=("127.0.0.1", 51000)) as client,
        TestClient(app, client=("127.0.0.1", 51001)) as concurrent_client,
    ):
        _same_command_id_is_principal_scoped(client, authority)
        _accepted_replay_survives_policy_pending(client, authority)
        _unfinalized_ack_remains_pending(client, authority)
        accepted = _accepted_replay_and_conflict(client, authority)
        _response_loss_replays_exactly(client, authority)
        _wrong_target_recovers_on_same_key(client, authority, record)
        _replay_before_receipt_recovers_on_same_key(client, authority)
        _accepted_relation_moves_both_ticket_heads(client, authority)
        _assert_receipt_mismatches_are_rejected(client, authority)
        _assert_primary_evidence(authority, accepted)
        local_commands, ambiguity = _standby_loss_is_bounded_and_dependency_safe(
            client, concurrent_client, authority
        )

    _assert_secret_free_telemetry(captures, authority.tenant)
    _assert_primary_loss_boundary(authority, accepted, local_commands)
    _assert_promoted_replay(authority, ambiguity)


def _accepted_replay_survives_policy_pending(
    client: TestClient, authority: _AuthorityFixture
) -> None:
    command_id = uuid4()
    first = _create_ticket(client, authority.tenant, command_id, title="Monotonic acceptance")
    position = _acceptance_position(authority, command_id)
    _set_mode(authority, "pending_only")
    try:
        replay = _create_ticket(client, authority.tenant, command_id, title="Monotonic acceptance")
    finally:
        _set_mode(authority, "cutover_rpo0")

    assert first.status_code == HTTP_ACCEPTED
    assert replay.status_code == HTTP_ACCEPTED
    assert replay.content == first.content
    assert _acceptance_position(authority, command_id) == position


def _same_command_id_is_principal_scoped(client: TestClient, authority: _AuthorityFixture) -> None:
    command_id = uuid4()
    operator = _create_ticket(
        client,
        authority.tenant,
        command_id,
        title="Operator command identity",
        credential=authority.tenant.operator_credential,
    )
    commander = _create_ticket(
        client,
        authority.tenant,
        command_id,
        title="Commander command identity",
        credential=authority.tenant.commander_credential,
    )
    operator_replay = _create_ticket(
        client,
        authority.tenant,
        command_id,
        title="Operator command identity",
        credential=authority.tenant.operator_credential,
    )
    commander_replay = _create_ticket(
        client,
        authority.tenant,
        command_id,
        title="Commander command identity",
        credential=authority.tenant.commander_credential,
    )

    assert operator.status_code == HTTP_ACCEPTED
    assert commander.status_code == HTTP_ACCEPTED
    assert operator.content == operator_replay.content
    assert commander.content == commander_replay.content
    assert operator.json()["ticket"]["ticket_id"] != commander.json()["ticket"]["ticket_id"]


def _accepted_replay_and_conflict(
    client: TestClient, authority: _AuthorityFixture
) -> tuple[UUID, UUID]:
    command_id = uuid4()
    first = _create_ticket(client, authority.tenant, command_id, title="Accepted authority")
    replay = _create_ticket(client, authority.tenant, command_id, title="Accepted authority")
    changed = _create_ticket(client, authority.tenant, command_id, title="Changed request")

    assert first.status_code == HTTP_ACCEPTED
    assert first.json()["durability_state"] == "accepted"
    assert replay.status_code == HTTP_ACCEPTED
    assert replay.content == first.content
    assert replay.json()["event_ids"] == first.json()["event_ids"]
    assert changed.status_code == HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"
    return command_id, UUID(cast(str, first.json()["ticket"]["ticket_id"]))


def _unfinalized_ack_remains_pending(client: TestClient, authority: _AuthorityFixture) -> None:
    command_id = uuid4()
    _install_finalization_refusal(authority.database.admin_dsn)
    try:
        first = _create_ticket(client, authority.tenant, command_id, title="Unfinalized ACK")
    finally:
        _remove_finalization_refusal(authority.database.admin_dsn)
    _assert_ack_without_finalization(authority, command_id)
    _set_mode(authority, "pending_only")
    try:
        replay = _create_ticket(client, authority.tenant, command_id, title="Unfinalized ACK")
    finally:
        _set_mode(authority, "cutover_rpo0")

    assert first.status_code == HTTP_PENDING
    assert replay.status_code == HTTP_PENDING
    assert replay.content == first.content
    _assert_ack_without_finalization(authority, command_id)


def _response_loss_replays_exactly(client: TestClient, authority: _AuthorityFixture) -> None:
    command_id = uuid4()
    _create_ticket(client, authority.tenant, command_id, title="Discarded first response")
    replay = _create_ticket(client, authority.tenant, command_id, title="Discarded first response")
    assert replay.status_code == HTTP_ACCEPTED
    assert replay.json()["durability_state"] == "accepted"
    _assert_one_result_and_ack(authority, command_id)


def _wrong_target_recovers_on_same_key(
    client: TestClient, authority: _AuthorityFixture, record: PostgresRecord
) -> None:
    _set_target(authority, "wrong_standby_identity")
    command_id = uuid4()
    pending = _create_ticket(client, authority.tenant, command_id, title="Wrong named target")
    health = record.durability_health(now=_database_now(authority.database.admin_dsn))
    assert pending.status_code == HTTP_PENDING
    assert pending.headers["Retry-After"] == "1"
    assert pending.json()["durability_state"] == "durability_pending"
    assert health.status is DurabilityHealthStatus.DEGRADED
    _assert_replay_without_receipt(authority, command_id)

    _set_target(authority, "ctower_i1_standby")
    accepted = _create_ticket(client, authority.tenant, command_id, title="Wrong named target")
    healthy = record.durability_health(now=_database_now(authority.database.admin_dsn))
    assert accepted.status_code == HTTP_ACCEPTED
    assert healthy.status is DurabilityHealthStatus.HEALTHY
    assert healthy.acceptance_position is not None
    assert _semantic_without_durability(accepted.json()) == _semantic_without_durability(
        pending.json()
    )
    assert accepted.json()["event_ids"] == pending.json()["event_ids"]


def _replay_before_receipt_recovers_on_same_key(
    client: TestClient, authority: _AuthorityFixture
) -> None:
    _install_ack_delay(authority.database.admin_dsn)
    command_id = uuid4()
    try:
        started = time.monotonic()
        pending = _create_ticket(client, authority.tenant, command_id, title="Delayed receipt")
        elapsed = time.monotonic() - started
    finally:
        _remove_ack_delay(authority.database.admin_dsn)

    assert pending.status_code == HTTP_PENDING
    assert pending.headers["Retry-After"] == "1"
    assert elapsed < BOUND_SECONDS
    _assert_replay_without_receipt(authority, command_id)

    accepted = _create_ticket(client, authority.tenant, command_id, title="Delayed receipt")
    assert accepted.status_code == HTTP_ACCEPTED
    assert _semantic_without_durability(accepted.json()) == _semantic_without_durability(
        pending.json()
    )
    assert accepted.json()["event_ids"] == pending.json()["event_ids"]


def _standby_loss_is_bounded_and_dependency_safe(
    client: TestClient,
    concurrent_client: TestClient,
    authority: _AuthorityFixture,
) -> tuple[tuple[UUID, ...], _AmbiguousFinalization]:
    setup = _prepare_standby_loss(client, authority)
    ambiguity = _create_ambiguous_finalization(concurrent_client, authority)
    accepted_replay = _create_ticket(
        client, authority.tenant, setup.accepted_command, title="Accepted before standby loss"
    )
    assert accepted_replay.status_code == HTTP_ACCEPTED
    assert accepted_replay.content == setup.accepted_content
    assert _acceptance_position(authority, setup.accepted_command) == setup.position
    serialization_commands = assert_subject_serialization(
        client,
        concurrent_client,
        authority.tenant,
        authority.database,
        setup.serialization_ticket_id,
    )
    local_commands = _exercise_pending_dependencies(client, authority, setup)
    return (*local_commands, *serialization_commands), ambiguity


@dataclass(frozen=True, slots=True)
class _LossSetup:
    accepted_command: UUID
    accepted_content: bytes
    position: int
    relation_source_id: UUID
    serialization_ticket_id: UUID
    unrelated_ticket_id: UUID


def _prepare_standby_loss(client: TestClient, authority: _AuthorityFixture) -> _LossSetup:
    accepted_command = uuid4()
    accepted = _create_ticket(
        client, authority.tenant, accepted_command, title="Accepted before standby loss"
    )
    relation_source = _create_ticket(
        client, authority.tenant, uuid4(), title="Accepted relation source"
    )
    unrelated_ticket = _create_ticket(
        client, authority.tenant, uuid4(), title="Accepted unrelated ticket"
    )
    serialization_ticket = _create_ticket(
        client, authority.tenant, uuid4(), title="Serialized subject boundary"
    )
    relation_source_id = UUID(cast(str, relation_source.json()["ticket"]["ticket_id"]))
    unrelated_ticket_id = UUID(cast(str, unrelated_ticket.json()["ticket"]["ticket_id"]))
    serialization_ticket_id = UUID(cast(str, serialization_ticket.json()["ticket"]["ticket_id"]))
    position = _acceptance_position(authority, accepted_command)
    assert accepted.status_code == HTTP_ACCEPTED
    assert relation_source.status_code == HTTP_ACCEPTED
    assert unrelated_ticket.status_code == HTTP_ACCEPTED
    assert serialization_ticket.status_code == HTTP_ACCEPTED
    return _LossSetup(
        accepted_command,
        accepted.content,
        position,
        relation_source_id,
        serialization_ticket_id,
        unrelated_ticket_id,
    )


def _exercise_pending_dependencies(
    client: TestClient, authority: _AuthorityFixture, setup: _LossSetup
) -> tuple[UUID, ...]:
    pending_command = uuid4()
    started = time.monotonic()
    pending = _create_ticket(
        client,
        authority.tenant,
        pending_command,
        title="Primary-local before replay",
    )
    elapsed = time.monotonic() - started
    pending_ticket = UUID(cast(str, pending.json()["ticket"]["ticket_id"]))
    assert pending.status_code == HTTP_PENDING
    assert pending.headers["Retry-After"] == "1"
    assert elapsed < BOUND_SECONDS
    _assert_primary_only_result(authority.database.admin_dsn, pending_command)

    relation_command = uuid4()
    relation = _add_relation(
        client,
        authority.tenant,
        setup.relation_source_id,
        pending_ticket,
        relation_command,
    )
    assert relation.status_code == HTTP_CONFLICT
    assert relation.json()["code"] == "durability_pending"
    _assert_exact_refusal(authority.database.admin_dsn, relation_command)
    _assert_no_relation(authority, setup.relation_source_id, pending_ticket)

    unrelated_progress_command = uuid4()
    unrelated_progress = _change_priority(
        client,
        authority.tenant,
        setup.unrelated_ticket_id,
        unrelated_progress_command,
    )
    assert unrelated_progress.status_code == HTTP_PENDING

    refusal_command = uuid4()
    refused = _change_priority(
        client,
        authority.tenant,
        pending_ticket,
        refusal_command,
    )
    assert refused.status_code == HTTP_CONFLICT
    assert refused.json()["code"] == "durability_pending"
    _assert_exact_refusal(authority.database.admin_dsn, refusal_command)

    unrelated_command = uuid4()
    unrelated = _create_ticket(
        client,
        authority.tenant,
        unrelated_command,
        title="Unrelated local progress",
    )
    assert unrelated.status_code == HTTP_PENDING
    assert UUID(cast(str, unrelated.json()["ticket"]["ticket_id"])) != pending_ticket
    return (
        pending_command,
        refusal_command,
        unrelated_command,
        relation_command,
        unrelated_progress_command,
    )


def _accepted_relation_moves_both_ticket_heads(
    client: TestClient, authority: _AuthorityFixture
) -> None:
    source = _create_ticket(client, authority.tenant, uuid4(), title="Relation head source")
    target = _create_ticket(client, authority.tenant, uuid4(), title="Relation head target")
    source_id = UUID(cast(str, source.json()["ticket"]["ticket_id"]))
    target_id = UUID(cast(str, target.json()["ticket"]["ticket_id"]))
    command_id = uuid4()
    relation = _add_relation(client, authority.tenant, source_id, target_id, command_id)
    replay = _add_relation(client, authority.tenant, source_id, target_id, command_id)

    assert relation.status_code == HTTP_OK
    assert replay.content == relation.content
    event_id = UUID(cast(str, relation.json()["event_ids"][0]))
    with psycopg.connect(authority.database.admin_dsn) as connection:
        links = connection.execute(
            """
            SELECT subject_kind, subject_id FROM event_links
            WHERE tenant_id = %s AND event_id = %s
            """,
            (authority.tenant.tenant_id, event_id),
        ).fetchall()
        heads = connection.execute(
            """
            SELECT subject_id, principal_id, client_command_id
            FROM durability_subject_heads
            WHERE tenant_id = %s AND subject_kind = 'ticket' AND subject_id = ANY(%s)
            """,
            (authority.tenant.tenant_id, [source_id, target_id]),
        ).fetchall()
    assert {row for row in links if row[0] == "ticket"} == {
        ("ticket", source_id),
        ("ticket", target_id),
    }
    assert set(heads) == {
        (source_id, authority.tenant.commander_id, command_id),
        (target_id, authority.tenant.commander_id, command_id),
    }

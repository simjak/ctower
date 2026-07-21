"""Fail-closed live health evidence for the named durability standby."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import DurabilityHealth, DurabilityHealthStatus
from ctower_kernel.record.transaction import authority_connection

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Policy:
    policy_ref: str
    mode: str
    standby_application_name: str
    standby_identity: str


@dataclass(frozen=True, slots=True)
class _PrimaryEvidence:
    policy: _Policy
    acceptance_position: int | None
    synchronous_standby_names: str
    system_identifier: int
    timeline_id: int
    flush_lsn: str
    matching_sender_count: int
    application_name: str | None
    replication_state: str | None
    sync_state: str | None
    replay_lsn: str | None


@dataclass(frozen=True, slots=True)
class _StandbyEvidence:
    cluster_name: str
    system_identifier: int
    timeline_id: int
    replay_lsn: str
    in_recovery: bool
    replay_paused: bool
    matching_receiver_count: int
    receiver_status: str | None


def durability_health(
    primary_dsn: str, standby_dsn: str | None, *, now: datetime
) -> DurabilityHealth:
    """Return healthy only for one live, synchronous, exactly-current standby."""

    try:
        primary = _primary_evidence(primary_dsn)
    except (psycopg.Error, RuntimeError, ValueError):
        return _health(
            DurabilityHealthStatus.STATE_UNKNOWN,
            "unavailable",
            "unknown",
            None,
            now,
            "primary_unavailable",
        )
    policy = primary.policy
    if policy.mode == "pending_only":
        return _health(
            DurabilityHealthStatus.STATE_UNKNOWN,
            policy.policy_ref,
            policy.standby_identity,
            primary.acceptance_position,
            now,
            "pending_only",
        )
    if standby_dsn is None:
        return _health(
            DurabilityHealthStatus.STATE_UNKNOWN,
            policy.policy_ref,
            policy.standby_identity,
            primary.acceptance_position,
            now,
            "standby_unconfigured",
        )
    try:
        standby = _standby_evidence(standby_dsn)
    except (psycopg.Error, ValueError):
        return _health(
            DurabilityHealthStatus.DEGRADED,
            policy.policy_ref,
            policy.standby_identity,
            primary.acceptance_position,
            now,
            "target_not_live",
        )
    failure = _live_target_failure(primary, standby)
    return _health(
        DurabilityHealthStatus.HEALTHY if failure is None else DurabilityHealthStatus.DEGRADED,
        policy.policy_ref,
        policy.standby_identity,
        primary.acceptance_position,
        now,
        "target_ready" if failure is None else failure,
    )


def _primary_evidence(dsn: str) -> _PrimaryEvidence:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        policy_row = connection.execute(
            """
            SELECT policy_ref, mode, standby_application_name, standby_identity
            FROM durability_policy_state WHERE singleton
            """
        ).fetchone()
        if policy_row is None:
            raise RuntimeError("durability policy is unavailable")
        policy = _Policy(
            str(policy_row["policy_ref"]),
            str(policy_row["mode"]),
            str(policy_row["standby_application_name"]),
            str(policy_row["standby_identity"]),
        )
        position_row = connection.execute(
            """
            SELECT max(acceptance_position) AS value
            FROM durability_acceptance_finalizations
            """
        ).fetchone()
        state = connection.execute(
            "SELECT * FROM public.durability_primary_live_evidence()"
        ).fetchone()
    if state is None:
        raise ValueError("primary durability evidence is unavailable")
    value = position_row["value"] if position_row is not None else None
    return _PrimaryEvidence(
        policy,
        int(cast(int, value)) if value is not None else None,
        str(state["synchronous_standby_names"]),
        int(str(state["system_identifier"])),
        int(cast(int, state["timeline_id"])),
        str(state["primary_flush_lsn"]),
        int(cast(int, state["matching_sender_count"])),
        None if state["application_name"] is None else str(state["application_name"]),
        None if state["replication_state"] is None else str(state["replication_state"]),
        None if state["sync_state"] is None else str(state["sync_state"]),
        None if state["replay_lsn"] is None else str(state["replay_lsn"]),
    )


def _standby_evidence(dsn: str) -> _StandbyEvidence:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        state = connection.execute(
            "SELECT * FROM public.durability_standby_live_evidence()"
        ).fetchone()
    if state is None:
        raise ValueError("standby durability evidence is unavailable")
    return _StandbyEvidence(
        cluster_name=str(state["cluster_name"]),
        system_identifier=int(str(state["system_identifier"])),
        timeline_id=int(cast(int, state["timeline_id"])),
        replay_lsn=str(state["replay_lsn"]),
        in_recovery=bool(state["in_recovery"]),
        replay_paused=bool(state["replay_paused"]),
        matching_receiver_count=int(cast(int, state["matching_receiver_count"])),
        receiver_status=(
            None if state["receiver_status"] is None else str(state["receiver_status"])
        ),
    )


def _live_target_failure(primary: _PrimaryEvidence, standby: _StandbyEvidence) -> str | None:
    policy = primary.policy
    normalized = "".join(primary.synchronous_standby_names.split()).casefold()
    expected = f"first1({policy.standby_application_name})".casefold()
    sender_ready = all(
        (
            primary.matching_sender_count == 1,
            primary.application_name == policy.standby_application_name,
            primary.replication_state == "streaming",
            primary.sync_state == "sync",
            primary.replay_lsn is not None,
        )
    )
    identity_ready = all(
        (
            standby.cluster_name == policy.standby_identity,
            standby.in_recovery,
            standby.system_identifier == primary.system_identifier,
            standby.timeline_id == primary.timeline_id,
        )
    )
    receiver_ready = all(
        (standby.matching_receiver_count == 1, standby.receiver_status == "streaming")
    )
    current = (
        primary.replay_lsn is not None
        and _lsn_position(primary.replay_lsn) >= _lsn_position(primary.flush_lsn)
        and _lsn_position(standby.replay_lsn) >= _lsn_position(primary.flush_lsn)
    )
    failures = (
        ("target_config_mismatch", normalized != expected),
        ("sender_not_live", not sender_ready),
        ("target_mismatch", not identity_ready),
        ("replay_paused", standby.replay_paused),
        ("receiver_not_live", not receiver_ready),
        ("replay_not_current", not current),
    )
    return next((reason for reason, failed in failures if failed), None)


def _health(
    status: DurabilityHealthStatus,
    policy_ref: str,
    standby_identity: str,
    acceptance_position: int | None,
    now: datetime,
    reason: str,
) -> DurabilityHealth:
    return DurabilityHealth(
        status,
        policy_ref,
        standby_identity,
        acceptance_position,
        now,
        reason,
    )


def _lsn_position(value: str) -> int:
    high, low = value.split("/", maxsplit=1)
    return (int(high, 16) << 32) | int(low, 16)

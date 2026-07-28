"""Fail-closed live health evidence for the named durability standby."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

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
    replay_lsn: str | None
    in_recovery: bool
    replay_paused: bool
    matching_receiver_count: int
    receiver_status: str | None


def durability_health(
    primary_dsn: str, standby_dsn: str | None, *, now: datetime
) -> DurabilityHealth:
    """Return healthy only for one live, synchronous, exactly-current standby."""

    primary = _read_primary_health(primary_dsn, now=now)
    if isinstance(primary, DurabilityHealth):
        return primary
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
    standby = _read_standby_health(standby_dsn, primary, now=now)
    if isinstance(standby, DurabilityHealth):
        return standby
    failure = _validated_target_failure(primary, standby)
    if failure is None and policy.mode == "development_offhost_ack":
        return _health(
            DurabilityHealthStatus.DEGRADED,
            policy.policy_ref,
            policy.standby_identity,
            primary.acceptance_position,
            now,
            "development_offhost_ack_cp3_d_not_proven",
        )
    return _health(
        DurabilityHealthStatus.HEALTHY if failure is None else DurabilityHealthStatus.DEGRADED,
        policy.policy_ref,
        policy.standby_identity,
        primary.acceptance_position,
        now,
        "target_ready" if failure is None else failure,
    )


def _read_primary_health(primary_dsn: str, *, now: datetime) -> _PrimaryEvidence | DurabilityHealth:
    try:
        return _primary_evidence(primary_dsn)
    except (psycopg.Error, RuntimeError, KeyError, TypeError, ValueError) as error:
        reason = (
            "primary_unavailable"
            if isinstance(error, (psycopg.Error, RuntimeError))
            else "primary_evidence_unreadable"
        )
        return _health(
            DurabilityHealthStatus.STATE_UNKNOWN,
            "unavailable",
            "unknown",
            None,
            now,
            reason,
        )


def _read_standby_health(
    standby_dsn: str, primary: _PrimaryEvidence, *, now: datetime
) -> _StandbyEvidence | DurabilityHealth:
    policy = primary.policy
    try:
        return _standby_evidence(standby_dsn)
    except psycopg.Error:
        return _health(
            DurabilityHealthStatus.DEGRADED,
            policy.policy_ref,
            policy.standby_identity,
            primary.acceptance_position,
            now,
            "target_not_live",
        )
    except (KeyError, TypeError, ValueError):
        return _health(
            DurabilityHealthStatus.DEGRADED,
            policy.policy_ref,
            policy.standby_identity,
            primary.acceptance_position,
            now,
            "target_evidence_unreadable",
        )


def _validated_target_failure(primary: _PrimaryEvidence, standby: _StandbyEvidence) -> str | None:
    try:
        return _live_target_failure(primary, standby)
    except (TypeError, ValueError):
        return "target_evidence_unreadable"


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
            _required_text(policy_row["policy_ref"]),
            _required_text(policy_row["mode"]),
            _required_text(policy_row["standby_application_name"]),
            _required_text(policy_row["standby_identity"]),
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
        _optional_positive_integer(value),
        _required_text(state["synchronous_standby_names"], allow_empty=True),
        _positive_integer(state["system_identifier"]),
        _positive_integer(state["timeline_id"]),
        _required_lsn(state["primary_flush_lsn"]),
        _nonnegative_integer(state["matching_sender_count"]),
        _optional_text(state["application_name"]),
        _optional_text(state["replication_state"]),
        _optional_text(state["sync_state"]),
        _optional_lsn(state["replay_lsn"]),
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
        cluster_name=_required_text(state["cluster_name"]),
        system_identifier=_positive_integer(state["system_identifier"]),
        timeline_id=_positive_integer(state["timeline_id"]),
        replay_lsn=_optional_lsn(state["replay_lsn"]),
        in_recovery=_boolean(state["in_recovery"]),
        replay_paused=_boolean(state["replay_paused"]),
        matching_receiver_count=_nonnegative_integer(state["matching_receiver_count"]),
        receiver_status=_optional_text(state["receiver_status"]),
    )


def _live_target_failure(primary: _PrimaryEvidence, standby: _StandbyEvidence) -> str | None:
    policy = primary.policy
    if primary.replay_lsn is None or standby.replay_lsn is None:
        return "replay_evidence_unreadable"
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
    current = _lsn_position(primary.replay_lsn) >= _lsn_position(
        primary.flush_lsn
    ) and _lsn_position(standby.replay_lsn) >= _lsn_position(primary.flush_lsn)
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
    if not re.fullmatch(r"[0-9A-Fa-f]+/[0-9A-Fa-f]+", value):
        raise ValueError("live replay evidence contains an invalid LSN")
    high, low = value.split("/", maxsplit=1)
    return (int(high, 16) << 32) | int(low, 16)


def _required_text(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError("live evidence contains invalid text")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _required_text(value)


def _positive_integer(value: object) -> int:
    parsed = _integer(value)
    if parsed <= 0:
        raise ValueError("live evidence contains a non-positive integer")
    return parsed


def _nonnegative_integer(value: object) -> int:
    parsed = _integer(value)
    if parsed < 0:
        raise ValueError("live evidence contains a negative integer")
    return parsed


def _optional_positive_integer(value: object) -> int | None:
    return None if value is None else _positive_integer(value)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise TypeError("live evidence contains an invalid integer")
    parsed = int(value)
    if value != parsed:
        raise ValueError("live evidence contains a fractional integer")
    return parsed


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("live evidence contains an invalid boolean")
    return value


def _required_lsn(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("live evidence contains an invalid LSN")
    _lsn_position(value)
    return value


def _optional_lsn(value: object) -> str | None:
    return None if value is None else _required_lsn(value)

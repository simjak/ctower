"""Off-host command-root comparison and immutable durability acknowledgement authority."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from ctower_kernel.record import (
    DurabilityDecision,
    DurabilityHealth,
    DurabilityHealthStatus,
    DurabilityReason,
    DurabilityState,
    RecordProblem,
)
from ctower_kernel.record._command_root import CommandSnapshot, command_snapshot, digest
from ctower_kernel.record.transaction import (
    arm_remote_apply_deadline,
    authority_connection,
)

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Policy:
    policy_ref: str
    mode: str
    standby_application_name: str
    standby_identity: str
    commit_deadline_ms: int
    retry_after_seconds: int


@dataclass(frozen=True, slots=True)
class _StandbyIdentity:
    application_name: str
    cluster_name: str
    system_identifier: int
    timeline_id: int
    replay_lsn: str
    in_recovery: bool


@dataclass(frozen=True, slots=True)
class _Receipt:
    request_digest: bytes
    command_root: bytes
    acceptance_position: int
    policy_ref: str
    standby_application_name: str
    standby_identity: str
    standby_system_identifier: int
    standby_timeline_id: int
    standby_replay_lsn: str


def reconcile_durability(
    primary_dsn: str,
    standby_dsn: str | None,
    tenant_id: UUID,
    command_id: UUID,
    *,
    now: datetime,
) -> DurabilityDecision | RecordProblem:
    """Return accepted only after the exact receipt is visible on the named standby."""

    with _service_connection(primary_dsn) as primary:
        policy = _policy(primary)
        snapshot = command_snapshot(primary, tenant_id, command_id)
    if isinstance(snapshot, RecordProblem):
        return snapshot
    if policy.mode == "pending_only":
        return _pending(snapshot, policy, "policy_pending_only")
    if standby_dsn is None:
        _record_unavailable_observation(
            primary_dsn, snapshot, policy, now=now, reason="standby probe is unconfigured"
        )
        return _pending(snapshot, policy, "standby_unconfigured")
    proof = _prove_standby_copy(primary_dsn, standby_dsn, snapshot, policy, now=now)
    if isinstance(proof, DurabilityDecision):
        return proof
    receipt = _replicate_receipt(primary_dsn, standby_dsn, snapshot, policy, proof, now=now)
    if isinstance(receipt, DurabilityDecision):
        return receipt

    _record_observation(
        primary_dsn,
        snapshot,
        policy,
        proof,
        now=now,
        request_matches=True,
        root_matches=True,
        replay_visible=True,
        receipt_visible=True,
        outcome="matched",
        reason="exact acknowledgement receipt is replay-visible",
    )
    return DurabilityDecision(
        command_id=command_id,
        state=DurabilityState.ACCEPTED,
        reason="standby_receipt_proven",
        policy_ref=policy.policy_ref,
        command_root=digest(snapshot.root),
        acceptance_position=receipt.acceptance_position,
        retry_after_seconds=policy.retry_after_seconds,
    )


def _prove_standby_copy(
    primary_dsn: str,
    standby_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    *,
    now: datetime,
) -> _StandbyIdentity | DurabilityDecision:
    try:
        with psycopg.connect(standby_dsn, row_factory=dict_row) as standby:
            identity = _standby_identity(standby)
            if not _target_matches(primary_dsn, identity, policy):
                return _observed_pending(
                    primary_dsn,
                    snapshot,
                    policy,
                    identity,
                    now=now,
                    reason="target_mismatch",
                    detail="named standby identity or synchronous policy did not match",
                )
            standby.execute("SET ROLE ctower_svc")
            replica = command_snapshot(standby, snapshot.tenant_id, snapshot.command_id)
    except (psycopg.Error, ValueError):
        _record_unavailable_observation(
            primary_dsn, snapshot, policy, now=now, reason="standby observation was unavailable"
        )
        return _pending(snapshot, policy, "standby_not_ready")
    if isinstance(replica, RecordProblem):
        return _observed_pending(
            primary_dsn,
            snapshot,
            policy,
            identity,
            now=now,
            reason="replay_missing",
            detail="command result is not replay-visible on the named standby",
        )
    request_matches = hmac.compare_digest(snapshot.request_digest, replica.request_digest)
    root_matches = hmac.compare_digest(snapshot.root, replica.root)
    if request_matches and root_matches:
        return identity
    return _observed_pending(
        primary_dsn,
        snapshot,
        policy,
        identity,
        now=now,
        reason="integrity_mismatch",
        detail="standby request digest or canonical command root differs",
        request_matches=request_matches,
        root_matches=root_matches,
        replay_visible=True,
        outcome="integrity_mismatch",
    )


def _observed_pending(
    primary_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    identity: _StandbyIdentity,
    *,
    now: datetime,
    reason: str,
    detail: str,
    request_matches: bool = False,
    root_matches: bool = False,
    replay_visible: bool = False,
    outcome: str = "pending",
) -> DurabilityDecision:
    _record_observation(
        primary_dsn,
        snapshot,
        policy,
        identity,
        now=now,
        request_matches=request_matches,
        root_matches=root_matches,
        replay_visible=replay_visible,
        receipt_visible=False,
        outcome=outcome,
        reason=detail,
    )
    return _pending(snapshot, policy, reason)


def _replicate_receipt(
    primary_dsn: str,
    standby_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    identity: _StandbyIdentity,
    *,
    now: datetime,
) -> _Receipt | DurabilityDecision:
    try:
        _append_acknowledgement(primary_dsn, snapshot, policy, identity, now=now)
    except psycopg.Error:
        return _pending(snapshot, policy, "commit_ambiguous")
    try:
        with psycopg.connect(standby_dsn, row_factory=dict_row) as standby:
            replay_identity = _standby_identity(standby)
            standby.execute("SET ROLE ctower_svc")
            receipt = _receipt(standby, snapshot)
    except (psycopg.Error, ValueError):
        return _pending(snapshot, policy, "receipt_pending")
    if (
        receipt is None
        or not _same_standby(replay_identity, identity)
        or not _receipt_matches(receipt, snapshot, policy, identity)
    ):
        return _pending(snapshot, policy, "receipt_pending")
    return receipt


def durability_health(
    primary_dsn: str, standby_dsn: str | None, *, now: datetime
) -> DurabilityHealth:
    """Inspect only the first durability boundary and never infer a green target."""

    try:
        policy, position = _primary_health_state(primary_dsn)
    except psycopg.Error:
        return DurabilityHealth(
            DurabilityHealthStatus.STATE_UNKNOWN,
            "unavailable",
            "unknown",
            None,
            now,
            "primary_unavailable",
        )
    if policy.mode == "pending_only":
        return DurabilityHealth(
            DurabilityHealthStatus.STATE_UNKNOWN,
            policy.policy_ref,
            policy.standby_identity,
            position,
            now,
            "pending_only",
        )
    if standby_dsn is None:
        return DurabilityHealth(
            DurabilityHealthStatus.STATE_UNKNOWN,
            policy.policy_ref,
            policy.standby_identity,
            position,
            now,
            "standby_unconfigured",
        )
    matches = _health_target_matches(primary_dsn, standby_dsn, policy)
    return DurabilityHealth(
        DurabilityHealthStatus.HEALTHY if matches else DurabilityHealthStatus.DEGRADED,
        policy.policy_ref,
        policy.standby_identity,
        position,
        now,
        "target_ready" if matches else "target_mismatch",
    )


def _primary_health_state(primary_dsn: str) -> tuple[_Policy, int | None]:
    with _service_connection(primary_dsn) as primary:
        policy = _policy(primary)
        row = primary.execute(
            "SELECT max(acceptance_position) AS value FROM durability_acknowledgements"
        ).fetchone()
    value = row["value"] if row is not None else None
    return policy, int(cast(int, value)) if value is not None else None


def _health_target_matches(primary_dsn: str, standby_dsn: str, policy: _Policy) -> bool:
    try:
        with psycopg.connect(standby_dsn, row_factory=dict_row) as standby:
            identity = _standby_identity(standby)
        return _target_matches(primary_dsn, identity, policy)
    except (psycopg.Error, ValueError):
        return False


def _service_connection(dsn: str) -> psycopg.Connection[dict[str, object]]:
    connection = authority_connection(dsn)
    connection.execute("SET ROLE ctower_svc")
    return connection


def _policy(connection: psycopg.Connection[dict[str, object]]) -> _Policy:
    row = connection.execute(
        """
        SELECT policy_ref, mode, standby_application_name, standby_identity,
            commit_deadline_ms, retry_after_seconds
        FROM durability_policy_state WHERE singleton
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("durability policy is unavailable")
    return _Policy(
        str(row["policy_ref"]),
        str(row["mode"]),
        str(row["standby_application_name"]),
        str(row["standby_identity"]),
        int(cast(int, row["commit_deadline_ms"])),
        int(cast(int, row["retry_after_seconds"])),
    )


def _standby_identity(connection: psycopg.Connection[dict[str, object]]) -> _StandbyIdentity:
    row = connection.execute(
        """
        SELECT current_setting('cluster_name') AS cluster_name,
            current_setting('primary_conninfo') AS primary_conninfo,
            pg_is_in_recovery() AS in_recovery,
            pg_last_wal_replay_lsn()::text AS replay_lsn,
            (pg_control_system()).system_identifier AS system_identifier,
            (pg_control_checkpoint()).timeline_id AS timeline_id
        """
    ).fetchone()
    if row is None:
        raise ValueError("standby identity is unavailable")
    conninfo = conninfo_to_dict(str(row["primary_conninfo"]))
    return _StandbyIdentity(
        application_name=str(conninfo.get("application_name", "")),
        cluster_name=str(row["cluster_name"]),
        system_identifier=int(str(row["system_identifier"])),
        timeline_id=int(cast(int, row["timeline_id"])),
        replay_lsn=str(row["replay_lsn"]),
        in_recovery=bool(row["in_recovery"]),
    )


def _target_matches(primary_dsn: str, identity: _StandbyIdentity, policy: _Policy) -> bool:
    if not identity.in_recovery:
        return False
    if identity.application_name != policy.standby_application_name:
        return False
    if identity.cluster_name != policy.standby_identity:
        return False
    with _service_connection(primary_dsn) as primary:
        setting = primary.execute("SHOW synchronous_standby_names").fetchone()
    if setting is None:
        return False
    normalized = "".join(str(setting["synchronous_standby_names"]).split()).casefold()
    expected = f"first1({policy.standby_application_name})".casefold()
    return normalized == expected


def _append_acknowledgement(
    primary_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    identity: _StandbyIdentity,
    *,
    now: datetime,
) -> None:
    with _service_connection(primary_dsn) as primary:
        _set_remote_apply(primary, policy)
        primary.execute(
            """
            INSERT INTO durability_acknowledgements (
                tenant_id, principal_id, client_command_id, request_sha256, command_root,
                policy_ref, standby_application_name, standby_identity,
                standby_system_identifier, standby_timeline_id, standby_replay_lsn,
                acknowledged_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, principal_id, client_command_id) DO NOTHING
            """,
            (
                snapshot.tenant_id,
                snapshot.principal_id,
                snapshot.command_id,
                snapshot.request_digest,
                snapshot.root,
                policy.policy_ref,
                identity.application_name,
                identity.cluster_name,
                identity.system_identifier,
                identity.timeline_id,
                identity.replay_lsn,
                now,
            ),
        )


def _receipt(
    connection: psycopg.Connection[dict[str, object]], snapshot: CommandSnapshot
) -> _Receipt | None:
    row = connection.execute(
        """
        SELECT request_sha256, command_root, acceptance_position, policy_ref,
            standby_application_name, standby_identity, standby_system_identifier,
            standby_timeline_id, standby_replay_lsn::text AS standby_replay_lsn
        FROM durability_acknowledgements
        WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
        """,
        (snapshot.tenant_id, snapshot.principal_id, snapshot.command_id),
    ).fetchone()
    if row is None:
        return None
    return _Receipt(
        bytes(cast(bytes, row["request_sha256"])),
        bytes(cast(bytes, row["command_root"])),
        int(cast(int, row["acceptance_position"])),
        str(row["policy_ref"]),
        str(row["standby_application_name"]),
        str(row["standby_identity"]),
        int(str(row["standby_system_identifier"])),
        int(cast(int, row["standby_timeline_id"])),
        str(row["standby_replay_lsn"]),
    )


def _receipt_matches(
    receipt: _Receipt,
    snapshot: CommandSnapshot,
    policy: _Policy,
    identity: _StandbyIdentity,
) -> bool:
    return (
        hmac.compare_digest(receipt.request_digest, snapshot.request_digest)
        and hmac.compare_digest(receipt.command_root, snapshot.root)
        and receipt.policy_ref == policy.policy_ref
        and receipt.standby_application_name == identity.application_name
        and receipt.standby_identity == identity.cluster_name
        and receipt.standby_system_identifier == identity.system_identifier
        and receipt.standby_timeline_id == identity.timeline_id
        and _lsn_position(identity.replay_lsn) >= _lsn_position(receipt.standby_replay_lsn)
    )


def _same_standby(left: _StandbyIdentity, right: _StandbyIdentity) -> bool:
    return (
        left.application_name == right.application_name
        and left.cluster_name == right.cluster_name
        and left.system_identifier == right.system_identifier
        and left.timeline_id == right.timeline_id
        and left.in_recovery
        and right.in_recovery
    )


def _lsn_position(value: str) -> int:
    high, low = value.split("/", maxsplit=1)
    return (int(high, 16) << 32) | int(low, 16)


def _set_remote_apply(connection: psycopg.Connection[dict[str, object]], policy: _Policy) -> None:
    connection.execute("SELECT set_config('synchronous_commit', 'remote_apply', true)")
    connection.execute(
        "SELECT set_config('statement_timeout', %s, true)",
        (f"{policy.commit_deadline_ms}ms",),
    )
    arm_remote_apply_deadline(connection, policy.commit_deadline_ms)


def _record_unavailable_observation(
    primary_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    *,
    now: datetime,
    reason: str,
) -> None:
    identity = _StandbyIdentity(
        application_name=policy.standby_application_name,
        cluster_name="unobserved",
        system_identifier=0,
        timeline_id=0,
        replay_lsn="0/0",
        in_recovery=False,
    )
    _record_observation(
        primary_dsn,
        snapshot,
        policy,
        identity,
        now=now,
        request_matches=False,
        root_matches=False,
        replay_visible=False,
        receipt_visible=False,
        outcome="pending",
        reason=reason,
    )


def _record_observation(
    primary_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    identity: _StandbyIdentity,
    *,
    now: datetime,
    request_matches: bool,
    root_matches: bool,
    replay_visible: bool,
    receipt_visible: bool,
    outcome: str,
    reason: str,
) -> None:
    try:
        with _service_connection(primary_dsn) as primary:
            _set_remote_apply(primary, policy)
            primary.execute(
                """
                INSERT INTO durability_target_observations (
                    observation_id, tenant_id, principal_id, client_command_id,
                    request_sha256, command_root, policy_ref, standby_application_name,
                    expected_standby_identity, observed_standby_identity,
                    standby_system_identifier, standby_timeline_id, standby_replay_lsn,
                    standby_in_recovery, request_matches, command_root_matches,
                    replay_visible, receipt_visible, outcome, reason, observed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    uuid4(),
                    snapshot.tenant_id,
                    snapshot.principal_id,
                    snapshot.command_id,
                    snapshot.request_digest,
                    snapshot.root,
                    policy.policy_ref,
                    policy.standby_application_name,
                    policy.standby_identity,
                    None if identity.cluster_name == "unobserved" else identity.cluster_name,
                    None if identity.system_identifier == 0 else identity.system_identifier,
                    None if identity.timeline_id == 0 else identity.timeline_id,
                    None if identity.replay_lsn == "0/0" else identity.replay_lsn,
                    identity.in_recovery,
                    request_matches,
                    root_matches,
                    replay_visible,
                    receipt_visible,
                    outcome,
                    reason,
                    now,
                ),
            )
    except psycopg.Error:
        pass


def _pending(snapshot: CommandSnapshot, policy: _Policy, reason: str) -> DurabilityDecision:
    return DurabilityDecision(
        command_id=snapshot.command_id,
        state=DurabilityState.PENDING,
        reason=cast(DurabilityReason, reason),
        policy_ref=policy.policy_ref,
        command_root=digest(snapshot.root),
        acceptance_position=None,
        retry_after_seconds=policy.retry_after_seconds,
    )

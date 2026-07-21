"""Off-host command-root comparison and immutable durability acknowledgement authority."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from ctower_kernel.record import (
    DurabilityDecision,
    DurabilityReason,
    DurabilityState,
    RecordProblem,
)
from ctower_kernel.record._command_root import CommandSnapshot, command_snapshot, digest
from ctower_kernel.record._durability_evidence import Finalization as _Finalization
from ctower_kernel.record._durability_evidence import Policy as _Policy
from ctower_kernel.record._durability_evidence import Receipt as _Receipt
from ctower_kernel.record._durability_evidence import StandbyIdentity as _StandbyIdentity
from ctower_kernel.record._durability_evidence import (
    finalization_matches_receipt as _finalization_matches_receipt,
)
from ctower_kernel.record._durability_evidence import (
    finalization_matches_snapshot as _finalization_matches_snapshot,
)
from ctower_kernel.record._durability_evidence import receipt_matches as _receipt_matches
from ctower_kernel.record._durability_evidence import same_standby as _same_standby
from ctower_kernel.record._durability_observation_sql import (
    record_observation,
    record_unavailable_observation,
)
from ctower_kernel.record.transaction import (
    arm_remote_apply_deadline,
    authority_connection,
)

__all__: tuple[str, ...] = ()


def reconcile_durability(
    primary_dsn: str,
    standby_dsn: str | None,
    tenant_id: UUID,
    principal_id: UUID,
    command_id: UUID,
    *,
    now: datetime,
) -> DurabilityDecision | RecordProblem:
    """Return accepted only after the exact receipt is visible on the named standby."""

    with _service_connection(primary_dsn) as primary:
        snapshot = command_snapshot(primary, tenant_id, principal_id, command_id)
        finalization = (
            None if isinstance(snapshot, RecordProblem) else _finalization(primary, snapshot)
        )
    if isinstance(snapshot, RecordProblem):
        outcome: DurabilityDecision | RecordProblem = snapshot
    elif finalization is not None:
        outcome = _finalized_outcome(snapshot, finalization)
    else:
        outcome = _reconcile_unfinalized(primary_dsn, standby_dsn, snapshot, now=now)
    return outcome


def _finalized_outcome(
    snapshot: CommandSnapshot, finalization: _Finalization
) -> DurabilityDecision | RecordProblem:
    if _finalization_matches_snapshot(finalization, snapshot):
        return _accepted(snapshot, finalization)
    return RecordProblem(
        "durability-integrity",
        "Finalized acceptance evidence does not match the immutable command root.",
        503,
        "Durability integrity unavailable",
        snapshot.command_id,
    )


def _reconcile_unfinalized(
    primary_dsn: str,
    standby_dsn: str | None,
    snapshot: CommandSnapshot,
    *,
    now: datetime,
) -> DurabilityDecision:
    with _service_connection(primary_dsn) as primary:
        policy = _policy(primary)
    if policy.mode == "pending_only":
        return _pending(snapshot, policy, "policy_pending_only")
    if standby_dsn is None:
        record_unavailable_observation(
            primary_dsn, snapshot, policy, now=now, reason="standby probe is unconfigured"
        )
        return _pending(snapshot, policy, "standby_unconfigured")
    proof = _prove_standby_copy(primary_dsn, standby_dsn, snapshot, policy, now=now)
    if isinstance(proof, DurabilityDecision):
        return proof
    receipt = _replicate_receipt(primary_dsn, standby_dsn, snapshot, policy, proof, now=now)
    if isinstance(receipt, DurabilityDecision):
        return receipt
    finalization = _finalize_acceptance(
        primary_dsn,
        snapshot,
        receipt,
        policy,
        now=now,
    )
    if finalization is None:
        return _pending(snapshot, policy, "commit_ambiguous")

    record_observation(
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
    return _accepted(snapshot, finalization)


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
            replica = command_snapshot(
                standby, snapshot.tenant_id, snapshot.principal_id, snapshot.command_id
            )
    except (psycopg.Error, ValueError):
        record_unavailable_observation(
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
    record_observation(
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
    replay = _replayed_receipt(standby_dsn, snapshot)
    if replay is None:
        return _pending(snapshot, policy, "receipt_pending")
    replay_identity, receipt = replay
    if (
        receipt is None
        or not _same_standby(replay_identity, identity)
        or not _receipt_matches(receipt, snapshot, policy, identity)
    ):
        return _pending(snapshot, policy, "receipt_pending")
    return receipt


def _replayed_receipt(
    standby_dsn: str, snapshot: CommandSnapshot
) -> tuple[_StandbyIdentity, _Receipt | None] | None:
    try:
        with psycopg.connect(standby_dsn, row_factory=dict_row) as standby:
            identity = _standby_identity(standby)
            standby.execute("SET ROLE ctower_svc")
            return identity, _receipt(standby, snapshot)
    except (psycopg.Error, ValueError):
        return None


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
        snapshot.tenant_id,
        snapshot.principal_id,
        snapshot.command_id,
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


def _finalize_acceptance(
    primary_dsn: str,
    snapshot: CommandSnapshot,
    receipt: _Receipt,
    policy: _Policy,
    *,
    now: datetime,
) -> _Finalization | None:
    """Commit finalization with remote-apply and resolve ambiguity by exact lookup."""

    try:
        with _service_connection(primary_dsn) as primary:
            _set_remote_apply(primary, policy)
            primary.execute(
                """
                INSERT INTO durability_acceptance_finalizations (
                    tenant_id, principal_id, client_command_id, request_sha256,
                    command_root, acceptance_position, policy_ref,
                    standby_application_name, standby_identity,
                    standby_system_identifier, standby_timeline_id,
                    standby_replay_lsn, finalized_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, principal_id, client_command_id) DO NOTHING
                """,
                (
                    snapshot.tenant_id,
                    snapshot.principal_id,
                    snapshot.command_id,
                    receipt.request_digest,
                    receipt.command_root,
                    receipt.acceptance_position,
                    receipt.policy_ref,
                    receipt.standby_application_name,
                    receipt.standby_identity,
                    receipt.standby_system_identifier,
                    receipt.standby_timeline_id,
                    receipt.standby_replay_lsn,
                    now,
                ),
            )
    except psycopg.Error:
        pass
    try:
        with _service_connection(primary_dsn) as primary:
            finalization = _finalization(primary, snapshot)
    except psycopg.Error:
        return None
    if finalization is None or not _finalization_matches_receipt(finalization, receipt):
        return None
    return finalization


def _finalization(
    connection: psycopg.Connection[dict[str, object]], snapshot: CommandSnapshot
) -> _Finalization | None:
    row = connection.execute(
        """
        SELECT tenant_id, principal_id, client_command_id, request_sha256,
            command_root, acceptance_position, policy_ref, standby_application_name,
            standby_identity, standby_system_identifier, standby_timeline_id,
            standby_replay_lsn::text AS standby_replay_lsn
        FROM durability_acceptance_finalizations
        WHERE tenant_id = %s AND principal_id = %s AND client_command_id = %s
        """,
        (snapshot.tenant_id, snapshot.principal_id, snapshot.command_id),
    ).fetchone()
    if row is None:
        return None
    return _Finalization(
        cast(UUID, row["tenant_id"]),
        cast(UUID, row["principal_id"]),
        cast(UUID, row["client_command_id"]),
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


def _accepted(snapshot: CommandSnapshot, finalization: _Finalization) -> DurabilityDecision:
    return DurabilityDecision(
        command_id=snapshot.command_id,
        state=DurabilityState.ACCEPTED,
        reason="standby_receipt_proven",
        policy_ref=finalization.policy_ref,
        command_root=digest(snapshot.root),
        acceptance_position=finalization.acceptance_position,
        retry_after_seconds=1,
    )


def _set_remote_apply(connection: psycopg.Connection[dict[str, object]], policy: _Policy) -> None:
    connection.execute("SELECT set_config('synchronous_commit', 'remote_apply', true)")
    connection.execute(
        "SELECT set_config('statement_timeout', %s, true)",
        (f"{policy.commit_deadline_ms}ms",),
    )
    arm_remote_apply_deadline(connection, policy.commit_deadline_ms)


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

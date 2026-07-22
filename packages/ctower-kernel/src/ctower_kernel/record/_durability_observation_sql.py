"""Best-effort immutable observations of the configured durability target."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

import psycopg

from ctower_kernel.record._command_root import CommandSnapshot
from ctower_kernel.record.transaction import (
    arm_remote_apply_deadline,
    authority_connection,
)

__all__: tuple[str, ...] = ()


class _Policy(Protocol):
    @property
    def policy_ref(self) -> str: ...

    @property
    def standby_application_name(self) -> str: ...

    @property
    def standby_identity(self) -> str: ...

    @property
    def commit_deadline_ms(self) -> int: ...


class _Identity(Protocol):
    @property
    def cluster_name(self) -> str: ...

    @property
    def system_identifier(self) -> int: ...

    @property
    def timeline_id(self) -> int: ...

    @property
    def replay_lsn(self) -> str: ...

    @property
    def in_recovery(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class _UnobservedIdentity:
    cluster_name: str = "unobserved"
    system_identifier: int = 0
    timeline_id: int = 0
    replay_lsn: str = "0/0"
    in_recovery: bool = False


def record_unavailable_observation(
    primary_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    *,
    now: datetime,
    reason: str,
) -> None:
    """Persist an unavailable probe without inventing a target identity."""

    record_observation(
        primary_dsn,
        snapshot,
        policy,
        _UnobservedIdentity(),
        now=now,
        request_matches=False,
        root_matches=False,
        replay_visible=False,
        receipt_visible=False,
        outcome="pending",
        reason=reason,
    )


def record_observation(
    primary_dsn: str,
    snapshot: CommandSnapshot,
    policy: _Policy,
    identity: _Identity,
    *,
    now: datetime,
    request_matches: bool,
    root_matches: bool,
    replay_visible: bool,
    receipt_visible: bool,
    outcome: str,
    reason: str,
) -> None:
    """Persist one immutable observation without changing the command outcome."""

    try:
        with authority_connection(primary_dsn) as primary:
            primary.execute("SET ROLE ctower_svc")
            _set_remote_apply(primary, policy.commit_deadline_ms)
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


def _set_remote_apply(connection: psycopg.Connection[dict[str, object]], deadline_ms: int) -> None:
    connection.execute("SELECT set_config('synchronous_commit', 'remote_apply', true)")
    connection.execute(
        "SELECT set_config('statement_timeout', %s, true)",
        (f"{deadline_ms}ms",),
    )
    arm_remote_apply_deadline(connection, deadline_ms)

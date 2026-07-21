"""Typed immutable evidence values and exact comparison rules."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from uuid import UUID

from ctower_kernel.record._command_root import CommandSnapshot

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Policy:
    policy_ref: str
    mode: str
    standby_application_name: str
    standby_identity: str
    commit_deadline_ms: int
    retry_after_seconds: int


@dataclass(frozen=True, slots=True)
class StandbyIdentity:
    application_name: str
    cluster_name: str
    system_identifier: int
    timeline_id: int
    replay_lsn: str
    in_recovery: bool


@dataclass(frozen=True, slots=True)
class Receipt:
    tenant_id: UUID
    principal_id: UUID
    command_id: UUID
    request_digest: bytes
    command_root: bytes
    acceptance_position: int
    policy_ref: str
    standby_application_name: str
    standby_identity: str
    standby_system_identifier: int
    standby_timeline_id: int
    standby_replay_lsn: str


@dataclass(frozen=True, slots=True)
class Finalization:
    tenant_id: UUID
    principal_id: UUID
    command_id: UUID
    request_digest: bytes
    command_root: bytes
    acceptance_position: int
    policy_ref: str
    standby_application_name: str
    standby_identity: str
    standby_system_identifier: int
    standby_timeline_id: int
    standby_replay_lsn: str


def receipt_matches(
    receipt: Receipt,
    snapshot: CommandSnapshot,
    policy: Policy,
    identity: StandbyIdentity,
) -> bool:
    return all(
        (
            receipt.tenant_id == snapshot.tenant_id,
            receipt.principal_id == snapshot.principal_id,
            receipt.command_id == snapshot.command_id,
            hmac.compare_digest(receipt.request_digest, snapshot.request_digest),
            hmac.compare_digest(receipt.command_root, snapshot.root),
            receipt.policy_ref == policy.policy_ref,
            receipt.standby_application_name == identity.application_name,
            receipt.standby_identity == identity.cluster_name,
            receipt.standby_system_identifier == identity.system_identifier,
            receipt.standby_timeline_id == identity.timeline_id,
            lsn_position(identity.replay_lsn) >= lsn_position(receipt.standby_replay_lsn),
        )
    )


def finalization_matches_snapshot(finalization: Finalization, snapshot: CommandSnapshot) -> bool:
    return all(
        (
            finalization.tenant_id == snapshot.tenant_id,
            finalization.principal_id == snapshot.principal_id,
            finalization.command_id == snapshot.command_id,
            hmac.compare_digest(finalization.request_digest, snapshot.request_digest),
            hmac.compare_digest(finalization.command_root, snapshot.root),
        )
    )


def finalization_matches_receipt(finalization: Finalization, receipt: Receipt) -> bool:
    return all(
        (
            finalization.tenant_id == receipt.tenant_id,
            finalization.principal_id == receipt.principal_id,
            finalization.command_id == receipt.command_id,
            hmac.compare_digest(finalization.request_digest, receipt.request_digest),
            hmac.compare_digest(finalization.command_root, receipt.command_root),
            finalization.acceptance_position == receipt.acceptance_position,
            finalization.policy_ref == receipt.policy_ref,
            finalization.standby_application_name == receipt.standby_application_name,
            finalization.standby_identity == receipt.standby_identity,
            finalization.standby_system_identifier == receipt.standby_system_identifier,
            finalization.standby_timeline_id == receipt.standby_timeline_id,
            finalization.standby_replay_lsn == receipt.standby_replay_lsn,
        )
    )


def same_standby(left: StandbyIdentity, right: StandbyIdentity) -> bool:
    return all(
        (
            left.application_name == right.application_name,
            left.cluster_name == right.cluster_name,
            left.system_identifier == right.system_identifier,
            left.timeline_id == right.timeline_id,
            left.in_recovery,
            right.in_recovery,
        )
    )


def lsn_position(value: str) -> int:
    high, low = value.split("/", maxsplit=1)
    return (int(high, 16) << 32) | int(low, 16)

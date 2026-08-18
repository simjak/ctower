"""Commands, receipts, and the three-axis read view for harness credential pools."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ctower_kernel.pools.topology import TOPOLOGY_REVISION, model_weights
from ctower_kernel.record.pool_events import (
    HARNESS_KEYS,
    MAX_ENTRIES,
    PoolObservationEntryPayload,
)

__all__ = [
    "PoolDriftFinding",
    "PoolEntryState",
    "PoolLimitsView",
    "PoolObservationCommand",
    "PoolObservationReceipt",
    "PoolProfileLimits",
    "selectable",
]

_PROFILE_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def selectable(entry: PoolObservationEntryPayload) -> bool:
    """An entry is selectable only when all three axes are clear.

    `unknown` is not `available`. Every default-toward-optimism in this system has
    eventually dispatched work into a dead substrate, so an unobserved axis blocks
    selection rather than being read as health, and a `discovered` identity is never
    selectable however reachable it happens to be.
    """

    return (
        entry.registration_state == "enrolled"
        and entry.auth_state == "healthy"
        and entry.quota_state == "available"
        and entry.reach_state == "ok"
    )


@dataclass(frozen=True, slots=True)
class PoolObservationCommand:
    """One projected sweep of one harness profile's credential store."""

    client_command_id: UUID
    harness_key: str
    profile_key: str
    observed_at: datetime
    entries: tuple[PoolObservationEntryPayload, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID):
            raise TypeError("pool observation command identity must be a UUID")
        if self.harness_key not in HARNESS_KEYS:
            raise ValueError("pool observation harness is outside the authored contract")
        if _PROFILE_KEY.fullmatch(self.profile_key) is None:
            raise ValueError("pool observation profile is outside the authored contract")
        if not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None:
            raise ValueError("pool observation observed_at must be timezone-aware")
        if len(self.entries) > MAX_ENTRIES:
            raise ValueError("pool observation carries more entries than the contract allows")

    def request_payload(self) -> dict[str, object]:
        return {
            "entries": [entry.to_mapping() for entry in self.entries],
            "harness_key": self.harness_key,
            "observed_at": self.observed_at.isoformat(),
            "profile_key": self.profile_key,
        }


@dataclass(frozen=True, slots=True)
class PoolObservationReceipt:
    tenant_id: UUID
    actor_principal_id: UUID
    command_id: UUID
    observation_id: UUID
    recorded_at: datetime
    event_ids: tuple[UUID, ...] = ()

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "observation_id": str(self.observation_id),
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PoolDriftFinding:
    """Desired-versus-actual, in the direction that says what to do about it."""

    finding: str
    provider_key: str
    subscription_identity: str | None
    enactment: str
    detail: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "detail": self.detail,
            "enactment": self.enactment,
            "finding": self.finding,
            "provider_key": self.provider_key,
            "subscription_identity": self.subscription_identity,
        }


@dataclass(frozen=True, slots=True)
class PoolEntryState:
    """One entry's three axes, its own reset clock, and what it has cost.

    `metered_millicredits` is `None` under `credit_state = "unmetered"` because a sweep of a
    harness's own credential store observes request counts and not tokens. Spend is observed,
    never predicted, so an unpriced entry says so instead of reporting zero.
    """

    entry: PoolObservationEntryPayload
    observed_at: datetime
    credit_state: str = "unmetered"
    metered_millicredits: int | None = None

    def to_mapping(self) -> dict[str, object]:
        reset = self.entry.quota_reset_at
        return {
            "auth_state": self.entry.auth_state,
            "credit_state": self.credit_state,
            "entry_label": self.entry.entry_label,
            "last_status_observed": self.entry.last_status_observed,
            "metered_millicredits": self.metered_millicredits,
            "observed_at": self.observed_at.isoformat(),
            "provider_key": self.entry.provider_key,
            "quota_reset_at": None if reset is None else reset.isoformat(),
            "quota_state": self.entry.quota_state,
            "reach_state": self.entry.reach_state,
            "registration_state": self.entry.registration_state,
            "request_count": self.entry.request_count,
            "selectable": selectable(self.entry),
            "subscription_identity": self.entry.subscription_identity,
        }


@dataclass(frozen=True, slots=True)
class PoolProfileLimits:
    """One profile's per-entry rows. There is no aggregate verdict, deliberately."""

    harness_key: str
    profile_key: str
    observed_at: datetime
    entries: tuple[PoolEntryState, ...]
    drift: tuple[PoolDriftFinding, ...]

    def earliest_known_reset(self) -> datetime | None:
        clocks = [
            state.entry.quota_reset_at
            for state in self.entries
            if state.entry.quota_reset_at is not None
        ]
        return min(clocks) if clocks else None

    def to_mapping(self) -> dict[str, object]:
        earliest = self.earliest_known_reset()
        return {
            "drift": [finding.to_mapping() for finding in self.drift],
            "earliest_known_reset_at": None if earliest is None else earliest.isoformat(),
            "entries": [state.to_mapping() for state in self.entries],
            "harness_key": self.harness_key,
            "observed_at": self.observed_at.isoformat(),
            "profile_key": self.profile_key,
            "selectable_entry_count": sum(1 for state in self.entries if selectable(state.entry)),
        }


@dataclass(frozen=True, slots=True)
class PoolLimitsView:
    profiles: tuple[PoolProfileLimits, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "profiles": [profile.to_mapping() for profile in self.profiles],
            "topology_revision": TOPOLOGY_REVISION,
            "weights": [
                {
                    "cached_input_millicredits_per_mtok": (
                        weight.cached_input_millicredits_per_mtok
                    ),
                    "input_millicredits_per_mtok": weight.input_millicredits_per_mtok,
                    "model_ref": weight.model_ref,
                    "output_millicredits_per_mtok": weight.output_millicredits_per_mtok,
                    "subscription_key": weight.subscription_key,
                }
                for weight in model_weights()
            ],
        }

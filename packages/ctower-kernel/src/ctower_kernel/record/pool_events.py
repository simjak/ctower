"""Strict payloads for harness credential-pool observations.

This module is the projection allowlist in type form. A harness's own credential store
keeps `access_token` and `refresh_token` *adjacent to* the metadata worth reading, so an
observer that copied the entry object rather than projecting named fields would move
credential values into the ledger. The dataclasses below therefore have no field a
credential value can occupy: a credential appears only as `secret_fingerprint`, and only
as a fingerprint.

The three state axes are separate fields on purpose. AUTH is not QUOTA is not REACH: a
capped account passes login and refuses work, a dead lineage may sit on untouched quota,
and an entry with both healthy can still be unreachable because the provider's edge is
challenging our egress. Collapsing them into one status is what prescribes the wrong
ceremony — a re-mint against a perfectly good credential.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = [
    "PoolObservationEntryPayload",
    "PoolObservationRecordedPayload",
]

AUTH_STATES = frozenset({"healthy", "lineage-dead", "chain-burned"})
QUOTA_STATES = frozenset({"available", "capped", "unfunded", "unknown"})
REACH_STATES = frozenset({"ok", "edge-challenged", "unknown"})
REGISTRATION_STATES = frozenset({"enrolled", "discovered"})
HARNESS_KEYS = frozenset({"hermes", "claude-code"})
MAX_ENTRIES = 64

_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_STATUS_WORD = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_MIN_IDENTITY_LENGTH = 3
_MAX_IDENTITY_LENGTH = 254
_MAX_LABEL_LENGTH = 128


@dataclass(frozen=True, slots=True)
class PoolObservationEntryPayload:
    """One pool entry, keyed by its decoded identity rather than by its label."""

    entry_ordinal: int
    provider_key: str
    subscription_identity: str | None
    entry_label: str | None
    registration_state: str
    auth_state: str
    quota_state: str
    quota_reset_at: datetime | None
    reach_state: str
    request_count: int
    last_status_observed: str | None
    secret_fingerprint: str | None

    def __post_init__(self) -> None:
        _validate_entry_identity(self)
        _validate_entry_axes(self)
        _validate_entry_observation(self)

    def to_mapping(self) -> dict[str, object]:
        return {
            "auth_state": self.auth_state,
            "entry_label": self.entry_label,
            "entry_ordinal": self.entry_ordinal,
            "last_status_observed": self.last_status_observed,
            "provider_key": self.provider_key,
            "quota_reset_at": (
                None if self.quota_reset_at is None else self.quota_reset_at.isoformat()
            ),
            "quota_state": self.quota_state,
            "reach_state": self.reach_state,
            "registration_state": self.registration_state,
            "request_count": self.request_count,
            "secret_fingerprint": self.secret_fingerprint,
            "subscription_identity": self.subscription_identity,
        }


@dataclass(frozen=True, slots=True)
class PoolObservationRecordedPayload:
    """One appended sweep of one harness profile's credential store."""

    observation_id: UUID
    harness_key: str
    profile_key: str
    observed_at: datetime
    entries: tuple[PoolObservationEntryPayload, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, UUID):
            raise TypeError("pool observation identity must be a UUID")
        if self.harness_key not in HARNESS_KEYS:
            raise ValueError("pool observation harness is outside the authored contract")
        if _KEY.fullmatch(self.profile_key) is None:
            raise ValueError("pool observation profile is outside the authored contract")
        if not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None:
            raise ValueError("pool observation observed_at must be timezone-aware")
        if len(self.entries) > MAX_ENTRIES:
            raise ValueError("pool observation carries more entries than the contract allows")
        if [entry.entry_ordinal for entry in self.entries] != list(range(len(self.entries))):
            raise ValueError("pool observation entry ordinals must be dense and ascending")

    def to_mapping(self) -> dict[str, object]:
        return {
            "entries": [entry.to_mapping() for entry in self.entries],
            "harness_key": self.harness_key,
            "observation_id": str(self.observation_id),
            "observed_at": self.observed_at.isoformat(),
            "profile_key": self.profile_key,
        }


def _validate_entry_identity(entry: PoolObservationEntryPayload) -> None:
    if not isinstance(entry.entry_ordinal, int) or isinstance(entry.entry_ordinal, bool):
        raise TypeError("pool entry ordinal must be an integer")
    if not 0 <= entry.entry_ordinal < MAX_ENTRIES:
        raise ValueError("pool entry ordinal is outside the authored contract")
    if _KEY.fullmatch(entry.provider_key) is None:
        raise ValueError("pool entry provider is outside the authored contract")
    identity = entry.subscription_identity
    if identity is not None and not (_MIN_IDENTITY_LENGTH <= len(identity) <= _MAX_IDENTITY_LENGTH):
        raise ValueError("pool entry identity is outside the authored contract")
    if entry.entry_label is not None and not (1 <= len(entry.entry_label) <= _MAX_LABEL_LENGTH):
        raise ValueError("pool entry label is outside the authored contract")


def _validate_entry_axes(entry: PoolObservationEntryPayload) -> None:
    if entry.registration_state not in REGISTRATION_STATES:
        raise ValueError("pool entry registration state is outside the authored contract")
    if entry.auth_state not in AUTH_STATES:
        raise ValueError("pool entry auth state is outside the authored contract")
    if entry.quota_state not in QUOTA_STATES:
        raise ValueError("pool entry quota state is outside the authored contract")
    if entry.reach_state not in REACH_STATES:
        raise ValueError("pool entry reach state is outside the authored contract")


def _validate_entry_observation(entry: PoolObservationEntryPayload) -> None:
    _validate_entry_clock(entry)
    if not isinstance(entry.request_count, int) or isinstance(entry.request_count, bool):
        raise TypeError("pool entry request count must be an integer")
    if entry.request_count < 0:
        raise ValueError("pool entry request count is outside the authored contract")
    status = entry.last_status_observed
    if status is not None and _STATUS_WORD.fullmatch(status) is None:
        raise ValueError("pool entry status word is outside the authored contract")
    fingerprint = entry.secret_fingerprint
    if fingerprint is not None and _FINGERPRINT.fullmatch(fingerprint) is None:
        raise ValueError("pool entry secret reference must be a fingerprint, never a value")


def _validate_entry_clock(entry: PoolObservationEntryPayload) -> None:
    """A reset clock is meaningless without the cap it belongs to."""

    reset = entry.quota_reset_at
    if reset is None:
        return
    if not isinstance(reset, datetime) or reset.tzinfo is None:
        raise ValueError("pool entry quota reset must be timezone-aware")
    if entry.quota_state != "capped":
        raise ValueError("pool entry reset clock belongs only to an observed cap")

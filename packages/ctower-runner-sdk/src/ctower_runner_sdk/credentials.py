"""The sibling `CredentialPool` Interface, resolved at `spawn` and never a sixth verb.

Five verbs plus `request_mint`, and **no copy verb**. The absent verb is a design element:
OAuth refresh tokens here are single-use chains, so installing a copied auth file replays a
consumed token and the provider revokes the whole chain — every grant derived from that
login dies at once. Every entry is its own device-flow mint; rotation switches which entry
an attempt rides, never which file sits where.

Observation projects a strict named-field allowlist. A harness's own credential store keeps
`access_token` and `refresh_token` *adjacent to* the metadata worth reading, so a reader
that copied the entry object rather than projecting named fields would move credential
values into the ledger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, TypedDict
from uuid import UUID

from ctower_runner_sdk.refusals import Refusal

__all__ = [
    "ENTRY_ALLOWLIST",
    "LEASE_SCHEMA_REF",
    "CredentialPool",
    "EntryState",
    "Lease",
    "MeterObservation",
    "MintRequest",
    "ProbeReading",
    "ProbeResponse",
    "exhaustion_refusal",
    "project_entry",
    "selectable",
]

LEASE_SCHEMA_REF = "ctower.credential-lease/v1"

# The complete set of names an observation may read off a pool entry. Anything else stays
# in the harness's own store; there is no field here a credential value can occupy. These
# are the kernel's own pool-observation names: one vocabulary across both planes, so a lease
# and a recorded observation never need translating into each other.
ENTRY_ALLOWLIST: tuple[str, ...] = (
    "auth_state",
    "entry_label",
    "last_status_observed",
    "provider_key",
    "quota_reset_at",
    "quota_state",
    "reach_state",
    "registration_state",
    "request_count",
    "secret_fingerprint",
    "subscription_identity",
)


class MeterObservation(TypedDict):
    """The only caller-supplied fields a pool usage sink may accept."""

    event: Literal["spawn"]
    model_ref: str


_MEANINGS: dict[tuple[str, str], tuple[str, str]] = {
    ("auth", "lineage-dead"): (
        "this profile's grant expired; the shell may still say logged in",
        "re-mint this profile's own device flow — never copy another profile's file",
    ),
    ("auth", "chain-burned"): (
        "a copy replayed a single-use refresh token and the provider revoked the chain",
        "fresh mint, never a copy",
    ),
    ("quota", "capped"): (
        "the account passed login and refused work; quota is spent for this window",
        "wait for the provider's own reset — no ceremony adds quota",
    ),
    ("quota", "unfunded"): (
        "the prepaid balance is exhausted; money is a liveness condition",
        "operator refill — ctower can request it and never perform it",
    ),
    ("quota", "unknown"): (
        "no trustworthy observation of this window; unknown is not available",
        "run a real probe against the model the seats run",
    ),
    ("reach", "edge-challenged"): (
        "the provider's edge is challenging our egress; auth and quota are both fine",
        "infra-plane only — client fingerprint, headers, or egress. Never a mint or rotation",
    ),
    ("reach", "unknown"): (
        "reachability was not observed",
        "run a real probe against the model the seats run",
    ),
    ("registration", "discovered"): (
        "this identity is reachable and was never enrolled",
        "operator keep-or-evict; reaching a credential is not entitlement to it",
    ),
}


@dataclass(frozen=True, slots=True)
class EntryState:
    """One pool entry on three orthogonal axes, keyed by its own decoded identity.

    Labels have twice pointed at the wrong account, so `subscription_identity` is the key
    and `entry_label` is a display attribute with no authority.
    """

    provider_key: str
    subscription_identity: str | None
    entry_label: str | None
    registration_state: Literal["enrolled", "discovered"]
    auth_state: Literal["healthy", "lineage-dead", "chain-burned"]
    quota_state: Literal["available", "capped", "unfunded", "unknown"]
    quota_reset_at: datetime | None
    reach_state: Literal["ok", "edge-challenged", "unknown"]
    request_count: int
    last_status_observed: str | None
    secret_fingerprint: str | None

    def blocking_axes(self) -> tuple[tuple[str, str], ...]:
        """Every axis that is not clear, in a fixed order, with no collapsing."""

        axes = (
            ("registration", self.registration_state),
            ("auth", self.auth_state),
            ("quota", self.quota_state),
            ("reach", self.reach_state),
        )
        clear = {"enrolled", "healthy", "available", "ok"}
        return tuple((axis, value) for axis, value in axes if value not in clear)

    def to_mapping(self) -> dict[str, object]:
        reset = self.quota_reset_at
        return {
            "auth_state": self.auth_state,
            "entry_label": self.entry_label,
            "last_status_observed": self.last_status_observed,
            "provider_key": self.provider_key,
            "quota_reset_at": None if reset is None else reset.isoformat(),
            "quota_state": self.quota_state,
            "reach_state": self.reach_state,
            "registration_state": self.registration_state,
            "request_count": self.request_count,
            "secret_fingerprint": self.secret_fingerprint,
            "subscription_identity": self.subscription_identity,
        }


@dataclass(frozen=True, slots=True)
class Lease:
    """Which entry an attempt rides, as a reference. Read at spawn, never mutated live."""

    lease_id: UUID
    harness_key: str
    profile_key: str
    model_ref: str
    entry: EntryState
    acquired_at: datetime

    def to_mapping(self) -> dict[str, object]:
        """The lease as its authored contract describes it, discriminator included."""

        return {
            "acquired_at": self.acquired_at.isoformat(),
            "entry_state": self.entry.to_mapping(),
            "harness_key": self.harness_key,
            "lease_id": str(self.lease_id),
            "model_ref": self.model_ref,
            "profile_key": self.profile_key,
            "schema": LEASE_SCHEMA_REF,
        }


@dataclass(frozen=True, slots=True)
class ProbeResponse:
    """What a probe actually got back, before anything classifies it."""

    status_code: int
    body: str
    model_ref: str
    drawn_from_pool: bool
    after_invalidation: bool


@dataclass(frozen=True, slots=True)
class ProbeReading:
    """Three axes and the basis for each. `unknown` is a reading, not a gap."""

    auth: Literal["healthy", "lineage-dead", "chain-burned", "unknown"]
    quota: Literal["available", "capped", "unfunded", "unknown"]
    reach: Literal["ok", "edge-challenged", "unknown"]
    basis: str

    def is_unknown(self) -> bool:
        return self.auth == "unknown" and self.quota == "unknown" and self.reach == "unknown"


@dataclass(frozen=True, slots=True)
class MintRequest:
    """What the pool may ask for and may never perform."""

    provider_key: str
    subscription_identity: str | None
    enactment: Literal["operator-ceremony", "secret-reference"]


def selectable(entry: EntryState) -> bool:
    """An entry is selectable only when all three axes and its registration are clear."""

    return not entry.blocking_axes()


def project_entry(raw: Mapping[str, object]) -> EntryState:
    """Read exactly the allowlisted names off a harness's own entry record.

    Named projection rather than object copy is the whole control: the fields beside these
    are the credential itself.
    """

    reset = raw.get("quota_reset_at")
    return EntryState(
        provider_key=str(raw["provider_key"]),
        subscription_identity=_optional_text(raw.get("subscription_identity")),
        entry_label=_optional_text(raw.get("entry_label")),
        registration_state=_literal(raw["registration_state"], ("enrolled", "discovered")),
        auth_state=_literal(raw["auth_state"], ("healthy", "lineage-dead", "chain-burned")),
        quota_state=_literal(raw["quota_state"], ("available", "capped", "unfunded", "unknown")),
        quota_reset_at=reset if isinstance(reset, datetime) else None,
        reach_state=_literal(raw["reach_state"], ("ok", "edge-challenged", "unknown")),
        request_count=int(str(raw.get("request_count", 0))),
        last_status_observed=_optional_text(raw.get("last_status_observed")),
        secret_fingerprint=_optional_text(raw.get("secret_fingerprint")),
    )


def exhaustion_refusal(entries: Sequence[EntryState]) -> Refusal:
    """The refusal body a caller can act on without reading a pane.

    Each unselectable entry contributes its own diagnosis row mapping to its exact
    meaning/action pair, so a reachability fault is never routed to a credential ceremony,
    and the earliest known reset is stated or explicitly unknown.
    """

    rows: list[tuple[str, str]] = []
    meanings: list[str] = []
    actions: list[str] = []
    for entry in entries:
        subject = entry.subscription_identity or f"{entry.provider_key} entry"
        for axis, value in entry.blocking_axes():
            meaning, action = _MEANINGS[axis, value]
            rows.append((f"{subject} {axis}", value))
            meanings.append(f"{subject}: {meaning}")
            actions.append(f"{subject}: {action}")
    resets = [entry.quota_reset_at for entry in entries if entry.quota_reset_at is not None]
    earliest = min(resets).isoformat() if resets else "unknown"
    rows.append(("earliest_known_reset", earliest))
    return Refusal(
        name="credential-pool-exhausted",
        observed=f"{len(entries)} entries observed, none selectable on all three axes",
        meaning=" | ".join(meanings) or "no entry is enrolled for this pool",
        action=" | ".join(actions) or "enrol an entry through the operator's mint ceremony",
        detail=tuple(rows),
    )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _literal[T: str](value: object, allowed: tuple[T, ...]) -> T:
    if value not in allowed:
        raise ValueError(f"pool entry axis is outside the contract: {value!r}")
    return next(item for item in allowed if item == value)


class CredentialPool(Protocol):
    """One pool per harness. Configure-and-observe or provided — same five verbs.

    A binding declares which class it is in its `HarnessSpec`, and that declaration is the
    only place the difference appears. No caller branches on harness name.
    """

    def acquire(self, model_ref: str, tier: str) -> Lease | Refusal:
        """Lease an entry whose window for that exact model is clear on all three axes."""

    def meter(self, lease: Lease, observation: MeterObservation) -> None:
        """Record usage, cost, and cache-reset events against the leased entry."""

    def limits(self, profile_key: str | None = None) -> tuple[EntryState, ...]:
        """Per-entry rows with their own reset clocks. Never an aggregate verdict."""

    def rotate(self, reason: str) -> object:
        """Record the engine's rotation, or perform ctower's own. Never both policies."""

    def probe(self, response: ProbeResponse) -> ProbeReading | Refusal:
        """Classify a response the pool's own entries produced, on its body."""

    def request_mint(self, identity: str | None) -> MintRequest | Refusal:
        """Ask for credential material. The pool never mints, refills, or raises a plan."""

"""The hermes credential pool: configure and observe, implement neither layer.

Hermes owns the pool. This class registers, meters, and reports what the engine already
knows, and keeps the history the engine does not — `auth.json` carries *current* state and
is overwritten as it changes, so a ledger is the only thing that can answer "how often are
we rotating, and what is it costing us". Ctower never writes that file.

Two controls carry most of the weight here. Observation projects a **strict named-field
allowlist**, because OAuth entries keep `access_token` and `refresh_token` adjacent to the
metadata being read and an observer that copied the object would move credential values
into the ledger. And an observation taken **before** the declared invalidation hook
completed is stale rather than authoritative: a stale proxy once translated
`usage_limit_reached` into `No available credentials` for an entire night.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Literal
from uuid import UUID

from ctower_runner.hermes.substrate import EngineStatePort
from ctower_runner_sdk.credentials import (
    EntryState,
    Lease,
    MintRequest,
    ProbeReading,
    ProbeResponse,
    exhaustion_refusal,
    project_entry,
    selectable,
)
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.rotation import (
    FlapWindow,
    RotationEvent,
    classify_probe,
    record_rotation,
)
from ctower_runner_sdk.spec import HarnessSpec

__all__ = ["HermesPool"]

_CODEX_ENACTMENT: Literal["operator-ceremony", "secret-reference"] = "operator-ceremony"


class HermesPool:
    """One pool per harness, resolved at `spawn`, carrying deliberately no copy verb."""

    def __init__(
        self,
        spec: HarnessSpec,
        engine: EngineStatePort,
        profile_key: str,
        clock: Callable[[], datetime],
        lease_ids: Callable[[], UUID],
    ) -> None:
        self._spec = spec
        self._engine = engine
        self._profile_key = profile_key
        self._clock = clock
        self._lease_ids = lease_ids
        self._flap: dict[str, FlapWindow] = {}
        self.metered: list[Mapping[str, object]] = []

    def acquire(self, model_ref: str, tier: str) -> Lease | Refusal:
        """Lease an entry clear on all three axes, or refuse with the whole diagnosis.

        Acquisition fails only when EVERY entry is unselectable. A pool holding two spent
        entries and one near-full one is not dry, and a status model with one word per
        substrate cannot say so.
        """

        stale = self._staleness_refusal()
        if stale is not None:
            return stale
        entries = self.limits()
        entry = next((item for item in entries if self._is_ready(item)), None)
        if entry is None:
            return exhaustion_refusal(entries)
        return Lease(
            lease_id=self._lease_ids(),
            harness_key=self._spec.key,
            profile_key=tier or self._profile_key,
            model_ref=model_ref,
            entry=entry,
            acquired_at=self._clock(),
        )

    def meter(self, lease: Lease, observation: Mapping[str, object]) -> None:
        """Record usage and cost against the leased entry. No second opinion is formed."""

        self.metered.append({"lease_id": str(lease.lease_id), **dict(observation)})

    def limits(self, profile_key: str | None = None) -> tuple[EntryState, ...]:
        """Per-entry rows, each with its own reset clock. Never an aggregate verdict.

        Three subscriptions reset at three different times, and the one that matters is
        whichever entry an attempt would actually ride.
        """

        raw = self._engine.entries(profile_key or self._profile_key)
        return tuple(project_entry(record) for record in raw)

    def rotate(self, reason: str) -> RotationEvent | Refusal:
        """Record the engine's own rotation. Ctower does not run a second policy."""

        entries = self.limits()
        entry = entries[0] if entries else _absent_entry()
        return record_rotation(
            reason=reason,
            layer="pool",
            hook=self._spec.pool.cache_invalidation_hook,
            hook_completed=self._hook_completed(),
            entry=entry,
            completed_at=self._clock(),
        )

    def probe(self, response: ProbeResponse) -> ProbeReading | Refusal:
        """Classify a response the pool's own entries produced, on its body."""

        return classify_probe(self._spec.probe, response)

    def request_mint(self, identity: str | None) -> MintRequest:
        """Ask for a mint. The pool never performs one, and never copies an auth file."""

        return MintRequest(
            provider_key=self._spec.pool.providers[0],
            subscription_identity=identity,
            enactment=_CODEX_ENACTMENT,
        )

    def observe_window(self, identity: str, *, available: bool) -> FlapWindow:
        """Advance one entry's flap window. Good news alone does not make it selectable."""

        window = self._flap.get(identity, FlapWindow(consecutive_available=0)).observe(
            available=available
        )
        self._flap[identity] = window
        return window

    def _is_ready(self, entry: EntryState) -> bool:
        if not selectable(entry):
            return False
        identity = entry.subscription_identity
        if identity is None:
            return True
        window = self._flap.get(identity)
        return window is None or window.is_selectable()

    def _hook_completed(self) -> bool:
        return self._engine.invalidated_at(self._profile_key) <= self._engine.observed_at(
            self._profile_key
        )

    def _staleness_refusal(self) -> Refusal | None:
        if self._hook_completed():
            return None
        hook = self._spec.pool.cache_invalidation_hook
        return Refusal(
            name="pool-state-stale",
            observed=f"the pool state predates the last {hook}",
            meaning="a cache invalidated after this reading was taken; this is not exhaustion",
            action=f"complete {hook} and re-observe before believing any entry state",
            detail=(("hook", hook),),
        )


def _absent_entry() -> EntryState:
    """The shape a rotation is refused against when the engine reports no entries at all."""

    return EntryState(
        provider_key="unknown",
        subscription_identity=None,
        entry_label=None,
        registration_state="discovered",
        auth_state="healthy",
        quota_state="unknown",
        quota_reset_at=None,
        reach_state="unknown",
        request_count=0,
        last_status_observed=None,
        secret_fingerprint=None,
    )

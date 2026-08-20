"""The pool ctower PROVIDES for a harness that ships none: topology A.

One config home per account, so seats do not contend over a single live credential file, and
a rotation switches which home an attempt rides rather than which file sits where. There is
deliberately **no copy verb**: OAuth refresh tokens here are single-use chains, so installing
a copied auth file replays a consumed token and the provider revokes the whole chain — every
grant derived from that login dies at once. New material enters only through `request_mint`,
which this pool may ask for and never perform.

Four rules the fleet already paid for, in the order a rotation applies them:

1. **One live holder.** Two concurrent holders of a single-use refresh chain burn it between
   them. The holder is checked before anything is written, so a refused rotation leaves the
   journal untouched.
2. **Write-back before swap, always.** Refresh tokens rotate as they are used, so a stored
   snapshot goes stale the moment its account is live. Skipping the write-back is what killed
   a set of snapshots with `refresh_token_reused`.
3. **Never swap to a snapshot older than the live generation.** A rotation tool once installed
   a stale snapshot and revoked every grant at once, killing a review mid-run.
4. **Invalidate, then believe.** The config home is respawned before any entry state is
   re-observed; until it completes, an observation is stale rather than authoritative, and a
   stale reader once translated a spent window into "no available credentials" for a night.

Observation projects the same strict named-field allowlist the configure-and-observe side
uses. An account file keeps its tokens beside the metadata worth reading, so a reader that
copied the record rather than projecting named fields would move credential values into the
ledger.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from ctower_runner_sdk.credentials import (
    EntryState,
    Lease,
    MeterObservation,
    MintRequest,
    ProbeReading,
    ProbeResponse,
    exhaustion_refusal,
    project_entry,
    selectable,
)
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.rotation import FlapWindow, RotationEvent, classify_probe, record_rotation
from ctower_runner_sdk.spec import HarnessSpec

__all__ = ["ClaudeCodePool", "ConfigHome", "ConfigHomeStore"]

_MINT_ENACTMENT: Literal["operator-ceremony", "secret-reference"] = "operator-ceremony"


@dataclass(frozen=True, slots=True)
class ConfigHome:
    """One account's own `CLAUDE_CONFIG_DIR`. A reference, never a credential value.

    `refresh_generation` counts how many times this account's chain has rotated. It is the
    only thing that distinguishes a current snapshot from one that will replay a consumed
    token, and `account_identity` rather than `slug` is what an entry is keyed by, because a
    label has pointed at the wrong account twice.

    `entry` is the account file's own metadata record, held raw and read only through the
    projection allowlist: the fields beside the readable ones are the credential itself.
    """

    slug: str
    account_identity: str
    config_dir: str
    refresh_generation: int
    entry: Mapping[str, object]


@dataclass(slots=True)
class ConfigHomeStore:
    """Every account's home, which one is live, and what the last rotation actually did.

    `journal` is the ordered record of steps taken. It exists so write-back-before-swap is a
    checkable fact rather than a claim in a comment. `holder` is whichever lane currently
    holds the refresh chain; `respawn_completes` states whether the config-home respawn this
    host can run actually finishes, because a rotation whose hook did not complete is
    incomplete rather than done.
    """

    homes: dict[str, ConfigHome]
    live_slug: str
    holder: str | None = None
    hook_completed: bool = True
    respawn_completes: bool = True
    last_live_generation: dict[str, int] = field(default_factory=dict)
    journal: list[str] = field(default_factory=list)

    def live(self) -> ConfigHome:
        return self.homes[self.live_slug]

    def ordered(self) -> tuple[ConfigHome, ...]:
        return tuple(self.homes[slug] for slug in sorted(self.homes))

    def record(self, step: str) -> None:
        self.journal.append(step)


class ClaudeCodePool:
    """One provided pool per harness, resolved at `spawn`, carrying no copy verb."""

    def __init__(
        self,
        spec: HarnessSpec,
        store: ConfigHomeStore,
        profile_key: str,
        clock: Callable[[], datetime],
        lease_ids: Callable[[], UUID],
        holder: str = "",
    ) -> None:
        self._spec = spec
        self._store = store
        self._profile_key = profile_key
        self._clock = clock
        self._lease_ids = lease_ids
        self._holder = holder or profile_key
        self._flap: dict[str, FlapWindow] = {}
        self.metered: list[Mapping[str, object]] = []

    def acquire(self, model_ref: str, tier: str) -> Lease | Refusal:
        """Lease an entry clear on all three axes, or refuse with the whole diagnosis.

        Acquisition fails only when EVERY entry is unselectable. A pool holding two spent
        homes and one near-full one is not dry, and a status model with one word per account
        cannot say so.
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

    def meter(self, lease: Lease, observation: MeterObservation) -> None:
        """Project typed usage fields and preserve the lease as the authority."""

        self.metered.append(
            {
                "lease_id": str(lease.lease_id),
                "event": observation["event"],
                "model_ref": observation["model_ref"],
            }
        )

    def limits(self, profile_key: str | None = None) -> tuple[EntryState, ...]:
        """Per-entry rows, each with its own reset clock. Never an aggregate verdict.

        Three accounts reset at three different times, and the one that matters is whichever
        home an attempt would actually ride.
        """

        if profile_key is not None and profile_key != self._profile_key:
            return ()
        return tuple(project_entry(home.entry) for home in self._store.ordered())

    def rotate(self, reason: str) -> RotationEvent | Refusal:
        """Switch which config home is live, in the only order that is safe."""

        held = self._holder_refusal()
        if held is not None:
            return held
        target = self._rotation_target()
        if isinstance(target, Refusal):
            return target
        generation = self._write_back()
        stale = self._generation_refusal(target, generation)
        if stale is not None:
            return stale
        self._swap_in(target)
        return record_rotation(
            reason=reason,
            layer="pool",
            hook=self._spec.pool.cache_invalidation_hook,
            hook_completed=self._store.hook_completed,
            entry=project_entry(target.entry),
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
            enactment=_MINT_ENACTMENT,
        )

    def observe_window(self, identity: str, *, available: bool) -> FlapWindow:
        """Advance one account's flap window. Good news alone does not make it selectable."""

        window = self._flap.get(identity, FlapWindow(consecutive_available=0)).observe(
            available=available
        )
        self._flap[identity] = window
        return window

    def _write_back(self) -> int:
        """Write the live credential back before anything is swapped, and say so."""

        live = self._store.live()
        generation = live.refresh_generation + 1
        self._store.record(f"write-back live -> slot {live.slug}")
        self._store.homes[live.slug] = replace(live, refresh_generation=generation)
        self._store.last_live_generation[live.account_identity] = generation
        return generation

    def _swap_in(self, target: ConfigHome) -> None:
        self._store.record(f"swap-in slot {target.slug}")
        self._store.live_slug = target.slug
        hook = self._spec.pool.cache_invalidation_hook
        self._store.hook_completed = self._store.respawn_completes
        self._store.record(
            f"invalidate {hook}: {'completed' if self._store.hook_completed else 'incomplete'}"
        )

    def _rotation_target(self) -> ConfigHome | Refusal:
        entries = self.limits()
        ready = {entry.subscription_identity for entry in entries if self._is_ready(entry)}
        target = next(
            (
                home
                for home in self._store.ordered()
                if home.slug != self._store.live_slug and home.account_identity in ready
            ),
            None,
        )
        return target if target is not None else exhaustion_refusal(entries)

    def _is_ready(self, entry: EntryState) -> bool:
        if not selectable(entry):
            return False
        identity = entry.subscription_identity
        if identity is None:
            return True
        window = self._flap.get(identity)
        return window is None or window.is_selectable()

    def _holder_refusal(self) -> Refusal | None:
        current = self._store.holder
        if current is None or current == self._holder:
            return None
        return Refusal(
            name="rotation-refused-concurrent-holder",
            observed=f"{current!r} holds the refresh chain and {self._holder!r} asked to rotate",
            meaning="two holders of a single-use refresh chain burn it between them",
            action="wait for the holder to release, then rotate; nothing has been written",
            detail=(("holder", current), ("requested_by", self._holder)),
        )

    def _generation_refusal(self, target: ConfigHome, live_generation: int) -> Refusal | None:
        known = self._store.last_live_generation.get(
            target.account_identity, target.refresh_generation
        )
        if target.refresh_generation >= known:
            return None
        return Refusal(
            name="rotation-refused-stale-generation",
            observed=(
                f"slot {target.slug!r} holds generation {target.refresh_generation} "
                f"while generation {known} was last live for that account"
            ),
            meaning="swapping it in would replay a consumed refresh token and revoke the chain",
            action="re-mint this account's own device flow; a snapshot is never the repair",
            detail=(
                ("slot", target.slug),
                ("snapshot_generation", str(target.refresh_generation)),
                ("live_generation", str(known)),
                ("written_back_generation", str(live_generation)),
            ),
        )

    def _staleness_refusal(self) -> Refusal | None:
        if self._store.hook_completed:
            return None
        hook = self._spec.pool.cache_invalidation_hook
        return Refusal(
            name="pool-state-stale",
            observed=f"the pool state predates the last {hook}",
            meaning="a cache invalidated after this reading was taken; this is not exhaustion",
            action=f"complete {hook} and re-observe before believing any entry state",
            detail=(("hook", hook),),
        )

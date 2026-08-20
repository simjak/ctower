"""The pool ctower PROVIDES for a harness that ships none — by wrapping, not by writing.

The direct CLI holds one active account per config home and has no pool of its own, so the
layer is ctower's. It is not ctower's to *implement*: `tools/codex-auth-all`,
`tools/codex-grant-ceremony`, `tools/codex-rotate-fallback` and `tools/codex-pool` already own
enrolment, per-account re-mint, generation-guarded rotation, and the ~5h cooldown, and a fifth
rotation implementation over the same single-use refresh chains would be a race rather than a
spare. So this class does four things and no more:

1. **Selects.** An entry is leased only when registration, auth, quota, and reach are all
   clear, and only after a window that returned to `available` has held a full observation
   cycle. A brief is staged inside that window and nothing launches.
2. **Refuses before asking.** A rotation is refused rather than attempted while the live entry
   is `edge-challenged`: this survey answers `egress_topology: shared`, so every entry behind
   that egress is equally unreachable and no ceremony repairs a provider's edge.
3. **Reports the ceremony's own verdict.** The generation guard lives inside
   `codex-rotate-fallback`, hardened there after a stale snapshot revoked every grant derived
   from one login at once. This class surfaces that refusal by name and does not re-derive it.
4. **Records.** The account file carries *current* state and is overwritten as it changes, so a
   ledger is the only thing that can answer how often the fleet rotates and what it costs.

There is deliberately **no copy verb**, and nothing here writes an account file at all.
Observation projects the same strict named-field allowlist the configure-and-observe side uses:
an account record keeps its tokens beside the metadata worth reading, so a reader that copied
the record rather than projecting named fields would move credential values into the ledger.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from ctower_runner.codex.ceremonies import CeremonyOutcome, ceremony_for
from ctower_runner.codex.substrate import CeremonyPort
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

__all__ = ["CodexAccount", "CodexPool", "ConfigHomeStore"]

_MINT_ENACTMENT: Literal["operator-ceremony", "secret-reference"] = "operator-ceremony"


@dataclass(frozen=True, slots=True)
class CodexAccount:
    """One account's own `CODEX_HOME`. A reference, never a credential value.

    `refresh_generation` counts how many times this account's chain has rotated; it is the only
    thing that distinguishes a current grant from a snapshot that will replay a consumed token.
    The account's decoded identity rather than its label is what an entry is keyed by, because
    a label has pointed at the wrong account twice and once hid two accounts behind one name.

    `entry` is the account record as its own store keeps it, held raw and read only through the
    projection allowlist: the fields beside the readable ones are the credential itself.
    """

    account_identity: str
    codex_home: str
    refresh_generation: int
    entry: Mapping[str, object]


@dataclass(slots=True)
class ConfigHomeStore:
    """Every account's home, which one is live, and what the last ceremony actually did.

    `journal` is the ordered record of steps, so what a ceremony was asked is a checkable fact
    rather than a claim in a comment. `hook_completed` states whether the config-home respawn
    finished: until it does, an entry state read now comes from a cache the rotation already
    invalidated, and a stale reader once translated a spent window into "no available
    credentials" for a whole night.
    """

    accounts: dict[str, CodexAccount]
    live_identity: str
    hook_completed: bool = True
    journal: list[str] = field(default_factory=list)

    def live(self) -> CodexAccount:
        return self.accounts[self.live_identity]

    def ordered(self) -> tuple[CodexAccount, ...]:
        return tuple(self.accounts[identity] for identity in sorted(self.accounts))

    def record(self, step: str) -> None:
        self.journal.append(step)


class CodexPool:
    """One provided pool per harness, resolved at `spawn`, carrying no copy verb."""

    def __init__(
        self,
        spec: HarnessSpec,
        store: ConfigHomeStore,
        ceremonies: CeremonyPort,
        profile_key: str,
        clock: Callable[[], datetime],
        lease_ids: Callable[[], UUID],
    ) -> None:
        self._spec = spec
        self._store = store
        self._ceremonies = ceremonies
        self._profile_key = profile_key
        self._clock = clock
        self._lease_ids = lease_ids
        self._flap: dict[str, FlapWindow] = {}
        self._auto_flap: set[str] = set()
        self.metered: list[dict[str, str]] = []

    def acquire(self, model_ref: str, tier: str) -> Lease | Refusal:
        """Lease an entry clear on all three axes, or refuse with the whole diagnosis.

        Acquisition fails only when EVERY entry is unselectable. A pool holding two accounts
        resting out their cooldown and one near-full is not dry, and a status model with one
        word per substrate cannot say so.
        """

        if tier != self._profile_key:
            return Refusal(
                name="harness-credential-profile-mismatch",
                observed=f"the codex pool for {self._profile_key!r} was asked for {tier!r}",
                meaning="a lease cannot be relabelled as a foreign profile",
                action=f"acquire through the registered {self._profile_key!r} pool",
                detail=(("registered_profile", self._profile_key), ("requested_profile", tier)),
            )
        identity_refusal = self._identity_refusal()
        if identity_refusal is not None:
            return identity_refusal
        stale = self._staleness_refusal()
        if stale is not None:
            return stale
        entries = self.limits()
        self._ingest_availability(entries)
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

    def home_for(self, identity: str | None) -> str | Refusal:
        """Resolve the selected account to its config-home reference after validation."""

        refusal = self._identity_refusal()
        if refusal is not None:
            return refusal
        if identity is None or identity not in self._store.accounts:
            return Refusal(
                name="credential-identity-mismatch",
                observed="the selected lease has no validated account identity",
                meaning="a launch without an account home cannot preserve credential lineage",
                action="re-read the pool and acquire a validated entry",
            )
        return self._store.accounts[identity].codex_home

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

        Three accounts rest on three different clocks, and the one that matters is whichever
        home an attempt would actually ride.
        """

        if profile_key is not None and profile_key != self._profile_key:
            return ()
        return tuple(project_entry(account.entry) for account in self._store.ordered())

    def rotate(self, reason: str) -> RotationEvent | Refusal:
        """Ask the fleet's own generation-guarded ceremony, then guard and record its answer."""

        hook = self._spec.pool.cache_invalidation_hook
        live = project_entry(self._store.live().entry)
        if live.reach_state == "edge-challenged":
            return record_rotation(
                reason=reason,
                layer="pool",
                hook=hook,
                hook_completed=True,
                entry=live,
                completed_at=self._clock(),
            )
        dry = self._no_target_refusal()
        if dry is not None:
            return dry
        asked = ceremony_for("rotate")
        if isinstance(asked, Refusal):
            return asked
        self._store.record(f"ask {asked.ceremony}")
        try:
            outcome = self._ceremonies.run(asked)
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise
            self._store.hook_completed = False
            return _unknown_progress_refusal(hook)
        refused = _ceremony_refusal(outcome)
        if refused is not None:
            return refused
        return self._commit_rotation(reason, hook, outcome)

    def _commit_rotation(
        self, reason: str, hook: str, outcome: CeremonyOutcome
    ) -> RotationEvent | Refusal:
        """Validate the candidate before adopting it into the live store."""

        candidate = self._candidate_entry(outcome)
        if isinstance(candidate, Refusal):
            self._store.hook_completed = False
            return candidate
        event = record_rotation(
            reason=reason,
            layer="pool",
            hook=hook,
            hook_completed=outcome.hook_completed,
            entry=candidate,
            completed_at=self._clock(),
        )
        if isinstance(event, Refusal):
            if not outcome.hook_completed:
                self._store.hook_completed = False
            return event
        target_identity = outcome.installed_identity or self._store.live_identity
        stale = _generation_refusal(
            self._store.accounts[target_identity].refresh_generation,
            outcome.installed_generation,
        )
        if stale is not None:
            self._store.hook_completed = False
            return stale
        self._adopt(outcome)
        return event

    def probe(self, response: ProbeResponse) -> ProbeReading | Refusal:
        """Classify a response the pool's own entries produced, on its body."""

        return classify_probe(self._spec.probe, response)

    def request_mint(self, identity: str | None) -> MintRequest | Refusal:
        """Ask for a mint, unless the requested identity is blocked by the shared edge."""

        if identity is not None and identity in self._store.accounts:
            entry = project_entry(self._store.accounts[identity].entry)
            if entry.reach_state == "edge-challenged":
                return Refusal(
                    name="credential-mint-refused-unreachable",
                    observed="the requested identity is edge-challenged",
                    meaning="an egress fault is shared by every entry and a mint cannot repair it",
                    action="escalate the infra-plane challenge; do not mint or rotate",
                    detail=(("identity", identity), ("reach", entry.reach_state)),
                )
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

    def exhausted(self) -> bool:
        """Whether no entry is selectable. This is the fact `liveness` reports over a pane.

        A stale reading is not exhaustion, so it does not answer true here either: the pool
        that cannot see its own state says so through `acquire`, by name.
        """

        return self._store.hook_completed and not [
            entry for entry in self.limits() if self._is_ready(entry)
        ]

    def _ingest_availability(self, entries: tuple[EntryState, ...]) -> None:
        """Feed raw entry state through the recovery bar used by acquisition."""

        for entry in entries:
            identity = entry.subscription_identity
            if identity is None:
                continue
            available = not entry.blocking_axes()
            if identity in self._auto_flap:
                self.observe_window(identity, available=available)
            elif not available and identity not in self._flap:
                self.observe_window(identity, available=False)
                self._auto_flap.add(identity)

    def _candidate_entry(self, outcome: CeremonyOutcome) -> EntryState | Refusal:
        """Project the ceremony target without changing the live store."""

        identity = outcome.installed_identity or self._store.live_identity
        account = self._store.accounts.get(identity)
        if account is None:
            return Refusal(
                name="rotation-refused-unknown-identity",
                observed="the ceremony returned an identity absent from the registered pool",
                meaning="an unknown target cannot receive a lease or replace the live identity",
                action="invalidate the uncertain rotation and re-observe the registered pool",
                detail=(("identity", identity),),
            )
        try:
            return project_entry(account.entry)
        except (KeyError, TypeError, ValueError):
            return Refusal(
                name="rotation-refused-unknown-identity",
                observed="the ceremony target could not be projected to a registered entry",
                meaning="a malformed target cannot receive a lease or replace the live identity",
                action="invalidate the uncertain rotation and repair the pool record",
                detail=(("identity", identity),),
            )

    def _adopt(self, outcome: CeremonyOutcome) -> EntryState:
        """Believe what the ceremony reported, and record which hook it left outstanding."""

        identity = outcome.installed_identity or self._store.live_identity
        account = self._store.accounts[identity]
        self._store.accounts[identity] = replace(
            account, refresh_generation=outcome.installed_generation
        )
        self._store.live_identity = identity
        self._store.hook_completed = outcome.hook_completed
        self._store.record(f"{outcome.ceremony} installed generation")
        return project_entry(self._store.accounts[identity].entry)

    def _no_target_refusal(self) -> Refusal | None:
        """Refuse a rotation with nowhere to go, carrying every entry's own diagnosis."""

        entries = self.limits()
        live = self._store.live_identity
        movable = [
            entry
            for entry in entries
            if entry.subscription_identity != live and self._is_ready(entry)
        ]
        return None if movable else exhaustion_refusal(entries)

    def _is_ready(self, entry: EntryState) -> bool:
        if not selectable(entry):
            return False
        identity = entry.subscription_identity
        if identity is None:
            return True
        window = self._flap.get(identity)
        return window is None or window.is_selectable()

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

    def _identity_refusal(self) -> Refusal | None:
        """Require store key, decoded identity, and projected identity to agree."""

        for store_key, account in self._store.accounts.items():
            try:
                projected = project_entry(account.entry).subscription_identity
            except (KeyError, TypeError, ValueError):
                return Refusal(
                    name="credential-identity-mismatch",
                    observed="an account record could not be projected to a validated identity",
                    meaning="selection cannot establish which config home owns the lease",
                    action="repair the account identity record before selecting it",
                )
            if (
                not account.account_identity
                or store_key != account.account_identity
                or projected != account.account_identity
            ):
                return Refusal(
                    name="credential-identity-mismatch",
                    observed="store key, decoded account identity, and projected identity disagree",
                    meaning="a caller-supplied label or home cannot establish credential lineage",
                    action="repair the account record before selecting it",
                    detail=(
                        ("store_key", store_key),
                        ("account_identity", account.account_identity),
                        ("projected_identity", projected or "unknown"),
                    ),
                )
        return None


def _generation_refusal(current: int, installed_generation: int) -> Refusal | None:
    if not isinstance(installed_generation, int) or installed_generation <= current:
        return Refusal(
            name="rotation-refused-stale-generation",
            observed=(
                f"the ceremony reported generation {installed_generation!r} "
                f"below live {current}"
            ),
            meaning="a rotation may not move the refresh chain backward or leave it unchanged",
            action="discard the stale outcome and re-observe the live generation",
            detail=(
                ("installed_generation", str(installed_generation)),
                ("live_generation", str(current)),
            ),
        )
    return None


def _unknown_progress_refusal(hook: str) -> Refusal:
    return Refusal(
        name="rotation-incomplete",
        observed="the rotation ceremony failed after its external progress became uncertain",
        meaning=(
            "the pool cannot trust entry state until cache invalidation "
            "and re-observation complete"
        ),
        action=f"complete {hook}, then re-observe; no entry is selectable meanwhile",
        detail=(("hook", hook), ("outcome", "unknown")),
    )


def _ceremony_refusal(outcome: CeremonyOutcome) -> Refusal | None:
    """Surface the ceremony's own verdict by name, without forming a second opinion."""

    if outcome.refusal_name is None:
        return None
    observed = f"{outcome.ceremony} refused at generation {outcome.installed_generation}"
    return Refusal(
        name="rotation-refused-stale-generation",
        observed=observed,
        meaning="installing that snapshot would replay a consumed token and revoke the chain",
        action="re-mint this account's own device flow; a snapshot is never the repair",
        detail=(
            ("ceremony", outcome.ceremony),
            ("ceremony_refusal", outcome.refusal_name),
            ("snapshot_generation", str(outcome.installed_generation)),
        ),
    )

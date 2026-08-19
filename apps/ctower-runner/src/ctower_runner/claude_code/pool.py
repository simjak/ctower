"""The pool ctower PROVIDES for a harness that ships none: topology A.

One config home per account, so seats do not contend over a single live credential file, and
a rotation switches which home an attempt rides rather than which file sits where. There is
deliberately **no copy verb**: OAuth refresh tokens here are single-use chains, so installing
a copied auth file replays a consumed token and the provider revokes the whole chain — every
grant derived from that login dies at once. New material enters only through `request_mint`,
which this pool may ask for and never perform.

Four rules the fleet already paid for, in the order a rotation applies them:

1. **One live holder.** Two concurrent holders of a single-use refresh chain burn it. The
   holder is checked before anything is written, so a refused rotation leaves no trace.
2. **Write-back before swap, always.** Refresh tokens rotate as they are used, so a stored
   snapshot goes stale the moment its account is live. Skipping the write-back is what killed
   the codex snapshots with `refresh_token_reused`.
3. **Never install a snapshot older than the live generation.** A rotation tool once
   installed a stale snapshot and revoked every grant at once, killing a review mid-run.
4. **Invalidate, then believe.** Whatever caches the credential is restarted before any entry
   state is re-observed, or a stale reader marks healthy entries dead.

SEAM INTEGRATION (CT-I1-041): `rotate` becomes the provided-class implementation behind the
seam's `CredentialPool.rotate`, and its outcome is metered as one context re-read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ctower_runner.claude_code.refusal import Refusal
from ctower_runner.claude_code.spec import POOL_CACHE_INVALIDATION_HOOK

__all__ = [
    "PROVIDED_POOL_VERBS",
    "ConfigHome",
    "ConfigHomeStore",
    "RotationOutcome",
    "believe_entry_state",
    "rotate",
]

# The Interface this binding provides. The absent verb is a design element: there is no copy,
# install, or snapshot path, so the rule that a copied auth file self-revokes is not something
# an implementer has to remember.
PROVIDED_POOL_VERBS: tuple[str, ...] = (
    "acquire",
    "meter",
    "limits",
    "rotate",
    "probe",
    "request_mint",
)


@dataclass(frozen=True, slots=True)
class ConfigHome:
    """One account's own `CLAUDE_CONFIG_DIR`. A reference, never a credential value.

    `refresh_generation` counts how many times this account's chain has rotated. It is the
    only thing that distinguishes a current snapshot from one that will replay a consumed
    token, and `account_identity` rather than `slug` is what an entry is keyed by, because a
    label has pointed at the wrong account twice.
    """

    slug: str
    account_identity: str
    config_dir: str
    refresh_generation: int


@dataclass(slots=True)
class ConfigHomeStore:
    """Every account's home, which one is live, and what the last rotation actually did.

    `journal` is the ordered record of steps taken. It exists so write-back-before-swap is a
    checkable fact rather than a claim in a comment.
    """

    homes: dict[str, ConfigHome]
    live_slug: str
    last_live_generation: dict[str, int] = field(default_factory=dict)
    holder: str | None = None
    journal: tuple[str, ...] = ()

    def live(self) -> ConfigHome:
        return self.homes[self.live_slug]

    def record(self, step: str) -> None:
        self.journal = (*self.journal, step)


@dataclass(frozen=True, slots=True)
class RotationOutcome:
    """One rotation, and whether its cache-invalidation hook completed."""

    from_slug: str
    to_slug: str
    steps: tuple[str, ...]
    hook: str
    hook_completed: bool


def rotate(
    store: ConfigHomeStore,
    *,
    target_slug: str,
    holder: str,
    live_generation: int,
    invalidate: bool = True,
) -> RotationOutcome | Refusal:
    """Switch which config home is live, or refuse by name having changed nothing unsafe."""

    if store.holder is not None and store.holder != holder:
        return _held_refusal(store.holder, holder)
    live = store.live()
    store.record(f"write-back live -> slot {live.slug}")
    store.homes[live.slug] = ConfigHome(
        live.slug, live.account_identity, live.config_dir, live_generation
    )
    store.last_live_generation[live.account_identity] = live_generation
    target = store.homes[target_slug]
    known = store.last_live_generation.get(target.account_identity, target.refresh_generation)
    if target.refresh_generation < known:
        return _stale_refusal(target, known)
    store.record(f"swap-in slot {target_slug}")
    store.live_slug = target_slug
    if invalidate:
        store.record(f"invalidate {POOL_CACHE_INVALIDATION_HOOK}")
    return RotationOutcome(
        from_slug=live.slug,
        to_slug=target_slug,
        steps=store.journal,
        hook=POOL_CACHE_INVALIDATION_HOOK,
        hook_completed=invalidate,
    )


def believe_entry_state(outcome: RotationOutcome, *, observed_state: str) -> str | Refusal:
    """Return the observed state, or refuse to record one taken before the hook completed."""

    if outcome.hook_completed:
        return observed_state
    return Refusal(
        name="rotation-incomplete",
        observed=f"the {outcome.hook} hook has not completed",
        meaning="any state read now comes from a cache this rotation already invalidated",
        action=f"complete {outcome.hook}, then re-observe; the pre-hook reading is discarded",
        detail=(("hook", outcome.hook), ("observed_state", observed_state)),
    )


def _held_refusal(current: str, requested: str) -> Refusal:
    return Refusal(
        name="rotation-refused-concurrent-holder",
        observed=f"{current!r} holds the refresh lock and {requested!r} asked to rotate",
        meaning="two holders of a single-use refresh chain burn it between them",
        action="wait for the holder to release, then rotate; nothing was written",
        detail=(("holder", current), ("requested_by", requested)),
    )


def _stale_refusal(target: ConfigHome, known: int) -> Refusal:
    return Refusal(
        name="rotation-refused-stale-generation",
        observed=(
            f"slot {target.slug!r} holds generation {target.refresh_generation} "
            f"while generation {known} was last live for that account"
        ),
        meaning="installing it would replay a consumed refresh token and revoke the chain",
        action="re-mint this account's own device flow; a snapshot is never the repair",
        detail=(
            ("slot", target.slug),
            ("snapshot_generation", str(target.refresh_generation)),
            ("live_generation", str(known)),
        ),
    )

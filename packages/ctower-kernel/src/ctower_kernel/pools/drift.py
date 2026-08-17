"""Reconcile an observed sweep against the authored desired topology.

Drift is a derived read, never a sixth verb and never a stored verdict. Both directions
have a home: `missing` is desired-but-absent and routes to the enactment path its
subscription kind declares, and `unregistered` is present-but-undesired and maps to the
non-selectable `discovered` state pending an operator keep-or-evict decision.

A missing grant is not an exhausted one. A topology that is nineteen of twenty-four minted
must say so, rather than reporting the five gaps as ordinary unavailability — that is the
difference between an operator ceremony list and a pool that looks merely busy.
"""

from __future__ import annotations

from dataclasses import replace

from ctower_kernel.pools.models import PoolDriftFinding
from ctower_kernel.pools.topology import DesiredSubscription, desired_profile
from ctower_kernel.record.pool_events import PoolObservationEntryPayload

__all__ = ["reconcile", "resolve_registration"]

_UNREGISTERED_ENACTMENT = "operator-ceremony"


def resolve_registration(
    harness_key: str, entries: tuple[PoolObservationEntryPayload, ...]
) -> tuple[PoolObservationEntryPayload, ...]:
    """Resolve each observed entry against the registry that decides selectability.

    The sweep states the engine's fact — this entry is in the pool. Whether it is one this
    profile is supposed to hold is ctower's question, and an identity the desired topology
    does not declare becomes `discovered`: reachable, and never selectable, until an
    operator keeps or evicts it.
    """

    declared = frozenset(
        subscription.subscription_identity
        for subscription in desired_profile(harness_key)
        if subscription.subscription_identity is not None
    )
    keyed_providers = frozenset(
        subscription.provider_key
        for subscription in desired_profile(harness_key)
        if subscription.subscription_identity is not None
    )
    return tuple(_resolved(entry, declared, keyed_providers) for entry in entries)


def _resolved(
    entry: PoolObservationEntryPayload,
    declared: frozenset[str],
    keyed_providers: frozenset[str],
) -> PoolObservationEntryPayload:
    if entry.provider_key not in keyed_providers:
        return entry
    if entry.subscription_identity is not None and entry.subscription_identity in declared:
        return entry
    return replace(entry, registration_state="discovered")


def reconcile(
    harness_key: str, entries: tuple[PoolObservationEntryPayload, ...]
) -> tuple[PoolDriftFinding, ...]:
    """Return typed findings in both directions, in authored-desired-then-observed order."""

    desired = desired_profile(harness_key)
    observed = frozenset(
        (entry.provider_key, entry.subscription_identity)
        for entry in entries
        if entry.registration_state == "enrolled"
    )
    observed_providers = frozenset(entry.provider_key for entry in entries)
    findings = [
        _missing(subscription)
        for subscription in desired
        if not _satisfied(subscription, observed, observed_providers)
    ]
    findings.extend(
        _unregistered(entry) for entry in entries if entry.registration_state == "discovered"
    )
    return tuple(findings)


def _satisfied(
    subscription: DesiredSubscription,
    observed: frozenset[tuple[str, str | None]],
    observed_providers: frozenset[str],
) -> bool:
    """An identity-bearing subscription is satisfied only by that identity.

    Labels have twice pointed at the wrong account, so a keyed subscription is matched on
    the decoded identity claim alone. A key-wired subscription has no identity to decode,
    so its presence is the provider's own presence in the pool.
    """

    if subscription.subscription_identity is None:
        return subscription.provider_key in observed_providers
    return (subscription.provider_key, subscription.subscription_identity) in observed


def _missing(subscription: DesiredSubscription) -> PoolDriftFinding:
    identity = subscription.subscription_identity
    subject = identity if identity is not None else f"a {subscription.provider_key} key"
    return PoolDriftFinding(
        finding="missing",
        provider_key=subscription.provider_key,
        subscription_identity=identity,
        enactment=subscription.enactment,
        detail=(
            f"The desired topology holds {subject} for this profile and the sweep observed "
            f"no enrolled entry for it. This is an absent subscription, not an exhausted one."
        ),
    )


def _unregistered(entry: PoolObservationEntryPayload) -> PoolDriftFinding:
    identity = entry.subscription_identity
    subject = identity if identity is not None else f"an unidentified {entry.provider_key} entry"
    return PoolDriftFinding(
        finding="unregistered",
        provider_key=entry.provider_key,
        subscription_identity=identity,
        enactment=_UNREGISTERED_ENACTMENT,
        detail=(
            f"The sweep observed {subject} in the pool and the desired topology does not "
            f"declare it. It stays non-selectable pending an operator keep-or-evict decision."
        ),
    )

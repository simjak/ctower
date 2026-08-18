"""Project a harness's own credential store into one observation request.

This module is adapter-side: it reads the local harness state a seat runs on and its only
product is a `PoolObservationRequest` the CLI posts through the API under that seat's own
credential. It never writes a harness file, never connects to record-tier persistence, and
never makes a provider call — v1 observes stored metadata, and the usage-API probes that
would turn `unknown` into a measured state are a later slice.

Reading is projection, not copying. A hermes `auth.json` credential-pool entry carries
`access_token` and `refresh_token` in the same object as `last_status` and `request_count`,
so this module names every field it takes and takes nothing else. What it never does is
read a token into a variable that could reach a request body, a log line, or an exception
message; the only credential-derived value that leaves here is a fingerprint.

Identity comes from the credential's own decoded claim, never from the label. Labels have
twice pointed at the wrong account on this fleet — one `simasjak-gmail` label was a
different account's mint, and two identically-named labels hid two accounts — so a label is
carried as a display attribute with no authority and an undecodable entry reports its
identity as unknown rather than guessing from the label.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ctower_client.models import (
    PoolAuthState,
    PoolObservationRequest,
    PoolObservedEntry,
    PoolQuotaState,
    PoolReachState,
    PoolRegistrationState,
)

__all__: tuple[str, ...] = ()

_IDENTITY_CLAIM = "https://api.openai.com/profile"
_EXHAUSTED_STATUSES = frozenset({"exhausted", "usage_limit_reached", "rate_limited"})
_UNFUNDED_STATUSES = frozenset({"unfunded", "insufficient_quota"})
_DEAD_AUTH_STATUSES = frozenset({"needs_login", "unauthorized"})
_BURNED_AUTH_STATUSES = frozenset({"refresh_token_reused"})
_MAX_ENTRIES = 64
_JWT_SEGMENTS = 3
_MIN_PROVIDER_KEY = 3
_MAX_PROVIDER_KEY = 64


@dataclass(frozen=True, slots=True)
class _Projection:
    """The named fields one pool entry contributes, and nothing adjacent to them."""

    provider_key: str
    identity: str | None
    label: str | None
    status: str | None
    reset_at: datetime | None
    request_count: int
    fingerprint: str | None


def observation_request(
    profile_home: Path, *, profile_key: str, observed_at: datetime
) -> PoolObservationRequest:
    """Build one sweep of a hermes profile home into a wire-ready observation."""

    document = _read_json(profile_home / "auth.json")
    pool = cast(dict[str, object], document.get("credential_pool") or {})
    projections = [
        _project(provider_key, cast(dict[str, object], entry))
        for provider_key, entries in sorted(pool.items())
        if isinstance(entries, list)
        for entry in cast(list[object], entries)
        if isinstance(entry, dict)
    ]
    return PoolObservationRequest(
        harness_key="hermes",
        profile_key=profile_key,
        observed_at=observed_at,
        entries=tuple(_entry(projection) for projection in projections[:_MAX_ENTRIES]),
    )


def _project(provider_key: str, entry: dict[str, object]) -> _Projection:
    """Take the named metadata fields, and never the token fields beside them."""

    return _Projection(
        provider_key=_provider_key(provider_key),
        identity=_identity(entry),
        label=_text(entry.get("label"), limit=128),
        status=_status_word(entry.get("last_status")),
        reset_at=_timestamp(entry.get("last_error_reset_at")),
        request_count=_count(entry.get("request_count")),
        fingerprint=_fingerprint(entry),
    )


def _entry(projection: _Projection) -> PoolObservedEntry:
    """Report presence in the pool; the registry, not the feeder, decides enrolment.

    Whether an identity ctower can reach is one ctower is entitled to select is a registry
    question, and the registry is not on this side of the seam. The sweep therefore states
    the engine's own fact — this entry is in the pool — and the read path resolves it
    against the authored desired topology.
    """

    quota_state, reset_at = _quota(projection)
    return PoolObservedEntry(
        provider_key=projection.provider_key,
        subscription_identity=projection.identity,
        entry_label=projection.label,
        registration_state=PoolRegistrationState.ENROLLED,
        auth_state=_auth(projection.status),
        quota_state=quota_state,
        quota_reset_at=reset_at,
        reach_state=PoolReachState.UNKNOWN,
        request_count=projection.request_count,
        last_status_observed=projection.status,
        secret_fingerprint=projection.fingerprint,
    )


def _auth(status: str | None) -> PoolAuthState:
    """A mint moves only this axis, so nothing but an auth word may set it."""

    if status in _BURNED_AUTH_STATUSES:
        return PoolAuthState.CHAIN_BURNED
    if status in _DEAD_AUTH_STATUSES:
        return PoolAuthState.LINEAGE_DEAD
    return PoolAuthState.HEALTHY


def _quota(projection: _Projection) -> tuple[PoolQuotaState, datetime | None]:
    """Cap observed with a known reset is a different state from cap with no clock."""

    status = projection.status
    if status in _UNFUNDED_STATUSES:
        return PoolQuotaState.UNFUNDED, None
    if status in _EXHAUSTED_STATUSES:
        return PoolQuotaState.CAPPED, projection.reset_at
    if status is None:
        return PoolQuotaState.UNKNOWN, None
    return PoolQuotaState.AVAILABLE, None


def _identity(entry: dict[str, object]) -> str | None:
    """Decode the identity claim the credential carries about itself."""

    token = entry.get("access_token")
    if not isinstance(token, str):
        return None
    segments = token.split(".")
    if len(segments) != _JWT_SEGMENTS:
        return None
    try:
        padded = segments[1] + "=" * (-len(segments[1]) % 4)
        claims = cast(dict[str, object], json.loads(base64.urlsafe_b64decode(padded)))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    profile = claims.get(_IDENTITY_CLAIM)
    if not isinstance(profile, dict):
        return None
    return _text(cast(dict[str, object], profile).get("email"), limit=254)


def _fingerprint(entry: dict[str, object]) -> str | None:
    """Carry a credential as a fingerprint, and refuse to carry it any other way."""

    existing = entry.get("secret_fingerprint")
    if isinstance(existing, str) and existing:
        return f"sha256:{hashlib.sha256(existing.encode()).hexdigest()}"
    token = entry.get("refresh_token")
    if not isinstance(token, str) or not token:
        return None
    return f"sha256:{hashlib.sha256(token.encode()).hexdigest()}"


def _provider_key(value: str) -> str:
    normalized = value.replace("_", "-").replace(":", "-").casefold()
    within_contract = _MIN_PROVIDER_KEY <= len(normalized) <= _MAX_PROVIDER_KEY
    return normalized if within_contract else "unnamed-provider"


def _status_word(value: object) -> str | None:
    text = _text(value, limit=64)
    if text is None:
        return None
    normalized = text.replace(" ", "_").casefold()
    return normalized if normalized[:1].isalpha() else None


def _text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:limit]


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cast(dict[str, object], document) if isinstance(document, dict) else {}

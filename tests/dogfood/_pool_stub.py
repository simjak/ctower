"""The credential-pool sweep the dogfood limits surface reads.

It is the fleet's own awkward shape rather than a tidy one: two accounts capped
at two different times, one available with no clock at all, one entry the record
holds no name for, one axis nobody could observe, and a drift finding. A stub
that answered with one healthy account would let a surface that collapses the
pool into a single word pass.

The poisoned field is the point of the second half. `PoolEntryState` — the read
projection this route answers with — has no field a credential value can occupy,
while the observation that feeds it may carry a fingerprint. This payload
carries one anyway, so the rendered document can be asked whether the strict
named-field parser really kept it off the screen, rather than trusted to.
"""

from __future__ import annotations

from typing import Any

__all__ = (
    "CAPPED_IDENTITY",
    "CAPPED_RESET_AT",
    "DRIFT_DETAIL",
    "POISON_FINGERPRINT",
    "PROFILE_KEY",
    "SELECTABLE_IDENTITY",
    "UNMETERED_PROVIDER",
    "limits",
)

PROFILE_KEY = "engineer"
CAPPED_IDENTITY = "capped@example.invalid"
SELECTABLE_IDENTITY = "available@example.invalid"
UNMETERED_PROVIDER = "zai"
CAPPED_RESET_AT = "2026-08-20T06:29:00Z"
DRIFT_DETAIL = "the authored topology names this account and the sweep did not observe it"
#: Credential-shaped material, on an entry the read projection has no field for.
POISON_FINGERPRINT = "sha256:" + "b" * 64
_OBSERVED_AT = "2026-08-17T20:00:00Z"


def _entry(
    provider_key: str,
    identity: str | None,
    *,
    quota_state: str,
    quota_reset_at: str | None,
    selectable: bool,
    request_count: int,
    reach_state: str = "ok",
    label: str | None = None,
    status: str | None = None,
    millicredits: int | None = None,
) -> dict[str, Any]:
    return {
        "provider_key": provider_key,
        "subscription_identity": identity,
        "entry_label": label,
        "registration_state": "enrolled",
        "auth_state": "healthy",
        "quota_state": quota_state,
        "quota_reset_at": quota_reset_at,
        "reach_state": reach_state,
        "selectable": selectable,
        "request_count": request_count,
        "last_status_observed": status,
        "credit_state": "unmetered" if millicredits is None else "metered",
        "metered_millicredits": millicredits,
        "observed_at": _OBSERVED_AT,
    }


def _entries() -> list[dict[str, Any]]:
    """Four accounts of one profile: two clocks, one absence, one unknown axis."""
    capped = _entry(
        "openai-codex",
        CAPPED_IDENTITY,
        quota_state="capped",
        quota_reset_at=CAPPED_RESET_AT,
        selectable=False,
        request_count=412,
        label="primary",
        status="exhausted",
    )
    return [
        # the poisoned one: a field the read projection has nowhere to put
        {**capped, "secret_fingerprint": POISON_FINGERPRINT},
        _entry(
            "openai-codex",
            "second@example.invalid",
            quota_state="capped",
            quota_reset_at="2026-08-20T08:00:00Z",
            selectable=False,
            request_count=388,
        ),
        _entry(
            "openai-codex",
            SELECTABLE_IDENTITY,
            quota_state="available",
            quota_reset_at=None,
            selectable=True,
            request_count=3,
            millicredits=1250,
        ),
        _entry(
            UNMETERED_PROVIDER,
            None,
            quota_state="unknown",
            quota_reset_at=None,
            selectable=True,
            request_count=17,
            reach_state="edge-challenged",
        ),
    ]


def _drift() -> list[dict[str, Any]]:
    return [
        {
            "finding": "missing",
            "provider_key": "openai-codex",
            "subscription_identity": "absent@example.invalid",
            "enactment": "operator-ceremony",
            "detail": DRIFT_DETAIL,
        }
    ]


def _weights() -> list[dict[str, Any]]:
    return [
        {
            "subscription_key": "codex-plus",
            "model_ref": "gpt-5",
            "input_millicredits_per_mtok": 1000,
            "cached_input_millicredits_per_mtok": 100,
            "output_millicredits_per_mtok": 8000,
        }
    ]


def limits() -> dict[str, Any]:
    """The whole `/v1/pools` answer, including one entry carrying a fingerprint."""
    return {
        "profiles": [
            {
                "harness_key": "hermes",
                "profile_key": PROFILE_KEY,
                "entries": _entries(),
                "drift": _drift(),
                "selectable_entry_count": 2,
                "earliest_known_reset_at": CAPPED_RESET_AT,
                "observed_at": _OBSERVED_AT,
            }
        ],
        "weights": _weights(),
        "topology_revision": 4,
    }

"""The feeder projects named fields out of a harness credential store, and nothing else.

Fixtures are materialized rather than committed: a realistic OAuth entry carries a JWT-shaped
access token, and a repository that commits one has put detector-shaped credential material
in its own tree. The poisoned fixture is the point of the suite — its token sits exactly where
a real one sits, adjacent to the metadata being read, and must not appear anywhere in the
request the feeder produces.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from ctowerctl._pool_feeder import observation_request

__all__: tuple[str, ...] = ()

POISON_MARKER = "PoIsOnEdCredentialMaterialThatMustNeverSurface"
_OBSERVED_AT = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
_JAKIT = "simonas@jakit.lt"
_JAKITLABS = "simonas@jakitlabs.com"
_SIMASJAK = "simasjak@gmail.com"
_DESIRED_HERMES_ENTRIES = 5
_CODEX_ENTRIES = 3
_DRIFTED_ENTRIES = 2


def _segment(payload: dict[str, object]) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return raw.rstrip("=")


def _access_token(identity: str) -> str:
    """Build a real-shaped credential in the test, never in the committed tree."""

    header = _segment({"alg": "RS256", "typ": "JWT"})
    claims = _segment({"https://api.openai.com/profile": {"email": identity}, "sub": identity})
    return f"{header}.{claims}.{POISON_MARKER}"


def _oauth(identity: str, label: str, **overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": label,
        "label": label,
        "auth_type": "oauth",
        "priority": 0,
        "source": "manual:device_code",
        "last_status": None,
        "last_status_at": None,
        "last_error_code": None,
        "last_error_reason": None,
        "last_error_message": None,
        "last_error_reset_at": None,
        "base_url": "https://chatgpt.com/backend-api/codex",
        "request_count": 0,
        "access_token": _access_token(identity),
        "refresh_token": f"{POISON_MARKER}-refresh",
    }
    entry.update(overrides)
    return entry


def _key_entry(provider: str) -> dict[str, object]:
    return {
        "id": provider,
        "label": provider,
        "auth_type": "api_key",
        "priority": 0,
        "source": "env",
        "last_status": "ok",
        "last_status_at": 1786925741.0,
        "last_error_code": None,
        "last_error_reason": None,
        "last_error_message": None,
        "last_error_reset_at": None,
        "base_url": "https://example.invalid/v1",
        "request_count": 17,
        "secret_fingerprint": f"{POISON_MARKER}-fingerprint-source",
    }


def _home(tmp_path: Path, pool: dict[str, list[dict[str, object]]]) -> Path:
    home = tmp_path / "profile"
    home.mkdir()
    (home / "auth.json").write_text(
        json.dumps({"version": 1, "credential_pool": pool}), encoding="utf-8"
    )
    return home


def _healthy_pool() -> dict[str, list[dict[str, object]]]:
    return {
        "openai-codex": [
            _oauth(_JAKIT, "jakit-engineer"),
            _oauth(_JAKITLABS, "jakitlabs-engineer"),
            _oauth(_SIMASJAK, "primary-0817"),
        ],
        "zai": [_key_entry("zai")],
        "alibaba": [_key_entry("alibaba")],
    }


def test_a_healthy_profile_projects_five_subscriptions_keyed_by_decoded_identity(
    tmp_path: Path,
) -> None:
    request = observation_request(
        _home(tmp_path, _healthy_pool()), profile_key="engineer", observed_at=_OBSERVED_AT
    )

    assert request.harness_key == "hermes"
    assert len(request.entries) == _DESIRED_HERMES_ENTRIES
    codex = [entry for entry in request.entries if entry.provider_key == "openai-codex"]
    assert len(codex) == _CODEX_ENTRIES
    assert sorted(str(entry.subscription_identity) for entry in codex) == sorted(
        (_JAKIT, _JAKITLABS, _SIMASJAK)
    )
    assert all(entry.auth_state == "healthy" for entry in codex)


def test_a_mislabelled_entry_is_keyed_by_its_claim_rather_than_by_its_label(
    tmp_path: Path,
) -> None:
    """Labels have twice pointed at the wrong account; the claim decides the key."""

    pool = _healthy_pool()
    pool["openai-codex"][0] = _oauth(_JAKIT, "simasjak-gmail")

    request = observation_request(
        _home(tmp_path, pool), profile_key="engineer", observed_at=_OBSERVED_AT
    )
    mislabelled = next(entry for entry in request.entries if entry.entry_label == "simasjak-gmail")

    assert mislabelled.subscription_identity == _JAKIT


def test_an_exhausted_entry_reports_a_cap_and_its_own_clock_not_dead_auth(
    tmp_path: Path,
) -> None:
    """AUTH is not QUOTA: an exhausted account passed login and is resting."""

    pool = _healthy_pool()
    pool["openai-codex"][0] = _oauth(
        _JAKIT,
        "jakit-engineer",
        last_status="exhausted",
        last_error_reset_at="2026-08-20T06:29:00+00:00",
    )

    request = observation_request(
        _home(tmp_path, pool), profile_key="engineer", observed_at=_OBSERVED_AT
    )
    capped = next(entry for entry in request.entries if entry.subscription_identity == _JAKIT)

    assert capped.quota_state == "capped"
    assert capped.auth_state == "healthy"
    assert capped.quota_reset_at is not None
    assert capped.quota_reset_at.isoformat().startswith("2026-08-20T06:29")


def test_an_unobserved_entry_reports_unknown_rather_than_available(tmp_path: Path) -> None:
    """A pool that cannot observe a state says so; reach is never assumed from a file."""

    request = observation_request(
        _home(tmp_path, _healthy_pool()), profile_key="engineer", observed_at=_OBSERVED_AT
    )
    codex = next(entry for entry in request.entries if entry.provider_key == "openai-codex")

    assert codex.quota_state == "unknown"
    assert codex.reach_state == "unknown"


def test_a_drifted_profile_projects_only_what_is_present(tmp_path: Path) -> None:
    """Nineteen of twenty-four minted is a shorter list, not five silent unavailabilities."""

    pool = _healthy_pool()
    pool["openai-codex"] = [_oauth(_JAKIT, "jakit-engineer")]
    pool.pop("alibaba")

    request = observation_request(
        _home(tmp_path, pool), profile_key="engineer", observed_at=_OBSERVED_AT
    )
    providers = {entry.provider_key for entry in request.entries}

    assert providers == {"openai-codex", "zai"}
    assert len(request.entries) == _DRIFTED_ENTRIES


def test_a_poisoned_pool_never_puts_a_credential_value_in_the_request(tmp_path: Path) -> None:
    """The projection allowlist proof: the token is adjacent to the metadata and stays there."""

    request = observation_request(
        _home(tmp_path, _healthy_pool()), profile_key="engineer", observed_at=_OBSERVED_AT
    )
    serialized = request.model_dump_json()

    assert POISON_MARKER not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    for entry in request.entries:
        assert POISON_MARKER not in json.dumps(entry.model_dump(mode="json"))
        fingerprint = entry.secret_fingerprint
        assert fingerprint is None or fingerprint.startswith("sha256:")

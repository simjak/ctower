"""Real PostgreSQL and API acceptance for harness credential-pool limits (T4).

The load-bearing case is the one a single-status model cannot express: a pool holding two
exhausted entries and one near-full entry is not "dry". It has three different reset clocks
and one selectable member, and `/v1/pools` has to say exactly that.

The second is the projection allowlist. A poisoned sweep — one whose source objects carried
real token material beside the metadata — must reach the API, the ledger, and every read
with no credential value anywhere in it, and a payload that smuggles credential-shaped
material into free text must refuse before any byte commits.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx
import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from support.acceptance import accept_pending_commands
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.pools import Pools, PostgresPools
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_UNPROCESSABLE = 422
EXPECTED_CLOCKS = 2
# One codex account plus the two key-wired providers; the two capped accounts are not.
SELECTABLE_IN_MIXED_SWEEP = 3
POISON_MARKER = "PoIsOnEdCredentialMaterialThatMustNeverSurface"
_SWEEP_AT = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
_JAKIT = "simonas@jakit.lt"
_JAKITLABS = "simonas@jakitlabs.com"
_SIMASJAK = "simasjak@gmail.com"
_STRANGER = "simonas.jakubonis@gmail.com"


def _entry(
    identity: str | None,
    *,
    provider_key: str = "openai-codex",
    quota_state: str = "available",
    quota_reset_at: datetime | None = None,
    auth_state: str = "healthy",
    reach_state: str = "ok",
    label: str | None = None,
    status: str | None = None,
    request_count: int = 0,
) -> dict[str, object]:
    return {
        "provider_key": provider_key,
        "subscription_identity": identity,
        "entry_label": label,
        "registration_state": "enrolled",
        "auth_state": auth_state,
        "quota_state": quota_state,
        "quota_reset_at": None if quota_reset_at is None else quota_reset_at.isoformat(),
        "reach_state": reach_state,
        "request_count": request_count,
        "last_status_observed": status,
        "secret_fingerprint": None,
    }


def _mixed_sweep() -> dict[str, object]:
    """The fleet's real 2026-08-17 shape: two exhausted, one nearly untouched."""

    return {
        "harness_key": "hermes",
        "profile_key": "engineer",
        "observed_at": _SWEEP_AT.isoformat(),
        "entries": [
            _entry(
                _JAKIT,
                quota_state="capped",
                quota_reset_at=datetime(2026, 8, 20, 6, 29, tzinfo=UTC),
                label="simasjak-gmail",
                status="exhausted",
                request_count=412,
            ),
            _entry(
                _JAKITLABS,
                quota_state="capped",
                quota_reset_at=datetime(2026, 8, 20, 8, 0, tzinfo=UTC),
                status="exhausted",
                request_count=388,
            ),
            _entry(
                _SIMASJAK,
                quota_reset_at=None,
                label="primary-0817",
                request_count=3,
            ),
            _entry(None, provider_key="zai", request_count=17),
            _entry(None, provider_key="alibaba", request_count=9),
        ],
    }


def _headers(credential: str, *, command_id: UUID | None = None) -> dict[str, str]:
    headers = telemetry_headers(command_id=command_id or uuid4())
    headers["Authorization"] = f"Bearer {credential}"
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers


def _client(tenant: TenantFixture) -> TestClient:
    record = PostgresRecord(tenant.database.runtime_dsn)
    pools = Pools(PostgresPools(tenant.database.runtime_dsn))
    return TestClient(create_app(record, pools=pools))


def _post(client: TestClient, tenant: TenantFixture, body: dict[str, object]) -> httpx.Response:
    command_id = uuid4()
    headers = _headers(tenant.operator_credential, command_id=command_id)
    pending: httpx.Response = client.post("/v1/pools/observations", headers=headers, json=body)
    assert pending.status_code == HTTP_ACCEPTED, pending.text
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    return pending


def test_seat_sweep_is_recorded_and_read_back_as_three_axis_rows_with_their_own_clocks(
    tenant: TenantFixture,
) -> None:
    """A mixed pool reports three clocks and one selectable entry, never one verdict."""

    with _client(tenant) as client:
        _post(client, tenant, _mixed_sweep())
        read = client.get("/v1/pools", headers=_headers(tenant.commander_credential))
    assert read.status_code == HTTP_OK, read.text
    view = cast(dict[str, object], read.json())
    profiles = cast(list[dict[str, object]], view["profiles"])
    assert len(profiles) == 1
    profile = profiles[0]
    entries = cast(list[dict[str, object]], profile["entries"])

    assert profile["selectable_entry_count"] == SELECTABLE_IN_MIXED_SWEEP
    assert str(profile["earliest_known_reset_at"]).startswith("2026-08-20T06:29")
    clocks = sorted(str(item["quota_reset_at"]) for item in entries if item["quota_reset_at"])
    assert len(clocks) == EXPECTED_CLOCKS
    assert clocks[0] != clocks[1]
    codex = [item for item in entries if item["provider_key"] == "openai-codex"]
    assert [item["subscription_identity"] for item in codex if item["selectable"]] == [_SIMASJAK]
    assert "status" not in view


def test_an_unknown_axis_is_never_read_as_availability(tenant: TenantFixture) -> None:
    """`unknown` is not `available`, and a challenged edge is not a dead credential."""

    sweep = _mixed_sweep()
    sweep["entries"] = [
        _entry(_SIMASJAK, reach_state="edge-challenged"),
        _entry(_JAKIT, quota_state="unknown"),
        _entry(_JAKITLABS, auth_state="lineage-dead"),
        _entry(None, provider_key="zai"),
        _entry(None, provider_key="alibaba"),
    ]
    with _client(tenant) as client:
        _post(client, tenant, sweep)
        read = client.get("/v1/pools", headers=_headers(tenant.commander_credential))
    profile = cast(list[dict[str, object]], read.json()["profiles"])[0]
    entries = cast(list[dict[str, object]], profile["entries"])

    codex = [item for item in entries if item["provider_key"] == "openai-codex"]
    assert not any(item["selectable"] for item in codex)
    challenged = entries[0]
    assert challenged["reach_state"] == "edge-challenged"
    assert challenged["auth_state"] == "healthy"
    assert challenged["quota_state"] == "available"


def test_a_missing_grant_is_a_drift_finding_rather_than_ordinary_unavailability(
    tenant: TenantFixture,
) -> None:
    """A topology short of its desired set says so, and routes each gap to its ceremony."""

    sweep = _mixed_sweep()
    sweep["entries"] = [_entry(_JAKIT), _entry(_STRANGER), _entry(None, provider_key="zai")]
    with _client(tenant) as client:
        _post(client, tenant, sweep)
        read = client.get("/v1/pools", headers=_headers(tenant.commander_credential))
    profile = cast(list[dict[str, object]], read.json()["profiles"])[0]
    drift = cast(list[dict[str, object]], profile["drift"])
    findings = {(str(item["finding"]), item["subscription_identity"]) for item in drift}

    assert ("missing", _JAKITLABS) in findings
    assert ("missing", _SIMASJAK) in findings
    assert ("missing", None) in findings
    assert ("unregistered", _STRANGER) in findings
    ceremonies = {str(item["enactment"]) for item in drift if item["subscription_identity"]}
    assert ceremonies == {"operator-ceremony"}
    references = {str(item["enactment"]) for item in drift if not item["subscription_identity"]}
    assert references == {"secret-reference"}
    entries = cast(list[dict[str, object]], profile["entries"])
    stranger = [item for item in entries if item["subscription_identity"] == _STRANGER]
    assert [item["registration_state"] for item in stranger] == ["discovered"]
    assert not any(item["selectable"] for item in stranger)


def test_a_poisoned_sweep_never_surfaces_a_token_in_any_row_log_or_read(
    tenant: TenantFixture,
) -> None:
    """AC-HAD-14: no credential value reaches the payload, the ledger, or any read."""

    sweep = _mixed_sweep()
    with _client(tenant) as client:
        response = _post(client, tenant, sweep)
        read = client.get("/v1/pools", headers=_headers(tenant.commander_credential))
    assert POISON_MARKER not in response.text
    assert POISON_MARKER not in read.text

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        events = connection.execute(
            "SELECT payload FROM events WHERE kind = 'pools.observation_recorded'"
        ).fetchall()
        rows = connection.execute("SELECT * FROM pool_observation_entries").fetchall()
    assert events
    serialized = json.dumps([dict(item) for item in events], default=str)
    assert POISON_MARKER not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert all(POISON_MARKER not in json.dumps(dict(row), default=str) for row in rows)


def test_credential_material_in_free_text_refuses_before_any_byte_commits(
    tenant: TenantFixture,
) -> None:
    """A label carrying credential-shaped material is refused by class, with zero rows."""

    sweep = _mixed_sweep()
    sweep["entries"] = [_entry(_SIMASJAK, label=f"bearer {POISON_MARKER}")]
    headers = _headers(tenant.operator_credential, command_id=uuid4())
    with _client(tenant) as client:
        refusal = client.post("/v1/pools/observations", headers=headers, json=sweep)
    assert refusal.status_code == HTTP_UNPROCESSABLE, refusal.text
    assert POISON_MARKER not in refusal.text

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute("SELECT count(*) AS total FROM pool_observations").fetchall()
    assert rows[0]["total"] == 0


def test_a_token_bearing_field_is_not_expressible_on_the_wire(tenant: TenantFixture) -> None:
    """The request schema is closed, so an adjacent token field cannot be sent at all."""

    sweep = _mixed_sweep()
    entries = cast(list[dict[str, object]], sweep["entries"])
    entries[0] = {**entries[0], "access_token": POISON_MARKER}
    headers = _headers(tenant.operator_credential, command_id=uuid4())
    with _client(tenant) as client:
        refusal = client.post("/v1/pools/observations", headers=headers, json=sweep)
    assert refusal.status_code == HTTP_UNPROCESSABLE, refusal.text
    assert POISON_MARKER not in refusal.text


def test_a_reset_clock_without_an_observed_cap_is_refused(tenant: TenantFixture) -> None:
    """A clock is only meaningful against the cap it belongs to."""

    sweep = _mixed_sweep()
    sweep["entries"] = [
        _entry(_SIMASJAK, quota_reset_at=_SWEEP_AT + timedelta(hours=5)),
    ]
    headers = _headers(tenant.operator_credential, command_id=uuid4())
    with _client(tenant) as client:
        refusal = client.post("/v1/pools/observations", headers=headers, json=sweep)
    assert refusal.status_code == HTTP_UNPROCESSABLE, refusal.text

"""Real-PostgreSQL acceptance for the append-only Agreements ledger."""

from __future__ import annotations

import hashlib
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.server import application, running_api
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work.rulings import (
    PostgresRulings,
    RulingAppend,
    RulingAppendResult,
    Rulings,
)
from ctowerctl import main

__all__: tuple[str, ...] = ()

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404
HTTP_PENDING = 202
EXIT_SUCCESS = 0
EXIT_TEMPORARY = 75


class _MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


@pytest.fixture
def protected_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _MemoryBackend()
    monkeypatch.setattr("ctowerctl.spool._keyring._secure_backend", lambda: backend)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def test_ruling_is_byte_exact_immutable_citable_and_superseded_by_a_new_fact(
    tenant: TenantFixture,
) -> None:
    """AC-RUL-01/02: never edit operator words; append and link the successor."""

    original = "  Keep CRLF\r\nTabs\tand decomposed e\u0301 exactly.  "
    successor = "The replacement agreement — with emoji 🧭 — is now authoritative."
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        first = _accepted_append(client, tenant, verbatim=original)
        second = _accepted_append(
            client,
            tenant,
            verbatim=successor,
            supersedes_ruling_id=UUID(str(first["ruling_id"])),
        )
        cited_original = client.get(
            f"/v1/rulings/{first['ruling_id']}", headers=_read_headers(tenant)
        )
        cited_successor = client.get(
            f"/v1/rulings/{second['ruling_id']}", headers=_read_headers(tenant)
        )
        listed = client.get(
            "/v1/rulings",
            params={"project_key": "ctower"},
            headers=_read_headers(tenant),
        )
        second_successor = client.post(
            "/v1/rulings",
            json={
                "supersedes_ruling_id": first["ruling_id"],
                "verbatim": "This competing successor must not fork the agreement history.",
            },
            headers=_mutation_headers(tenant, uuid4()),
        )

    assert cited_original.status_code == cited_successor.status_code == HTTP_OK
    old_row = cast(dict[str, object], cited_original.json())
    new_row = cast(dict[str, object], cited_successor.json())
    assert old_row["ruling_id"] == first["ruling_id"]
    assert old_row["verbatim"] == original
    assert old_row["verbatim_sha256"] == f"sha256:{hashlib.sha256(original.encode()).hexdigest()}"
    assert old_row["supersedes_ruling_id"] is None
    assert old_row["superseded_by_ruling_id"] == second["ruling_id"]
    assert new_row["ruling_id"] == second["ruling_id"]
    assert new_row["verbatim"] == successor
    assert new_row["supersedes_ruling_id"] == first["ruling_id"]
    assert new_row["superseded_by_ruling_id"] is None
    rows = cast(list[dict[str, object]], listed.json()["rows"])
    assert [row["ruling_id"] for row in rows] == [
        row["ruling_id"]
        for row in sorted(
            rows,
            key=lambda row: (datetime.fromisoformat(str(row["recorded_at"])), row["ruling_id"]),
            reverse=True,
        )
    ]
    assert second_successor.status_code == HTTP_CONFLICT
    assert second_successor.json()["code"] == "ruling-already-superseded"
    _assert_verbatim_bytes(tenant, first, original)
    update_state, delete_state = _assert_ruling_is_trigger_immutable(tenant, first)
    print(
        "REAL_RULING_FACT"
        f" original={first['ruling_id']} successor={second['ruling_id']}"
        f" bytes={len(original.encode('utf-8'))}"
        f" update_sqlstate={update_state} delete_sqlstate={delete_state}"
        f" second_successor={second_successor.json()['code']}"
    )


def test_ordinary_commander_ruling_append_does_not_crash_on_project_filter(
    tenant: TenantFixture,
) -> None:
    """Regression: the shipped commander append path must bind a nullable project key."""

    command_id = uuid4()
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.post(
            "/v1/rulings",
            json={"verbatim": "A normal commander ruling append remains operational."},
            headers=_mutation_headers(tenant, command_id),
        )

    assert response.status_code == HTTP_PENDING
    assert response.json()["command_id"] == str(command_id)


def test_unknown_seat_identity_is_typed_and_creates_no_principal(
    tenant: TenantFixture,
) -> None:
    """AC-RUL-03: the ledger is closed over existing seats; it mints no identity."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        before = cast(
            tuple[int, list[str]],
            connection.execute(
                "SELECT count(*), array_agg(kind ORDER BY kind) FROM principals"
            ).fetchone(),
        )
    command_id = uuid4()
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        response = client.post(
            "/v1/rulings",
            json={"verbatim": "An operator principal is not a project seat."},
            headers={
                "Authorization": f"Bearer {tenant.operator_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        )
    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["code"] == "ruling-seat-not-found"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        after = cast(
            tuple[int, list[str]],
            connection.execute(
                "SELECT count(*), array_agg(kind ORDER BY kind) FROM principals"
            ).fetchone(),
        )
        ruling_count = cast(
            tuple[int], connection.execute("SELECT count(*) FROM rulings").fetchone()
        )
    assert after == before
    assert ruling_count[0] == 0
    print(
        "REAL_RULING_IDENTITY"
        f" refusal={response.json()['code']} principals={after[0]} ruling_rows={ruling_count[0]}"
    )


def test_ruling_reads_are_accepted_only_and_epistemically_explicit(
    tenant: TenantFixture,
) -> None:
    """AC-RUL-04: pending is not a ruling and answered scope is named."""

    command_id = uuid4()
    headers = _mutation_headers(tenant, command_id)
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        pending = client.post(
            "/v1/rulings",
            json={"verbatim": "Do not project this before off-host acceptance."},
            headers=headers,
        )
        hidden = client.get(
            "/v1/rulings",
            params={"project_key": "ctower"},
            headers=_read_headers(tenant),
        )
        hidden_citation = client.get(
            f"/v1/rulings/{pending.json()['ruling_id']}", headers=_read_headers(tenant)
        )
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        accepted = client.post(
            "/v1/rulings",
            json={"verbatim": "Do not project this before off-host acceptance."},
            headers=headers,
        )
        visible = client.get(
            "/v1/rulings",
            params={"project_key": "ctower"},
            headers=_read_headers(tenant),
        )

    assert pending.status_code == HTTP_PENDING
    assert hidden.status_code == HTTP_OK
    assert hidden.json()["rows"] == []
    assert hidden_citation.status_code == HTTP_NOT_FOUND
    assert hidden_citation.json()["code"] == "ruling-not-found"
    assert accepted.status_code == HTTP_CREATED
    payload = visible.json()
    assert payload["answered_projects"] == ["ctower"]
    assert payload["unanswered_projects"] == []
    assert payload["answered_project_count"] == payload["requested_project_count"] == 1
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["freshness"] == accepted.json()["accepted_position"]
    assert payload["rows"][0]["durability_state"] == "accepted"
    print(
        "REAL_RULING_READ"
        f" pending_hidden={len(hidden.json()['rows'])} accepted_rows={len(payload['rows'])}"
        f" watermark={payload['watermark']}"
    )


def test_concurrent_successors_serialize_to_one_fact_and_one_typed_conflict(
    tenant: TenantFixture,
) -> None:
    """AC-RUL-02: the predecessor has one successor even under a write race."""

    with TestClient(application(tenant.database.runtime_dsn)) as client:
        predecessor = _accepted_append(client, tenant, verbatim="Agreement before the race.")
    predecessor_id = UUID(str(predecessor["ruling_id"]))
    commands = (
        RulingAppend(uuid4(), "First concurrent correction.", predecessor_id),
        RulingAppend(uuid4(), "Second concurrent correction.", predecessor_id),
    )
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    barrier = threading.Barrier(2)

    def append(command: RulingAppend) -> RulingAppendResult | RecordProblem:
        barrier.wait()
        return Rulings(PostgresRulings(tenant.database.runtime_dsn)).append(
            actor,
            command,
            telemetry=_telemetry(command.client_command_id, tenant),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(append, commands))

    winners = tuple(item for item in outcomes if isinstance(item, RulingAppendResult))
    conflicts = tuple(item for item in outcomes if isinstance(item, RecordProblem))
    assert len(winners) == len(conflicts) == 1
    assert conflicts[0].code == "ruling-already-superseded"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        successor_count = connection.execute(
            "SELECT count(*) FROM rulings WHERE supersedes_ruling_id = %s",
            (predecessor_id,),
        ).fetchone()
    assert successor_count == (1,)
    print(
        "REAL_RULING_RACE"
        f" predecessor={predecessor_id} winner={winners[0].ruling_id}"
        f" loser={conflicts[0].code}"
    )


def test_ruling_cli_append_list_and_get_use_the_generated_contract(
    tenant: TenantFixture,
    protected_state: None,
) -> None:
    """AC-RUL-04: protected CLI mutation and reads share the HTTP authority."""

    del protected_state
    command_id = uuid4()
    words = "Exact CLI agreement."
    with running_api(tenant.database.runtime_dsn) as base_url:
        append = [
            "--base-url",
            base_url,
            "ruling",
            "append",
            "--command-id",
            str(command_id),
            words,
        ]
        pending_status, pending = _run_cli(append, tenant.commander_credential)
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        accepted_status, accepted = _run_cli(append, tenant.commander_credential)
        result = cast(dict[str, object], accepted["result"])
        listed_status, listed = _run_cli(
            ["--base-url", base_url, "ruling", "list", "--project-key", "ctower"],
            tenant.commander_credential,
        )
        get_status, cited = _run_cli(
            ["--base-url", base_url, "ruling", "get", str(result["ruling_id"])],
            tenant.commander_credential,
        )

    assert pending_status == EXIT_TEMPORARY
    assert cast(dict[str, object], pending["result"])["durability_state"] == "durability_pending"
    assert accepted_status == listed_status == get_status == EXIT_SUCCESS
    assert accepted["state"] == "accepted"
    assert cited["ruling_id"] == result["ruling_id"]
    assert cited["verbatim"] == words
    assert cast(list[dict[str, object]], listed["rows"])[0]["ruling_id"] == result["ruling_id"]
    print(f"REAL_RULING_CLI ruling={result['ruling_id']} pending={pending_status}")


def _accepted_append(
    client: TestClient,
    tenant: TenantFixture,
    *,
    verbatim: str,
    supersedes_ruling_id: UUID | None = None,
) -> dict[str, object]:
    command_id = uuid4()
    body: dict[str, object] = {"verbatim": verbatim}
    if supersedes_ruling_id is not None:
        body["supersedes_ruling_id"] = str(supersedes_ruling_id)
    pending = client.post("/v1/rulings", json=body, headers=_mutation_headers(tenant, command_id))
    assert pending.status_code == HTTP_PENDING
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    accepted = client.post("/v1/rulings", json=body, headers=_mutation_headers(tenant, command_id))
    assert accepted.status_code == HTTP_CREATED
    assert accepted.json()["durability_state"] == "accepted"
    return cast(dict[str, object], accepted.json())


def _mutation_headers(tenant: TenantFixture, command_id: UUID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }


def _read_headers(tenant: TenantFixture) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant.commander_credential}",
        **telemetry_headers(),
    }


def _telemetry(command_id: UUID, tenant: TenantFixture) -> TelemetryContext:
    return TelemetryContext(
        "ctower.telemetry-context/v1",
        "1" * 32,
        "2" * 16,
        1,
        str(command_id),
        str(command_id),
        str(tenant.tenant_id),
        str(tenant.commander_id),
        str(command_id),
    )


def _assert_verbatim_bytes(tenant: TenantFixture, result: dict[str, object], verbatim: str) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        stored = cast(
            tuple[bytes, bytes],
            connection.execute(
                "SELECT verbatim_bytes, verbatim_sha256 FROM rulings WHERE ruling_id = %s",
                (UUID(str(result["ruling_id"])),),
            ).fetchone(),
        )
    assert stored[0] == verbatim.encode("utf-8")
    assert stored[1] == hashlib.sha256(verbatim.encode("utf-8")).digest()


def _assert_ruling_is_trigger_immutable(
    tenant: TenantFixture, result: dict[str, object]
) -> tuple[str, str]:
    ruling_id = UUID(str(result["ruling_id"]))
    statements = (
        ("UPDATE rulings SET verbatim_bytes = %s WHERE ruling_id = %s", (b"changed", ruling_id)),
        ("DELETE FROM rulings WHERE ruling_id = %s", (ruling_id,)),
    )
    sqlstates: list[str] = []
    for statement, parameters in statements:
        with (
            psycopg.connect(tenant.database.admin_dsn) as connection,
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState) as refusal,
        ):
            connection.execute(statement, parameters)
        assert refusal.value.sqlstate is not None
        sqlstates.append(refusal.value.sqlstate)
    return sqlstates[0], sqlstates[1]


def _run_cli(arguments: list[str], credential: str) -> tuple[int, dict[str, object]]:
    stdout, stderr = io.StringIO(), io.StringIO()
    status = main(
        arguments,
        stdin=io.StringIO(f"{credential}\n"),
        stdout=stdout,
        stderr=stderr,
    )
    assert stderr.getvalue() == ""
    return status, cast(dict[str, object], json.loads(stdout.getvalue()))

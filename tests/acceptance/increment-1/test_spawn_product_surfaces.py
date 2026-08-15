"""Product-surface acceptance for spawn HTTP routes and CLI reads."""

from __future__ import annotations

import io
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from support.http import operator_headers
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture, provision_seat

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime.spawn_driver import SpawnSpool
from ctower_kernel.runtime.spawn_records import PostgresSpawnRecords, SpawnRecordCreate
from ctowerctl import main

__all__: tuple[str, ...] = ()

_HTTP_PENDING = 202
_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_SPOOL_MODE = 0o600
_EXIT_SUCCESS = 0


def test_spawn_create_surfaces_pending_durability_like_driver_spool(
    tenant: TenantFixture, tmp_path: Path
) -> None:
    payload = _create_payload()

    with TestClient(_app(tenant)) as client:
        response = client.post(
            "/v1/spawn-records",
            json=payload,
            headers=operator_headers(tenant, command_id=uuid4()),
        )

    assert response.status_code == _HTTP_PENDING
    assert response.headers["Retry-After"] == "1"
    response_payload = response.json()
    assert response_payload["durability_state"] == "durability_pending"

    spool = SpawnSpool(tmp_path / "spawn-spool.jsonl")
    entry = spool.append(
        SpawnRecordCreate(
            client_command_id=uuid4(),
            project_key=payload["project_key"],
            seat_key=payload["seat_key"],
            crew_name=payload["crew_name"],
            task_file_ref=payload["task_file_ref"],
            worktree_path=payload["worktree_path"],
            harness=payload["harness"],
            model=payload["model"],
            effort=payload["effort"],
            workspace_id=None,
        )
    )
    assert entry.state == response_payload["durability_state"]
    assert (tmp_path / "spawn-spool.jsonl").stat().st_mode & 0o777 == _SPOOL_MODE


def test_spawn_http_routes_round_trip_through_the_real_app(tenant: TenantFixture) -> None:
    workspace_id = uuid4()
    create_command_id = uuid4()
    payload = _create_payload(workspace_id=workspace_id)

    with TestClient(_app(tenant)) as client:
        created_response = client.post(
            "/v1/spawn-records",
            json=payload,
            headers=operator_headers(tenant, command_id=create_command_id),
        )
        assert created_response.status_code == _HTTP_PENDING
        assert created_response.headers["Retry-After"] == "1"
        created = created_response.json()
        assert created["durability_state"] == "durability_pending"
        spawn_id = UUID(created["spawn_id"])
        assert created["effort"] == "high"
        assert created["workspace_id"] == str(workspace_id)

        transition_response = client.post(
            f"/v1/spawn-records/{spawn_id}/transitions",
            json={"to_status": "accepted", "reason": "operator accepted dispatch"},
            headers=operator_headers(tenant, command_id=uuid4()),
        )
        assert transition_response.status_code == _HTTP_PENDING
        assert transition_response.headers["Retry-After"] == "1"
        assert transition_response.json()["durability_state"] == "durability_pending"
        assert transition_response.json()["status"] == "accepted"

        list_response = client.get(
            "/v1/spawn-records",
            params={"project_key": "ctower", "status": "accepted", "limit": "1", "offset": "0"},
            headers=operator_headers(tenant),
        )
        assert list_response.status_code == _HTTP_OK
        listed = list_response.json()["records"]
        assert [record["spawn_id"] for record in listed] == [str(spawn_id)]

        get_response = client.get(
            f"/v1/spawn-records/{spawn_id}",
            headers=operator_headers(tenant),
        )
        assert get_response.status_code == _HTTP_OK
        fetched = get_response.json()
        assert fetched["spawn_id"] == str(spawn_id)
        assert fetched["status"] == "accepted"
        assert fetched["transitions"][0]["to_status"] == "accepted"

    with _serve(_app(tenant)) as base_url:
        list_status, list_text, list_error = _run_cli(
            [
                "--base-url",
                base_url,
                "spawn",
                "list",
                "--project-key",
                "ctower",
                "--status",
                "accepted",
            ],
            authority=tenant.operator_credential,
        )
        show_status, show_text, show_error = _run_cli(
            ["--base-url", base_url, "spawn", "show", str(spawn_id)],
            authority=tenant.operator_credential,
        )

    assert list_status == _EXIT_SUCCESS
    assert list_error == ""
    assert [record["spawn_id"] for record in json.loads(list_text)["records"]] == [str(spawn_id)]
    assert show_status == _EXIT_SUCCESS, show_error
    assert show_error == ""
    assert json.loads(show_text)["spawn_id"] == str(spawn_id)


def test_spawn_http_routes_exercise_typed_refusals(tenant: TenantFixture) -> None:
    _, seat_credential = provision_seat(tenant, "engineer")
    with TestClient(_app(tenant)) as client:
        _assert_unauthenticated_refusals(client)
        spawn_id = _create_refusal_fixture(client, tenant, seat_credential)
        _assert_transition_refusals(client, tenant, spawn_id)
        _assert_list_refusals(client, tenant, seat_credential)
        _assert_get_refusals(client, tenant)


def _assert_unauthenticated_refusals(client: TestClient) -> None:
    _assert_problem(client.post("/v1/spawn-records", json={}), _HTTP_UNAUTHORIZED)
    _assert_problem(
        client.post("/v1/spawn-records/not-a-uuid/transitions", json={}),
        _HTTP_UNAUTHORIZED,
    )
    _assert_problem(client.get("/v1/spawn-records"), _HTTP_UNAUTHORIZED)
    _assert_problem(client.get(f"/v1/spawn-records/{uuid4()}"), _HTTP_UNAUTHORIZED)


def _create_refusal_fixture(
    client: TestClient,
    tenant: TenantFixture,
    seat_credential: str,
) -> UUID:
    invalid_boundary = _create_payload()
    invalid_boundary["seat_key"] = "Engineer"
    _assert_problem(
        client.post(
            "/v1/spawn-records",
            json=invalid_boundary,
            headers=operator_headers(tenant, command_id=uuid4()),
        ),
        _HTTP_UNPROCESSABLE,
    )
    scope_problem = _assert_problem(
        client.post(
            "/v1/spawn-records",
            json=_create_payload(project_key="other"),
            headers=_seat_headers(seat_credential, command_id=uuid4()),
        ),
        _HTTP_FORBIDDEN,
    )
    assert scope_problem["code"] == "project-scope-denied"
    created_response = client.post(
        "/v1/spawn-records",
        json=_create_payload(),
        headers=operator_headers(tenant, command_id=uuid4()),
    )
    assert created_response.status_code == _HTTP_PENDING
    assert created_response.headers["Retry-After"] == "1"
    return UUID(created_response.json()["spawn_id"])


def _assert_transition_refusals(
    client: TestClient,
    tenant: TenantFixture,
    spawn_id: UUID,
) -> None:
    transition_problem = _assert_problem(
        client.post(
            f"/v1/spawn-records/{spawn_id}/transitions",
            json={"to_status": "completed"},
            headers=operator_headers(tenant, command_id=uuid4()),
        ),
        _HTTP_UNPROCESSABLE,
    )
    assert transition_problem["code"] == "invalid-transition"
    _assert_problem(
        client.post(
            "/v1/spawn-records/not-a-uuid/transitions",
            json={"to_status": "accepted"},
            headers=operator_headers(tenant, command_id=uuid4()),
        ),
        _HTTP_UNPROCESSABLE,
    )


def _assert_list_refusals(
    client: TestClient,
    tenant: TenantFixture,
    seat_credential: str,
) -> None:
    _assert_problem(
        client.get("/v1/spawn-records", headers=operator_headers(tenant)),
        _HTTP_UNPROCESSABLE,
    )
    _assert_problem(
        client.get(
            "/v1/spawn-records",
            params={"project_key": "ctower", "limit": "not-an-integer"},
            headers=operator_headers(tenant),
        ),
        _HTTP_UNPROCESSABLE,
    )
    invalid_status = _assert_problem(
        client.get(
            "/v1/spawn-records",
            params={"project_key": "ctower", "status": "bogus"},
            headers=operator_headers(tenant),
        ),
        _HTTP_UNPROCESSABLE,
    )
    assert invalid_status["code"] == "invalid-status"
    _assert_problem(
        client.get(
            "/v1/spawn-records",
            params={"project_key": "other"},
            headers=_seat_headers(seat_credential),
        ),
        _HTTP_FORBIDDEN,
    )


def _assert_get_refusals(client: TestClient, tenant: TenantFixture) -> None:
    _assert_problem(
        client.get("/v1/spawn-records/not-a-uuid", headers=operator_headers(tenant)),
        _HTTP_UNPROCESSABLE,
    )
    _assert_problem(
        client.get(f"/v1/spawn-records/{uuid4()}", headers=operator_headers(tenant)),
        _HTTP_NOT_FOUND,
    )


def _app(tenant: TenantFixture) -> FastAPI:
    dsn = tenant.database.runtime_dsn
    return create_app(
        PostgresRecord(dsn),
        spawn_records=PostgresSpawnRecords(dsn),
    )


def _create_payload(
    *,
    project_key: str = "ctower",
    workspace_id: UUID | None = None,
) -> dict[str, str]:
    payload = {
        "project_key": project_key,
        "seat_key": "engineer",
        "crew_name": "mc-engineer-r3000-spawn",
        "task_file_ref": "coordination/spawn.task.md",
        "worktree_path": "/srv/projects/ctower/.worktrees/r3000-spawn",
        "harness": "codex-crew",
        "model": "gpt-5-codex",
        "effort": "high",
    }
    if workspace_id is not None:
        payload["workspace_id"] = str(workspace_id)
    return payload


def _seat_headers(
    credential: str,
    *,
    command_id: UUID | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {credential}",
        **telemetry_headers(),
    }
    if command_id is not None:
        headers["Idempotency-Key"] = str(command_id)
    return headers


def _assert_problem(response: httpx.Response, status: int) -> dict[str, object]:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = cast(dict[str, object], response.json())
    assert payload["status"] == status
    return payload


def _run_cli(arguments: list[str], *, authority: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    status = main(
        arguments,
        stdin=io.StringIO(f"{authority}\n"),
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue()


@contextmanager
def _serve(application: FastAPI) -> Iterator[str]:
    port = _unused_port()
    config = uvicorn.Config(
        application,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_config=None,
        log_level="critical",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("acceptance API server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("acceptance API server did not stop")


def _unused_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return cast(int, candidate.getsockname()[1])

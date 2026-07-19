"""First-tenant trust-root ceremony acceptance evidence."""

from __future__ import annotations

import io
import json
import os
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from support.postgres import DatabaseFixture

from ctower_api.interface import create_app
from ctower_api.postgres import PostgresRecord, apply_migrations, provision_bootstrap

ROOT = Path(__file__).parents[3]
LOCAL_CLIENT = ("127.0.0.1", 51000)
HTTP_CREATED = 201
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
HTTP_GONE = 410
HTTP_SERVER_ERROR = 500

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BootstrapContext:
    """Runtime-only bootstrap capability and its composed API."""

    database: DatabaseFixture
    record: PostgresRecord
    token: str


@pytest.fixture
def bootstrap(database: DatabaseFixture) -> BootstrapContext:
    """Migrate and provision one runtime-only bootstrap capability."""

    apply_migrations(database.dsn)
    token = secrets.token_urlsafe(32)
    provision_bootstrap(
        database.dsn,
        capability_input=io.StringIO(f"{token}\n"),
        allowed_origin="127.0.0.1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return BootstrapContext(database, PostgresRecord(database.dsn), token)


def test_success_exact_replay_changed_body_second_use_and_token_non_persistence(
    bootstrap: BootstrapContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    command_id = uuid4()
    body = _request_body()
    app = create_app(bootstrap.record)

    with TestClient(app, client=LOCAL_CLIENT) as client:
        first = _bootstrap(client, bootstrap.token, command_id, body)
        replay = _bootstrap(client, bootstrap.token, command_id, body)
        changed = _bootstrap(
            client, bootstrap.token, command_id, {**body, "tenant_name": "Changed"}
        )
        second = _bootstrap(client, bootstrap.token, uuid4(), body)

    assert first.status_code == HTTP_CREATED
    assert replay.status_code == HTTP_CREATED
    assert replay.content == first.content
    assert replay.json()["event_ids"] == first.json()["event_ids"]
    assert changed.status_code == HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"
    assert second.status_code == HTTP_CONFLICT
    assert second.json()["code"] == "bootstrap-consumed"
    _assert_one_complete_bootstrap(bootstrap.database.dsn)
    _assert_token_absent(bootstrap, caplog.text)


def test_expiry_and_wrong_origin_have_zero_mutation(database: DatabaseFixture) -> None:
    apply_migrations(database.dsn)
    token = secrets.token_urlsafe(32)
    provision_bootstrap(
        database.dsn,
        capability_input=io.StringIO(f"{token}\n"),
        allowed_origin="127.0.0.1",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    record = PostgresRecord(database.dsn)
    app = create_app(record)

    with TestClient(app, client=LOCAL_CLIENT) as client:
        expired = _bootstrap(client, token, uuid4(), _request_body())
    assert expired.status_code == HTTP_GONE
    assert expired.json()["code"] == "bootstrap-expired"
    _assert_empty_authority(database.dsn)

    with psycopg.connect(database.dsn) as connection:
        connection.execute(
            "UPDATE bootstrap_capability SET expires_at = %s",
            (datetime.now(UTC) + timedelta(minutes=5),),
        )
    with TestClient(app, client=("198.51.100.10", 51000)) as client:
        wrong_origin = _bootstrap(client, token, uuid4(), _request_body())
    assert wrong_origin.status_code == HTTP_FORBIDDEN
    assert wrong_origin.json()["code"] == "bootstrap-origin"
    _assert_empty_authority(database.dsn)


def test_concurrent_attempts_create_exactly_one_authority(bootstrap: BootstrapContext) -> None:
    app = create_app(bootstrap.record)
    body = _request_body()

    def invoke(command_id: UUID) -> tuple[int, dict[str, object]]:
        with TestClient(app, client=LOCAL_CLIENT) as client:
            response = _bootstrap(client, bootstrap.token, command_id, body)
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = tuple(executor.map(invoke, (uuid4() for _ in range(12))))

    assert sum(status == HTTP_CREATED for status, _ in responses) == 1
    assert all(status in {HTTP_CREATED, HTTP_CONFLICT} for status, _ in responses)
    assert {payload.get("code") for status, payload in responses if status == HTTP_CONFLICT} == {
        "bootstrap-consumed"
    }
    _assert_one_complete_bootstrap(bootstrap.database.dsn)


def test_forced_outbox_failure_rolls_back_every_authority_row(
    bootstrap: BootstrapContext,
) -> None:
    app = create_app(bootstrap.record)
    command_id = uuid4()
    body = _request_body()
    with psycopg.connect(bootstrap.database.dsn) as connection:
        connection.execute(
            """
            CREATE FUNCTION reject_bootstrap_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'injected outbox failure';
            END
            $$;
            CREATE TRIGGER reject_bootstrap_outbox BEFORE INSERT ON outbox
                FOR EACH ROW EXECUTE FUNCTION reject_bootstrap_outbox();
            """
        )

    with TestClient(app, client=LOCAL_CLIENT, raise_server_exceptions=False) as client:
        failed = _bootstrap(client, bootstrap.token, command_id, body)
    assert failed.status_code == HTTP_SERVER_ERROR
    _assert_empty_authority(bootstrap.database.dsn)

    with psycopg.connect(bootstrap.database.dsn) as connection:
        connection.execute("DROP TRIGGER reject_bootstrap_outbox ON outbox")
        connection.execute("DROP FUNCTION reject_bootstrap_outbox()")
    with TestClient(app, client=LOCAL_CLIENT) as client:
        retry = _bootstrap(client, bootstrap.token, command_id, body)
    assert retry.status_code == HTTP_CREATED
    _assert_one_complete_bootstrap(bootstrap.database.dsn)


def _request_body() -> dict[str, str]:
    return {
        "commander_name": "Ctower Commander",
        "commander_vault_ref": "vault-ref:ctower/commander",
        "operator_credential_ref": "credential-ref:ctower/operator",
        "operator_name": "First Operator",
        "operator_vault_ref": "vault-ref:ctower/operator",
        "tenant_name": "Ctower",
        "tenant_slug": "ctower",
    }


def _bootstrap(
    client: TestClient,
    token: str,
    command_id: UUID,
    body: dict[str, str],
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/bootstrap/first-tenant",
            content=json.dumps(body, separators=(",", ":"), sort_keys=True),
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": str(command_id),
                "X-Ctower-Bootstrap-Capability": token,
            },
        ),
    )


def _assert_empty_authority(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM tenants),
                (SELECT count(*) FROM principals),
                (SELECT count(*) FROM events),
                (SELECT count(*) FROM command_results),
                (SELECT count(*) FROM outbox),
                (SELECT count(*) FROM bootstrap_capability WHERE consumed_at IS NOT NULL)
            """
        ).fetchone()
    assert counts == (0, 0, 0, 0, 0, 0)


def _assert_one_complete_bootstrap(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM tenants),
                (SELECT count(*) FROM principals),
                (SELECT count(*) FROM events),
                (SELECT count(*) FROM command_results),
                (SELECT count(*) FROM outbox),
                (SELECT count(*) FROM bootstrap_capability WHERE consumed_at IS NOT NULL)
            """
        ).fetchone()
        kinds = connection.execute("SELECT kind, disabled FROM principals ORDER BY kind").fetchall()
    assert counts == (1, 3, 1, 1, 1, 1)
    assert kinds == [
        ("bootstrap_installer", True),
        ("commander", False),
        ("operator", False),
    ]


def _assert_token_absent(bootstrap: BootstrapContext, captured_logs: str) -> None:
    assert bootstrap.token not in " ".join(sys.argv)
    assert all(bootstrap.token not in value for value in os.environ.values())
    assert bootstrap.token not in captured_logs
    with psycopg.connect(bootstrap.database.dsn) as connection:
        persisted = connection.execute(
            """
            SELECT concat_ws('|',
                encode(capability_digest, 'hex'),
                coalesce(receipt_body::text, ''),
                coalesce((SELECT string_agg(payload::text, '|') FROM events), ''),
                coalesce((SELECT string_agg(response_body::text, '|') FROM command_results), ''),
                coalesce((SELECT string_agg(payload::text, '|') FROM outbox), '')
            )
            FROM bootstrap_capability
            """
        ).fetchone()
    assert persisted is not None
    assert bootstrap.token not in persisted[0]
    assert all(
        bootstrap.token.encode() not in path.read_bytes()
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts and "node_modules" not in path.parts
    )

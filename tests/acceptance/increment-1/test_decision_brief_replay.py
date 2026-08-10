"""Real-PostgreSQL replay proof for the Request-linked Ruling boundary."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.server import application
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
HTTP_CREATED = 201
HTTP_PENDING = 202


def test_pre_link_ruling_receipt_is_canonicalized_for_exact_strict_replay(
    tenant: TenantFixture,
) -> None:
    """AC-BRIEF-04: migration 0061 upgrades old receipts once, without a runtime fallback."""

    command_id = uuid4()
    body = {"verbatim": "A pre-link standalone Ruling receipt."}
    headers = {
        "Authorization": f"Bearer {tenant.commander_credential}",
        "Idempotency-Key": str(command_id),
        **telemetry_headers(command_id),
    }
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        pending = client.post("/v1/rulings", json=body, headers=headers)
        accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
        accepted = client.post("/v1/rulings", json=body, headers=headers)

    assert pending.status_code == HTTP_PENDING
    assert accepted.status_code == HTTP_CREATED
    migration = (
        ROOT / "packages/ctower-kernel/migrations/0061_request_decision_briefs.sql"
    ).read_text(encoding="utf-8")
    canonicalization = migration[migration.index("UPDATE command_results") :]
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE command_results
            SET response_body = response_body - 'request_id' - 'supersedes_ruling_id'
            WHERE principal_id = %s AND client_command_id = %s
            """,
            (tenant.commander_id, command_id),
        )
        before = cast(
            tuple[dict[str, object]],
            connection.execute(
                """
                SELECT response_body FROM command_results
                WHERE principal_id = %s AND client_command_id = %s
                """,
                (tenant.commander_id, command_id),
            ).fetchone(),
        )[0]
        connection.execute(canonicalization)
        after = cast(
            tuple[dict[str, object]],
            connection.execute(
                """
                SELECT response_body FROM command_results
                WHERE principal_id = %s AND client_command_id = %s
                """,
                (tenant.commander_id, command_id),
            ).fetchone(),
        )[0]

    assert "request_id" not in before
    assert "supersedes_ruling_id" not in before
    assert after["request_id"] is None
    assert after["supersedes_ruling_id"] is None
    with TestClient(application(tenant.database.runtime_dsn)) as client:
        replay = client.post("/v1/rulings", json=body, headers=headers)
    assert replay.status_code == HTTP_CREATED
    assert replay.json()["ruling_id"] == accepted.json()["ruling_id"]
    assert replay.json()["request_id"] is None
    print(
        "REAL_RULING_REPLAY_CANONICALIZED"
        f" ruling={replay.json()['ruling_id']} request_id=null supersedes=null"
    )

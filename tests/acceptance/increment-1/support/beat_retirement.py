"""Real-PostgreSQL support for terminal fleet-beat retirement acceptance."""

from __future__ import annotations

import io
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid4

import psycopg
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import load_routine_revisions
from ctower_api.interface import create_app
from ctower_client import CtowerClient
from ctower_kernel.record import Actor
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime import RoutineRevision
from ctower_kernel.runtime.postgres import PostgresRuntime
from ctower_kernel.runtime.retirement import BeatRoutineRetireCommand
from ctowerctl import main as ctowerctl_main

__all__ = [
    "RetirementReceipt",
    "api_cli_retirement",
    "beat_revisions",
    "due_mark",
    "non_operator_principals",
    "retire",
    "retirement_is_immutable",
    "retirement_lineage_counts",
    "retirement_protected_counts",
    "routine_snapshot",
    "set_principal_disabled",
]


class RetirementReceipt(Protocol):
    command_id: UUID
    retirement_id: UUID
    event_id: UUID
    routine_ref: str
    revision_digest: str
    retired_at: datetime
    durability_state: str


@dataclass(frozen=True, slots=True)
class _RoutineSnapshot:
    revisions: tuple[str, ...]
    occurrences: tuple[UUID, ...]
    effects: tuple[UUID, ...]
    target_triggers: tuple[str, ...]
    unrelated_trigger_count: int


def beat_revisions() -> dict[str, RoutineRevision]:
    root = Path(__file__).parents[4]
    return {
        revision.beat_dispatch.beat_key: revision
        for revision in load_routine_revisions(root / "packs")
        if revision.beat_dispatch is not None
    }


def due_mark(revision: RoutineRevision) -> datetime:
    due = datetime.now(UTC).replace(second=0, microsecond=0)
    while due.minute not in revision.minute_marks or (
        revision.hour_marks is not None and due.hour not in revision.hour_marks
    ):
        due -= timedelta(minutes=1)
    return due


def retire(
    store: PostgresRuntime,
    actor: Actor,
    command_id: UUID,
    routine_ref: str,
) -> object:
    command = BeatRoutineRetireCommand(client_command_id=command_id, routine_ref=routine_ref)
    return store.retire_beat_routine(actor, command)


def api_cli_retirement(
    tenant: TenantFixture,
    store: PostgresRuntime,
    target: RoutineRevision,
) -> tuple[RetirementReceipt, int]:
    command_id = uuid4()
    application = create_app(
        PostgresRecord(tenant.database.runtime_dsn), beat_dispatch_runtime=store
    )
    with TestClient(application) as transport:
        client = CtowerClient(str(transport.base_url), credential=tenant.operator_credential)
        client._http.close()
        client._http = transport
        receipt = cast(
            RetirementReceipt,
            client.retire_beat_routine(target.routine_ref, command_id=command_id),
        )
    stdout, stderr = io.StringIO(), io.StringIO()
    with _serve(application) as base_url:
        status = ctowerctl_main(
            [
                "--base-url",
                base_url,
                "beat-dispatch",
                "retire",
                target.routine_ref,
                "--command-id",
                str(command_id),
            ],
            stdin=io.StringIO(tenant.operator_credential + "\n"),
            stdout=stdout,
            stderr=stderr,
        )
    assert status in {0, 75}
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue()) == _receipt_payload(receipt)
    return receipt, status


def routine_snapshot(
    tenant: TenantFixture,
    routine_ref: str,
    unrelated_ref: str,
) -> _RoutineSnapshot:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        revisions = connection.execute(
            """
            SELECT encode(revision_digest, 'hex') FROM routine_revisions
            WHERE routine_ref = %s ORDER BY revision_digest
            """,
            (routine_ref,),
        ).fetchall()
        occurrences = connection.execute(
            """
            SELECT occurrence_id FROM routine_occurrences AS occurrence
            JOIN routine_revisions AS revision USING (revision_digest)
            WHERE occurrence.tenant_id = %s AND revision.routine_ref = %s
            ORDER BY occurrence_id
            """,
            (tenant.tenant_id, routine_ref),
        ).fetchall()
        effects = connection.execute(
            """
            SELECT effect_id FROM runtime_beat_dispatch_effects
            WHERE tenant_id = %s AND routine_ref = %s ORDER BY effect_id
            """,
            (tenant.tenant_id, routine_ref),
        ).fetchall()
        target_triggers = connection.execute(
            """
            SELECT encode(trigger.revision_digest, 'hex')
            FROM routine_triggers AS trigger
            JOIN routine_revisions AS revision USING (revision_digest)
            WHERE trigger.tenant_id = %s AND revision.routine_ref = %s
            ORDER BY trigger.revision_digest
            """,
            (tenant.tenant_id, routine_ref),
        ).fetchall()
        unrelated = connection.execute(
            """
            SELECT count(*) FROM routine_triggers AS trigger
            JOIN routine_revisions AS revision USING (revision_digest)
            WHERE trigger.tenant_id = %s AND revision.routine_ref = %s
            """,
            (tenant.tenant_id, unrelated_ref),
        ).fetchone()
    assert unrelated is not None
    return _RoutineSnapshot(
        revisions=tuple("sha256:" + str(row[0]) for row in revisions),
        occurrences=tuple(cast(UUID, row[0]) for row in occurrences),
        effects=tuple(cast(UUID, row[0]) for row in effects),
        target_triggers=tuple("sha256:" + str(row[0]) for row in target_triggers),
        unrelated_trigger_count=int(unrelated[0]),
    )


def retirement_lineage_counts(
    tenant: TenantFixture,
    command_id: UUID,
    retirement_id: UUID,
) -> tuple[int, int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM routine_retirements
                WHERE tenant_id = %s AND retirement_id = %s),
              (SELECT count(*) FROM events
                WHERE tenant_id = %s AND kind = 'routine.retired'
                  AND client_command_id = %s),
              (SELECT count(*) FROM command_results
                WHERE tenant_id = %s AND principal_id = %s
                  AND client_command_id = %s),
              (SELECT count(*) FROM outbox AS delivery
                 JOIN events AS event
                   ON event.tenant_id = delivery.tenant_id
                  AND event.event_id = delivery.event_id
                WHERE event.tenant_id = %s AND event.client_command_id = %s
                  AND event.kind = 'routine.retired')
            """,
            (
                tenant.tenant_id,
                retirement_id,
                tenant.tenant_id,
                command_id,
                tenant.tenant_id,
                tenant.operator_id,
                command_id,
                tenant.tenant_id,
                command_id,
            ),
        ).fetchone()
    assert row is not None
    return cast(tuple[int, int, int, int], row)


def retirement_is_immutable(tenant: TenantFixture, retirement_id: UUID) -> None:
    statements = (
        "UPDATE routine_retirements SET retired_at = retired_at WHERE retirement_id = %s",
        "DELETE FROM routine_retirements WHERE retirement_id = %s",
    )
    for statement in statements:
        with (
            psycopg.connect(tenant.database.admin_dsn) as connection,
            pytest.raises(psycopg.DatabaseError, match="immutable"),
        ):
            connection.execute(statement, (retirement_id,))


def retirement_protected_counts(tenant: TenantFixture) -> tuple[int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM routine_retirements WHERE tenant_id = %s),
              (SELECT count(*) FROM events
                WHERE tenant_id = %s AND kind = 'routine.retired'),
              (SELECT count(*) FROM routine_triggers WHERE tenant_id = %s)
            """,
            (tenant.tenant_id, tenant.tenant_id, tenant.tenant_id),
        ).fetchone()
    assert row is not None
    return cast(tuple[int, int, int], row)


def non_operator_principals(tenant: TenantFixture) -> dict[str, UUID]:
    kinds = ("agent", "reviewer", "runner", "viewer")
    principals = {kind: uuid4() for kind in kinds}
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.cursor().executemany(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, %s, %s, false, transaction_timestamp())
            """,
            [
                (principal_id, tenant.tenant_id, kind, f"Retire refusal {kind}")
                for kind, principal_id in principals.items()
            ],
        )
    return principals


def set_principal_disabled(tenant: TenantFixture, *, disabled: bool) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE principals SET disabled = %s
            WHERE tenant_id = %s AND principal_id = %s
            """,
            (disabled, tenant.tenant_id, tenant.operator_id),
        )


def _receipt_payload(receipt: RetirementReceipt) -> dict[str, object]:
    return {
        "command_id": str(receipt.command_id),
        "durability_state": receipt.durability_state,
        "event_id": str(receipt.event_id),
        "retired_at": receipt.retired_at.isoformat().replace("+00:00", "Z"),
        "retirement_id": str(receipt.retirement_id),
        "revision_digest": receipt.revision_digest,
        "routine_ref": receipt.routine_ref,
    }


@contextmanager
def _serve(application: FastAPI) -> Iterator[str]:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = cast(int, candidate.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_config=None,
            log_level="critical",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        raise RuntimeError("beat retirement acceptance API server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("beat retirement acceptance API server did not stop")

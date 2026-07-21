"""Atomic first-tenant bootstrap implementation behind the Record Adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.record import BootstrapCommand, BootstrapReceipt, RecordProblem
from ctower_kernel.record._event_store import append_event, enqueue_event
from ctower_kernel.record.events import (
    BootstrapCreatedPayload,
    EventEnvelope,
    EventKind,
    EventOrigin,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
ZERO_HASH = bytes(32)


@dataclass(frozen=True, slots=True)
class _BootstrapIds:
    tenant: UUID
    installer: UUID
    operator: UUID
    commander: UUID
    event: UUID
    outbox: UUID


def bootstrap_transaction(
    dsn: str,
    command: BootstrapCommand,
    *,
    capability_digest: bytes,
    request_digest: bytes,
    origin: str,
    now: datetime,
    telemetry: TelemetryContext,
) -> BootstrapReceipt | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        connection.execute("SET ROLE ctower_svc")
        capability = connection.execute(
            """
            SELECT capability_digest, host(allowed_origin) AS allowed_origin, expires_at,
                consumed_at, consumed_command_id, consumed_request_sha256, receipt_body
            FROM bootstrap_capability
            WHERE singleton
            FOR UPDATE
            """
        ).fetchone()
        refusal = _bootstrap_refusal(
            capability,
            command,
            capability_digest=capability_digest,
            request_digest=request_digest,
            origin=origin,
            now=now,
        )
        if refusal is not None:
            return refusal
        connection.execute("LOCK TABLE tenants IN SHARE MODE")
        nonempty = connection.execute("SELECT EXISTS (SELECT 1 FROM tenants)").fetchone()
        if nonempty is None or bool(nonempty["exists"]):
            return bootstrap_problem(
                command,
                "bootstrap-nonempty",
                409,
                "Bootstrap requires an empty Ctower instance",
            )
        return _commit_bootstrap(
            connection,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def bootstrap_problem(
    command: BootstrapCommand, code: str, status: int, title: str
) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=command.client_command_id,
    )


def _bootstrap_refusal(
    capability: dict[str, object] | None,
    command: BootstrapCommand,
    *,
    capability_digest: bytes,
    request_digest: bytes,
    origin: str,
    now: datetime,
) -> BootstrapReceipt | RecordProblem | None:
    if capability is None or not hmac.compare_digest(
        bytes(cast(bytes, capability["capability_digest"])), capability_digest
    ):
        return bootstrap_problem(command, "unauthorized", 401, "Bootstrap capability refused")
    if capability["allowed_origin"] != origin:
        return bootstrap_problem(command, "bootstrap-origin", 403, "Bootstrap origin refused")
    consumed_command = cast(UUID | None, capability["consumed_command_id"])
    if consumed_command is not None:
        return _consumed_outcome(
            capability,
            command,
            consumed_command=consumed_command,
            request_digest=request_digest,
        )
    expires_at = cast(datetime, capability["expires_at"])
    if expires_at <= now:
        return bootstrap_problem(command, "bootstrap-expired", 410, "Bootstrap capability expired")
    return None


def _consumed_outcome(
    capability: dict[str, object],
    command: BootstrapCommand,
    *,
    consumed_command: UUID,
    request_digest: bytes,
) -> BootstrapReceipt | RecordProblem:
    if consumed_command != command.client_command_id:
        return bootstrap_problem(command, "bootstrap-consumed", 409, "Bootstrap already consumed")
    consumed_request = bytes(cast(bytes, capability["consumed_request_sha256"]))
    if not hmac.compare_digest(consumed_request, request_digest):
        return bootstrap_problem(command, "idempotency-conflict", 409, "Idempotency conflict")
    return _receipt_from_payload(cast(dict[str, object], capability["receipt_body"]))


def _new_bootstrap_ids(now: datetime) -> _BootstrapIds:
    return _BootstrapIds(*(_uuid7(now) for _ in range(6)))


def _bootstrap_event_payload(
    command: BootstrapCommand, identifiers: _BootstrapIds
) -> BootstrapCreatedPayload:
    return BootstrapCreatedPayload(
        commander_id=identifiers.commander,
        commander_vault_ref=command.commander_vault_ref,
        operator_credential_ref=command.operator_credential_ref,
        operator_id=identifiers.operator,
        operator_vault_ref=command.operator_vault_ref,
        tenant_id=identifiers.tenant,
        tenant_slug=command.tenant_slug,
    )


def _bootstrap_response(command: BootstrapCommand, identifiers: _BootstrapIds) -> dict[str, object]:
    provisional: dict[str, object] = {
        "command_id": str(command.client_command_id),
        "commander_id": str(identifiers.commander),
        "durability_state": "durability_pending",
        "event_ids": [str(identifiers.event)],
        "operator_id": str(identifiers.operator),
        "tenant_id": str(identifiers.tenant),
    }
    digest = f"sha256:{hashlib.sha256(_canonical_json(provisional)).hexdigest()}"
    return {**provisional, "receipt_digest": digest}


def _commit_bootstrap(
    connection: psycopg.Connection[dict[str, object]],
    command: BootstrapCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> BootstrapReceipt:
    identifiers = _new_bootstrap_ids(now)
    event = EventEnvelope(
        actor_principal_id=identifiers.installer,
        aggregate_id=identifiers.tenant,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=identifiers.event,
        kind=EventKind.BOOTSTRAP_CREATED,
        origin=EventOrigin.BOOTSTRAP,
        payload=_bootstrap_event_payload(command, identifiers),
        prev_hash=ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"tenant:{identifiers.tenant}:bootstrap",
        tenant_id=identifiers.tenant,
    )
    response_body = _bootstrap_response(command, identifiers)
    _insert_authority(connection, command, identifiers=identifiers, now=now)
    _insert_event_and_receipt(
        connection,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        event=event,
        response_body=response_body,
        now=now,
        telemetry=telemetry,
    )
    return _receipt_from_payload(response_body)


def _principal_rows(
    command: BootstrapCommand,
    identifiers: _BootstrapIds,
    now: datetime,
) -> tuple[tuple[object, ...], ...]:
    return (
        (
            identifiers.installer,
            identifiers.tenant,
            "bootstrap_installer",
            "Bootstrap Installer B0",
            True,
            None,
            None,
            now,
        ),
        (
            identifiers.operator,
            identifiers.tenant,
            "operator",
            command.operator_name,
            False,
            command.operator_credential_ref,
            command.operator_vault_ref,
            now,
        ),
        (
            identifiers.commander,
            identifiers.tenant,
            "commander",
            command.commander_name,
            False,
            None,
            command.commander_vault_ref,
            now,
        ),
    )


def _insert_authority(
    connection: psycopg.Connection[dict[str, object]],
    command: BootstrapCommand,
    *,
    identifiers: _BootstrapIds,
    now: datetime,
) -> None:
    connection.execute(
        "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
        (identifiers.tenant, command.tenant_slug, command.tenant_name, now),
    )
    for principal in _principal_rows(command, identifiers, now):
        connection.execute(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled,
                credential_ref, vault_ref, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            principal,
        )


def _insert_event_and_receipt(
    connection: psycopg.Connection[dict[str, object]],
    command: BootstrapCommand,
    *,
    identifiers: _BootstrapIds,
    request_digest: bytes,
    event: EventEnvelope,
    response_body: dict[str, object],
    now: datetime,
    telemetry: TelemetryContext,
) -> None:
    append_event(connection, event)
    _insert_bootstrap_result(
        connection,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        response_body=response_body,
        now=now,
    )
    enqueue_event(
        connection,
        identifiers.outbox,
        event,
        telemetry.bind(
            tenant_id=str(identifiers.tenant),
            actor_id=str(identifiers.installer),
            command_id=str(command.client_command_id),
        ),
        now,
    )
    connection.execute(
        """
        UPDATE bootstrap_capability
        SET consumed_at = %s, consumed_command_id = %s,
            consumed_request_sha256 = %s, receipt_body = %s
        WHERE singleton
        """,
        (now, command.client_command_id, request_digest, Jsonb(response_body)),
    )


def _insert_bootstrap_result(
    connection: psycopg.Connection[dict[str, object]],
    command: BootstrapCommand,
    *,
    identifiers: _BootstrapIds,
    request_digest: bytes,
    response_body: dict[str, object],
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO command_results (
            tenant_id, principal_id, client_command_id, request_sha256, status_code,
            response_body, event_ids, created_at
        ) VALUES (%s, %s, %s, %s, 201, %s, %s, %s)
        """,
        (
            identifiers.tenant,
            identifiers.installer,
            command.client_command_id,
            request_digest,
            Jsonb(response_body),
            [identifiers.event],
            now,
        ),
    )


def _receipt_from_payload(payload: dict[str, object]) -> BootstrapReceipt:
    event_ids = cast(list[str], payload["event_ids"])
    return BootstrapReceipt(
        command_id=UUID(str(payload["command_id"])),
        commander_id=UUID(str(payload["commander_id"])),
        event_ids=tuple(UUID(item) for item in event_ids),
        operator_id=UUID(str(payload["operator_id"])),
        receipt_digest=str(payload["receipt_digest"]),
        tenant_id=UUID(str(payload["tenant_id"])),
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

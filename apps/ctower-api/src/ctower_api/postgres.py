"""Postgres Adapter implementing the kernel's atomic Record Interface."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_api._setup_sql import apply_migrations, provision_bootstrap
from ctower_api._ticket_sql import actor_for_credential as _actor_for_credential
from ctower_api._ticket_sql import create_ticket as _create_ticket
from ctower_api._ticket_sql import get_ticket as _get_ticket
from ctower_api._ticket_sql import ticket_timeline as _ticket_timeline
from ctower_kernel.record import (
    Actor,
    BootstrapCommand,
    BootstrapReceipt,
    RecordProblem,
    Ticket,
    TicketCommand,
    TicketCommandResult,
    TicketTimeline,
)

__all__ = ["PostgresRecord", "apply_migrations", "provision_bootstrap"]

ZERO_HASH = bytes(32)


@dataclass(frozen=True, slots=True)
class _BootstrapIds:
    tenant: UUID
    installer: UUID
    operator: UUID
    commander: UUID
    event: UUID
    outbox: UUID


class PostgresRecord:
    """Password-agnostic Postgres implementation of atomic Record commands."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def bootstrap_first_tenant(
        self,
        command: BootstrapCommand,
        *,
        capability_digest: bytes,
        request_digest: bytes,
        origin: str,
        now: datetime,
    ) -> BootstrapReceipt | RecordProblem:
        """Serialize, deduplicate, and commit the complete trust root."""

        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
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
            return _commit_bootstrap(connection, command, request_digest=request_digest, now=now)

    def actor_for_credential(self, credential_digest: bytes) -> Actor | None:
        """Resolve one active principal through the credential index."""

        return _actor_for_credential(self._dsn, credential_digest)

    def create_ticket(
        self,
        actor: Actor,
        command: TicketCommand,
        *,
        request_digest: bytes,
        now: datetime,
    ) -> TicketCommandResult | RecordProblem:
        """Append or replay one ticket transaction."""

        return _create_ticket(
            self._dsn,
            actor,
            command,
            request_digest=request_digest,
            now=now,
        )

    def get_ticket(self, actor: Actor, ticket_id: UUID) -> Ticket | RecordProblem:
        """Read one tenant-scoped ticket."""

        return _get_ticket(self._dsn, actor, ticket_id)

    def ticket_timeline(self, actor: Actor, ticket_id: UUID) -> TicketTimeline | RecordProblem:
        """Read one tenant-scoped event timeline."""

        return _ticket_timeline(self._dsn, actor, ticket_id)


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
        return _problem(command, "unauthorized", 401, "Bootstrap capability refused")
    if capability["allowed_origin"] != origin:
        return _problem(command, "bootstrap-origin", 403, "Bootstrap origin refused")
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
        return _problem(command, "bootstrap-expired", 410, "Bootstrap capability expired")
    return None


def _consumed_outcome(
    capability: dict[str, object],
    command: BootstrapCommand,
    *,
    consumed_command: UUID,
    request_digest: bytes,
) -> BootstrapReceipt | RecordProblem:
    if consumed_command != command.client_command_id:
        return _problem(command, "bootstrap-consumed", 409, "Bootstrap already consumed")
    consumed_request = bytes(cast(bytes, capability["consumed_request_sha256"]))
    if not hmac.compare_digest(consumed_request, request_digest):
        return _problem(command, "idempotency-conflict", 409, "Idempotency conflict")
    return _receipt_from_payload(cast(dict[str, object], capability["receipt_body"]))


def _new_bootstrap_ids(now: datetime) -> _BootstrapIds:
    return _BootstrapIds(*(_uuid7(now) for _ in range(6)))


def _bootstrap_event_payload(
    command: BootstrapCommand, identifiers: _BootstrapIds
) -> dict[str, object]:
    return {
        "commander_id": str(identifiers.commander),
        "commander_vault_ref": command.commander_vault_ref,
        "operator_credential_ref": command.operator_credential_ref,
        "operator_id": str(identifiers.operator),
        "operator_vault_ref": command.operator_vault_ref,
        "tenant_id": str(identifiers.tenant),
        "tenant_slug": command.tenant_slug,
    }


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
) -> BootstrapReceipt:
    identifiers = _new_bootstrap_ids(now)
    event_payload = _bootstrap_event_payload(command, identifiers)
    event_hash = _event_hash(
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        payload=event_payload,
        now=now,
    )
    response_body = _bootstrap_response(command, identifiers)
    _insert_authority(connection, command, identifiers=identifiers, now=now)
    _insert_event_and_receipt(
        connection,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        event_hash=event_hash,
        event_payload=event_payload,
        response_body=response_body,
        now=now,
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
    event_hash: bytes,
    event_payload: dict[str, object],
    response_body: dict[str, object],
    now: datetime,
) -> None:
    _insert_bootstrap_event(
        connection,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        event_hash=event_hash,
        event_payload=event_payload,
        now=now,
    )
    _insert_bootstrap_result(
        connection,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        response_body=response_body,
        now=now,
    )
    connection.execute(
        """
        INSERT INTO outbox (outbox_id, tenant_id, event_id, topic, payload, created_at)
        VALUES (%s, %s, %s, 'record.events', %s, %s)
        """,
        (
            identifiers.outbox,
            identifiers.tenant,
            identifiers.event,
            Jsonb(event_payload),
            now,
        ),
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


def _insert_bootstrap_event(
    connection: psycopg.Connection[dict[str, object]],
    command: BootstrapCommand,
    *,
    identifiers: _BootstrapIds,
    request_digest: bytes,
    event_hash: bytes,
    event_payload: dict[str, object],
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id,
            causation_id, origin, server_time, payload, prev_hash, event_hash
        ) VALUES (%s, %s, %s, %s, 1, 'bootstrap.first_tenant_created', 1,
            %s, %s, %s, %s, NULL, 'bootstrap', %s, %s, %s, %s)
        """,
        (
            identifiers.event,
            identifiers.tenant,
            f"tenant/{identifiers.tenant}/bootstrap",
            identifiers.tenant,
            identifiers.installer,
            command.client_command_id,
            request_digest,
            command.client_command_id,
            now,
            Jsonb(event_payload),
            ZERO_HASH,
            event_hash,
        ),
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


def _event_hash(
    command: BootstrapCommand,
    *,
    identifiers: _BootstrapIds,
    request_digest: bytes,
    payload: dict[str, object],
    now: datetime,
) -> bytes:
    material: dict[str, object] = {
        "actor_principal_id": str(identifiers.installer),
        "aggregate_id": str(identifiers.tenant),
        "causation_id": None,
        "client_command_id": str(command.client_command_id),
        "correlation_id": str(command.client_command_id),
        "event_id": str(identifiers.event),
        "kind": "bootstrap.first_tenant_created",
        "origin": "bootstrap",
        "payload": payload,
        "prev_hash": f"sha256:{ZERO_HASH.hex()}",
        "request_sha256": f"sha256:{request_digest.hex()}",
        "schema_version": 1,
        "sequence": 1,
        "server_time": _timestamp(now),
        "stream_id": f"tenant/{identifiers.tenant}/bootstrap",
        "tenant_id": str(identifiers.tenant),
    }
    return hashlib.sha256(_canonical_json(material)).digest()


def _problem(command: BootstrapCommand, code: str, status: int, title: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=command.client_command_id,
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


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

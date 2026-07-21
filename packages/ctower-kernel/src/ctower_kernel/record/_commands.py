"""Principal-scoped command-key serialization and replay authority."""

from __future__ import annotations

import hmac
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import RecordProblem

__all__: tuple[str, ...] = ()
HTTP_BAD_REQUEST = 400


def reserve_command(
    connection: psycopg.Connection[dict[str, object]],
    principal_id: UUID,
    command_id: UUID,
    request_digest: bytes,
) -> dict[str, object] | RecordProblem | None:
    """Serialize one principal/command key before any aggregate read or mutation."""

    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{principal_id}:{command_id}",),
    )
    row = connection.execute(
        """
        SELECT request_sha256, status_code, response_body
        FROM command_results
        WHERE principal_id = %s AND client_command_id = %s
        """,
        (principal_id, command_id),
    ).fetchone()
    if row is None:
        return None
    stored_digest = bytes(cast(bytes, row["request_sha256"]))
    if not hmac.compare_digest(stored_digest, request_digest):
        return RecordProblem(
            code="idempotency-conflict",
            detail="The command key was already used with a different request body.",
            status=409,
            title="Idempotency conflict",
            command_id=command_id,
        )
    payload = cast(dict[str, object], row["response_body"])
    if int(cast(int, row["status_code"])) >= HTTP_BAD_REQUEST:
        return _problem_from_payload(payload)
    return payload


def _problem_from_payload(payload: dict[str, object]) -> RecordProblem:
    command_id = payload.get("command_id")
    current_version = payload.get("current_version")
    unmet_facts = cast(list[object], payload.get("unmet_facts", []))
    return RecordProblem(
        code=str(payload["code"]),
        detail=str(payload["detail"]),
        status=int(cast(int, payload["status"])),
        title=str(payload["title"]),
        command_id=UUID(str(command_id)) if command_id is not None else None,
        current_version=int(cast(int, current_version)) if current_version is not None else None,
        unmet_facts=tuple(str(item) for item in unmet_facts),
    )

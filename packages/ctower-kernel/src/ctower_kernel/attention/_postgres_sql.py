"""Append-only poison disposition persistence."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.attention import (
    PoisonDisposition,
    PoisonDispositionAction,
    PoisonDispositionReceipt,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def disposition(dsn: str, actor: Actor, command: PoisonDisposition) -> PoisonDispositionReceipt:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        target = connection.execute(
            """
            SELECT 1 FROM outbox_poison
            WHERE consumer_key = %s AND tenant_id = %s AND topic = %s AND outbox_id = %s
            """,
            (command.consumer_key, actor.tenant_id, command.topic, command.outbox_id),
        ).fetchone()
        if target is None:
            raise ValueError("poison disposition target is unavailable")
        connection.execute(
            """
            INSERT INTO outbox_poison_dispositions (
                tenant_id, actor_principal_id, client_command_id,
                consumer_key, topic, outbox_id, action, reason, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, transaction_timestamp())
            ON CONFLICT (tenant_id, actor_principal_id, client_command_id) DO NOTHING
            """,
            (
                actor.tenant_id,
                actor.principal_id,
                command.client_command_id,
                command.consumer_key,
                command.topic,
                command.outbox_id,
                command.action.value,
                command.reason,
            ),
        )
        row = connection.execute(
            """
            SELECT * FROM outbox_poison_dispositions
            WHERE tenant_id = %s AND actor_principal_id = %s AND client_command_id = %s
            """,
            (actor.tenant_id, actor.principal_id, command.client_command_id),
        ).fetchone()
    if row is None or not _matches(row, command):
        raise ValueError("poison disposition command identity conflicts with stored content")
    return PoisonDispositionReceipt(
        actor.tenant_id,
        actor.principal_id,
        command,
        cast(datetime, row["recorded_at"]),
    )


def _matches(row: dict[str, object], command: PoisonDisposition) -> bool:
    return all(
        (
            row["consumer_key"] == command.consumer_key,
            row["topic"] == command.topic,
            row["outbox_id"] == command.outbox_id,
            PoisonDispositionAction(str(row["action"])) is command.action,
            row["reason"] == command.reason,
        )
    )

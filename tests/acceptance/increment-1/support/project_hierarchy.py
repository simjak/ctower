"""Authoritative Project Delivery hierarchy fixture for intake acceptance."""

from __future__ import annotations

import hashlib
from uuid import uuid4

import psycopg
from support.tenant_fixture import TenantFixture

__all__ = ["declare_ctower_project"]


def declare_ctower_project(tenant: TenantFixture) -> None:
    """Declare the bounded I1 project through its canonical hierarchy table."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        event = connection.execute(
            """
            SELECT event_id, actor_principal_id, server_time
            FROM events WHERE tenant_id = %s
            ORDER BY server_time, event_id LIMIT 1
            """,
            (tenant.tenant_id,),
        ).fetchone()
        if event is None:
            raise RuntimeError("bootstrap event is unavailable")
        connection.execute(
            """
            INSERT INTO project_delivery_checkpoint_definitions (
                checkpoint_definition_id, tenant_id, company_key, project_key,
                checkpoint_key, definition_revision, ordered_position,
                checkpoint_label, outcome, accountable_owner, applicable_states,
                catalog_revision, catalog_digest, event_id, actor_principal_id,
                recorded_at
            ) VALUES (
                %s, %s, 'ctower', 'ctower', 'I1.0', 1, 1,
                'intake authority fixture', 'declared project authority',
                'ctower-operator', ARRAY['planned', 'done']::text[],
                'ctower.intake-authority@1', %s, %s, %s, %s
            )
            ON CONFLICT DO NOTHING
            """,
            (
                uuid4(),
                tenant.tenant_id,
                hashlib.sha256(b"ctower.intake-authority@1").digest(),
                event[0],
                event[1],
                event[2],
            ),
        )

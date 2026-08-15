"""Authored SQL for spawn-custody records.

Lifecycle state is DERIVED: spawn_records carries no status column; the
effective state is the latest spawn_record_transitions row (COALESCE 'requested'),
exactly like ticket_work_sessions. All writes are INSERTs — append-only facts.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()

# One create: the spawn fact itself. Idempotency comes from the
# (tenant_id, principal_id, command_id) UNIQUE + reserve_command.
INSERT_SPAWN_RECORD = """
INSERT INTO spawn_records (
    spawn_id, tenant_id, project_key, seat_key, crew_name, task_file_ref,
    worktree_path, harness, model, effort, workspace_id,
    principal_id, command_id, event_id, created_at
) VALUES (
    %(spawn_id)s, %(tenant_id)s, %(project_key)s, %(seat_key)s, %(crew_name)s,
    %(task_file_ref)s, %(worktree_path)s, %(harness)s, %(model)s, %(effort)s,
    %(workspace_id)s, %(principal_id)s, %(command_id)s, %(event_id)s, %(now)s
)
ON CONFLICT (tenant_id, principal_id, command_id) DO NOTHING
RETURNING spawn_id
"""

TENANT_EXISTS = """
SELECT 1 FROM tenants WHERE tenant_id = %(tenant_id)s
"""

# One transition: computed next number, derived-state check in one statement.
# The state check is inside the INSERT..SELECT so a concurrent transition
# either takes this number or fails the state predicate — no lost facts.
APPEND_TRANSITION = """
INSERT INTO spawn_record_transitions (
    transition_id, spawn_id, tenant_id, transition_number, to_status, reason,
    principal_id, command_id, event_id, transitioned_at
)
SELECT
    %(transition_id)s, spawn.spawn_id, %(tenant_id)s,
    COALESCE(latest.transition_number, 0) + 1,
    %(to_status)s, %(reason)s, %(principal_id)s, %(command_id)s, %(event_id)s, %(now)s
FROM spawn_records AS spawn
LEFT JOIN LATERAL (
    SELECT transition.transition_number, transition.to_status
    FROM spawn_record_transitions AS transition
    WHERE transition.spawn_id = spawn.spawn_id
      AND transition.tenant_id = %(tenant_id)s
    ORDER BY transition.transition_number DESC
    LIMIT 1
) AS latest ON true
WHERE spawn.spawn_id = %(spawn_id)s
  AND spawn.tenant_id = %(tenant_id)s
  AND %(to_status)s = (
        -- authored lifecycle: from derived current state, no skipping
        CASE COALESCE(latest.to_status, 'requested')
            WHEN 'requested' THEN CASE
                WHEN %(to_status)s IN ('accepted', 'failed') THEN %(to_status)s
                ELSE NULL
            END
            WHEN 'accepted' THEN CASE
                WHEN %(to_status)s IN ('running', 'failed') THEN %(to_status)s
                ELSE NULL
            END
            WHEN 'running' THEN CASE
                WHEN %(to_status)s IN ('completed', 'failed', 'reaped') THEN %(to_status)s
                ELSE NULL
            END
            ELSE NULL
        END
      )
RETURNING transition_number
"""

# Derived-state read: the effective status is the latest transition.
GET_SPAWN_RECORD = """
SELECT
    spawn.spawn_id, spawn.tenant_id, spawn.project_key, spawn.seat_key,
    spawn.crew_name, spawn.task_file_ref, spawn.worktree_path, spawn.harness,
    spawn.model, spawn.effort, spawn.workspace_id, spawn.principal_id,
    spawn.created_at,
    COALESCE(latest.to_status, 'requested') AS status,
    latest.transitioned_at AS updated_at
FROM spawn_records AS spawn
LEFT JOIN LATERAL (
    SELECT transition.to_status, transition.transitioned_at
    FROM spawn_record_transitions AS transition
    WHERE transition.spawn_id = spawn.spawn_id
      AND transition.tenant_id = spawn.tenant_id
    ORDER BY transition.transition_number DESC
    LIMIT 1
) AS latest ON true
WHERE spawn.spawn_id = %(spawn_id)s AND spawn.tenant_id = %(tenant_id)s
"""

LIST_SPAWN_RECORDS = """
SELECT
    spawn.spawn_id, spawn.tenant_id, spawn.project_key, spawn.seat_key,
    spawn.crew_name, spawn.task_file_ref, spawn.worktree_path, spawn.harness,
    spawn.model, spawn.effort, spawn.workspace_id, spawn.principal_id,
    spawn.created_at,
    COALESCE(latest.to_status, 'requested') AS status,
    latest.transitioned_at AS updated_at
FROM spawn_records AS spawn
LEFT JOIN LATERAL (
    SELECT transition.to_status, transition.transitioned_at
    FROM spawn_record_transitions AS transition
    WHERE transition.spawn_id = spawn.spawn_id
      AND transition.tenant_id = spawn.tenant_id
    ORDER BY transition.transition_number DESC
    LIMIT 1
) AS latest ON true
WHERE spawn.tenant_id = %(tenant_id)s
  AND spawn.project_key = %(project_key)s
  AND (%(status_filter)s::text IS NULL
       OR COALESCE(latest.to_status, 'requested') = %(status_filter)s)
ORDER BY spawn.created_at DESC
LIMIT %(limit)s OFFSET %(offset)s
"""

GET_TRANSITIONS = """
SELECT
    transition.transition_id, transition.spawn_id, transition.transition_number,
    transition.to_status, transition.reason, transition.principal_id,
    transition.transitioned_at,
    LAG(transition.to_status, 1, 'requested') OVER (
        PARTITION BY transition.spawn_id ORDER BY transition.transition_number
    ) AS from_status
FROM spawn_record_transitions AS transition
WHERE transition.spawn_id = %(spawn_id)s AND transition.tenant_id = %(tenant_id)s
ORDER BY transition.transition_number
"""

# Derived current state for the transition path (pre-INSERT validation + races).
CURRENT_DERIVED_STATE = """
SELECT COALESCE(latest.to_status, 'requested') AS status
FROM spawn_records AS spawn
LEFT JOIN LATERAL (
    SELECT transition.to_status
    FROM spawn_record_transitions AS transition
    WHERE transition.spawn_id = spawn.spawn_id
      AND transition.tenant_id = %(tenant_id)s
    ORDER BY transition.transition_number DESC
    LIMIT 1
) AS latest ON true
WHERE spawn.spawn_id = %(spawn_id)s AND spawn.tenant_id = %(tenant_id)s
"""

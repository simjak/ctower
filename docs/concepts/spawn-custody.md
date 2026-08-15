# Spawn custody

Spawn custody records the pre-dispatch commitment for a crew before any host
session is created. A record names the tenant/project scope, seat and crew,
task reference, worktree intent, harness/model pin, and optional workspace
reference. Workspace remains absent until first-class workspace custody exists.

## Append-only lifecycle

The initial state is `requested`. Lifecycle changes are separate POST transition
facts and are derived in read models rather than written into the spawn row:

`requested → accepted → running → completed|failed|reaped`

A transition cannot skip a state or move a terminal record again. The base row
and transition facts are immutable database facts. Reusing an idempotency key
returns the original result; a different request body with that key is refused.
Credential values and other prohibited data classes are refused before any
spawn fact is committed.

## Record before drive

The external driver records the create command before it invokes a host
substrate. If ctower is unreachable, the identical typed command is appended to
one local JSONL spool with mode `0600` and an explicit `durability_pending`
state. Recovery replays pending commands and removes an entry only after a
strongly typed create acknowledgement; refused or unacknowledged entries stay
pending.

The driver-side history helper folds external rows by source UUID, with the
latest status effective. The initial running set contains only source identities
whose effective status has never entered a terminal state. Reconcile continues
to name the external registry twin until a separately recorded parity proof
admits the ctower read path; this candidate does not silently swap authority.

See the [CLI reference](../reference/cli.md#spawn-custody) and [HTTP reference](../reference/http-api.md).

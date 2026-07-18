# ctower architecture atlas

| Field | Value |
|---|---|
| Status | Derived operator and implementer map |
| Normative authority | [`SPEC.md`](SPEC.md) |
| Decision history | [`DECISIONS.md`](DECISIONS.md) |
| Last reviewed | 2026-07-17 |

This file is the one compact, terminal-safe architecture atlas requested by the operator. It does not
create a second specification. It explains the current `SPEC.md` with ASCII views and implementation
boundaries. If this atlas and the SPEC disagree, the SPEC wins and this file must be repaired.

## System architecture

The durable boundary is deliberate: Postgres and content-addressed objects hold accepted truth; models,
sessions, processes, tmux panes, sandboxes, remote providers, and VPS workers are replaceable capacity.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                      OPERATOR PLANE                                          │
│                                                                                              │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐                     │
│  │ ctower-web         │  │ ctowerctl / ctl    │  │ Slack/Git/Webhooks │                     │
│  │ board · ticket     │  │ capture · inspect  │  │ ingress/attention  │                     │
│  │ fleet · live steer │  │ approve · steer    │  │ adapters           │                     │
│  └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘                     │
└────────────┼───────────────────────┼───────────────────────┼────────────────────────────────┘
             └───────────────────────┴───────────────────────┘
                                             │ authenticated commands / event streams
                                             ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                              TRUSTED CONTROL PLANE — Python                                   │
│                                                                                              │
│  ┌────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────────────────┐ │
│  │ Access + Command   │  │ Commander / Custody  │  │ Workflow + Policy                   │ │
│  │ authz · idempotency│  │ smartest model seat  │  │ stage graph · risk tier · gates     │ │
│  │ CAS · validation   │  │ plan · route · steer │  │ rounds · budgets · escalation       │ │
│  └─────────┬──────────┘  └──────────┬───────────┘  └──────────────────┬───────────────────┘ │
│            └────────────────────────┴──────────────────────────────────┘                     │
│                                             │                                                │
│  ┌──────────────────────────────────────────▼──────────────────────────────────────────────┐ │
│  │ ORCHESTRATION KERNEL                                                                    │ │
│  │ Work · Catalog · Workflow · Proof · Runtime · Effects · Attention · Projections         │ │
│  │ tickets, revisions, assignments, gates, leases, receipts, alerts, read models            │ │
│  └─────────────┬───────────────────────┬──────────────────────────┬──────────────────────────┘ │
│                │                       │                          │                            │
│     ┌──────────▼──────────┐ ┌──────────▼──────────┐   ┌──────────▼──────────┐                │
│     │ Scheduler / Jobs    │ │ Proof / Gate engine │   │ Extension Host      │                │
│     │ lease · fence · ACK │ │ evidence · verdicts │   │ signed data-only    │                │
│     │ retry · reconcile   │ │ invalidation        │   │ manifests + grants  │                │
│     └──────────┬──────────┘ └─────────────────────┘   └─────────────────────┘                │
└────────────────┼─────────────────────────────────────────────────────────────────────────────┘
                 │ committed jobs / fenced leases
                 ▼
       ┌────────────────────────────────────────────┐
       │            DURABLE RECORD PLANE            │
       │                                            │
       │  ┌──────────────┐    ┌──────────────────┐ │
       │  │ PostgreSQL   │    │ Object storage   │ │
       │  │ events/CAS   │    │ artifacts/logs   │ │
       │  │ jobs/outbox  │    │ screenshots      │ │
       │  │ projections  │    │ evidence         │ │
       │  └──────┬───────┘    └────────┬─────────┘ │
       │         └──────────┬───────────┘           │
       │           PITR backup + restore drills     │
       └────────────────────┼───────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                         REPLACEABLE WORKER / EXECUTION PLANE                                  │
│                                                                                              │
│  ┌──────────────────────────── Runner Supervisor ──────────────────────────────────────────┐ │
│  │ lease heartbeat · epoch fencing · cursor · cancel · logs · checkpoint · final receipt   │ │
│  └───────────────┬──────────────────────┬──────────────────────┬────────────────────────────┘ │
│                  │                      │                      │                              │
│      ┌───────────▼──────────┐ ┌────────▼─────────┐ ┌──────────▼────────────────┐             │
│      │ Local/VPS adapter    │ │ Sandbox adapter  │ │ Crabbox-compatible remote│             │
│      │ process/tmux/systemd │ │ image + terminal │ │ execution provider       │             │
│      └───────────┬──────────┘ └────────┬─────────┘ └──────────┬────────────────┘             │
│                  └──────────────────────┴──────────────────────┘                              │
│                                         │                                                    │
│                      ┌──────────────────▼──────────────────┐                                 │
│                      │ Immutable execution capsule         │                                 │
│                      │ harness + model/profile + skills    │                                 │
│                      │ workspace/image digest + limits     │                                 │
│                      │ NO standing credentials             │                                 │
│                      └──────────────────┬──────────────────┘                                 │
└─────────────────────────────────────────┼────────────────────────────────────────────────────┘
                                          │ proposed artifacts/evidence/effects
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                              PROTECTED EFFECT / RELEASE PLANE                                 │
│                                                                                              │
│  ┌─────────────────┐    short-lived grant    ┌──────────────────────┐                       │
│  │ Effect Broker   ├────────────────────────►│ SCM / CI / registry  │                       │
│  │ policy + JIT    │                         └──────────┬───────────┘                       │
│  │ secrets + dedupe│                                    │ verified immutable candidate       │
│  └────────┬────────┘                         ┌──────────▼───────────┐                       │
│           │ immutable receipt                │ Staging deploy + QA  │                       │
│           │                                  └──────────┬───────────┘                       │
│           │                                  ┌──────────▼───────────┐                       │
│           └─────────────────────────────────►│ Production + smoke   │                       │
│                                              │ rollback on failure  │                       │
│                                              └──────────────────────┘                       │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Day-one infrastructure

```text
┌──────────────────────────────── PRIVATE VPS ──────────────────────────────────────────────────┐
│ Private edge: Tailscale/private TLS · no public DB · root-owned bootstrap Unix socket        │
│                                                                                              │
│ systemd                                                                                      │
│ ├── ctower-api.service              API + authenticated commands                             │
│ ├── ctower-worker.service           outbox, scheduler, wake dispatcher, projections          │
│ ├── ctower-reconciler.service       leases, cursors, receipts, provider observations         │
│ ├── ctower-runner-supervisor        local/VPS runner connections                             │
│ ├── ctower-release-supervisor       root-owned privileged release seam                       │
│ ├── ctower-maintenance.timer        redundant scheduler/reconciler kick, not routine truth   │
│ └── ctower-backup.timer             backup, anchor, restore-drill jobs                        │
│                                                                                              │
│ containers / durable volumes                                                                      │
│ ├── Postgres + WAL/PITR             ├── S3-compatible object store                           │
│ ├── vault/secret provider           └── OpenTelemetry Collector                              │
│                                                                                              │
│ telemetry                                                                                     │
│ └── logs + metrics + traces + completeness alerts + dashboards                              │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                           │ outbound mTLS / short-lived OIDC
                ┌──────────────────────────┼──────────────────────────┐
                ▼                          ▼                          ▼
       local runner/tmux          another owned VPS          sandbox/Crabbox provider
```

Routine schedules do **not** become one operating-system cron entry per routine. Postgres owns due
occurrences. A logical scheduler inside `ctower-worker` claims them transactionally. The systemd timer is
only a redundant wake/recovery mechanism if the continuous worker is restarted or idle.

## Work state is orthogonal

```text
priority:       P0 / P1 / P2
Board lane:     Backlog / To Do / In Progress / In Review / Blocked / Done
factory stage:  Think → Plan → Design → Implement → QA → Review → Docs → Release → QA → Retro
custody:        Commander C0
executor:       E1 / D1 / Q1 / ...
reviewer:       independent R1
runner:         fenced lease RL42 on runner incarnation RI7
delivery:       unmerged / merged / staging-verified / production-verified / incident
```

Changing an executor, reviewer, runner, model, process, or session does not move ticket custody and does
not silently change Board lane, workflow stage, priority, proof, or delivery truth.

## Heartbeats, wakes, routines, and cron

Paperclip usefully demonstrates that agents should sleep until real work arrives, but the word
“heartbeat” is overloaded in agent systems. ctower separates five concepts:

| Concept | Durable meaning | Explicit non-meaning |
|---|---|---|
| Trigger | A versioned reason work may become due: event, assignment, mention, gate resolution, schedule, webhook, manual command, retry, or reconciliation | Not a model invocation |
| Wake intent | Idempotent committed request to create or coalesce a bounded job with exact cause and context pins | Not proof that a worker received it |
| Reasoning heartbeat | Operator-friendly name for one bounded execution run that claims a wake job, makes progress, records events/checkpoints, and terminates | Not identity or durable memory |
| Lease heartbeat | A runner liveness/progress frame that may renew only the current fenced lease | Not an instruction to reason or a success fact |
| Scheduler beat | A deterministic scan/kick that materializes due routine occurrences | Not one cron process per agent |

The authoritative entity behind a reasoning heartbeat is an **Execution run**. The friendly term may
appear in the UI, but schemas and events say `wake_intent`, `job`, `execution_run`,
`lease.heartbeat`, or `scheduler.scan` so operators and implementers cannot confuse them.

### Event-driven default

- New agent profiles have periodic timer wakes off.
- Assignment, comment/mention, gate resolution, explicit steering, retry, and routine occurrence create
  event-driven wake intents.
- Recurring business work is a versioned Routine with a schedule trigger, not “wake every agent every N
  seconds to see if anything happened.”
- A periodic agent poll is allowed only when the source has no webhook/event interface. It is represented
  as a named Routine with an explicit cost, staleness goal, owner, and disable switch.
- Pausing a schedule trigger stops new schedule occurrences. Pausing an agent blocks all new execution
  claims for that agent. These are different commands and are displayed separately.

### Routine definition

A Routine is a stable key whose immutable revisions pin:

- title/instructions template and typed variables;
- tenant, project, goal, optional parent ticket, and default stage/capability assignment;
- schedule, signed webhook, event, or manual triggers;
- IANA timezone and daylight-saving policy;
- concurrency, catch-up, idempotency, maximum backlog, timeout, cost, and escalation policy;
- referenced Profile, Skill, Workflow, Execution Policy, environment, and secret **references**.

Every occurrence pins the exact Routine and component revision. Editing or rolling back creates a new
revision; it cannot rewrite an in-flight or historical occurrence.

### Cron firing transaction

```text
system clock / event
        │
        ▼
┌───────────────────┐   SELECT ... FOR UPDATE SKIP LOCKED   ┌────────────────────────┐
│ scheduler scan    ├───────────────────────────────────────►│ due trigger revision   │
└───────────────────┘                                        └───────────┬────────────┘
                                                                          ▼
                                                               compute due occurrence(s)
                                                                          │
                                                                          ▼
┌────────────────────────────────── ONE DATABASE TRANSACTION ────────────────────────────────┐
│ 1. insert unique occurrence(trigger_revision_id, scheduled_for)                            │
│ 2. apply catch-up and concurrency policy                                                    │
│ 3. append received / coalesced / skipped / queued outcome                                  │
│ 4. create ticket, inbound event, or wake job when required                                 │
│ 5. write outbox message                                                                     │
│ 6. advance next_fire_at under compare-and-swap                                              │
└────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                         │ commit before dispatch
                                         ▼
                               outbox dispatcher → wake/job queue
```

The occurrence key makes restart and duplicate scans idempotent. Scheduling uses database time and stores
both the UTC instant and original local civil time/timezone. The default DST policy is
`wall_clock_once`: a nonexistent civil time is recorded as skipped and an ambiguous repeated civil time
fires once at the earlier offset. Fixed elapsed-time polling uses a UTC interval trigger instead.

Concurrency policy is one of:

- `coalesce_if_active` — attach the new occurrence to the active execution and queue no duplicate;
- `skip_if_active` — record a skipped occurrence with reason;
- `serialize_one_pending` — retain exactly one pending follow-up;
- `always_enqueue_bounded` — create distinct work up to a server/policy cap.

Catch-up policy is one of:

- `skip_missed` — record the missed window and advance;
- `coalesce_latest` — materialize one occurrence representing all missed windows;
- `enqueue_missed_with_cap` — materialize each missed occurrence up to a declared ceiling and record how
  many were dropped.

Defaults are `coalesce_if_active` and `skip_missed`. Every tick remains visible even when skipped or
coalesced. No restart may create a silent flood.

### Wake and reasoning-heartbeat flow

```text
assignment / comment / gate / routine / manual / retry / reconcile
                              │
                              ▼
                    ┌────────────────────┐
                    │ committed wake     │  dedupe/coalesce, policy, budget,
                    │ intent + outbox    │  cooldown, capability, current state
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ accepted job       │
                    └─────────┬──────────┘
                              ▼ lease + fencing token
                    ┌────────────────────┐
                    │ execution run      │──── structured events/log cursors ───► live view
                    │ bounded heartbeat  │──── checkpoints/artifacts ───────────► object store
                    └─────────┬──────────┘
                              ▼
                  terminal result / wait / typed failure
                              │
                              ▼
          Workflow + Proof evaluate; they do not trust process exit
```

Every reasoning heartbeat follows this server-enforced protocol:

1. Claim one accepted job under a current lease/fencing token.
2. Pin the exact Profile, Persona, Skill, Workflow, policy, harness/model, environment, image, workspace,
   context manifest, and wake-cause revisions.
3. Re-fetch current ticket/job/cancellation state; a stale wake cannot authorize work.
4. Read the specific cause first, then the compact eligible inbox; checkout/claim before mutation.
5. Execute bounded work while emitting ordered progress events and checkpoints.
6. Commit ticket comments, outputs, evidence declarations, and requested transitions through authenticated
   idempotent commands.
7. Emit one terminal result or explicit waiting/blocked result; process exit alone proves nothing.
8. Reconcile touched effects and release the lease. A stale process may upload quarantined forensics only.

A profile may include a revision-pinned `HEARTBEAT.md` checklist, as Paperclip does. That file is useful
role procedure, not scheduler, workflow, gate, counter, assignment, or completion authority.

### Continuations and steering

Resolving a human gate, approval, or structured question commits the result and an optional continuation
wake in the same authoritative transaction. The continuation names the exact ticket, interaction revision,
result digest, intended assignee/capability, and idempotency key. Live steering is a durable ordered command
with `queued → delivered → acknowledged|rejected|expired|superseded`; injecting text into a terminal is
never delivery proof.

### Watchdogs and reconciliation

ctower uses four separate deterministic detectors:

| Detector | Observes | Automatic action |
|---|---|---|
| Scheduler completeness | due occurrences, scan watermark, clock skew, outbox lag | claim/replay due work; degrade health on gaps |
| Runner liveness | current lease heartbeat, cursor progress, checkpoint, incarnation | suspect, expire, fence, requeue/resume |
| Ticket progress | stage age, blocker SLA, stopped subtree, no-progress lineage | re-evaluate or create one scoped watchdog-review job |
| Control/effect reconciliation | projections, receipts, provider inventory, backups, synthetics | replay, quarantine, incident, or owner alert |

An agent watchdog is a reviewer of a **detected condition**, not the liveness clock itself. Its input is a
fingerprinted desired/observed state. The same unchanged fingerprint is reviewed once, so a quiet failure
does not create endless duplicate comments or expensive wakes. Custom instructions may narrow review but
cannot expand authority, bypass a typed gate, approve a protected decision, or leave the ticket subtree.

### Health and operator surfaces

Fleet shows routines and heartbeat/run state without requiring terminal access:

- enabled/paused state, next due time, timezone, last occurrence, last success, backlog, and owner;
- every received/coalesced/skipped/queued/running/completed/failed occurrence;
- current agent run, wake reason, profile/model/harness, cost, timestamps, logs/events, checkpoint, touched
  tickets, cancellation, retry/resume, and terminal reconciliation;
- scheduler scan watermark, clock skew, due lag, outbox lag, leases, runner health, and unknown state;
- scoped “disable schedule,” “pause agent,” “cancel run,” “drain runner,” and audited emergency stop.

CLI and web call the same commands. There is no routine operation that edits the database directly. A
root-owned break-glass helper may submit a signed emergency command through the local control socket, and
its result is appended and visible like every other protected command.

## Autonomous verification loop

```text
dispatch ──► execute ──► evidence ──► QA/review gate ──PASS──► next stage
                              ▲               │
                              │               └──FAIL──► bounded repair attempt
                              │                                │
                              └────────────────────────────────┘
                                               retry ceiling reached ──► Needs You
```

The Commander selects the strongest healthy capable reasoning profile and proposes the risk-scaled review
topology. The kernel enforces gate floors, independence, current-digest proof, repair lineage accounting,
and the automatic ceiling. The Commander can raise rigor with evidence; it cannot fabricate a verdict,
reset consumption, or bypass an operator-only decision.

## Paperclip prior art: adopt and harden

The heartbeat design was checked against the complete relevant Paperclip documentation under
`paperclip-docs/`: heartbeat/routine guides, daily routine and stuck-heartbeat recipes, task watchdogs,
agent/run/activity surfaces, agent and routine API/CLI references, continuation interactions, execution
policy, and scheduler settings.

Adopt:

- event-driven wakes and timer-off defaults;
- versioned routines with cron/timezone, webhooks, manual runs, variables, and secret refs;
- explicit concurrency and catch-up policy;
- idempotent manual firing, run attribution, coalesced/skipped outcomes, revision-pinned runs;
- wake context, short-lived run credentials, visible live runs, cancellation, retry/resume;
- continuation wakes after gate decisions;
- stopped-state fingerprinting for watchdog review;
- a mechanical per-role heartbeat checklist.

Harden:

- Paperclip documentation sometimes uses “heartbeat” for both a scheduled alarm and any event-driven run;
  ctower uses the five distinct concepts above.
- Routine-level versus trigger-level delivery policy is inconsistent across Paperclip API and CLI prose;
  ctower keeps it in the immutable Routine revision and records trigger-specific overrides explicitly.
- A resumed vendor session is a convenience hint, not durable memory; ctower rehydrates from committed
  state and pins context by digest.
- Cancellation cannot wait for “the next heartbeat”; it revokes/fences state-changing authority now.
- Full transcripts are not permanent truth and may contain sensitive content; ctower preserves redacted
  structured events, byte/object cursors, evidence, and receipts under explicit retention.
- Direct database maintenance commands are not normal control paths.
- Agent status, ticket status, workflow stage, run state, health, and delivery remain orthogonal.

## Required failure proofs

Before scheduling and heartbeat support is called complete, tests must prove:

1. Duplicate scheduler scans, webhook retries, manual retries, and outbox replay create one logical
   occurrence and no duplicate effect.
2. A restart between occurrence insert and dispatch replays the outbox without losing or duplicating work.
3. Timezone, DST gap/repeat, clock skew, long downtime, and catch-up caps produce the declared outcomes.
4. Routine/profile edits do not alter already-created occurrences or execution manifests.
5. Agent pause, routine pause, project pause, budget stop, and runner drain have distinct fail-closed
   behavior and visible reasons.
6. Missed lease heartbeats never imply job success; stale fencing tokens cannot mutate ticket/proof/effect
   state.
7. Cancellation prevents new state-changing commands and protected effects from an old run.
8. The same stopped-state watchdog fingerprint creates one review; changed evidence creates a new one.
9. Scheduler/outbox/projection completeness loss renders Fleet and health degraded or `STATE UNKNOWN`.
10. A worker, tmux session, sandbox, remote provider, or whole VPS can disappear without losing accepted
    ticket, wake, occurrence, proof, checkpoint, or effect-receipt truth.

tmux therefore remains useful for same-host continuity and visibility, but it is only one Supervisor
Adapter. Durability comes from committed commands/events, occurrence keys, outbox replay, leases and
fencing, replayable cursors, immutable evidence, checkpoints, and external-effect receipts.

# Board lanes

The Board is the only cross-ticket work index. It is a read-only projection: a deterministic fold of ticket
facts into six lanes. You cannot write to it, and no lane is a stored status you can set.

## The six lanes

`backlog`, `ready`, `in_progress`, `in_review`, `blocked`, `complete`.

## How a lane is derived

The fold is small enough to state exactly. From `packages/ctower-kernel/src/ctower_kernel/projections/`:

```text
base lane:
    not admitted                    -> backlog
    admitted, no active workflow    -> ready
    active workflow,
        stage activity_class ==
        "verification"              -> in_review
    otherwise                       -> in_progress

then, in precedence order:
    lifecycle is resolved or closed -> complete   (underlying_lane cleared)
    a blocker is open               -> blocked    (base lane kept as underlying_lane)
```

Three consequences worth internalising:

1. **`in_review` comes from the stage's `activity_class`, not from a stage named "review".** A workflow that
   calls its verification stage `security-audit` still lands in `in_review`. The Board never has to know
   your stage vocabulary.
2. **`blocked` is an overlay, not a destination.** The card keeps `underlying_lane` so you can see what it
   will return to. Unblocking restores that lane rather than guessing.
3. **`complete` wins over `blocked`.** A resolved ticket with a stale open blocker reads as complete, and
   `underlying_lane` is cleared.

Cancellation is specified as a separate terminal disposition rather than a lane. Nothing produces it at this
revision — see [lifecycle episode](tickets.md#lifecycle-episode).

## What a card carries

Every `BoardCard` field is required by the contract; optional values are explicitly `null` rather than
absent:

| Field | Notes |
|---|---|
| `ticket_id`, `title`, `version` | Identity and aggregate version |
| `lane`, `underlying_lane` | As derived above; `underlying_lane` is non-null only while blocked |
| `priority` | `P0`, `P1`, or `P2` |
| `stage_key`, `stage_label`, `activity_class` | `null` when no workflow is active; `activity_class` is `work` or `verification` |
| `custodian_id`, `assignee_id` | Accountability versus current worker — see [custody](tickets.md#custody) |
| `blocker_reason`, `blocker_opened_at` | Non-null while blocked |
| `risk` | Derived, never a writable field |
| `delivery_facts` | Derived delivery observations |

## Why the Board tells you how stale it is

A `BoardView` carries `source_watermark`, `projection_watermark`, and a `health` value of `CURRENT` or
`STATE_UNKNOWN`.

A projection that has fallen behind, or cannot establish its own validity, says so. It does not serve
plausible old rows as if they were current. This is the same discipline that makes a write report
["committed here, acknowledgement pending"](durability.md): the system reports what it knows, including that
it does not know.

The specified — and [not yet built](proof.md#typed-evidence-slots) — evidence-slot rule extends this: once
slots exist, Board summaries must show the unfilled and unknown counts and expose the slot keys in API and
CLI detail, and a declared slot is never dropped from the denominator to make coverage look better.

## Querying it

```bash
ctl --base-url http://127.0.0.1:8080 board query \
  --lane in_progress --priority P1 --stage-key implement
```

All five filters are optional and combine: `--lane`, `--priority`, `--stage-key`, `--custodian-id`,
`--assignee-id`. The operation is `GET /v1/board`. It is a query, never spooled, and returns exit `0` on
success.

## Related

- [Ticket and lifecycle episode](tickets.md) — the facts the fold reads.
- [Project Delivery projection](project-delivery.md) — the other projection, at checkpoint rather than
  ticket granularity.
- [CLI reference](../reference/cli.md#board-and-health) — the exact flags.

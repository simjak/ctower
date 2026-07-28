# Project Delivery projection

Project Delivery answers "how is the project actually going?" at checkpoint granularity, and it is built so
that a good-looking answer cannot hide a weak one.

Like the [Board](board.md) it is a read-only fold with its own watermark. Unlike the Board it is not about
individual tickets: each row is a delivery checkpoint.

## The problem it solves

Status reporting drifts optimistic. A row says "done", and three separate things are quietly conflated:
the work was merged, the work was verified, and the evidence for that verification is still valid.

Project Delivery keeps them apart by carrying two states per row plus explicit reasons.

## Headline state versus underlying maturity

| Field | Values |
|---|---|
| `headline_state` | `planned`, `in_progress`, `ready_to_land`, `merged`, `verified`, `released`, `blocked`, `done` |
| `underlying_maturity` | `planned`, `in_progress`, `ready_to_land`, `merged`, `verified`, `released` |

`blocked` and `done` exist only as headline states. `underlying_maturity` cannot be blocked, so a blocked
row still tells you how far the work genuinely got. A row that reads `done` still exposes the maturity that
earned it.

## Every row states its own trust

These fields are required on every row. They are the reason this projection does not overclaim. The values
are the exact strings you will read in the JSON output; the right-hand column says what each one means:

| Field | Values | Reads as |
|---|---|---|
| `criteria` | `{proven, declared}` | Proof coverage as a fraction. Anything not proven is excluded from `proven` and named in the reasons |
| `freshness` | `fresh`, `stale`, `STATE_UNKNOWN` | Whether the view has caught up. `STATE_UNKNOWN` means "cannot be established" — never "fine" |
| `confidence` | `development_degraded`, `disaster_safe`, `STATE_UNKNOWN` | How far the environment itself can be trusted: `development_degraded` is a development environment making no data-safety promise |
| `health` | `CP3_D_NOT_PROVEN`, `CURRENT`, `STATE_UNKNOWN` | Whether the disaster-recovery checkpoint has been proven; `CP3_D_NOT_PROVEN` means it has not |
| `durability` | `CP3_D_NOT_PROVEN`, `CP3_D_PROVEN`, `STATE_UNKNOWN` | Whether writes are proven to survive losing this host, rather than assumed to |
| `recovery` | `EXTERNAL_FAILURE_DOMAIN_UNPROVEN` / `_PROVEN`, `STATE_UNKNOWN` | Whether a standby *outside* this machine's failure domain has been proven |
| `data_class` | `RECONSTRUCTIBLE_ONLY`, `DISASTER_SAFE_CTOWER_ENGINEERING`, `STATE_UNKNOWN` | What may be stored here. `RECONSTRUCTIBLE_ONLY` means only data you could rebuild from elsewhere |
| `derivation_reasons` | at least one string | Why this row says what it says |

`derivation_reasons` has `minItems: 1`. A row cannot assert a state without giving a reason for it.

At this revision the only environments that exist are development and test fixtures, and they report
`CP3_D_NOT_PROVEN` with `development_degraded` — durability unproven, environment not to be trusted with real
work. That is the honest reading, not a defect.

## Freshness and rebuild

Every row carries how far the underlying record had got when it was folded
(`source_record_position`, `projection_record_position`), when that happened (`reconciled_at`), when the
answer goes stale (`freshness_due_at`), a digest of the row's meaning (`projection_semantic_digest`), and
which rebuild produced it (`rebuild_generation`).

The projection is disposable: rows can be deleted and deterministically rebuilt from the record. Rebuilding
at the same source watermark must reproduce byte-equivalent semantic rows and the same derivation reasons —
that is what `projection_semantic_digest` is for. A projection you cannot rebuild is a second source of
truth, and ctower does not allow one.

Expiry, revocation, a dependency-digest change, rollback, an incident, or a superseding outcome removes
exactly the conditions that depended on invalidated proof, before the row may keep saying `done`. Doing that
slot by slot is part of the [typed evidence slots](proof.md#typed-evidence-slots) rule, which is specified
and not built.

## Reading it

```bash
ctl --base-url http://127.0.0.1:8080 project delivery query ctower --output json
```

`--output text` (the default) renders a compact CLI projection; `--output json` emits the deterministic
structured view. The operation is `GET /v1/projects/{project_key}/delivery`, requires an authenticated
principal, and `project_key` currently accepts only `ctower`.

If the projection cannot serve a trustworthy answer it refuses with `project-delivery-unavailable` rather
than returning a stale row.

## Implementation status

The read-only contract, the strict schema, and the CLI text/JSON projection are implemented. This evidence
is available through the command line only; showing the same data in a browser starts later, at the planned
stage the roadmap calls `CT-I2-005` / I2.4.

## Related

- [Board lanes](board.md) — the ticket-granularity projection.
- [Proof](proof.md) — where `criteria.proven` comes from.
- [Delivery state](../project-status.md) — the current capability matrix in the engineering record.

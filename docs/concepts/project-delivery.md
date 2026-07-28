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

These fields are required on every row. They are the reason this projection does not overclaim:

| Field | Values | Reads as |
|---|---|---|
| `criteria` | `{proven, declared}` | Proof coverage as a fraction; unfilled slots are excluded from `proven` and named in the reasons |
| `freshness` | `fresh`, `stale`, `STATE_UNKNOWN` | Whether the fold has caught up |
| `confidence` | `development_degraded`, `disaster_safe`, `STATE_UNKNOWN` | How much the environment itself can be trusted |
| `health` | `CP3_D_NOT_PROVEN`, `CURRENT`, `STATE_UNKNOWN` | Whether the disaster-recovery checkpoint has been proven |
| `durability` | `CP3_D_NOT_PROVEN`, `CP3_D_PROVEN`, `STATE_UNKNOWN` | Whether durability is proven, not assumed |
| `recovery` | `EXTERNAL_FAILURE_DOMAIN_UNPROVEN` / `_PROVEN`, `STATE_UNKNOWN` | Whether a standby outside the primary failure domain is proven |
| `data_class` | `RECONSTRUCTIBLE_ONLY`, `DISASTER_SAFE_CTOWER_ENGINEERING`, `STATE_UNKNOWN` | What class of data is allowed here |
| `derivation_reasons` | at least one string | Why this row says what it says |

`derivation_reasons` has `minItems: 1`. A row cannot assert a state without giving a reason for it.

At this revision, a real deployment reports `CP3_D_NOT_PROVEN` and `development_degraded`. That is the
honest reading, not a defect.

## Freshness and rebuild

The view carries `source_record_position`, `projection_record_position`, `reconciled_at`,
`freshness_due_at`, `projection_semantic_digest`, and `rebuild_generation`.

The projection is disposable: rows can be deleted and deterministically rebuilt from the record. Rebuilding
at the same source watermark must reproduce byte-equivalent semantic rows and the same derivation reasons —
that is what `projection_semantic_digest` is for. A projection you cannot rebuild is a second source of
truth, and ctower does not allow one.

Expiry, revocation, a dependency-digest change, rollback, an incident, or a superseding outcome removes
exactly the conditions that depended on invalidated proof, and renders each affected
[evidence slot](proof.md#typed-evidence-slots) unfilled *before* the row may remain `done`.

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

The read-only contract, the strict schema, and the CLI text/JSON projection are implemented. Increment 1
delivers this evidence through the CLI only; the browser rendering of the same data first activates at
CT-I2-005 / I2.4.

## Related

- [Board lanes](board.md) — the ticket-granularity projection.
- [Proof](proof.md) — where `criteria.proven` comes from.
- [Delivery state](../project-status.md) — the current capability matrix in the engineering record.

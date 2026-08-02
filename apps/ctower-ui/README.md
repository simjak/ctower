# ctower-ui boundary — phase-1 read-only operator surface

This is **not** `apps/ctower-web`. It is a separate, explicitly non-product boundary: a
read-only operator dogfood surface over the running shadow instance, ordered by the operator
(R2710) and built against the approved mockup set vendored under `design-reference/`.

## What it is, and what it is not

| | |
|---|---|
| Is | A Next.js server that reads the shadow instance's existing read API and renders eight approved screens. |
| Is | Read-only. Every path it calls is a `GET`. There is no mutation function in this boundary to call by accident. |
| Is not | The I2.4 browser product. `apps/ctower-web` remains untouched, and D22 §1 (React 19 / React Router 7 / Vite static, no SSR) still governs it. |
| Is not | An authority. The browser receives no API bearer, no session and no credential of any kind; every read happens server-side. The instance's API origin *is* printed, deliberately, in the provenance foot of every screen — see below. |

Two repository facts this boundary deliberately does **not** decide, and which need an operator
decision entry before it merges as anything other than a dogfood surface:

- `SPEC.md` `CT-I1-005` reads *"No I1 browser implementation, route, placeholder, or browser
  evidence is authorized."* This boundary is a browser implementation. It exists because the
  operator dispatched it; it does not consume `CT-I1-005`/`CT-I2-005`, and it claims none of
  their evidence.
- `DECISIONS.md` D22 §1 selected React Router 7 + Vite for `ctower-web`. Next.js here is a
  second frontend stack in the repository. D22 is not rewritten by this boundary — it is not
  `ctower-web` — but a second stack is a real fact that belongs in an append-only entry the
  operator locks.

## Layout

```
design-reference/   the approved mockups, vendored verbatim; app.css is imported by the app,
                    so the rendered screens and the design reference read the same bytes
src/read/           the record-read contract and its one implementation
src/frame/          the chrome every screen shares: mark, nav, theme, provenance foot
src/surfaces/       one directory per screen family
src/app/            the eight routes
```

### What the browser is and is not given

No bearer, no session cookie, no CSRF token and no credential reaches the page: `src/read/` runs
only on the server. What the page *does* carry is the instance's API origin, printed in the
provenance foot next to the posture and the render time. That is deliberate — a capture from one
instance would otherwise be indistinguishable from a capture from another, which is the failure
mode the foot exists to prevent. The origin is not a credential and grants a reader nothing; if a
future deployment wants it hidden, `frame/RecordFoot.tsx` is the one place to change.

### Bounded reads (O10)

`src/read/bounded.ts` is the only module in `apps/` that names `fetch`. Every record read goes
through it under a bounded policy: a per-attempt timeout, a finite attempt count *and* a finite
elapsed deadline, full-jittered exponential backoff capped and clamped to the remaining deadline, a
typed transient/permanent predicate with no catch-all branch, and a typed `ReadExhausted` outcome
that preserves the attempt count, elapsed time and last classified failure and is counted and
written once to stderr. Idempotency is satisfied by construction: the chokepoint issues `GET` and
accepts no method or body, so no mutation call site exists here.

`tests/repository/test_browser_network_chokepoint.py` derives the call-site denominator from the
repository tree — not from a hand-kept endpoint list — and fails closed when a network-capable
construct appears outside an approved policy holder, when the chokepoint loses one of its required
bounds, or when an application value-imports the generated client's single-shot runtime.

### The data adapter

`src/read/interface.ts` declares every read this surface makes as a typed function returning
`Reading<T>` — `present`, `absent` (with the work item that will land the source), or
`unavailable`. `src/read/httpRecordAdapter.ts` implements it against `/v1/board`,
`/v1/tickets/{id}` and `/v1/tickets/{id}/audit`. `src/read/adapter.ts` binds the one that is
active.

Landing the #186 typed feed changes `adapter.ts` and nothing else: no screen constructs a
client, and no screen knows a URL.

### Wave 2 — every screen on a live source

| Screen | Source today | Swaps to |
|---|---|---|
| Board · Ticket | ctower read API (`/v1/board`, `/v1/tickets/{id}`, `/audit`) | #211's typed feed |
| Inbox | Mission Control `state/inbox.jsonl`, read-only | #186 notification channel |
| Heartbeats | host `crontab -l` + `state/` fire markers — or `systemctl --user list-timers` | a native cadence registry |
| Files | this repository's git tree at a committed revision | — |
| Workspace · Feed | the tmux capture bridge (`mux list`, `mux read`) | G5 session facts |
| Explorer | `git worktree list` + `git diff <base>...HEAD` | G5 worktree facts |

These are **interim, director-sanctioned** adapters, and they name a third boundary this repository
does not otherwise cross: `SPEC.md` line 67 calls Mission Control *migration or research provenance
only, not a runtime dependency*. Wiring the Inbox, Heartbeats, Workspace and Feed to its live state
makes it one for those four screens. It exists because the operator escalated (R2710 wave 2), every
path is overridable, and nothing outside `src/read/sources/` knows any of them — but it belongs in
the operator's decision entry beside the two boundaries above.

Three hard lines hold across all of them, and each is enforced structurally rather than promised:

- **Read-only, including other repositories' files.** No module under `apps/` may call a filesystem
  write; `test_browser_network_chokepoint.py` fails the gate if one appears.
- **Concurrent appends.** `state/inbox.jsonl` is appended to while this surface reads it, so a
  mid-write final line is skipped *and counted*, and the screen states the count. Reading N-1 lines
  and calling that the inbox would be a lie of omission.
- **Redaction before render.** Every interim source must import `./redact`; the check fails closed
  on one that does not. Coordination text and terminal panes are the most exposed strings on this
  surface, and nothing guarantees a seat never pasted a credential into one.

### Honest empty states — and the difference between empty and unreachable

Board and Ticket render live record facts. Heartbeats, Inbox, Feed session facts, Files,
Workspace and Explorer have no source in ctower today, so each renders its approved layout and
an explicit block naming the work that lands its source (`#186` / `G5`). No screen invents a
number, a name, a duration or a token count. The ticket work timeline in particular reads
`no session data yet` and totals `—` until G5 session events exist.

**A source that exists and did not answer is never rendered as one that does not exist.** These are
opposite claims to an operator, so they are different states, different blocks and different words:
`no data source yet` versus `the record was not reached`, the latter carrying the classified
failure and the bounded attempts that were spent. A `Reading` is unwrapped only in
`frame/Declared.tsx` — `Resolved` for a panel, `InlineReading` for a row — so no surface can
flatten a failed read into an empty one, and the structural test above fails closed if one tries.
Inline, the two read `not recorded` and `not reached` rather than a bare dash.

### Read-only v1

The steering composer (Feed) and the Save/Revert controls (Files) render as visibly disabled
affordances with the reason on the control itself, never as a page banner and never as a
dead-looking control. View switches — Chat/Raw, File/Diff, the board source filter — choose a
reading rather than issue a command, so they stay live.

## Running it

```text
apps/ctower-ui/serve-development.sh          # builds nothing; serves the built output on :3117
```

The script resolves the operator credential from the Secret Service reference the instance
already uses and exports it for the life of the Node process. It is never written to a file,
never passed as an argument, and never reaches the browser.

| Variable | Default | Meaning |
|---|---|---|
| `CTOWER_UI_API_BASE_URL` | `http://127.0.0.1:8091` | The loopback read API. |
| `CTOWER_UI_API_TOKEN` | — | Bearer for the read path. Required; there is no anonymous read. |
| `CTOWER_UI_INSTANCE_LABEL` | `shadow` | Shown in the header chip. |
| `CTOWER_UI_INSTANCE_POSTURE` | `SHADOW_ONLY_CP3_D_NOT_PROVEN` | Shown in the provenance foot. |
| `CTOWER_UI_INSTANCE_REVISION` | served commit | Shown beside the instance label. |
| `CTOWER_UI_PORT` | `3117` | Listen port. |

Build first with `pnpm --filter @ctower/ui build`. The repository gates
(`pnpm run format:check`, `pnpm run lint`, `pnpm run typecheck`) cover this boundary and are
run by `just check`.

## Deviations from the approved mockups

Each is a fact the record does not carry, not a design preference. They are listed in full in
the phase-1 status note; the two structural ones are:

1. **Board columns are the record's lanes**, not the mockup's seven pipeline stage names. The
   shadow instance runs `ctower.trust-spine-four-stage@1` and every card carries `lane`;
   painting stage names over lane data would have been an invented mapping.
2. **The filter dimension is `source.kind`**, not project. The record carries no project fact
   yet (#185 / D29); `source.kind` is recorded and is a first-class `/v1/board` query filter.

The section nav carries the eight screens in this phase. `Workflow` (R2707) is not built here,
and a nav entry that leads nowhere would be a dead control.

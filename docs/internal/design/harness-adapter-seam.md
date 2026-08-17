# The harness-adapter seam — T0 design

**Status: non-normative think-stage design input.** It is the think-stage output of pilot ticket
`01a010da-2b91-7edf-abc0-3b462a05039c` ("PILOT EPIC T0: harness-adapter abstraction — the seam
contract") and the intended input to that ticket's plan stage. `docs/internal/SPEC.md` remains
authoritative; this document may not override or extend it, does not amend `ARCHITECTURE.md`, adds
no CT row, no D entry, and no active scope. When the plan stage freezes acceptance criteria and a
spec lane consumes these sections into SPEC rows, this file is superseded and should be deleted
rather than maintained as a second architecture source.

**Written against:** ticket T0 (P1, source `operator-order` / `pilot-adapters-2026-08-17`, workflow
`engineering.software-factory@1`, stage `think` at workflow version 2, transitioned
2026-08-17T18:02:02Z). Origin order, verbatim: *"we need implement the harness adapters for claude
code, hermes, codex, later openclaw, qwen code, zcode, deepseek harness — so we need decent
abstraction"*. Scope addition (operator via director, 2026-08-17 18:04Z): a per-harness credentials
pool — create and maintain a pool per harness, track usage limits, rotate automatically — specified
in §4 with draft criteria `AC-HAD-13..15`.

**Prior art it is derived from:** D10 (compositional execution, the Supervisor Interface, and the
two-real-Adapters-plus-fake rule that has kept adapters design-only until now), D11 (extension host,
manifests as data), D13 (placement/remote deferral), INV-48/49/58/69/73/75/76/77, the SPEC's local
runner section, and the fleet's *living* manual adapters — `tools/claude-crew`, `tools/hermes-crew`,
`tools/crew-send`, `tools/crew-model-watch`, `tools/ctower-beat-watchdog` in Mission Control. Those
five scripts already implement this seam by hand; every lesson named below was paid for in a
production incident recorded in `projects/ctower/decisions.md`. The design's job is to keep those
lessons and delete the hand-work, not to invent a new abstraction over an unexplored problem.

---

## 0. What T0 actually is, and what it is not

D10 already owns **process control**: the Supervisor Interface is `probe`, `launch`,
`observe(after_cursor)`, `deliver_input`, `interrupt`, `terminate`, `snapshot`, `adopt`, every
mutation carrying attempt ID, idempotent command ID, and fencing epoch, with `bin/mux`/tmux as the
production Supervisor Adapter. That vocabulary is not reopened here. Inventing a second
process-control vocabulary at the harness layer would be exactly the "two authorities for one fact"
mistake this repository refuses everywhere else.

T0 owns the **harness-facing** layer that sits above it: what a *seat* needs in order to be briefed,
believed, collected from, and credited — a layer the Supervisor Interface deliberately does not
model, because `launch` cannot tell you that the pane it started is serving a different model than
the one you asked for, and `probe` cannot tell you that the lane is alive but past its context
window and therefore no longer trustworthy.

So the seam is:

```
HarnessSpec (revision-pinned DATA: key, revision, artifact/config digests,
             input/output protocol, capabilities, liveness evidence sources)
        +
five verbs: spawn · liveness · collect · writeback · teardown
        composed over the existing Supervisor Interface
        drawing credentials from one CredentialPool per harness (§4)
```

Capabilities are **data, not methods** — a manifest parsed without executing package code, the shape
D11 already requires of every extension manifest. An adapter that cannot declare a capability does
not get to discover it at runtime; an unknown, incompatible, revoked, or digest-mismatched
`HarnessSpec` is a refusal and never a fallback to a generic process (INV-48).

The credentials pool of §4 is a **sibling Interface, not a sixth verb**. It is resolved at `spawn` and
consumed by the binding, because a pool owned per-adapter is how a fleet ends up with three
incompatible rotation policies and a fourth substrate class with no pool at all — which is exactly
today's state.

---

## 1. The seam contract

Every binding implements exactly these five verbs. Sketches are illustrative Python; the plan stage
freezes exact payload schemas, and every payload crossing this seam is strict and typed (no unknown
fields, no open dicts, secrets as references only).

### 1.1 `spawn(attempt, seat, brief, context) -> DispatchReceipt | Refusal`

```python
def spawn(
    attempt: AttemptPin,          # attempt id, fencing epoch, pinned Harness/Supervisor/Target/
                                  # Workspace/Telemetry revisions + composition digest (D10)
    seat: SeatRef,                # durable seat key + crew engagement label; NEVER a principal
    brief: BriefBundle,           # rendered instruction + its digest + the ACK predicate to satisfy
    context: WorkspaceContext,    # worktree path, branch, base ref, artifact sinks
) -> DispatchReceipt | Refusal
```

`spawn` composes the launch plan, hands it to the Supervisor Adapter's `launch`, delivers the brief
through the harness's native input path, and **returns only after the harness's own ACK predicate is
observed**. It returns `harness-dispatch-unacknowledged` otherwise, with zero session-start fact and
zero assignment stamp recorded.

- **Lesson: "delivery is not acknowledgement."** `bin/mux send` + `submit` reports success while the
  text sits in the composer; the crew then reads as *idle* — indistinguishable from finished — while
  holding an unread instruction. This happened eight times in one day before `tools/crew-send` was
  written to verify instead of assume. SPEC already states the kernel half of this rule (D10:
  "`send-keys` delivery is not an acknowledged command"; steer counts as `acknowledged` only when
  the harness returns the command ID). The adapter half is that **the ACK predicate is
  harness-private and belongs in the binding**: Claude Code needs a literal `send-keys` followed by
  a separate `Enter`; the Codex TUI collapses a long brief into a `[Pasted Content NNNN chars]`
  block that one `Enter` does not flush and two do. Neither fact may leak into the kernel.
- **Lesson: "a spinner is not a turn."** A pane whose auth is dead shows a normal footer and an
  advancing timer while the dispatched turn died at birth. `spawn` therefore treats a
  cap/limit/credit banner as `dead_auth` and refuses, rather than reporting a dispatch.
- **Guard before dispatch (INV-58).** `spawn` obtains and enforces a current versioned CommandGuard
  decision for the exact normalized execution plan at its final pre-dispatch boundary. `block` and
  `needs_operator` dispatch nothing; if the required receipt cannot be durably recorded first, the
  adapter performs zero dispatch.
- **Credential lineage is pinned at spawn, never mutated live.** Codex credentials are read at spawn
  time, so a rotation reaches a running lane only by respawning it; hermes profiles own their own
  `auth.json`/`auth.lock` lineage and a *copied* refresh chain self-revokes (R2994 — the raw-CLI
  path died twice in one night from the single-use-refresh dual-copy conflict). This matches D13's
  rule exactly: an active pointer change affects future attempts only.

### 1.2 `liveness(attempt, after_cursor) -> LivenessFact`

```python
@dataclass(frozen=True)
class LivenessFact:
    state: Literal["working", "idle", "queued_stuck", "saturated",
                   "capped", "dead_auth", "unknown"]
    served_model: ModelObservation | None   # value + evidence source + observed_at
    context_used_pct: int | None            # percentage, never absolute tokens
    probe: str                              # the exact probe that produced this fact
    evidence: EvidencePointer               # opaque; never raw pane bytes
```

`liveness` never returns a boolean and never returns `True` by default. `unknown` is a first-class
outcome carrying the exact `substrate-unobservable:<probe>` name INV-76 already requires; silence,
terminal text, and a model's claim about itself are never liveness truth.

- **Lesson: "served model is footer-truth, because launch routing lies."** Three times in one night
  a lane printed `luna` at launch while the substrate served `glm-5.3`; on 2026-08-05 a review pane
  footer read `gpt-5.6-terra` while the gateway served deepseek. The record of what was *requested*
  is not evidence of what is *serving*. The sharpened rule, which `tools/crew-model-watch` encodes:
  **each binding declares its own serving-truth source, and a source that only proves the request is
  recorded as a conflict, never as truth.** For hermes that source is the gateway/provider log (the
  footer shows the request); for Claude Code it is the session transcript, because those panes carry
  no parseable model footer; for a codex child process the launch argv is request-ground-truth and
  outranks a status-bar text match. A model observed to differ appends a `model_changed` observation
  (INV-76: `from`, `to`, `observed_at`, `source`, probe evidence) and never overwrites the dispatch
  stamp.
- **Lesson: "saturation is a death, not a slowdown."** A lane at or past its context window has a
  live timer and is emitting tokens, and cannot be trusted to still hold the evidence it cites — a
  CSO gate was found at 178K against a 131.1K window, one step from signing a security verdict; two
  feature lanes were found at 964K and 667K against a 202.8K window. `saturated` counts as **not
  working**, exactly as the fleet floor already counts it, because the floor exists to guarantee
  trustworthy throughput rather than motion.
- **Lesson: "the percentage is the portable signal."** A 1M-window lane at 170K reads 17% and is
  healthy; a 131K-window lane at 178K reads 136% and is not. The ratio's units prove nothing on
  their own, so the threshold is expressed as a percentage of the declared window per binding.
- **Lesson: "an untested monitor pattern is not a monitor."** The first saturation detector matched
  nothing at all: `█+` is a *byte* quantifier in this locale and silently failed against the real
  multibyte footer, and it would have reported a clean fleet forever. Every liveness classifier ships
  with a fixture of real captured substrate output, per binding, or it is decoration. Untested
  monitors fail silently in the direction of *looking fine*, every time.
- **Lesson: "a failure that renders as the healthy state is the whole problem."** The Claude limit
  menu (`Enter to confirm · Esc to cancel`) matched the generic `· esc` liveness pattern, so a
  rate-limit-dead lane counted as working for hours on the critical path. Cap detection is evaluated
  **before** any working marker and wins over it; a limit/upgrade/out-of-credits pane is dead
  regardless of what else is on the screen. New cap phrasings belong in the classifier, not in a
  note — the last extension of those patterns was lost because it was left uncommitted in a shared
  working tree.
- **Lesson: "the composer renders during turns."** Some harnesses show a between-turn composer with
  no marker while the pane is visibly moving. A prior/current pane-content hash delta is the
  harness-independent fallback that proves *working* without knowing the harness's spinner; first
  sight establishes only a baseline. This is a deliberate, named limitation: a changing error loop
  counts as working, which is why cap and saturation are evaluated first and fail closed.
- **Steering into a live turn is refused.** A reviewer an hour into a real finding was steered
  mid-turn because a codex-only liveness pattern read a hermes lane as idle; had it been re-seated,
  the finding — that a build lane had claimed gate coverage it never ran — would have died with it.
  `deliver_input` into a `working` lane requires the interrupt capability or returns unsupported
  (D10's `LIVE_INPUT` vs `INTERRUPT_AND_RESUME` distinction, applied at the harness layer).

### 1.3 `collect(attempt, reason) -> ArtifactSet | Refusal`

```python
def collect(attempt: AttemptPin, reason: CollectReason) -> ArtifactSet | Refusal
    # reason ∈ {terminal, checkpoint, park, forensic}
```

`collect` gathers what the run produced: committed and pushed refs, gate output paths, the status
artifact, and typed metadata. It never gathers pane text as evidence.

- **Lesson: "a fix that is not committed is not a fix, and an audit that reads the working tree
  cannot tell the difference."** A watchdog repair sat in a shared repository's working tree and was
  overwritten by a later commit while an audit reported it fixed for hours. `collect` reads
  committed refs; an uncommitted working tree is `checkpoint-uncollectable`, naming the dirty paths,
  rather than a silently smaller artifact set.
- **Lesson: "the branch is the handoff."** Two saturated lanes were reaped without ever writing a
  status file; their pushed branches carried the work, and continuation lanes reconstructed from the
  diff. `collect` therefore never depends on the seat's cooperation: everything a successor needs
  must be derivable from pushed refs and durable records, because the seat that would have written
  the handoff is precisely the seat that is too saturated to write one.
- **Lesson: "pane existence is not proof."** INV-49 and D10 both already say it; the adapter's job is
  to make it structurally impossible to satisfy an evidence slot with `capture-pane` output.
  `capture-pane`, `pipe-pane`, pane existence, and `send-keys` remain visibility conveniences.

### 1.4 `writeback(attempt, seat_credential, facts) -> WritebackReceipt | Refusal`

```python
def writeback(
    attempt: AttemptPin,
    seat_credential: CredentialRef,   # a REFERENCE to the seat's own project-seat credential
    facts: WritebackBatch,            # session facts | comments | evidence | transition REQUESTS
) -> WritebackReceipt | Refusal
```

This is the verb that makes the seam worth building, and the one with the least room for
interpretation. Every fact is written **as the seat**, under the seat's own project-seat credential,
and the authority ceiling is exactly the three scopes SPEC already enumerates as exhaustive:
`capture`, `transition`, `evidence` (INV-69).

- **A transition is a *request*, never a transition.** SPEC's scope table grants a `transition`-scoped
  seat the right to "issue ordinary typed comment, priority, admit/defer, block/unblock,
  assignment/handback, and Workflow transition or resolve **requests** when all existing state,
  assignment, evidence, and policy rules also permit them". The adapter emits requests and reports
  the server's answer; it never advances a stage, and a refusal is a result to report, not an error
  to retry differently. Stage-role membership is checked server-side for the destination stage being
  entered (CT-I1-036/CT-I2-006, D68); the adapter supplies no role claim of its own, because no
  caller, token claim, principal ID, display name, profile, **model, harness, or crew label** may
  supply a `seat_key` or `role_key`.
- **Lesson: "seats must file as themselves."** Fifteen tickets were filed by a shared principal with
  a wrong project key, and the wrong key was *unrefusable* precisely because the principal was
  shared: with one identity behind many seats, the server has nothing to check the claim against.
  One credential per seat is what makes `project-scope-denied` possible at all. An adapter holding an
  operator or commander credential is a design failure, not a convenience.
- **One request, one Actor (INV-73).** The adapter resolves exactly one durable principal and one
  typed Actor context per call. It creates no principal, no seat, no second custody model, and no
  second attribution model. A seat credential is what mints an address; a bundle entry alone does
  not.
- **Lesson: "stamp from the clock, never the narrative."** Every journal label across five hours
  drifted up to +3h43m because timestamps were incremented by narrative rather than read from the
  clock. Session duration is Record-owned — committed close time minus committed start time — and is
  never a caller claim (INV-75). The adapter reports observation times it actually read, and cost
  facts as bounded typed values.
- **Lesson: "never wake a commander seat."** Writeback reaches humans through the durable inbox at
  every severity, never by injecting into a pane. This is a standing operator order, and it is also
  the only shape consistent with INV-80's mirror rule: the durable delivery happens first, and no
  mirror failure can reverse it.

### 1.5 `teardown(attempt, order) -> TeardownReceipt | Refusal`

```python
def teardown(attempt: AttemptPin, order: TeardownOrder) -> TeardownReceipt | Refusal
    # order ∈ {checkpoint, park, reap}
```

- **`checkpoint`** is the *checkpoint order*, promoted from a manual commander action to an adapter
  verb: commit and push work in progress, write the handoff artifact with its four required sections
  (done / in progress / not started / next three steps), stop. It is issued on a `saturated` or
  `capped` liveness fact, because a lane past its window cannot be trusted to hold its own evidence.
- **`park`** suspends a lane on a *stated basis* with an *explicit expiry*. The fleet's park mode
  re-proves its basis every sweep and fails loud at 120 minutes: a forgotten park cannot silence the
  floor forever, and a wake condition turning true (a substrate coming back alive) breaks the park
  immediately. That asymmetry — cheap to arm, self-expiring, broken by good news — is the design,
  and it belongs in the verb rather than in an operator's memory.
- **`reap`** is refused while sole work is unpushed, and refused for a `dead_auth` lane, whose pane is
  preserved for resume-on-refill. **A resume nudge precedes a respawn**: a lane that ended a turn
  without delivering is first offered one input; only a lane that cannot be resumed is replaced.
  Reconstruction after pane, tmux-server, or host loss comes from ctower state, never from crew-log
  memory (SPEC's local-runner section).

### 1.6 Refusals

Refusals are by exact name with zero mutation. Where SPEC already owns the name, the seam reuses it
(`project-scope-denied`, `role-resolution-unavailable`, `substrate-unobservable:<probe>`,
`workflow-stage-role-not-permitted`). Names this design needs and SPEC does not yet own:
`harness-dispatch-unacknowledged`, `harness-capability-unsupported`, `checkpoint-uncollectable`,
`teardown-would-destroy-sole-work`. The spec lane mints the final spellings and must check them
against the existing refusal vocabulary before freezing — refusal-name overlap was a P1 finding
against the step-5 role spec, and this seam introduces four candidates at once.

---

## 2. What stays out

| Concern | Stays with | Why the adapter must not have it |
|---|---|---|
| Authority | Operator (issuance/revocation), seat credential (action) | An adapter gets one seat's credential with `capture`/`transition`/`evidence` scope and nothing more. Operator or commander credentials in an adapter defeat INV-69's whole point; issuance is operator-only. |
| Stage advancement | Workflow evaluator, server-side | Adapters emit transition **requests**. Membership, predicates, gates, and refusal precedence are server-owned (D68/CT-I2-006). |
| Judgment | Independent review seats, human or cross-family | Verdicts bind effective identity and independence rules; switching model or harness under the same author assignment does not create reviewer independence. An adapter that could sign a verdict would make the reviewer's family irrelevant. |
| Scheduling | Routines and the Commander | An adapter runs one attempt when asked. It owns no cron, no cadence, no backlog ranking, no floor. The 32-cron migration is a separate measured problem and is not solved by giving adapters timers. |
| Placement and remote execution | D13, deferred | No adapter provisions a target, holds provider credentials, or opens a remote Seam. A public remote/image Seam needs two real Adapters, an unchanged conformance suite, and an append-only scope decision. |
| Record persistence | Kernel only | Runner, provider, web, CLI, extension, and YAML packs never connect to record-tier persistence. An adapter reaches ctower through the generated client, holding no database credential. |
| Model policy | Profiles, catalog revisions, operator rulings | The adapter *observes and reports* the served model. Which model a lane may run is a policy question decided outside it; the adapter's contribution is making a substitution visible, not adjudicating it. |
| Harness-private formats | Inside the binding, and nowhere else | INV-77: no custody, event, status, reporter, Board, CLI, Evidence, or session integration may assume one harness's session shape or transcript format. |
| Pool membership | Operator ceremony | An adapter selects, observes, and reports credentials (§4); it never mints an entry, refills credits, or raises a plan. It can only surface the exact refusal and the earliest known reset. Reaching a credential is not entitlement to it. |

---

## 3. The first three bindings

Two of these earn the Seam; the third is the honest special case. D10's rule is unchanged: the public
Seam is earned only when two real Adapters plus one deterministic fault-injection fake pass the same
conformance suite. Seven adapters do not earn it faster; they earn it not at all if the first two
never proved the contract.

### 3.1 `claude-code` — mechanics from `tools/claude-crew`

| Seam verb | Harness mechanic | The trap it encodes |
|---|---|---|
| `spawn` | `bin/mux spawn` a wrapper script that `cd`s to the worktree and `exec`s the CLI with an explicit model; wait for TUI readiness; deliver the brief as a literal `send-keys` followed by a **separate** `Enter`; verify the composer cleared. | `mux send` does not work on this TUI. The wrapper is also a policy blind spot: a launcher that spawns through a temp script hides the binary's name from any check that inspects `argv[0]`, so every spawn path needs its own refusal rather than relying on a shared one. |
| `liveness` | `esc to interrupt` / running-shell markers for working; limit-menu and "reached your … limit" text for `capped`; context-bar percentage for `saturated`; pane-hash delta as the marker-free fallback. | The limit menu matched the generic working pattern for hours. "N shells still running" with no esc-marker is working, not idle: the turn ended but the gate run continues. |
| served model | Session transcript JSONL under the pane's cwd, most recent real assistant turn, `<synthetic>` turns skipped, stale beyond one hour = `unknown`. | These panes carry **no** parseable model footer; treating absence as agreement made an entire harness family read `unknown` forever. A stale transcript in a shared worktree once reported a dead session's model as live truth. |
| `collect` | Worktree branch + status artifact; `just check` / `just verify` closing lines as gate output. | The status file is optional; the pushed branch is not. |
| `writeback` | Seat credential through the generated client. | Same as every binding — no exceptions for the harness the commander happens to run on. |
| `teardown` | Checkpoint order on saturation; pane preserved on `dead_auth`. | Claude cap text differs from every other harness's and was missing from the classifier twice. |

### 3.2 `hermes` — profiles, ladders, and gateway truth

| Seam verb | Harness mechanic | The trap it encodes |
|---|---|---|
| `spawn` | `bin/mux spawn` a wrapper that execs `hermes` with `HERMES_HOME` pointing at a **profile directory**; model and reasoning effort come from that profile's config, never from the launcher's arguments. | Model-in-the-launcher is how a launcher gets named after a model and a phantom harness category is born. The profile is the pinned component; the launcher is not. |
| credentials | Each profile owns its own credential lineage (`auth.json` + `auth.lock`); tokens are minted per profile, never copied. | A copied refresh chain self-revokes — the single-use-refresh dual-copy conflict killed the raw path twice in one night. Account pooling as a *launcher argument* is retired; it lives in the profile or nowhere. |
| `liveness` | Footer timer glyphs (`⏲`/`⏱`) rather than an "esc to interrupt" hint; footer `used/window │ [bar] pct` gives the saturation percentage; pool errors (`credential pool: no available entries`, non-retryable 401) are `dead_auth`. | Five working hermes lanes read as idle against a Claude-shaped pattern and fired false floor breaches every cycle. |
| served model | **Gateway/provider log**, not the footer — the footer shows the *requested* model. A footer/ledger disagreement is recorded as a conflict, not paged as substitution. | A footer said `gpt-5.6-terra` while the gateway served deepseek. This is the single clearest case for per-binding evidence sources. |
| ladders | A profile declares a fallback chain; serving a known fallback rung of the spawn intent is the never-stall ladder, not a substitution — **except on judgment lanes, where tolerance is zero**. | Anchoring "expected" to the latest ledger row instead of the durable spawn intent reports the *recovery* as the violation. |
| `teardown` | Same checkpoint/park orders; profile stays pinned across a resume. | A resumed lane on a different profile is a different composition and therefore a different attempt. |

### 3.3 `codex-runtime` — a runtime under a harness, not a third harness

This binding is where the abstraction earns its keep by *refusing* a category. On this fleet there is
no codex crew: codex models are reached through a hermes profile's codex runtime, and "a model is not
a harness — naming a launcher after the model is what produced the phantom category". SPEC keeps
`codex` as a legal baseline `harness_ref` (INV-77) for a direct-CLI binding, and the roadmap's I2.2
exercises "local Codex/Claude Harness compositions", so the value is legitimate; today's fleet route
to it is not a separate harness.

The seam expresses this with two pinned fields rather than one: the observed `harness_ref` **and**
the runtime/profile reference that carries credential lineage. The credential mechanics below are the
concrete case that §4 generalizes into one `CredentialPool` per harness; they are kept here because
this binding is where every one of them was learned.

| Seam concern | Mechanic | The trap it encodes |
|---|---|---|
| credential pool | A shared pool serves mints through a local proxy; each account contributes one mint; per-profile primaries hold their own lineage. Rotation happens in the pool, not by copying files. | "Tokens are minted, never copied." |
| rotation | Credentials are read **at spawn**; a rotated credential reaches a running lane only via respawn. | Matches D13 exactly: active-pointer changes affect future attempts only. A live credential swap under a running attempt would break the immutable manifest. |
| exhaustion | Pool exhaustion presents as a non-retryable 401 on the first API call, with a *separate liveness probe still reporting the substrate alive* — probe path and pool path differ. | A sentinel said `codex=alive` while every reviewer seat was dying; two review turns were lost. `liveness` must report the pool fact, not the substrate fact, when the two disagree. |
| credit exhaustion | An OpenRouter-routed model can answer 402 on its first call after working all morning. | Money is a liveness condition. `dead_auth` covers revoked, capped, and unfunded alike, because they are indistinguishable from the seat's side and identical in consequence. |
| flap policy | A substrate that flips alive is not usable until it holds a full sentinel cycle; briefs are staged and nothing launches during the verification window. | Two flips in one morning; the second lasted two sweeps. Zero lanes were half-started because the bar was enforced. |

### 3.4 The later wave — stubs that prove the abstraction holds

The operator named openclaw, qwen code, zcode, and deepseek. Classifying them honestly is itself the
test: two are harnesses, one is a harness whose route is a gateway, and one is a model that only
looks like a harness because it is spoken of alongside them.

| Candidate | Class | `spawn` | serving-truth source | credential shape | Notes |
|---|---|---|---|---|---|
| `openclaw` | Harness, gateway-routed | Join/invite → approval → **device pairing** → gateway run over ws/wss | Gateway run events | Two planes: gateway auth token *and* a persisted device key; ctower approval does not confer device approval | Preflight assertions (adapter type, non-placeholder token length, device key present, device auth **not** disabled) are the readiness proof; a successful invite is not readiness |
| `qwen-code` | Harness (INV-77 baseline value) | CLI/TUI spawn under the Supervisor Adapter | TBD per binding; declare it or return `unknown` | Weekly-plan quota with a known reset time | Already a legal harness value today; used on judgment lanes when the codex pool is dry |
| `zcode` | Harness, unproven here | TBD | TBD | TBD | No live evidence on this fleet. It enters as a stub row and stays a stub until a real binding is written; a table row is not an adapter |
| `deepseek` | **Model, not a harness** | n/a — reached as a model through a hermes profile | Gateway/provider log of the routing profile | Provider credits (402 is its exhaustion mode) | The clearest proof the abstraction holds: it needs *no* new adapter, only a profile. If a design cannot say "this one is not a harness", it will grow one adapter per model name |

Two of the four therefore need no new adapter at all, and the seam says so before anyone writes one.
That is the abstraction working. What the later wave does need is the `HarnessSpec` capability
declaration to be honest: `qwen-code` and `zcode` declare their liveness evidence sources or their
`liveness` returns `unknown` by name — never a guess.

---

## 4. The per-harness credentials pool

**Scope addition, operator via director, 2026-08-17 18:04Z:** create and maintain a pool per harness,
track usage limits, rotate automatically. Every constraint below was paid for by an incident today or
this week; they are written as requirements, not as background.

### 4.1 It is a sibling Interface, not a sixth verb

The pool must **not** become a method on the adapter. If each binding owns its own rotation policy,
the result is what exists today: three hand-rolled pools with three different cap semantics —
`tools/codex-pool` (a JSON store with a five-hour cooldown, `rotate`/`cap`/`next`, swapping the file
vanilla codex reads), `tools/claude-pool` (slot directories with `meta.json` cap marks and a
write-back-before-swap rule), and the hermes forge pool (one shared pool of mints served through a
local proxy, rotation happening inside the proxy) — plus a fourth class with no pool at all: raw
provider keys (openrouter, z.ai, the Alibaba token plan) held as single env values with nothing
tracking their limits.

So the shape is one `CredentialPool` Interface with one **pool per harness**, resolved at `spawn` and
consumed by the binding:

```
CredentialPool(harness_ref)
  entries: [PoolEntry]                # references + labels + lineage. NEVER values.
  select(model_ref, tier) -> PoolEntry | PoolExhausted
  observe(entry, observation)         # append-only: what the substrate actually answered
  status() -> PoolStatus              # per-entry windows, reset times, unknowns
```

A `PoolEntry` is a credential **reference** with a label, its lineage (which account minted it, when,
and which profile or proxy owns it), and its per-model windows. No pool surface, log, status file, or
error may contain a credential value — today's tools already hold this line ("never prints tokens;
only labels, cooldown, status") and the seam inherits it, matching the repository rule that secrets
are references and never values.

Pool *membership* is operator-owned: minting an entry is a sign-in ceremony a human performs, and
"logging in does not add quota — capped accounts stay capped until their reset". The adapter selects,
observes, and reports; it never creates an entry, and it never treats a credential it can reach as a
credential it is entitled to.

### 4.2 Usage and limit tracking

Capacity is tracked per **(entry × model or tier) window**, not per account, and each window carries
its own state and reset time. The most mature existing model already does this — Claude capacity is
computed per tracked model as an exhausted window with a `reset_at` and a rotation trigger — and the
seam generalizes that shape rather than the binary `alive|capped` the fleet sentinel writes.

| Window state | Meaning | Selectable? |
|---|---|---|
| `available` | Observed serving within the window | Yes |
| `exhausted(reset_at)` | Cap observed, reset time known | No, until `reset_at` |
| `exhausted(reset_unknown)` | Cap observed, reset time not known | **No** |
| `unfunded` | Credit/billing refusal (HTTP 402) | No, until an operator refill |
| `needs_login` | Refresh chain dead or revoked | No, until a mint ceremony |
| `unknown` | No trustworthy observation | **No** |

Two rows carry the whole lesson. **An unknown reset is not availability.** The live Claude pool today
holds a slot marked `capped_until: "unknown"` with a `capped_marked_at` stamp, and the sentinel's
availability count treats an unknown reset as alive — a credential explicitly marked capped renders
as healthy, which is the same failure class as a cap menu matching the working pattern. **And
`unknown` is not `available`.** A pool that cannot observe a window says so; it does not default
toward optimism, because every default-toward-optimism in this system has eventually dispatched work
into a dead substrate.

Consumption is observed, never predicted. Where a substrate reports usage against a window
(percentage, tokens, requests), the pool records it; where it does not, exhaustion is learned from
the refusal the substrate actually returned. A pool never estimates that an entry is *probably* fine.

### 4.3 Rotation

- **Write-back before swap, always.** OAuth refresh tokens rotate as they are used, so a stored
  snapshot of an account goes stale the moment that account is live. Every rotation first saves the
  live credential back into its own slot, then swaps the next one in. Skipping this is what killed
  our codex snapshots with `refresh_token_reused`, and it is the single most expensive rotation bug
  available.
- **Minted, never copied.** A copied refresh chain self-revokes; each account contributes its own
  mint to the pool and each profile holds its own lineage. Rotation happens *inside* the pool, not by
  copying credential files between profiles — the raw-copy path died twice in one night from the
  single-use-refresh dual-copy conflict.
- **One live holder per entry**, enforced by the supervised-refresh lock the hermes profiles already
  carry. Two concurrent holders of a single-use refresh chain is the same bug wearing a different hat.
- **Rotation reaches a running attempt only through a respawn.** Credentials are read at spawn; an
  attempt's credential reference is part of its immutable pinned composition, so a rotation changes
  the *next* attempt and never mutates a live one. This is D13's active-pointer rule applied to
  credentials, and it is why "rotate, then respawn the capped seats" is the correct order rather than
  an inconvenience.
- **Automatic where it is mechanical, ceremonial where it is human.** Selecting a healthy entry,
  marking an observed cap, and rotating to the next available entry are automatic. Minting a new
  entry, refilling credits, and raising a plan are operator ceremonies the pool can only *request* —
  by surfacing the exact refusal and the earliest known reset.

### 4.4 Cap-aware routing

`select(model_ref, tier)` returns an entry whose window for that exact model is `available`. It never
substitutes a different model to find an available credential: model policy belongs to profiles,
ladders, and operator rulings (§2), and a pool that silently reroutes a judgment lane to whatever
happened to be funded would defeat the zero-tolerance rule judgment lanes already carry.

**Flap discipline is part of selection.** A window that flips from exhausted to available is not
selectable until it holds for a full observation cycle. This is not caution for its own sake: z.ai
flipped alive twice in one morning and the second flip lasted exactly two sweeps, and because the
hold-one-cycle bar was enforced, zero lanes were half-started — briefs were staged and nothing
launched. A pool that routes on the first good news manufactures precisely the half-dead lanes the
rest of this design spends its length detecting.

### 4.5 Fail-loud exhaustion, with the exact error surfaced

When no entry is selectable, `spawn` performs **zero dispatch** and refuses `credential-pool-exhausted`
carrying: the harness, the requested model/tier, the exact substrate refusal string and HTTP status
observed, the per-entry window states, the earliest known `reset_at` (or an explicit unknown), and
what would clear it (mint, refill, wait). It never downgrades to another model, never retries into
another family, never returns a receipt, and never lets the lane render as idle.

The incidents this is written from, in one line each:

| Incident | What the pool must do differently |
|---|---|
| Codex pool exhausted 04:33Z: `credential pool: no available entries` → non-retryable 401 ×13; two review turns died mid-turn | Refuse at selection with that exact string, before dispatch — not thirteen times at the API |
| Deepseek/openrouter 402 mid-review: the seat died on its *first* API call after three good verdicts that morning | `unfunded` is a first-class window state; money is a liveness condition, and a funded-this-morning entry proves nothing now |
| Qwen weekly-plan caps | Windows carry plan periods with known resets; a weekly reset is a scheduled return to `available`, not a surprise |
| z.ai flaps | Hold-one-cycle before an entry becomes selectable again (§4.4) |
| Claude slot marked capped with `capped_until: "unknown"` | Unknown reset is not availability (§4.2) |

### 4.6 The probe must draw from the pool it reports on

This is the requirement the operator singled out, and today's state proves why. The fleet sentinel's
codex value is not a probe at all: it reads a human-marked state file and **defaults to `alive`** when
that file is absent, because OAuth quota is not cheaply probe-able without burning a turn. So at
04:30Z the sentinel reported `codex=alive` while three minutes later every reviewer seat took a
non-retryable 401 from an empty pool — and `state/capacity.json` still carries `codex: alive` on an
813-sweep streak while the pool has been dry all day.

The requirement: **a pool's reported health is an observation drawn from the same pool entries it
reports on.** A probe that authenticates by a different credential path than the one seats will use
is reporting on a different thing and must be labelled as such; a constant, a default, or a
human-marked file is not an observation and reports `unknown`, never `available`. Where a real probe
would cost a turn, the honest answer is `unknown` plus the last real observation's age — the pool
learns from the refusals seats actually receive (`observe()`), which costs nothing and is the only
evidence that is never stale in the wrong direction.

The same rule already exists one layer up in this design for models (a source that proves only the
request is a conflict, never truth) and for liveness (`substrate-unobservable:<probe>` rather than a
guess). Credentials get it too, for the same reason: **an availability signal that cannot fail is not
a signal.**

---

## 5. Draft acceptance criteria for T0 (freezable)

Fifteen: twelve for the seam, then three for the credentials pool of §4 (`AC-HAD-13..15`, added by
the 2026-08-17 18:04Z scope addition). Every one is falsifiable by a fixture, and no criterion is
satisfiable by a screenshot or a seat's self-report. Draft ids `AC-HAD-*` are placeholders: the spec
lane mints final ids and **must add a matching row to the evidence-manifest fixture**, or the release
gate fails late. If the frozen set must stay within the brief's original 8–12, the pool rows are the
ones to fold into 06 and 11 rather than the ones to drop — the pool is now scope, not commentary.

| Draft id | Criterion | Evidence |
|---|---|---|
| AC-HAD-01 | The public Seam publishes only when two real bindings (`claude-code`, `hermes`) plus one deterministic fault-injection fake pass one shared conformance suite. The fake injects unacknowledged dispatch, a queued/collapsed-paste composer, a cap menu, context saturation, silent model substitution, dead auth, and pane loss. A publication attempt with one real binding fails closed. | Conformance run across three implementations; injected-fault matrix; publication refusal fixture |
| AC-HAD-02 | `spawn` returns a receipt only after the binding's declared ACK predicate is observed. A queued-composer fixture and a collapsed-paste fixture each return `harness-dispatch-unacknowledged` with zero session-start fact, zero assignment stamp, and zero evidence row. | Per-binding composer fixtures; zero-mutation ledger assertion; ACK-predicate declaration in each `HarnessSpec` |
| AC-HAD-03 | `liveness` reports `served_model` with its per-binding evidence source. A fixture whose launch/requested model differs from the served model appends one `model_changed` observation and overwrites no dispatch stamp; a footer that proves only the request is recorded as a conflict, never as serving truth; an unreadable substrate returns `substrate-unobservable:<probe>` and surfaces `STATE_UNKNOWN`; a seat self-report satisfies neither and refuses by name. | Three-source matrix (gateway log, transcript, launch argv); substitution/conflict/unknown fixtures; self-report refusal |
| AC-HAD-04 | Cap and saturation are classified before any working marker and win over it. A pane at or past the declared window percentage is `saturated`; a limit/upgrade/out-of-credits pane is `capped`; both count as not working while a spinner or timer advances. A healthy large-window lane at the same absolute token count is not flagged. Each binding's classifier is proven against captured real substrate output, and a coverage-style `95%` line in scrolled output does not trip it. | Captured-footer corpus per binding; percentage-vs-absolute counter-fixtures; precedence assertions; false-positive corpus |
| AC-HAD-05 | Input delivered into a `working` lane requires the declared interrupt capability; without it the call returns unsupported and delivers nothing. Steer counts as acknowledged only when the harness returns the durable command ID. | Mid-turn steer refusal fixture; ACK-only-on-command-id assertion; capability-absent path |
| AC-HAD-06 | Every `writeback` fact attributes to one seat's own project-seat credential and resolves exactly one Actor. Facts outside `capture`/`transition`/`evidence` refuse by name with zero mutation; a Workflow stage change is emitted only as a request and its refusal is reported verbatim; an adapter presented with an operator or commander credential refuses rather than using it; a foreign project key returns `project-scope-denied` with zero disclosure. | Scope matrix over the three scopes; transition-request-not-transition trace; operator-credential refusal; foreign-project refusal with zero rows |
| AC-HAD-07 | `collect` derives artifacts from committed refs and durable records only. An uncommitted worktree returns `checkpoint-uncollectable` naming the dirty paths; no terminal capture, pane text, or session existence can fill an evidence slot; a run whose seat wrote no status artifact still yields a complete artifact set from its pushed branch. | Dirty-tree refusal fixture; evidence-slot inventory proving no capture-sourced satisfier; no-status-file collection transcript |
| AC-HAD-08 | A `saturated` or `capped` liveness fact triggers `teardown(checkpoint)`: work in progress is committed and pushed and a handoff carrying done / in progress / not started / next three steps is written before the lane stops. A `park` carries a stated basis and an explicit expiry, re-proves its basis on each evaluation, and fails loud on expiry or when a wake condition turns true. | Saturation-to-checkpoint trace; handoff-section assertion; park expiry and basis-broken fixtures |
| AC-HAD-09 | `teardown(reap)` refuses while sole work is unpushed and refuses a `dead_auth` lane, which is preserved for resume. A stalled lane is offered one resume input before any replacement is proposed. After pane, tmux-server, or host loss, the adapter reconstructs from ctower state, rejects old epochs, and never treats pane disappearance as success. | Sole-work refusal; dead-auth preservation; nudge-before-respawn ordering; kill/restart reconstruction with epoch rejection |
| AC-HAD-10 | An unknown harness value is carried byte-for-byte through spawn, liveness, and writeback, displayed as observed, included in equality and cross-checks, and never normalized, downgraded, or collapsed. No kernel, reporter, projection, CLI, or Board path imports or parses a harness-private transcript or session format; harness-private observation exists only inside a binding and crosses the seam as typed facts. | Unknown-harness carry/display fixture; import-boundary inventory; per-binding private-parser containment check |
| AC-HAD-11 | Composition fails closed. An unknown, incompatible, revoked, or digest-mismatched `HarnessSpec` performs zero dispatch with no fallback to a generic process. Credential rotation affects future attempts only: a rotation during a live attempt changes nothing about that attempt and is visible as a pinned difference on the next one. | Four fail-closed component fixtures; live-rotation no-op proof; manifest digest comparison across attempts |
| AC-HAD-12 | Every `spawn` obtains and enforces a current versioned CommandGuard decision for the exact normalized execution plan at its final pre-dispatch boundary. `block` and `needs_operator` dispatch nothing; a receipt that cannot be durably recorded before dispatch yields zero dispatch; a changed plan, expired or replayed grant, or direct bypass fails closed. | Guard invocation trace per binding; zero-execution-on-block assertion; receipt-first ordering; replay/expiry/bypass refusals |
| AC-HAD-13 | Each harness has exactly one pool whose entries are credential **references** with per-(entry × model) windows. `exhausted` with an unknown reset, `unknown`, `needs_login`, and `unfunded` are all non-selectable; only an observed `available` window is selectable. No pool surface, status output, log line, error body, or refusal contains a credential value. A fixture entry marked capped with an unknown reset is never selected and never reported as available. | Window-state matrix over the six states; unknown-reset non-selection fixture; credential-value scan across pool status, logs, refusals, and telemetry; one-pool-per-harness registry assertion |
| AC-HAD-14 | Rotation writes the live credential back to its own entry **before** swapping the next one in, and a refresh-token-reuse fixture proves the old ordering fails while the new one survives. Entries are minted, never copied: a duplicated refresh chain is refused rather than stored. Exactly one live holder per entry is enforced. A rotation during a live attempt changes nothing about that attempt; the new credential reference appears only in the next attempt's pinned composition. | Write-back-before-swap ordering trace; `refresh_token_reused` regression fixture; duplicate-chain refusal; concurrent-holder lock test; live-rotation no-op plus next-attempt pin diff |
| AC-HAD-15 | With no selectable entry, `spawn` performs zero dispatch and refuses `credential-pool-exhausted` carrying the harness, requested model/tier, the exact observed substrate refusal string and HTTP status, per-entry window states, the earliest known reset or an explicit unknown, and the clearing action. No model downgrade, cross-family retry, receipt, or idle-looking lane results. Pool health is reported only from observations drawn from that pool's own entries: a constant, a default, or a human-marked file reports `unknown`, never `available`, and a window returning to `available` is not selectable until it holds a full observation cycle. | Exhaustion refusal body assertions for 401 pool-empty, 402 unfunded, and 429 cap; zero-dispatch and no-downgrade proofs; default-alive-constant rejected-as-evidence fixture; probe-credential-identity check; flap hold-one-cycle fixture |

---

## 6. Is Paperclip's `PLUGIN_SPEC` adoptable as our adapter packaging?

**No — and their own specification is the reason.** `PLUGIN_SPEC.md` defines two extension classes
and puts agent adapters firmly in the *other* one. Platform Modules are "trusted, in-process,
host-integrated, low-level", registered through explicit registries (`registerAgentAdapter()`,
`registerStorageProvider()`, …), and the spec states plainly that platform modules are "the right
place for new agent adapter packages". Plugins are the capability-gated, out-of-process,
npm-installed, operator-installable class — connectors, dashboards, sync integrations. Adopting the
plugin contract for harness adapters would misclassify them by the source document's own taxonomy.

Three ctower-specific reasons make the answer firmer than a taxonomy argument:

1. **Authority.** A harness adapter dispatches commands and writes back as a seat. D11 already
   restricts any future executable extension to invocation-scoped identity with no database
   credential, no kernel-table access, no host socket, no standing secret, and no canonical mutation
   path — which is *less* than a harness adapter needs, and correctly so. The right answer is not to
   loosen the extension host; it is to keep adapters inside the trusted control plane where INV-58's
   guard and INV-69's grants already bind them.
2. **Runtime.** Their install model is npm-into-an-instance-directory with a plugin worker process
   and a writable local package tree, which their own caveats say is not yet safe for multi-instance
   deployment. Ctower's hard boundary is a Python trusted control plane with TypeScript in the
   browser only. Adopting the packaging means adopting a second execution authority to run it.
3. **Earning order.** D10/D11 require two real Adapters plus an unchanged conformance suite before a
   public Seam exists. A plugin framework is the shape you build *after* that, if a third-party ever
   needs to ship an adapter you did not write. Building the framework first is precisely the
   speculative abstraction the engineering constitution forbids.

**Selectively adoptable — four concrete imports:**

- **Manifest-as-data, parsed without executing package code**, with a rejected-on-incompatible API
  version and a declared, operator-visible capability list. This is already D11's shape; Paperclip's
  version is a good concrete model for the `HarnessSpec` capability block, including the explicit
  *forbidden* capability list, which is more useful than an allowlist alone.
- **Deterministic load order with namespaced contributions and no core-route override.** Ctower's
  analogue: bindings are additive, never shadow a kernel path, and a duplicate declaration inside one
  binding is rejected at registration rather than resolved at runtime.
- **The no-remote-git cross-run persistence contract** from `packages/adapters/AUTHORING.md`: the
  local execution workspace is the only cross-run persistence boundary, no adapter may `git push`
  from runtime code, a failed sync-back is a run-level error that gates dependent work, and a
  legitimate exception is an explicit annotated opt-in caught by a static check. Ctower's boundary is
  the durable record rather than a worktree, and our checkpoint order deliberately *does* push — so
  the import is the discipline, not the rule: a push from adapter code is an explicitly authorized,
  named, statically-checked path, never an incidental one.
- **Two-key separation, from `HERMES_GATEWAY_ONBOARDING.md`:** the gateway key authenticating
  control-plane→harness traffic is a different credential from the claimed key authenticating
  harness→control-plane traffic, and the guide states outright that reusing one as the other is
  wrong. That is our credential-per-seat writeback lesson arrived at independently, and it is worth
  citing as convergent evidence. `OPENCLAW_ONBOARDING.md` adds the second half: an adapter can be
  fully approved on the control-plane side and still not runnable, because a *second* approval plane
  (device pairing) exists inside the harness. Readiness is proven by preflight assertions, never
  inferred from a successful invite.

---

## 7. Open questions the plan stage must close

1. **INV-77 versus per-binding transcript reads.** INV-77 bars *reporters* from deriving facts from
   harness-specific session internals, yet the only serving-truth source for `claude-code` panes is
   the session transcript. The design's position is that an adapter is the one place harness-private
   observation is permitted, because it exports only typed facts and no harness type crosses the
   seam — but that reading needs to be either confirmed in the spec lane or carried as an
   append-only decision. It is load-bearing for AC-HAD-03 and AC-HAD-10 and should not be assumed.
2. **Which CT rows this becomes.** The natural home is CT-I2-003/CT-I2-004 (effective manifests, the
   first real Harness compositions, CommandGuard), which are I2 work. If any part of this seam is
   needed before I2 activation, that resequencing is an operator/commander scope decision, not a
   lane's.
3. **Refusal-name minting.** Five candidate names above (four seam, plus
   `credential-pool-exhausted`) must be checked against the existing vocabulary before freeze; name
   overlap was already a P1 finding on an adjacent spec.
4. **Saturation threshold as policy, not constant.** The fleet uses 90% of the declared window. Where
   that number lives — Execution Policy, `HarnessSpec`, or both — is a plan-stage decision; this
   design only requires that it be declared and per-binding proven, never hard-coded in a monitor.
5. **Where the credentials pool lives, and who may read it.** §4 fixes the pool's *behaviour* but not
   its home. Secrets are references and never values here, and secret truth is kernel-owned, so the
   plausible shapes are a Catalog/secret-broker-backed pool inside the trusted control plane versus a
   thinner pool that only records window observations and defers every credential reference to the
   existing secret boundary. That choice decides whether an adapter can call `select()` at all or
   receives an already-resolved reference from Runtime, and it should be settled before AC-HAD-13's
   credential-value scan is frozen — the scan's boundary is only meaningful once the boundary is.
6. **Whether pool observations are Record facts.** A pool that learns from real refusals produces
   exactly the kind of durable operational history this system records elsewhere (append-only, typed,
   attributable). Making them Record facts buys audit and cross-seat learning; keeping them local
   state keeps the pool out of the kernel's write path. The design deliberately does not decide it,
   but AC-HAD-15's "earliest known reset" is only trustworthy if some store outlives one runner.

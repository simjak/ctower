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
in §4, carried by frozen criteria `AC-HAD-10..12`. That section is written against four operator-supplied
inputs rather than from first principles: the Hermes credential-pools and fallback-providers docs
(preserved at mission-control `board/assets/hermes-credential-pools-doc.md`), the operational law in
mission-control `playbooks/codex-hermes-auth-runbook.md`, the operator's own plan weights and reset
clocks, and the live state of this box's own pools.

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
today's state. Where a harness already ships a pool engine, that Interface **configures and observes
it rather than replacing it**: ctower's contribution is registry, ledger, policy, configuration, and
observation, not a second rotation policy competing with a working one.

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

### 3.0 The binding template

Every binding fills the same template before implementation, and the credentials half of it is a
**capability survey** — because the one thing that varies most between harnesses is not how they are
launched but how much resilience they already have. A binding that has not answered these ten
questions cannot be implemented, because the answers decide whether ctower configures a layer or
provides it (§4.1).

| # | Survey question | Why the answer changes the code |
|---|---|---|
| a | **Native credential pool?** | Present → configure and observe. Absent → ctower's registry plus the existing tool family operates it |
| b | **Native fallback?** | Absent means there is no in-session ladder at all, and failover becomes a new attempt (§4.1.1) |
| c | **Config surface — and is it authored-config-only?** | A surface an environment variable can override is not a pinned composition (§4.4.1) |
| d | **Identity proof** — decodable claim, account file, or nothing? | Decides whether the registry can key on identity or must degrade to a declared mapping (§4.1.3) |
| e | **Reset / window semantics** | Rolling block, weekly plan, prepaid balance, or unknown — decides what `limits()` can honestly report |
| f | **Cache semantics on rotation** | What a rotation costs, and which invalidation hook must complete before an observation counts |
| g | **Subagent credential inheritance** | Whether delegation is covered by the parent's ladder or needs its own acquisition |
| h | **Egress path — shared across entries, or per entry?** | A shared egress means a CDN challenge hits every entry at once (§4.2): correlated failure is then evidence about the path, not about N credentials |
| i | **Probe target — which product, endpoint, and model, and is it the one seats run?** | A probe aimed at a model no seat uses reports on something else; this is live on this fleet today (§4.6) |
| j | **Credit weights — per model, per direction, and where published?** | Tokens are not the billing unit; without the weight table the ledger cannot say which model drained a plan (§4.4.3) |

The rest of the template is the seam-verb mapping, the liveness evidence sources, the ACK predicate,
and the declared probe shape — each of which appears in the per-binding tables below.

### 3.1 `claude-code` — mechanics from `tools/claude-crew`

| Seam verb | Harness mechanic | The trap it encodes |
|---|---|---|
| `spawn` | `bin/mux spawn` a wrapper script that `cd`s to the worktree and `exec`s the CLI with an explicit model; wait for TUI readiness; deliver the brief as a literal `send-keys` followed by a **separate** `Enter`; verify the composer cleared. | `mux send` does not work on this TUI. The wrapper is also a policy blind spot: a launcher that spawns through a temp script hides the binary's name from any check that inspects `argv[0]`, so every spawn path needs its own refusal rather than relying on a shared one. |
| `liveness` | `esc to interrupt` / running-shell markers for working; limit-menu and "reached your … limit" text for `capped`; context-bar percentage for `saturated`; pane-hash delta as the marker-free fallback. | The limit menu matched the generic working pattern for hours. "N shells still running" with no esc-marker is working, not idle: the turn ended but the gate run continues. |
| served model | Session transcript JSONL under the pane's cwd, most recent real assistant turn, `<synthetic>` turns skipped, stale beyond one hour = `unknown`. | These panes carry **no** parseable model footer; treating absence as agreement made an entire harness family read `unknown` forever. A stale transcript in a shared worktree once reported a dead session's model as live truth. |
| `collect` | Worktree branch + status artifact; `just check` / `just verify` closing lines as gate output. | The status file is optional; the pushed branch is not. |
| credentials | **Survey: (a) no native pool · (b) no native fallback · (c) config home per install · (d) account file, no decodable pool claim · (e) 5-hour blocks with reset times · (f) cached per config home, invalidated by respawn · (g) no separate subagent credentials.** One account per install (`~/.claude/.credentials.json` OAuth, or an API-key variable), while the operator holds three accounts — so ctower operates **topology A: per-seat credential isolation**, one config home per account, rotation by write-back-then-swap, mint-never-copy applying to OAuth here exactly as it does for codex. | This is the harness where ctower must *provide* both layers, and where the absence of in-session fallback has a structural consequence (§4.1.1): a cross-provider failover is a respawn, not a rung. The isolated-config-home ceremony is already how a new account is seeded without disturbing the live one. |
| `writeback` | Seat credential through the generated client. | Same as every binding — no exceptions for the harness the commander happens to run on. |
| `teardown` | Checkpoint order on saturation; pane preserved on `dead_auth`. | Claude cap text differs from every other harness's and was missing from the classifier twice. |

### 3.2 `hermes` — profiles, ladders, and gateway truth

| Seam verb | Harness mechanic | The trap it encodes |
|---|---|---|
| `spawn` | `bin/mux spawn` a wrapper that execs `hermes` with `HERMES_HOME` pointing at a **profile directory**; model and reasoning effort come from that profile's config, never from the launcher's arguments. | Model-in-the-launcher is how a launcher gets named after a model and a phantom harness category is born. The profile is the pinned component; the launcher is not. |
| credentials | Each profile owns its own credential lineage (`auth.json` + `auth.lock`); tokens are minted per profile, never copied. **Hermes ships the pool engine** — per-provider pools, rotation strategies, error-class recovery, per-task leasing — so this binding configures and observes it (§4) and implements none of it. | A copied refresh chain self-revokes — the single-use-refresh dual-copy conflict killed the raw path twice in one night. Account pooling as a *launcher argument* is retired; it lives in the profile or nowhere. Building a second pool over a working one would be the same category error one layer down. |
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
the runtime/profile reference that carries credential lineage.

That distinction turns out to be load-bearing for credentials too, and it cuts both ways:

- **Codex as a runtime under hermes** — today's fleet route — has its subscriptions as OAuth
  device-code entries inside hermes's own `openai-codex` pool. Identical pool model, no special case:
  configure and observe.
- **Codex as a direct CLI harness** has a **single active account per `~/.codex` home and no native
  pool or fallback at all**. Survey: (a) none · (b) none · (c) an account file, not authored config ·
  (d) decodable identity claim (which is why labels can be checked against it) · (e) ~5-hour cooldown
  model · (f) proxy/home caching that must be invalidated after any token change · (g) no separate
  subagent credentials. Here ctower *provides* the layer — and the mechanism already exists as the
  fleet's tool family (§4.7), so the binding wraps `codex-auth-all`, `codex-grant-ceremony`,
  `codex-rotate-fallback` with its generation guard, and `codex-pool`, rather than writing a fifth
  rotation implementation. Three accounts, single-use refresh chains binding everything.

The mechanics below are the concrete case §4 generalizes; they are kept here because this binding is
where every one of them was learned.

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

**And each of them owes the §3.0 credentials survey before implementation, not after.** Their native
pool, native fallback, config surface, identity proof, reset semantics, cache semantics, subagent
inheritance, egress topology, probe target, and credit weights are all currently unknown to us, and §4.1's resolution rule cannot be applied to an
unknown: the choice between *configure* and *provide* is exactly what the survey decides. The
`deepseek` row shows why the survey is cheap insurance — answering (a) and (b) for it reveals that it
is served through a profile that already has both layers, so the correct amount of adapter work is
zero. An unanswered survey is the only thing here that can produce a duplicate rotation policy.

---

## 4. The per-harness credentials pool

**Scope addition, operator via director, 2026-08-17 18:04Z:** create and maintain a pool per harness,
track usage limits, rotate automatically. **T4 design input, operator, 2026-08-17 ~18:4xZ** (doc
preserved at mission-control `board/assets/hermes-credential-pools-doc.md`): Hermes already *ships*
the pool engine, so for the hermes binding ctower does not build pooling. Every constraint below was
paid for by an incident today or this week; they are written as requirements, not as background.

### 4.1 Capability-matrix-driven: configure where the layer exists, provide where it does not

The decisive fact is that **resilience is not uniformly missing, and not uniformly present.** Hermes
ships a per-provider credential pool with four rotation strategies (`fill_first`, `round_robin`,
`least_used`, `random`), error-class recovery, a pools-first-then-fallback-providers layering,
reference-only borrowed secrets, per-task credential leasing for subagents, and thread safety — with
strategies in `config.yaml` and live state in `~/.hermes/auth.json`. The Claude Code and Codex CLIs
ship neither pooling nor fallback and hold one account per config home.

So the resolution rule is per **layer**, per harness — read from the §3.0 survey, not from the
harness's name:

> **Where the harness has the layer, the adapter configures and observes it.
> Where it lacks the layer, the adapter provides it through ctower's registry and the existing tool
> family. Never both.**

"Never both" is the load-bearing half. Two rotation policies over one credential set do not add
redundancy; they add a race over single-use refresh chains, which is the failure that revokes
everything at once.

| Harness | Native pool | Native fallback | Identity proof | Reset semantics | Ctower's role |
|---|---|---|---|---|---|
| `hermes` | **Yes** — per-provider, 4 strategies | **Yes** — ordered `fallback_providers` + aux chains | Decodable claim per entry | Per-provider `reset_at`, authoritative | Configure + observe both layers |
| `codex` *via hermes* | Yes (inside hermes's `openai-codex` pool) | Yes (inherited) | Decodable claim | ~5h cooldown + provider reset | Configure + observe |
| `codex` *direct CLI* | **No** — one active account per home | **No** | Decodable claim | ~5h cooldown model | **Provide**, wrapping the tool family (§4.7) |
| `claude-code` | **No** — one account per install | **No** — no in-session ladder | Account file; no pool claim | **5-hour blocks** with reset times | **Provide**: topology A, per-seat credential isolation |
| `openclaw` · `qwen-code` · `zcode` · `deepseek-harness` | **Survey first** | **Survey first** | **Survey first** | **Survey first** | Undecidable until §3.0 (a)–(g) are answered |

The last row is a refusal, not a gap: the role cannot be chosen before the survey is filled, and
guessing it is how a second rotation policy gets built over a working one. A binding whose survey is
unanswered does not enter the conformance suite.

#### 4.1.1 Where there is no in-session fallback, failover is a new attempt

For `claude-code` — and any harness answering "no" to survey question (b) — cross-provider failover
cannot be a rung inside a running session, because no such rung exists. It is the **adapter's** job,
and it takes the only shape available: checkpoint the lane, tear it down, and respawn the seat on
another harness or account.

That is architecturally cleaner than it first sounds, and it costs nothing extra to specify, because
the seam already has every piece: `teardown(checkpoint)` preserves the work (§1.5), and the respawn
produces a **new attempt with its own immutable pinned composition** — new harness, new credential
reference, new manifest digest. What would be a hidden mid-session model swap on a fallback-capable
harness is, here, a visible attempt boundary in the ledger. The cost is the full context re-read the
new attempt pays, which §4.4.2 already meters, plus the checkpoint's own cost.

#### 4.1.2 The Interface: five verbs, one deliberately absent, one completion condition

The pool remains a **sibling Interface resolved at `spawn`, never a sixth adapter verb** (§0). Its five
verbs are the operator's:

```
CredentialPool(harness_ref)                    # one pool per harness
  acquire(model_ref, tier) -> Lease | PoolExhausted   # which credential this attempt runs on
  meter(lease, observation)                           # usage, cost, and cache-reset events
  limits(scope) -> [EntryState]                       # auth × quota axes per entry (§4.2)
  rotate(reason) -> RotationEvent | Refusal           # native: request+record · managed: perform
  probe(shape) -> PoolHealth                          # realistic-sized, pool-drawn (§4.6)

  # There is NO copy verb. Deliberately. New credential material enters only through
  # request_mint(identity) -> OperatorCeremony, which the pool can ask for and never perform.
```

**The absent verb is a design element.** OAuth refresh tokens here are single-use chains, and
installing a copied auth file — from another profile, another instance, or a stale snapshot — replays
a consumed token and the provider revokes *the whole chain*: every grant derived from that login dies
at once. That is not a rule an implementer should have to remember, so the Interface cannot express
it. Every entry is its own device-flow mint; rotation switches *which entry an attempt rides*, never
which file sits where.

**`rotate` is incomplete until its cache-invalidation hook completes.** Pool proxies cache state in
memory, so a rotation that changes tokens without invalidating the cache leaves the old grant live: a
stale proxy translated `usage_limit_reached` into `No available credentials` for an entire night, and
cached state can burn a fresh single-use refresh token. The `HarnessSpec` therefore declares the
invalidation hook for its pool (for the hermes forge pool: restarting the pool-proxy service), and a
`RotationEvent` whose hook has not completed is `rotation-incomplete` — never a success, and never a
basis for marking any entry's state.

For a native-engine harness these verbs **configure and observe**: `acquire` resolves which pool entry
the engine will serve this attempt and leases it; `rotate` records the engine's own rotation rather
than performing one; `probe` reads the engine's state. For a managed harness the identical verbs are
implemented by ctower's checkout topology. A binding declares which class it is in its `HarnessSpec`,
and that declaration is the only place the difference appears — no caller branches on harness name.

This split is the abstraction's real test. If the same five verbs cannot express both a shipped engine
and a hand-managed checkout without either leaking into the caller, the abstraction is wrong, and the
fleet has both cases *today* to prove it against.

#### 4.1.3 Ctower's five jobs for a layer the harness already owns

1. **Registry** — which pools exist, and which subscriptions feed them. A subscription is the paying
   thing (a codex account, the z.ai coding plan, the Alibaba token plan, an OpenRouter balance); an
   entry is its credential inside a pool. The mapping subscription → pool → entry is what makes
   "which plan paid for this attempt" answerable, and it is what budgets and hard-stops attach to.
   The live shape to register against is `auth.json`'s `credential_pool.<provider>[]` with its `id`,
   `label`, `auth_type`, `priority`, and `source`, across the providers actually present here:
   `openai-codex`, `zai`, `openrouter`, `alibaba`.
   **The registry also carries each subscription's per-model weight table** — the provider's own
   credit cost per model, per direction. Tokens are not the billing unit and do not answer the
   operator's question; credits are (§4.4.3).
   **The registry key is the credential's own decoded identity claim, never its label.** Labels have
   pointed at the wrong account twice — a `simasjak-gmail` label was actually a jakit.lt mint, and two
   identically-named labels hid two different accounts. So identity (the JWT email claim, decoded from
   the credential itself) is the primary key; `label` is a display attribute with no authority, and
   two entries sharing an identity are one subscription however they are named. A registry keyed on
   labels cannot answer "how many accounts do we actually have", which is the question the pool exists
   to answer.
   **A discovered identity is not an enrolled one.** The codex pool is three operator-confirmed
   accounts (`simonas@jakit.lt`, `simonas@jakitlabs.com`, `simasjak@gmail.com`); a fourth identity was
   found minted in the pool and awaits an operator keep-or-evict decision. `discovered` is therefore a
   first-class registry state that is **never selectable** — auto-adopting a credential because it is
   reachable is the same authority error as an adapter using an operator credential it happens to
   hold (§2).
2. **Ledger** — usage, limits, resets, and rotation events over time, including the cost event of
   §4.3. The engine's `auth.json` carries *current* state and is overwritten as it changes; a ledger
   is what turns that into history, which is the only thing that can answer "how often are we
   rotating, and what is it costing us".
3. **Policy** — budgets, hard-stops, and the *order of the ladder*. The engine decides which entry
   serves a request; ctower decides whether the attempt may run at all against a budget, and which
   providers may be fallen back to in what order (§4.4). Refusal happens before dispatch rather than
   as a discovery from a provider's 402.
4. **Configuration** — rotation strategies and the generated fallback ladder in `config.yaml`;
   credentials added by the harness's own `hermes auth add` device-flow ceremony. Ctower authors
   configuration as revision-pinned data and **generates each profile's chain from the registry**
   (§4.4.1); it never writes `auth.json`. **One writer per file** is the rule that prevents the whole
   copied-credential failure family: the harness owns its auth state, ctower owns its configuration,
   and neither edits the other's file.
5. **Observation** — read `last_status`, `last_status_at`, `last_error_code`, `last_error_reason`,
   `last_error_reset_at`, and `request_count` from each pool entry into the ledger, projected through
   a **strict metadata allowlist**. That last word is load-bearing: OAuth entries in `auth.json` carry
   `access_token` and `refresh_token` fields *adjacent to* the metadata being read, so an observation
   reader that copies the object rather than projecting named fields would move credential values into
   the ledger. Reference-only entries carry `secret_fingerprint` instead of a value — the shape our
   own secrets law already requires, arrived at independently by the engine.

Pool *membership* stays operator-owned in both classes: minting an entry is a sign-in ceremony a human
performs, and "logging in does not add quota — capped accounts stay capped until their reset". Ctower
acquires, meters, and reports; it never creates an entry, and it never treats a credential it can
reach as a credential it is entitled to.

#### 4.1.4 The target topology is authored desired state, and drift is a finding

The registry does not merely describe what exists; it **declares what should exist per profile**, and
the adapter reconciles actual against it. The operator's ruling fixes that desired state:

| Plane | Desired per unit | Yields |
|---|---|---|
| Each hermes profile | **five subscriptions** — three codex accounts (its *own* OAuth mint of each) plus a z.ai key and an Alibaba key | **three provider rungs**: codex primary → glm → qwen, in policy order |
| `claude-code` | **three Claude Code subscriptions** as per-seat credential homes (topology A, §3.1) | one rung per home; failover is a new attempt (§4.1.1) |

**Five subscriptions yielding three rungs is the layer split made arithmetic.** The three codex
accounts are not three rungs — they are one rung with three entries, rotated *within* the provider by
layer 1, while layer 2's ordered chain has three stops. Anyone who models subscriptions and rungs as
the same list gets 5 = 3 and knows something is wrong; the seam gets it right because §4.4 already
separates them.

**Mint-never-copy sets the ceremony's price, and it is not small.** Because each profile needs its
own mint of each account, the cost is *profiles × accounts* interactive device flows — for the
current eight persona profiles and three accounts, **24 sign-ins**, which is exactly what the fleet's
own `tools/codex-auth-all` now computes and sequences in one guided run. The cheap alternative —
mint once, copy the file into eight profiles — is the thing that revokes every grant at once, so the
price is the invariant's cost and not an implementation inefficiency to optimize away later.

**Enactment splits by subscription kind, and the registry carries which:**

| Subscription kind | `enactment` | How it is wired |
|---|---|---|
| Codex accounts (OAuth) | `operator-ceremony` | An interactive device flow per profile per account; ctower can *request* and sequence it, never perform it |
| z.ai, Alibaba (API keys) | `secret-reference` | Wired non-interactively from a secret reference — a reference, never a value, per this repository's standing rule |

That distinction is what makes a drift finding actionable rather than a complaint: a missing z.ai key
is automation's problem, while a missing codex grant is an item on the operator's ceremony list.

**Drift is a derived read, not a sixth verb.** Comparing the desired set to `limits()`'s actual set
yields findings in two directions, and both already have homes in the state model:

- **`missing`** — desired but absent. A finding routed to its enactment path. **Never silence**: an
  absent grant is not an exhausted one, and a topology that is 19 of 24 minted must say so rather
  than report the five gaps as ordinary unavailability.
- **`unregistered`** — present but not desired. This is precisely the fourth codex identity found
  minted in the pool, and it maps to the existing non-selectable `discovered` state pending an
  operator keep-or-evict decision (§4.1.3).

**Enactment is sequenced, because the current shape is mid-migration.** The forge pool and its local
proxy are legacy under this ruling, and the order is fixed by a dependency rather than by preference:
mint the grid, re-point each profile's provider off the proxy, *then* retire the proxy and forge
home. Reversing those steps breaks every profile whose configured provider still resolves to the
proxy — which today includes the engineer profile, whose primary provider is the proxy endpoint. The
registry's reconciliation must therefore express ordering, not just a target set; a desired state
that cannot say "not yet, and here is what must land first" will happily propose a step that breaks
the fleet.

**Weight tables attach per subscription** (§4.4.3), so all five carry their own — the three codex
accounts sharing a plan's weights while z.ai and Alibaba carry their own units. Cost-class routing is
only meaningful once every rung in a generated ladder is priced.

### 4.2 Usage and limit tracking — three axes, never one status

**AUTH ≠ QUOTA ≠ REACH.** This is the invariant that most changes the data shape, so it is modelled
structurally rather than described: every entry carries **three orthogonal states**, not one. A capped
account passes login and refuses work (`usage_limit_reached, plan_type: pro, resets_at …`); a dead
lineage fails login while quota may be untouched; and — discovered live on this fleet tonight — an
entry can have *both* fine and still be unable to reach the provider at all, because the provider's
CDN is bot-challenging our egress. A single `status` column forces those into one value, and every
tool that has flattened them has eventually told someone to run the wrong ceremony.

```
EntryState
  identity: IdentityClaim         # decoded from the credential (§4.1.3), not the label
  auth:  healthy | lineage-dead | chain-burned
  quota: available | capped(reset_at) | capped(reset_unknown) | unfunded | unknown
  reach: ok | edge-challenged | unknown
  windows: {model_ref: quota}     # quota is per (entry × model), not per account
```

| Axis value | Meaning | Clears by |
|---|---|---|
| `auth: healthy` | Login/refresh works | — |
| `auth: lineage-dead` | Per-profile grant expired; the shell may still say "logged in" | Re-mint that profile |
| `auth: chain-burned` | `refresh_token_reused` — a copy replayed a single-use token | Fresh mint, never a copy |
| `quota: available` | Observed serving within the window | — |
| `quota: capped(reset_at)` | Cap observed, provider reset known | Waiting; the provider's `reset_at` overrides any local cooldown |
| `quota: capped(reset_unknown)` | Cap observed, reset unknown | Waiting, with no predictable return |
| `quota: unfunded` | Prepaid balance exhausted (402) | Operator refill |
| `quota: unknown` | No trustworthy observation | A real probe (§4.6) |
| `reach: ok` | The provider's edge answers our egress | — |
| `reach: edge-challenged` | CDN bot-challenge on the path — 403 with a challenge page and a `cf_chl`-style token, **auth and quota both fine** | **Infra-plane action only**: client fingerprint, headers, or egress. Never a mint, rotation, or restart |
| `reach: unknown` | Reachability not observed | A real probe (§4.6) |

An entry is selectable only when **all three** axes are clear. Five consequences follow from the
shape, and are checkable because of it:

- **A reachability fault must never route to a credential ceremony.** `edge-challenged` looks like an
  auth failure at the status-code level — it is a 403 — and a model with one status column classifies
  it as `lineage-dead`, whose action is *re-mint*. That would consume a single-use device flow
  against a perfectly healthy credential and still not work, because nothing about the credential was
  ever wrong. This is the same shape as the runbook's original AUTH≠QUOTA lesson (where a full
  re-grant ceremony was run against what was actually a cap), which is exactly why it is the third
  axis and not a fourth `auth` value.
- **Correlated failure across independent identities is evidence about the path, not the
  credentials.** Entries in one pool typically share an egress, so a challenge hits all of them at
  once. N identities failing simultaneously and identically is a shared-path signal; genuine
  credential faults arrive one identity at a time. The pool should say so rather than reporting N
  broken credentials — and survey question (h) records whether a binding's egress is shared or
  per-entry, which is what makes the inference valid.
- **No ceremony adds quota.** A mint changes only the `auth` axis. If a rotation, ceremony, or reset
  appears to change `quota`, that is a bug in the observer, not a recovery — the fleet has twice run
  a full re-grant ceremony against what was actually a cap.
- **An unknown reset is not availability.** The live Claude pool holds a slot marked
  `capped_until: "unknown"` with a `capped_marked_at` stamp, and the sentinel's availability count
  treats an unknown reset as alive — a credential explicitly marked capped renders as healthy, the
  same failure class as a cap menu matching the working pattern.
- **`unknown` is not `available`.** A pool that cannot observe a state says so; it does not default
  toward optimism, because every default-toward-optimism in this system has eventually dispatched
  work into a dead substrate.

Quota is tracked per **(entry × model) window**, not per account — the shape `_claude_capacity.py`
already computes as an exhausted window with a `reset_at` and a rotation trigger, rather than the
binary `alive|capped` the fleet sentinel writes.

**Reset clocks are per account, and pool status is therefore never a scalar.** The three codex
subscriptions reset at three different times — 2026-08-20 06:29, 2026-08-20 08:00, and 2026-08-22
09:01 — and as of tonight the third is at roughly **99% remaining**. That single fact retires a phrase
this design has been using loosely all evening: the pool was never "dry". It had an exhausted
majority and an almost untouched member, and a status model with one word per substrate cannot say
so. `limits()` therefore returns per-entry rows with their own clocks and never an aggregate verdict,
and `acquire` fails only when **every** entry is unselectable — which is a different and much rarer
condition than the one the fleet paged on this morning.

Consumption is observed, never predicted. Where a substrate reports usage against a window
(percentage, tokens, requests), the pool records it; where it does not, exhaustion is learned from
the refusal the substrate actually returned. A pool never estimates that an entry is *probably* fine.

For a native-engine harness this table is a **projection, not a second source**: `limits()` derives it
from the engine's own per-entry fields — `last_status` (`exhausted` is the value live in this box's
pool files right now), `last_error_code`, `last_error_reason`, `last_error_reset_at`, and
`request_count`. Ctower does not maintain a parallel opinion about whether an entry is capped; it
records what the engine already knows, timestamps it, and keeps the history the engine does not.

### 4.3 Rotation, and what a rotation costs

**For a native-engine harness ctower does not rotate — it records rotations and their cost.** The
engine's recovery is already error-class-aware, and re-implementing it would guarantee two policies
disagreeing under load:

| Observed | Engine behaviour | Ctower's part |
|---|---|---|
| 429 rate-limited | Retry once, then rotate | Meter the retry and the rotation; no second policy |
| 402 unfunded | Rotate immediately, 1h cooldown on the entry | Ledger `unfunded`; escalate the refill as an operator ceremony |
| 401 unauthorized | Refresh, then rotate if the refresh fails | Ledger `needs_login` on refresh failure |
| Provider `reset_at` present | Overrides the local cooldown | Record the provider's reset as authoritative over any inferred one |

**Each rotation resets the provider's prompt cache — one full-price context re-read — and that is a
metered cost event, not a footnote.** It is the design consequence with the sharpest downstream
effect, because it makes rotation *not free* and therefore makes strategy a budget decision:
`fill_first` minimizes cache resets by exhausting one entry before moving on, while `round_robin`,
`least_used`, and `random` spread load and pay a cache reset at every hop. On lanes carrying
200K-token contexts, a strategy chosen for fairness can cost more than the capacity it balances. The
ledger is what makes that visible; without a metered cache-reset event, the expensive strategy and the
cheap one look identical on every dashboard we have.

It also sharpens routing policy: **rotate on exhaustion, not on preference.** A rotation that buys
nothing still costs a full context re-read.

**And never rotate on a reachability fault.** When `reach: edge-challenged`, every entry behind the
same egress is equally unreachable, so rotation cannot help — it merely pays a prompt-cache reset per
attempt while the edge keeps answering 403. A rotation requested against an edge-challenged
classification is refused, not attempted. The correct response is one layer up (cross-provider
fallback, §4.4.4) plus an infra-plane escalation, because a different provider is a different edge
while a different credential is the same one.

For a **managed** harness (`claude-code`), ctower performs the rotation itself and inherits the rules
the fleet already paid for:

- **Write-back before swap, always.** OAuth refresh tokens rotate as they are used, so a stored
  snapshot of an account goes stale the moment that account is live. Every rotation first saves the
  live credential back into its own slot, then swaps the next one in. Skipping this is what killed
  our codex snapshots with `refresh_token_reused`, and it is the single most expensive rotation bug
  available.
- **Minted, never copied** — structurally guaranteed by the absent copy verb (§4.1). The managed
  implementation additionally refuses to install a snapshot whose refresh-token generation is older
  than the live one, which is the exact hardening added after a rotation tool installed a stale
  snapshot and revoked every grant at once, killing a review mid-run.
- **One live holder per entry**, enforced by a supervised-refresh lock — the same guarantee the
  native engine provides with thread safety. Two concurrent holders of a single-use refresh chain is
  the same bug wearing a different hat.
- **Invalidate the cache, then believe the result** (§4.1). In the managed class this is the same
  rule at smaller scale: whatever caches the credential must be restarted before any entry's state is
  re-observed, or a stale reader will mark healthy entries dead.

Both classes share the last two rules:

- **Rotation reaches a running attempt only through a respawn.** Credentials are read at spawn; an
  attempt's credential reference is part of its immutable pinned composition, so a rotation changes
  the *next* attempt and never mutates a live one. This is D13's active-pointer rule applied to
  credentials, and it is why "rotate, then respawn the capped seats" is the correct order rather than
  an inconvenience.
- **Automatic where it is mechanical, ceremonial where it is human.** Acquiring a healthy entry,
  recording an observed cap, and rotating on exhaustion are automatic. Minting a new entry, refilling
  credits, and raising a plan are operator ceremonies the pool can only *request* — by surfacing the
  exact refusal and the earliest known reset.

### 4.4 Routing: ctower decides policy, the engine executes it

The division of labour is exact, and it is the whole answer to "who owns resilience":

> **Ctower decides policy** (which providers, in what order, under what budget stops).
> **Hermes executes it** (pools, then fallback providers, then aux chains).
> **The adapter translates** policy → `config.yaml`, and events → ledger.

`acquire(model_ref, tier)` leases an entry whose window for that exact model is `available`. It never
substitutes a *model* to find an available credential: model policy belongs to profiles, ladders, and
operator rulings (§2), and a pool that silently rerouted a judgment lane to whatever happened to be
funded would defeat the zero-tolerance rule judgment lanes already carry. Ctower's budgets and
hard-stops are evaluated **before dispatch**, so an over-budget attempt refuses at `acquire` rather
than discovering its answer from a provider's 402 mid-turn.

**Flap discipline is part of acquisition.** A window that flips from exhausted to available is not
selectable until it holds for a full observation cycle. This is not caution for its own sake: z.ai
flipped alive twice in one morning and the second flip lasted exactly two sweeps, and because the
hold-one-cycle bar was enforced, zero lanes were half-started — briefs were staged and nothing
launched. A pool that routes on the first good news manufactures precisely the half-dead lanes the
rest of this design spends its length detecting.

#### Three ordered layers, which the seam must never collapse

| Layer | Scope | Trigger | Ctower's part |
|---|---|---|---|
| 1. Credential pools | Same provider | Rotation strategy + error class (§4.3) | Register, meter; never re-implement |
| 2. `fallback_providers` | Cross-provider, ordered | 429/5xx after retries; 401/403/404 immediately; malformed responses | **Generate the chain from the registry**; meter each activation |
| 3. Aux per-task chains | Per task kind (vision, compression, web-extract, skills, mcp, approval, title, triage) | Own resolution per task | Attribute spend separately (§4.4.2) |

Collapsing layers 1 and 2 is how a cross-provider failover gets recorded as a rotation and a judgment
lane quietly changes family. Layer 1 is *the same subscription serving again*; layer 2 is *a different
vendor answering* — the distinction the fleet learned by hand as "a known fallback rung of the spawn
intent is the never-stall ladder, not substitution, except on judgment lanes where tolerance is zero"
(§3.2).

#### 4.4.1 The ladder is authored config, generated from the registry

The commander built tonight's ladder by hand — sol → glm → park — from knowledge of which
subscriptions were alive. That is precisely a **registry-derived artifact**: ctower's routing policy
generates each profile's `fallback_providers` list (and each aux `fallback_chain`) from the registry
of pools, subscriptions, and current windows, and the adapter writes it as configuration.

Under the target topology of §4.1.4 the generation is fully determined: five subscriptions per
profile produce the three-rung chain **codex → glm → qwen** in policy order, with the three codex
accounts rotating beneath the first rung rather than appearing as rungs of their own. The generator's
input is the desired topology plus current windows; its output is a pinned revision. A rung whose
subscription is `missing` is a drift finding, not a silently shorter ladder — a chain that quietly
drops an unminted rung is how a profile ends up one substrate deep without anyone deciding that.

Two rules govern how it is written, and the second is the engine's own, honored verbatim:

- **Generated, revision-pinned, and diffable.** A chain is authored desired state with a revision and
  digest, exactly as D12 already requires of configuration; the adapter applies it, and the engine
  reads it. Ctower still never writes `auth.json` — one writer per file (§4.1.3).
- **Config only. No environment variables.** Hermes's stated principle is that "fallback
  configuration is a deliberate choice, not something a stale shell export should override", and the
  seam adopts it as written. This is the same law ctower already holds from the other direction —
  authored configuration is data, runtime truth is never inferred from a shell — and a ladder that
  can be silently altered by an exported variable is not a pinned composition at all.

#### 4.4.2 What the ledger must model about a fallback

- **Turn-scoped.** The primary is restored each turn, with at most one activation per turn. A
  fallback is therefore an *event within a turn*, not a mode the seat is in; a ledger that records it
  as a state would report a seat as "on glm" for an hour when it was on glm for one turn.
- **Reset-aware.** An unelapsed `reset_at` skips the doomed retry and stays on the fallback until the
  reset passes — avoiding a second cache invalidation. That skip must be a **ledger-readable fact**
  ("did not retry primary: reset_at unelapsed"), because otherwise the absence of a retry is
  indistinguishable from a bug, and the next person to read it will helpfully "fix" the skip.
- **Every activation is a metered cost event, and it is charged twice.** Switching away invalidates
  the prompt cache, and switching back invalidates it again: one activation = **two full-price
  context re-reads**. Combined with §4.3's per-rotation cache reset, this is the arithmetic that makes
  resilience visibly expensive rather than invisibly expensive, and it is why the ladder's *order*
  is a budget decision and not just an availability one.
- **Aux spend is attributed separately.** A seat's cost is main-model spend **plus** its aux chains
  (compression, vision, web-extract, and the rest). Folding aux into the main line hides a real and
  variable cost — compression in particular runs on long-context lanes, which are exactly the
  expensive ones. The ledger keeps them as separate attributed lines under the same seat and attempt.
- **Degradation is recorded, not silent.** Compression that cannot run degrades to no-summary rather
  than failing the turn. That is correct behaviour and a *quality* event: the seat's context fidelity
  changed, and this design's standing rule is that a degraded state must never render as a healthy
  one.

#### 4.4.3 Meter in provider-native credits, not tokens

Tokens are the wrong unit. They are what the model consumed; **credits are what the subscription
paid**, and only the second answers "why is this account draining". The two differ by more than a
constant factor, because providers weight per model *and* per direction. The operator's codex plan,
as the concrete case the registry must carry:

| Model | Input | Cached input | **Output** |
|---|---|---|---|
| `gpt-5.6-sol` | 125 | 12.5 | **750** |
| `gpt-5.6-terra` | 50 | 5 | 300 |
| `gpt-5.6-luna` | 5 | 0.5 | 30 |

A **25× spread** between the cheapest and dearest rung, concentrated in the output direction — and
our judgment lanes are exactly the ones that run at max effort and emit long verdicts on the dearest
rung. So the fleet's intuition was inverted: **sol-max judgment was the quota burner, while luna
engineering barely dents the plan**, even though the engineering lanes look busier by every
token-shaped measure we had. A token-only ledger cannot show this; it would rank a chatty build lane
above a terse reviewer that cost thirty times more.

Three requirements follow:

- **The registry carries the weight table per subscription** (§4.1.3), versioned like any other
  authored fact, because the provider can change it and a stale table silently misprices history.
- **The ledger attributes spend as credits by model × account**, alongside the raw token counts it
  already keeps. The question it must answer directly, without a join anyone has to invent, is
  "which model on which account drained this plan".
- **Routing policy may weigh cost class** (§4.4): volume work belongs on cheap-weight rungs, and
  scarce-weight rungs are reserved for the work that needs them — which is a *policy* statement
  ctower owns, expressed in the generated ladder, not a preference an adapter improvises. Note the
  interaction with §4.3: cached input is an order of magnitude cheaper than fresh input, so every
  rotation and fallback that invalidates a prompt cache converts cached credits into full-price ones.
  The cache-reset cost event and the weight table are the same arithmetic seen twice.

#### 4.4.4 Capacity errors bypass an explicit choice; transient ones respect it

The aux ladder's semantics map onto the seam's error taxonomy and must agree with the runbook's
diagnosis table (§4.5):

| Class | Examples | Behaviour |
|---|---|---|
| Transient | 429 after retries | The explicitly configured provider is **respected** — retry it, then rotate within its pool |
| Capacity | 402, daily-quota phrasings, connection failures | The explicit choice is **bypassed**: primary-aux → task `fallback_chain` → main model → warn and raise |
| **Reachability** | 403 with a challenge page (`reach: edge-challenged`) | **Skip layer 1 entirely** — rotation cannot help behind a shared egress — go straight to cross-provider fallback and raise an infra-plane escalation |

The rule underneath: an explicit configuration choice binds while the chosen thing is merely *busy*,
and yields when it is *out of capacity*. Encoding that distinction is the same auth-versus-quota split
of §4.2 appearing one layer up — and mis-mapping it produces exactly the two failures we have already
seen, a doomed retry against an exhausted balance, and a stubborn respect for a provider that cannot
serve at all. The reachability row is the third axis appearing here for the same reason: it is the one
class where the *pool* layer has nothing to offer and only the *provider* layer does.

#### 4.4.5 Delegation and cron inherit the ladder

Subagents and cron-launched agents inherit the parent chain, and the engine shares the parent pool
with them through per-task credential leasing. Two consequences: `spawn` passes the resolved ladder
down as part of the attempt's pinned composition, so **subagent resilience comes for free rather than
as a second mechanism**; and the per-task lease is scoped metadata *beneath* ctower's outer job lease
and fencing epoch, exactly as D13 already requires of provider allocation and session identifiers. A
subagent's credential lease is never job identity, completion proof, or audit authority.

### 4.5 Fail-loud exhaustion: observed → meaning → action, in the refusal itself

When no entry is selectable, `spawn` performs **zero dispatch** and refuses `credential-pool-exhausted`.
The refusal is not a string dump: it carries the runbook's fast-diagnosis mapping **as fields**, so the
reader is not asked to re-derive what an operator already learned the hard way.

```
credential-pool-exhausted
  harness, model_ref, tier
  observed:  the exact substrate string + HTTP status (+ body shape when it classifies)
  meaning:   pool-state | capped | lineage-dead | chain-burned | unfunded | edge-challenged
  action:    restart+re-probe | wait until reset_at | re-mint profile | fresh mint | top up
             | infra-plane: fingerprint/headers/egress
  entries:   [{identity, auth, quota, reach, reset_at | unknown}]     # §4.2's three axes
  earliest_return: reset_at | explicit unknown
```

The classification table is the runbook's, imported whole because each row cost an incident — plus
tonight's new row:

| Observed | Meaning | Action |
|---|---|---|
| `No available … credentials` | Pool-state refusal — **often a stale cache**, not real exhaustion | Run the invalidation hook, re-probe (§4.1) |
| `usage_limit_reached … resets_at` | Account **capped, auth fine** | Wait for the reset, or use another entry |
| Lineage 401 while the shell reports "logged in" | Per-profile lineage expired | Re-mint that profile |
| `refresh_token_reused` | A copy burned the chain | Fresh mint — never a copy (§4.1) |
| Probe passes, real call 402 | Prepaid balance near zero | Top up (and see §4.6: the probe was too small) |
| **403 with an HTML challenge page and a `cf_chl`-style token** | **Edge challenge — auth and quota both fine**; the CDN is refusing our egress, not our credential | **Infra plane only**: client fingerprint, headers, or egress. Explicitly *not* a mint, rotation, or restart |

Two rows justify structure over prose more than the rest. **A pool-state refusal and a real
exhaustion look identical to the caller** — treating the first as the second is what let a stale proxy
report `No available credentials` for a night while the accounts underneath were merely resting. And
**an edge challenge looks exactly like an auth failure**, because it *is* a 403: the flattened reading
sends a seat to burn a fresh single-use mint against a credential that was never broken, and the mint
still will not work. A refusal that carries `meaning` and `action` as fields cannot make either
mistake silently.

`credential-pool-exhausted` never downgrades to another model, never retries into another family,
never returns a receipt, and never lets the lane render as idle.

The incidents this is written from, in one line each:

| Incident | What the pool must do differently |
|---|---|
| Codex pool exhausted 04:33Z: `credential pool: no available entries` → non-retryable 401 ×13; two review turns died mid-turn | Refuse at selection with that exact string, before dispatch — not thirteen times at the API |
| Deepseek/openrouter 402 mid-review: the seat died on its *first* API call after three good verdicts that morning | `unfunded` is a first-class window state; money is a liveness condition, and a funded-this-morning entry proves nothing now |
| Qwen weekly-plan caps | Windows carry plan periods with known resets; a weekly reset is a scheduled return to `available`, not a surprise |
| z.ai flaps | Hold-one-cycle before an entry becomes selectable again (§4.4) |
| Claude slot marked capped with `capped_until: "unknown"` | Unknown reset is not availability (§4.2) |

### 4.6 Probe validity: same pool, realistic size, after invalidation

Three conditions, each from a different incident. A probe failing any of them reports `unknown`, never
`available`.

**1. Drawn from the pool it reports on.** The fleet sentinel's codex value is not a probe at all: it
reads a human-marked state file and **defaults to `alive`** when that file is absent, because OAuth
quota is not cheaply probe-able without burning a turn. So at 04:30Z it reported `codex=alive` while
three minutes later every reviewer seat took a non-retryable 401 from an empty pool — and
`state/capacity.json` still carries `codex: alive` on an 813-sweep streak while the pool has been dry
all day. **The answer was readable the whole time:** the engine's own pool entries carry
`last_status: exhausted` in this box's `auth.json` right now. A pool's reported health is an
observation drawn from its own entries; a probe on a different credential path reports on a different
thing; a constant, a default, or a hand-marked file is not an observation at all.

**2. Realistically sized.** A one-token probe passes a nearly-empty prepaid account that 402s on
real-sized work. Size is therefore part of probe validity, not a performance detail: the `HarnessSpec`
declares the probe shape — a workload-shaped request with a real token budget — and anything smaller
is not evidence of capacity. The fleet already learned the neighbouring half of this rule for z.ai,
where a 200 OK with empty content is a hang rather than capacity, so a valid probe asserts on
*content*, not only on status.

**3. Taken after invalidation, never across it.** A probe against a stale cache measures the cache.
Any observation taken before the invalidation hook of §4.1 has completed is discarded rather than
recorded — this is the discipline the runbook states as clear the markers, restart the proxy, *then*
send one request per entry.

**4. Classified on the response body, not the status code alone.** This is the condition tonight's
edge challenge adds, and it runs in both directions: a `200` can be a failure (z.ai's empty-content
hang) and a `403` can be a perfectly healthy credential (a CDN challenge page carrying a `cf_chl`-style
token). So `probe` classifies on shape — HTML plus a challenge token means `reach: edge-challenged`
and **never** `auth: lineage-dead` — and a probe that reads only the status line is not a valid probe.
The cost of getting this wrong is asymmetric and immediate: the lineage-dead reading prescribes a
re-mint, which consumes a single-use device flow, cannot succeed against a challenged edge, and leaves
the operator believing the credential was the problem.

**5. Aimed at what the seats actually use.** A probe is a claim about a specific product, endpoint,
*and model*; if any of the three differs from what seats will run, the verdict is about something
else. This is not hypothetical, and it is checkable in this repository's own fleet tonight: the
capacity sentinel probes z.ai with **`glm-5.2`**, while the engineer profile's z.ai rungs are
**`glm-5.3`** and `glm-5-turbo` on that same endpoint. Its `capped` verdict — unbroken on every sweep
through the evening — is therefore a statement about a model no seat runs, and it is the state that
parked lanes and armed the substrate park.

The same probe compounds the error by flattening: it maps `401`, `402`, `403`, and `429` all to the
single word `capped`, which merges dead auth, no funding, **not entitled to this model**, and a real
rate limit. Those are three different axes and four different actions in §4.2's model — and an
entitlement 403 on an unused model is the reading most consistent with a coding plan the operator
reports as `0/140K` used and resetting 2026-08-25. I have not made a live call to settle which cause
it is; that is an infra-plane action, not a design lane's. What the design takes from it is the rule:
**probe target identity is part of probe validity**, recorded in survey question (i), and a probe
whose target differs from the seats' is reported as `unknown` for the seats' rung rather than as that
rung's state.

Where a valid probe would cost a real turn, the honest answer is `unknown` plus the age of the last
real observation — and the pool keeps learning from the refusals seats actually receive via `meter()`,
which costs nothing and is the only evidence that is never stale in the wrong direction.

The same rule already exists one layer up in this design for models (a source that proves only the
request is a conflict, never truth) and for liveness (`substrate-unobservable:<probe>` rather than a
guess). Credentials get it too, for the same reason: **an availability signal that cannot fail is not
a signal.**

### 4.7 The bindings wrap the existing tool family; they do not reinvent it

The ceremonies already exist and are the product of a year of incidents. The `codex` and `claude-code`
bindings wrap them rather than growing parallel implementations:

| Tool | Seam use |
|---|---|
| `tools/codex-auth-all` | The one-shot enrolment ceremony: every account into the shared pool plus a fresh primary per persona profile, ending with the pool-proxy restart. The seam's `request_mint` surfaces *this*, not a new flow. |
| `tools/codex-grant-ceremony [account]` | The per-account subset, for a single-identity re-mint |
| `hermes auth list / reset / status` | Per-profile inspection and marker clearing. Its `status` reports **auth, not quota** — the §4.2 split, in the tool's own words |
| `tools/codex-rotate-fallback` | Raw-CLI account rotation, generation-guarded against installing an older snapshot |
| `tools/codex-pool` | The older raw-CLI multi-account rotation on a ~5h cooldown model |

One inherited safety property is worth carrying into the seam's own CLI surface: a mutating tool must
refuse unknown flags. `--help` once *executed a rotation* on live credentials because the tool ignored
what it did not recognize. A verb that mutates credentials answers questions with usage, never with
side effects.

---

## 5. Draft acceptance criteria for T0 — the freezable twelve

**Twelve, written to be frozen at the plan stage as they stand.** Every one is falsifiable by a
fixture, and none is satisfiable by a screenshot or a seat's self-report. Draft ids `AC-HAD-*` are
placeholders: the spec lane mints final ids and **must add a matching row to the evidence-manifest
fixture**, or the release gate fails late.

The scope additions of §4 grew the underlying requirement set to nineteen; the post-seal ledger
addendum added a twentieth (credit-unit metering with per-model weights) and the target-topology
ruling four more (desired state, drift findings, the enactment split, and ordered reconciliation). Rather than hand the plan
stage an over-count, the set below is folded to twelve by merging criteria that share one failure
mode — no requirement is dropped, and §5.1 maps every one of the twenty-four to the row that carries it.
The addendum was folded into rows 10, 11, and 12 rather than opened as `AC-HAD-20`, because credit
metering is the same ledger-fidelity failure as the cost events already there, per-account reset
clocks are the same entry-state failure, and probe-target identity is the same
observation-validity failure. The freeze stays at twelve.

| Id | Criterion | Evidence |
|---|---|---|
| AC-HAD-01 | The public Seam publishes only when two real bindings (`claude-code`, `hermes`) plus one deterministic fault-injection fake pass one shared conformance suite, with the fake injecting unacknowledged dispatch, a queued/collapsed-paste composer, a cap menu, context saturation, silent model substitution, dead auth, and pane loss. Registration additionally requires a complete credentials survey — native pool, native fallback, config surface and whether it is authored-config-only, identity proof, reset/window semantics, rotation cache semantics, subagent inheritance, and egress topology — and enforces **never both**: a binding declaring a native layer and also enabling ctower's own for that layer is refused. | Conformance run across three implementations, one suite; injected-fault matrix; publication refusal with one real binding; survey-completeness refusal; both-layers-enabled registration refusal; per-layer role table derived from surveys rather than harness names |
| AC-HAD-02 | Delivery is never assumed. `spawn` returns a receipt only after the binding's declared ACK predicate is observed; a queued-composer and a collapsed-paste fixture each return `harness-dispatch-unacknowledged` with zero session-start fact, zero assignment stamp, and zero evidence row. Input into a `working` lane requires the declared interrupt capability or delivers nothing, and steer counts as acknowledged only when the harness returns the durable command ID. | Per-binding composer fixtures; zero-mutation ledger assertion; ACK-predicate declaration in each `HarnessSpec`; mid-turn steer refusal; ACK-only-on-command-id assertion |
| AC-HAD-03 | `liveness` reports `served_model` from its per-binding evidence source. A launch/served mismatch appends one `model_changed` observation and overwrites no dispatch stamp; a source proving only the request is recorded as a conflict, never as serving truth; an unreadable substrate returns `substrate-unobservable:<probe>` and surfaces `STATE_UNKNOWN`; a seat self-report satisfies neither and refuses by name. | Three-source matrix (gateway log, transcript, launch argv); substitution, conflict, and unknown fixtures; self-report refusal |
| AC-HAD-04 | Cap and saturation are classified before any working marker and win over it: a pane at or past the declared window percentage is `saturated`, a limit/upgrade/out-of-credits pane is `capped`, and both count as not working while a spinner or timer advances. A healthy large-window lane at the same absolute token count is not flagged. Each binding's classifier is proven against captured real substrate output, and a coverage-style `95%` line in scrolled output does not trip it. | Captured-footer corpus per binding; percentage-versus-absolute counter-fixtures; precedence assertions; false-positive corpus |
| AC-HAD-05 | Every `writeback` fact attributes to one seat's own project-seat credential and resolves exactly one Actor. Facts outside `capture`/`transition`/`evidence` refuse by name with zero mutation; a Workflow stage change is emitted only as a request and its refusal is reported verbatim; an adapter presented with an operator or commander credential refuses rather than using it; a foreign project key returns `project-scope-denied` with zero disclosure. | Scope matrix over the three scopes; transition-request-not-transition trace; operator-credential refusal; foreign-project refusal with zero rows |
| AC-HAD-06 | `collect` derives artifacts from committed refs and durable records only. An uncommitted worktree returns `checkpoint-uncollectable` naming the dirty paths; no terminal capture, pane text, or session existence can fill an evidence slot; a run whose seat wrote no status artifact still yields a complete artifact set from its pushed branch. | Dirty-tree refusal fixture; evidence-slot inventory proving no capture-sourced satisfier; no-status-file collection transcript |
| AC-HAD-07 | Lane termination preserves work and continuation. A `saturated` or `capped` fact triggers `teardown(checkpoint)` — work committed and pushed, handoff carrying done / in progress / not started / next three steps — before the lane stops; a `park` carries a stated basis and explicit expiry, re-proves its basis, and fails loud on expiry or when a wake condition turns true; `reap` refuses while sole work is unpushed and refuses a `dead_auth` lane, which is preserved for resume, with one nudge offered before any replacement. For a binding whose survey says "no native fallback", cross-provider failover is a **new attempt** with its own pinned composition after a successful checkpoint, never an in-session swap. After pane, tmux-server, or host loss the adapter reconstructs from ctower state, rejects old epochs, and never treats pane disappearance as success. | Saturation-to-checkpoint trace; handoff-section assertion; park expiry and basis-broken fixtures; sole-work and dead-auth refusals; nudge-before-respawn ordering; failover-to-new-attempt digest diff plus in-session-swap refusal; kill/restart reconstruction with epoch rejection |
| AC-HAD-08 | An unknown harness value is carried byte-for-byte through spawn, liveness, and writeback, displayed as observed, included in equality and cross-checks, and never normalized, downgraded, or collapsed. No kernel, reporter, projection, CLI, or Board path imports or parses a harness-private transcript or session format; harness-private observation exists only inside a binding and crosses the seam as typed facts. | Unknown-harness carry/display fixture; import-boundary inventory; per-binding private-parser containment check |
| AC-HAD-09 | Nothing dispatches unless the composition and the guard both clear. An unknown, incompatible, revoked, or digest-mismatched `HarnessSpec` performs zero dispatch with no fallback to a generic process; every `spawn` obtains and enforces a current versioned CommandGuard decision for the exact normalized plan at its final pre-dispatch boundary, where `block` and `needs_operator` dispatch nothing and a receipt that cannot be durably recorded first yields zero dispatch; a changed plan, expired or replayed grant, or direct bypass fails closed. | Four fail-closed component fixtures; guard invocation trace per binding; zero-execution-on-block assertion; receipt-first ordering; replay/expiry/bypass refusals |
| AC-HAD-10 | Every pool entry carries **three orthogonal states** — `auth ∈ {healthy, lineage-dead, chain-burned}`, `quota ∈ {available, capped(reset_at), capped(reset_unknown), unfunded, unknown}`, `reach ∈ {ok, edge-challenged, unknown}` — with no path collapsing them, selectable only when all three are clear, and a mint moving only the `auth` axis so an `edge-challenged` entry is never routed to a mint, rotation, or restart. Entries are keyed by decoded identity, never by label; a `discovered` identity is non-selectable pending operator keep-or-evict; the Interface exposes **no copy verb**. With no selectable entry, `spawn` performs zero dispatch and refuses `credential-pool-exhausted` carrying `observed`, `meaning`, `action`, per-entry three-axis states, and the earliest known reset or explicit unknown — each diagnosis row mapping to its exact meaning/action pair, with a stale-cache pool-state refusal never classified as real exhaustion. Observation projects a strict named-field allowlist, so no credential value reaches any ledger row, status output, log, refusal, or telemetry event despite adjacent token fields. `limits()` returns per-entry rows carrying each account's own reset clock and never an aggregate substrate verdict, and `acquire` fails only when every entry is unselectable: a fixture pool holding two exhausted entries and one near-full entry acquires successfully and reports three distinct clocks. | Three-axis matrix including auth-healthy/quota-available/reach-challenged; mint-changes-only-auth and no-ceremony-for-reachability proofs; mislabelled-entry and duplicate-label identity fixtures; discovered-not-selectable assertion; Interface inventory proving no copy path; refusal-body assertions per diagnosis row; stale-cache misclassification fixture; adjacent-token projection scan; mixed-exhaustion pool acquiring from its healthy entry; per-account reset-clock rows with no aggregate verdict |
| AC-HAD-11 | `rotate` is incomplete until its declared cache-invalidation hook completes — `rotation-incomplete` otherwise, with no entry state recorded from a pre-hook observation — and is **refused rather than attempted** against an `edge-challenged` classification. For a ctower-provided pool, rotation writes the live credential back before swapping, refuses a snapshot older than the live generation, and enforces one live holder. `probe` is valid only when drawn from the pool's own entries, sized to the declared workload shape, taken after invalidation, and classified on the response body rather than the status line: a 403 with a challenge page is `reach: edge-challenged`, never `auth: lineage-dead`; a 200 with empty content is a hang, never capacity; a one-token probe, a constant, a default, or a hand-marked file each report `unknown`. The probe's product, endpoint, and **model** must be the ones seats run: a probe aimed at a different model reports `unknown` for the seats' rung rather than that rung's state, and a status-code-only classifier that maps 401, 402, 403, and 429 to one word is refused as a state source. A window returning to `available` is not selectable until it holds a full observation cycle, and a rotation during a live attempt changes nothing about that attempt. | Hook-incomplete refusal and pre-hook discard; rotate-refused-on-reachability fixture; write-back-before-swap ordering plus `refresh_token_reused` regression; generation-guard and concurrent-holder tests; challenge-page-versus-401 classification pair; empty-content-200 rejection; tiny-probe-then-402 fixture; correlated-failure inference over a shared-egress survey answer; default-alive-constant rejected; probe-target-mismatch reports unknown; four-status-codes-to-one-word classifier refused; flap hold-one-cycle; live-rotation no-op with next-attempt pin diff |
| AC-HAD-12 | The ledger and the generated configuration stay faithful to what happened. Spend is metered in **provider-native credit units** using the subscription's versioned per-model, per-direction weight table from the registry, attributed as credits by model × account alongside raw token counts, so "which model on which account drained this plan" is answerable directly; a fixture whose weights span 25× ranks a low-token high-weight lane above a high-token low-weight one, and a stale or missing weight table refuses rather than silently mispricing. Every rotation is metered at one context re-read and every fallback activation at two (switch and return); fallback is recorded turn-scoped with at most one activation per turn, never as a mode; a retry skipped against an unelapsed `reset_at` is an explicit fact, not an absence; aux-task spend is attributed separately from main-model spend under the same seat and attempt; a compression degradation is a recorded quality event. The registry declares the **desired topology per profile** — five subscriptions yielding three rungs — and reconciliation against actual emits typed drift findings in both directions: a desired-but-absent subscription is `missing` and routed to its declared enactment path (`operator-ceremony` for OAuth grants, `secret-reference` for API keys), never reported as ordinary unavailability or silently dropped from the chain, while a present-but-undesired entry is `unregistered` and non-selectable pending operator keep-or-evict. A reconciliation plan whose steps have a dependency order states it, so no proposed step retires a provider that a profile still resolves to. Each profile's `fallback_providers` and aux `fallback_chain` are generated from that topology as revision-pinned authored configuration, applied by the adapter and read by the engine, with ctower never writing `auth.json`; no environment variable can alter a chain; and layer identity is preserved — a same-provider rotation is never recorded as a cross-provider fallback, while a transient 429 respects an explicitly configured provider and a capacity error (402, daily-quota, connection) bypasses it. | Credit-unit arithmetic against a weight-table fixture with a 25× spread; credits-by-model×account attribution query; stale/missing weight-table refusal; cached-versus-fresh input pricing across a cache reset; cost-event arithmetic for rotation and round-trip fallback; turn-scoped-not-modal ledger shape; explicit reset-skip fact; main-versus-aux attribution split; degradation event; desired-versus-actual reconciliation over a partially-minted topology (19 of 24) proving `missing` findings rather than silence; enactment-path routing per subscription kind; `unregistered` keep-or-evict fixture; ordered-plan assertion that no step precedes its dependency; five-subscriptions-to-three-rungs generation fixture; registry-to-chain generation diff with revision/digest pins; env-override-ignored fixture; one-writer-per-file inventory; layer-attribution fixture; transient-versus-capacity ladder matrix |

### 5.1 Coverage map — the twenty-four underlying requirements

Nothing was dropped in the fold. Each row above carries these:

| Frozen | Absorbs | Shared failure mode |
|---|---|---|
| AC-HAD-01 | conformance-earns-the-seam · survey completeness · never-both | What may register or publish |
| AC-HAD-02 | dispatch ACK · steer ACK | Delivery reported without acknowledgement |
| AC-HAD-03 | served-model truth | A record standing in for an observation |
| AC-HAD-04 | cap/saturation precedence | A failure rendering as the healthy state |
| AC-HAD-05 | seat-credentialed writeback | Authority claimed rather than resolved |
| AC-HAD-06 | collect from committed refs | Evidence sourced from a pane |
| AC-HAD-07 | checkpoint/park · teardown refusals · failover-as-new-attempt | Work or continuation lost at lane end |
| AC-HAD-08 | harness independence | Harness-private shape leaking across the seam |
| AC-HAD-09 | fail-closed composition · CommandGuard | Dispatch on an uncleared precondition |
| AC-HAD-10 | three-axis entry state · identity keying · no-copy verb · exhaustion refusal · per-account reset clocks | A collapsed state prescribing the wrong ceremony |
| AC-HAD-11 | invalidation hook · rotation rules · probe validity (5 conditions) · probe-target identity · flap hold | An observation that measured the wrong thing |
| AC-HAD-12 | credit-unit metering · weight tables · cost events · fallback semantics · desired-state reconciliation · drift findings · enactment split · generated ladder · layer identity | The ledger or config disagreeing with reality |

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
   append-only decision. It is load-bearing for AC-HAD-03 and AC-HAD-08 and should not be assumed.
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
5. **Where the credentials pool lives — now narrowed to the managed class only.** The T4 inputs answer
   it for native-engine harnesses: the credentials live in the engine, ctower holds references and
   history, and `acquire` leases rather than resolves. The question survives only for the managed
   class (`claude-code`), where ctower operates the checkout topology itself and therefore does touch
   credential material: does that store sit behind the existing kernel secret boundary, or is it an
   executor-side store holding only references? AC-HAD-10's projection scan is meaningful either way,
   but its *boundary* is only definable once this is settled.
6. **Whether pool observations are Record facts.** A pool that learns from real refusals produces
   exactly the kind of durable operational history this system records elsewhere (append-only, typed,
   attributable). Making them Record facts buys audit and cross-seat learning; keeping them local
   state keeps the pool out of the kernel's write path. The design deliberately does not decide it,
   but AC-HAD-10's "earliest known reset" and AC-HAD-12's cost arithmetic are only trustworthy if some
   store outlives one runner.
7. **What authority a generated ladder needs.** §4.4.1 has ctower generating each profile's
   `fallback_providers` chain from the registry and the adapter writing it as configuration. In this
   repository, applying configuration revisions is an operator-only command — a Commander may author
   or propose a revision but cannot apply it. A generated ladder is therefore either (a) authored
   desired state that still requires the operator's apply, which makes automatic re-generation on a
   substrate flip impossible by design, or (b) a narrower executor-side artifact that is not a Catalog
   revision at all. Tonight's hand-built sol → glm → park ladder was a commander decision made in
   minutes; the plan stage has to say plainly which of those two shapes it becomes, because the answer
   decides whether cap-aware re-routing is automatic or ceremonial.

# The operator cockpit — design (R3109)

**Status:** design proposal. Non-normative.

This document proposes; it does not approve. `docs/internal/SPEC.md` remains the only place that
may activate scope, `docs/internal/DECISIONS.md` the only place that may record a decision, and
this file adds a row to neither. R3109 has no stable CT ticket, so nothing here is buildable
product behaviour yet — the constitution puts product behaviour out of scope until its ticket and
dependencies are active. What this file is for is that when R3109 does earn a ticket, the design
argument is already made, already checked against the seam contract, and already carries its
citations.

Companion artifact: `operator-cockpit.html` beside this file — one static mockup of the four-pane
shell, openable with no build step.

**Direction, verbatim (operator, 2026-08-20):** *"I want the same clean UI as paperclip has for
ctower."* Paperclip's visual language is the target aesthetic. Two reads were granted with it:
paperclip's source at `/srv/projects/paperclip-eval/ui` for the real design system, and the live
instance at `http://127.0.0.1:3100`. This document cites source wherever source exists, and says
so explicitly on the few claims that rest on a screenshot instead.

---

## 1. The target

The brief: a four-pane cockpit. LEFT — projects and their crew members, the commander included,
each row carrying live `+adds −dels` badges. CENTER — tabbed chat with the selected crew: agent
turns with collapsible thinking, inline tool-call rows, `INTERRUPTED BY USER` chips, elapsed
time, a composer with a model indicator. RIGHT-TOP — the crew's workspace: changed files with
per-file `+N −N`, a diff view, a Create-PR button. RIGHT-BOTTOM — tabs Setup / Run / Terminal.

The operator's own words for the goal: *"ChatGPT/Claude-desktop experience with crew members… I
want in UI run harness setup wizard, and have open crews view and communication. no tmux or
whatever."*

The Conductor reference screenshot (`cmux-drop-a58d9154…png`, 5088×2822) reads pane by pane:

| Pane | What Conductor actually draws |
| --- | --- |
| Left rail | account switcher · Dashboard/Home/Create/Search · **Projects**, each with its workspaces indented under it, each workspace carrying a live `+1k −21` / `+333 −182` / `+3` badge and an unread count |
| Centre | workspace tabs (`import-scenari…` · **Create Simulation Page** · `Create agent simulation p…` · `+`) over a transcript: tool rows as *icon · label · truncated monospace command*, `Thinking` as a collapsible line, an `INTERRUPTED BY USER` chip, an elapsed stamp (`5m, 42s`), the operator's own turns as a right-side grey bubble, assistant markdown, per-turn duration + copy + more, and a `Next unread ›` jump |
| Composer | `Ask to make changes, @mention files, run /commands` · `⌘L to focus` · model chip `✳ Opus 4.8 1M` · a thinking-effort meter (`Max`) · attach/mic/send |
| Right-top | `All files · Changes 11 · Checks` + `Review`, `11 files changed +1012 −21`, per row a dimmed directory + bold basename and a right-aligned `U +39` / `+11 −9`, with `Create PR` in the window chrome |
| Right-bottom | `Setup · Run · ● Terminal · +` with a collapse chevron |

That is the shape to hit. The rest of this document is how ctower hits it without lying — because
almost every pane above states a fact that ctower is only sometimes able to observe, and the
difference between "renders the fact" and "renders a plausible number" is the whole design.

---

## 2. This is an assembly problem, not a green field

`apps/ctower-ui` already contains most of the cockpit, built against the approved phase-1 screen
set. Anyone scoping this as a new build will duplicate work that exists:

| Cockpit part | Already in `apps/ctower-ui` |
| --- | --- |
| Three-pane workspace shell | `src/app/conductor.css` — `grid-template-columns: 276px minmax(0, 1fr) 372px` at `min-width: 1100px` (`conductor.css:55–58`), collapsing to one route-chosen pane below that |
| Conversation list, transcript, composer, delivery state | `src/surfaces/chat/{ThreadList,Transcript,Composer,ThreadHead,NewThread,Delivery,LinkTicket}.tsx` |
| Work pane beside the conversation | `src/surfaces/chat/WorkPanel.tsx` |
| Live session pane under the work pane | `src/surfaces/chat/SessionPane.tsx`, `src/surfaces/terminal/{TerminalPane,LivePoll}.tsx` |
| File tree with `+N` badges | `src/surfaces/tree/TreePane.tsx` (`badge`, `badgeTone: "changed" \| "added"`) |
| File/Diff switch | `src/surfaces/explorer/FileDiffSwitch.tsx` |
| Crew rail, crew head, crew history | `src/surfaces/crew/{CrewRail,CrewHead,CrewCurrent,CrewHistory,marks}.tsx` |
| Worktree / git-tree / landed-change reads | `src/read/sources/{worktrees,gitTree,landedChanges,mergeHistory,tmuxBridge}.ts` |

`conductor.css` opens by naming the operator's north star in its own words — *"a list of
conversations on the left, the transcript in the middle with the composer under it, the work the
conversation is about on the right, and the live session under that"* — so the shell was already
built toward this target.

Three things are genuinely missing, and only one of them is UI work:

1. **The left rail is a conversation list, not a project→crew→workspace tree.** UI work.
2. **The fourth pane is a session view under the work panel, not a first-class tab strip.** UI work.
3. **The centre column is bound to an inbox thread, not to a crew session.** *Not* UI work. That
   binding is the harness-adapter seam's `spawn` / `liveness` / `collect` / `writeback`
   (CT-I1-041, CT-I1-042) plus the API operations §7 enumerates. The cockpit's plumbing and the
   harness-adapter epic's finish line are the same work. Nothing in this document asks for a
   second one.

One boundary fact that governs all of it: `apps/ctower-ui` is explicitly a non-product boundary —
its README's first line is *"This is **not** `apps/ctower-web`"* — an operator surface over a
running development instance, whose browser receives no API bearer, no session, and no credential
of any kind, because every read happens server-side. The cockpit lands there. It does not land on
`apps/ctower-web`, and §6.5 says why it may not arrive there by accretion.

---

## 3. Aesthetic: paperclip's system is the base

Paperclip's design language is a documented, enforced system, not a look, which is what makes
"the same clean UI" a portable instruction rather than a mood. Read
`/srv/projects/paperclip-eval/DESIGN.md` first; it is the anchor document and it says of itself
that Storybook *"is the verification surface — it documents the system; it does not define it."*

Its product stance is already ctower's, verbatim:

> Paperclip is an operational control plane… The user is an operator scanning state and making
> decisions. Every screen should answer, in order: *what is happening, does it need me, what do I
> do about it.* Density in service of scanning beats whitespace in service of aesthetics — but
> density comes from information, never from chrome.

### 3.1 What is actually being adopted

| Layer | Paperclip's rule | Source |
| --- | --- | --- |
| Token source | Exactly one. `ui/src/index.css`, Tailwind v4, no config file, tokens as CSS custom properties via `@theme`. A parallel `tokens/` directory is named as forbidden because it would produce two sources of truth. | `DESIGN.md` §"The token layer" |
| Runtime tunability | `@theme inline` bakes literals at build time, so anything that must retune at runtime (dark mode, theme editor) lives in a non-inline block. | same |
| Type | `--font-sans: "InterVariable", "Inter", ui-sans-serif, …`; `--font-mono` is a system monospace stack. | `ui/src/index.css:23–24` |
| Colour | OKLCH neutral semantic core — `--background: oklch(1 0 0)`, `--foreground: oklch(0.145 0 0)`, `--muted-foreground: oklch(0.556 0 0)`, `--border: oklch(0.922 0 0)` — with a complete `.dark` override block and a `--sidebar-*` family. | `index.css:74–91`, `.dark` at `289+` |
| Radius | **One knob.** `--radius: 0.5rem` and a multiplicative ladder — `--radius-sm: calc(var(--radius) * 0.6)` through `--radius-4xl: calc(var(--radius) * 2.6)` — so the whole app's corner language retunes from a single value. | `index.css:59–74` |
| Status | One seed hue per state, consumed through a `color-mix` recipe that derives both modes from that one seed: `.status-chip { background-color: color-mix(in srgb, var(--sc) 15%, white); color: color-mix(in srgb, var(--sc) 82%, black); border-color: var(--sc) }`, with a `.dark` counterpart at 22%/80%/48%. | `index.css:1951–1959` |
| Motion | Two tiers. Primitives `--motion-duration-{instant,fast,base,slow,deliberate}` = 80/160/240/360/520ms plus two house curves (`--motion-ease-out-expo: cubic-bezier(0.16,1,0.3,1)`, `--motion-ease-standard: cubic-bezier(0.4,0,0.2,1)`); every scoped token (`--motion-tool-enter`, `--motion-cot-collapse`, `--motion-diff-reveal`…) references a primitive. `prefers-reduced-motion` zeroes the **primitives**, and the comment states the reason: *"Zeroing the primitives cascades to every scoped token that references them."* | `index.css:221–253`, `544–560` |
| Components | shadcn `new-york`, `baseColor: neutral`, `cssVariables: true`, lucide icons. | `ui/components.json` |

Adopt all of the above. Two of paperclip's own principles are worth restating because they are
the ones that decide the cockpit's hard cases: **Principle 4**, *hierarchy through structure, not
decoration — a screen should survive the removal of one visual layer*; and **Principle 6**,
*machine values look machine-made* — IDs, costs, token counts, timestamps and log output use the
monospace token and shared formatting helpers, never per-screen formatting.

### 3.2 One thing the instruction does not mean

`DESIGN.md`'s own status line: *"Governs structure, not brand. Brand values (color, type,
iconography) are intentionally unspecified: they are being redesigned and will land as token
values only."* So "the same clean UI as paperclip" cannot mean "paperclip's hues", because
paperclip does not consider its hues settled. It means the structure, the density stance, the
single-token-source discipline, the one-knob ladders, the derive-both-modes-from-one-seed recipe,
and the copy rules. That is the portable part, and it is the part that survives paperclip's own
next redesign.

### 3.3 The deltas ctower's laws force

**D1 · A third state class: `unknown`.** Paperclip's status set is `idle/running/paused/error`
and `backlog/todo/in_progress/in_review/done/blocked/cancelled` (`index.css:155–165`) — every
value is a *known* state. ctower must render a fourth thing: a read that did not answer.
`AC-UX-03` requires degradation to flip views to `STATE UNKNOWN` and states that *no test case
displays "All clear."* `AC-HAD-03` returns `substrate-unobservable:<probe>`; `AC-HAD-10`'s quota
axis carries `capped(reset_unknown)` and `unknown` as first-class values.
→ Mint `--state-unknown` alongside the status hues, feed it through the same `--sc` recipe, and
forbid it from resolving to the idle grey or to any success hue. Paperclip's own Budget tab is the
counter-example this delta exists to prevent — see §5.5.

**D2 · No shadows, no gradients, no glows, in either theme.**
`apps/ctower-ui/design-reference/app.css:5` opens with exactly that rule, and the light set is
lifted from the manibo Vercel pack *"and its `--shadow-sm: none`"* (`app.css:10`). shadcn
`new-york` reaches for subtle elevation by default. Keep ctower's rule: it is the stricter reading
of paperclip's own Principle 4, so this is a defaults conflict, not a principles conflict.

**D3 · Keep ctower's semantic marks; port paperclip's recipe.** ctower's six state marks, its
seven-stage ramp (`--stage-1: #a3a3a3` …, `app.css:56`) and its three project marks
(`--p-ctower: #7c3aed`, `--p-manibo: #0d9488`, `--p-bhloop: #be185d`, `app.css:51–53`, each with
its own dark-mode value at `114–116`) are vocabulary the operator has already learned, carried by
a small mark and never by chip chrome. Port the *mechanism* — one seed per state, both modes
derived by `color-mix`, icon hues separately tuned to clear contrast as bare glyphs — not the hue
values. §3.2 is why: paperclip's hues are the part paperclip itself has not settled.

**D4 · No per-agent decorative gradient.** Paperclip mints ten brand gradients
(`--agent-1a/1b` … `--agent-10a/10b`, `index.css:128+`). ctower identifies a lane by **seat name +
project mark + harness**, all of which are facts. A gradient assigned by index is a fourth
identity that means nothing and competes with the project mark for the same glance. Drop it.

**D5 · Copy discipline is stricter than paperclip's.** The operator's binding amendment recorded
in `apps/ctower-ui/README.md` is: *remove unnecessary text; a screen that needs a paragraph to
explain itself fails the gate.* Paperclip's Tools tab stacks three explanatory banners plus a
sidebar essay on one screen (§5.2). Adopt paperclip's grid, spacing and density; do not adopt its
banner habit. ctower's rule already says where the words go instead: a control's caveat lives on
the control, a number's derivation lives in that number's hover, and a declared absence is a mark
plus the fact plus a citation chip.

**D6 · Machine values are mono, and ctower's list is longer.** Paperclip's Principle 6 covers IDs,
costs, token counts, timestamps and log output. ctower adds ULID prefixes, composition and
artifact digests, `HarnessSpec` revisions, per-account reset clocks, provider-native credit units,
fencing tokens, and console cursor positions. `src/surfaces/Count.tsx` already enforces that a
count carries its unit; extend the same rule to every value above.

**D7 · Adopt three dependencies; refuse a fourth.** `react-resizable-panels` (paperclip wraps it
at `ui/src/components/ui/resizable-panels.tsx`) gives the four-pane geometry with persisted sizes.
`@xterm/xterm` + `@xterm/addon-fit` gives the terminal pane's rendering. `cmdk` gives the palette
that Conductor's `⌘L to focus` implies. **Do not adopt `@assistant-ui/react` or any chat runtime.**
ctower's transcript is a projection of durable events, not a chat runtime; `AC-UX-09` requires a
browser command to remain visibly `unsent` or `durability pending` until authoritative acceptance
and never to paint optimistic state as accepted, and optimistic local echo is precisely what a
chat runtime exists to provide. Adopting one installs the projection-lag defect as a library.

**D8 · The stack ports at the token layer only.** Paperclip is Vite + React Router + TanStack
Query with client fetching. `apps/ctower-ui` is Next App Router with server components and no
client data layer, because its browser holds no credential at all. The tokens, the component
vocabulary and the copy rules port; the data layer does not.

---

## 4. The four panes, mapped to real backends

Shell: three columns via `react-resizable-panels`, the right column split horizontally. Below
1100px the existing route-chosen single-pane collapse in `conductor.css` applies unchanged — no
pane is ever dropped, and a phone reaches all four one at a time.

Each pane below names the seam verb or API operation it reads, and the failure it is designed to
refuse to fake.

### 4.1 Left — projects → crews → workspaces

**Backend:** the seam's registry plus `liveness`. In API terms today: `listSpawnRecords` /
`getSpawnRecord` / `appendSpawnTransition` (`GET|POST /v1/spawn-records…`) for the attempt
registry, `listProjectSessions` (`GET /v1/projects/{project_key}/sessions`) for a project's work
sessions, and `readPoolLimits` (`GET /v1/pools`) for the credential axis. The diff badges come
from `src/read/sources/{worktrees,gitTree,landedChanges}.ts`. §7 lists what is still missing.

Rows are **project** (its 6px mark) → **seat** → **workspace**. The Commander is a seat in the
list, not a chrome affordance — the brief says *incl. commander*, and the board already renders
the commander as an ordinary source.

Three rules make this rail honest:

- **Unread is an accent bar, not the word "unread"** — the existing ctower-ui rule, and D5.
- **`capped` and `saturated` outrank any working marker.** `AC-HAD-04` classifies cap and
  saturation *before* any working marker and states that both count as not working while a
  spinner or timer advances. A spinner advancing over a capped pane is exactly the failure the
  classification order exists to prevent, and it is a failure this seat has seen for real: a
  quota-dead pane renders a normal footer and an advancing timer with no visible error. The rail
  must never show a lane as busy when it is out of credits.
- **A workspace whose read did not answer shows `not reached` with its classified failure**, never
  a `+0 −0`. `+0 −0` is a measurement; a failed read is not. `AC-HAD-03` gives the shape:
  `substrate-unobservable:<probe>` surfacing as `STATE_UNKNOWN`.

### 4.2 Centre — the transcript, and the steer question the brief asked

**Backend:** `writeback` for outgoing turns, the `collect` transcript path for incoming ones.

Turn rows as Conductor draws them: agent turn, collapsible `Thinking`, inline tool rows
(*icon · label · truncated monospace command*), `INTERRUPTED` chip, elapsed stamp, per-turn
copy/more, `Next unread ›`. Operator turns sit on the operator's side of the column —
`src/surfaces/chat/Transcript.tsx` already makes that choice, and its header comment records why:
the rejected screen drew every message as an identical card, so the reader had to *read* each row
to learn whose it was.

Three ctower-forced additions, in order of how much they change the drawing.

**(a) The steer capability is declared data, and today both shipped bindings refuse mid-turn
input.** The brief asked the seam to *name* this per-harness capability. It does — the closed
capability vocabulary is `contracts/runner/harness-capability.schema.json`, whose description is
the whole design in one line: *"A capability is declared data, never a runtime discovery… an
undeclared capability is unsupported by name rather than attempted."* Three of its nine values
govern this pane:

| Capability | What it licenses the composer to do |
| --- | --- |
| `LIVE_INPUT` | deliver input to a lane at all |
| `INTERRUPT_AND_RESUME` | deliver input into a lane that is **working** |
| `STEER_DURABLE_COMMAND_ID` | the harness returns a durable command ID, so a steer can be *acknowledged* rather than assumed |

What the two shipped bindings actually declare:

| Binding | Declares | Does not declare | Composer state while the lane is `working` |
| --- | --- | --- | --- |
| `hermes` | `STEER_DURABLE_COMMAND_ID`, `CHECKPOINT`, `PARK`, `REAP`, `POOL_OBSERVE`, `POOL_ROTATE_RECORD`, `POOL_PROBE` | `INTERRUPT_AND_RESUME` | **disabled** |
| `claude-code` | `CHECKPOINT`, `PARK`, `REAP`, `POOL_OBSERVE`, `POOL_PROBE` | `INTERRUPT_AND_RESUME`, `STEER_DURABLE_COMMAND_ID` | **disabled** |

Both omissions are deliberate and both carry their reason in source.
`apps/ctower-runner/src/ctower_runner/hermes/spec.py:38–40`: *"Steering into a live hermes turn is
how an hour of a reviewer's real finding was nearly lost, so input into a working lane refuses by
name rather than being delivered on the hope that the turn was between messages."*
`apps/ctower-runner/src/ctower_runner/claude_code/spec.py:45–47`: *"this TUI queues a mid-turn
paste into its composer instead of refusing it, so input into a working lane would be silently
swallowed rather than delivered."* The enforcement is
`packages/ctower-runner-sdk/src/ctower_runner_sdk/policy.py:144–160` — `input_refusal` returns
`harness-capability-unsupported` unless the lane is not working or the spec declares the
capability.

**This is the single biggest gap between the operator's stated target and what ctower can honestly
draw**, and it must be designed for rather than papered over. "ChatGPT with crew members" implies
a composer you can always type into. On today's bindings you can type into an idle lane and not a
working one. The design answer:

- The composer's enabled state is **derived from the selected lane's `HarnessSpec` capabilities ×
  its current `liveness` state**, never from a UI-local guess. One function, one source.
- While a lane is `working` on a binding without `INTERRUPT_AND_RESUME`, the composer stays
  **visible, focusable and typable, and the send control is disabled**, carrying the refusal's own
  words on the control (D5): *this harness declares no interrupt capability; delivering into a
  live turn would destroy whatever that turn is holding.* Typed text is preserved and sends when
  the turn ends. A disabled control that explains itself is honest; a control that accepts a
  message and drops it is the failure `claude-code`'s comment describes.
- A binding that *does* declare `INTERRUPT_AND_RESUME` unlocks the same composer with no other
  change. The pane does not special-case a harness; it reads a capability.

**(b) Durability state on every outgoing turn.** `unsent` → `durability pending` → accepted, with
one stable command ID preserved across disconnect and reload (`AC-UX-09`, which also requires that
retry, refusal and quarantine be distinguishable without opening developer tools). A turn is not
accepted because the composer cleared; it is accepted because the record said so **and** the
projection folded. Note the trap this sits on: both bindings' `ack_predicate` is literally
`composer_cleared` — `claude-code`'s detail is *"the composer is empty and the pane shows an
active turn after submit"* — which is the harness's evidence that the harness received it, and is
a different claim from ctower's record having accepted it. The UI must not conflate the two.
`AC-HAD-02` is the same rule from the seam's side: delivery is never assumed, and steer counts as
acknowledged only when the harness returns the durable command ID — which, per the table above,
`claude-code` cannot do at all.

**(c) The model chip is the next attempt's pin, not a live switch.** Conductor's composer chip
(`✳ Opus 4.8 1M`) reads as a live model swap. ctower cannot offer that. `AC-HAD-07`: for a binding
whose survey says *no native fallback*, cross-provider failover is a **new attempt** with its own
pinned composition after a successful checkpoint, *never* an in-session swap; CT-I1-042 says the
same for `claude-code` in as many words. So the chip is labelled for what it is — the composition
the **next** attempt will pin — and changing it while the lane is `working` stages that next
attempt rather than pretending to retune the running one. For a configure-and-observe binding the
chip is **read-only** with its source named: `hermes`'s survey answers `config_surface:
authored_config_only`, and it spawns through a profile directory whose own config owns model and
reasoning effort. An input that appears to set a value ctower does not own is a lie in a control.

### 4.3 Right-top — workspace explorer and the change list

**Backend:** the crew worktree observed read-only, plus `collect`.

Conductor's shape: `All files · Changes N · Checks`, a totals line, per-row dimmed-directory +
bold-basename with a right-aligned `+N −N`, `Create PR` in the chrome. `TreePane.tsx` and
`FileDiffSwitch.tsx` already render both halves.

The ctower delta is the one that makes `Create PR` honest. `AC-HAD-06`: `collect` derives
artifacts from **committed refs and durable records only**; an uncommitted worktree returns
`checkpoint-uncollectable` naming the dirty paths; no terminal capture, pane text, or session
existence can fill an evidence slot. The SDK's `collect_refusal`
(`policy.py:163+`) carries the reason: *"A fix that is not committed is not a fix, and an audit
that reads the working tree cannot tell the difference."* Therefore:

- The change list separates **committed** from **uncommitted** rows visibly. They are different
  claims, and only one of them a successor can read.
- `Create PR` is a real `disabled` control while the tree is dirty, with the dirty paths named
  *on the control* (D5) — the treatment `New ticket` already gets in read-only v1 — not in a page
  banner.
- The `Checks` tab shows the gate verdicts that exist and `not reached` where a gate was not run.
  It does not compose an aggregate "passing" out of a partial set. (D1.)

### 4.4 Right-bottom — the terminal, and who it may speak for

The brief called this pane maximum-risk and asked what it must never do. **SPEC has already
settled it**, in more detail than the question assumed, and the answer is not "design a terminal" —
it is "render the console foundation that already exists, and add nothing to it."

The governing sentence is `docs/internal/SPEC.md:885`: *"Structured events and durable commands
are authoritative. The raw terminal is a compatibility view."* The implementation reality note at
`SPEC.md:14` is blunter: *"The console foundation has no browser UI and grants no typing
authority."*

What exists today, shipped under CT-I1-021 and already in the HTTP contract:

| Operation | Path | Role in this pane |
| --- | --- | --- |
| `listVisibleConsoleSessions` | `GET /v1/console/sessions` | discovery — what this Actor may view at all |
| `mintConsoleViewGrant` | `POST /v1/console/sessions/{id}/grants` | authority — one grant, one stream |
| `renewConsoleViewGrant` | `POST /v1/console/sessions/{id}/renewals` | continuation, re-evaluating every fact |
| `streamConsoleEvents` | `GET /v1/console/sessions/{id}/events` | the bounded SSE stream itself |
| `allowConsoleSession` / `revokeConsoleSession` / `setConsoleKillSwitch` | `/v1/admin/console/…` | operator-side allowance, revocation, global kill switch |

Every one of them carries `x-ctower-cli: null` and `x-ctower-spool: "forbidden"`: these are
browser-facing, same-origin, never spooled, and deliberately have no CLI equivalent.

The laws the pane inherits, and what each forbids it from drawing:

- **INV-91 — visibility is an exact current-fact join.** A session is visible only when an
  append-only operator allowance joins the authenticated **non-Commander** Actor's exact Project
  grant, seat/crew assignment interval, recorded work session, runtime attempt, runner identity and
  epoch, registered backend reference, live tmux `@project`, and session incarnation. *The
  allowance is eligibility rather than authority* — viewing additionally requires a
  `ConsoleViewGrant` bound to the exact human role binding, browser session, session reference,
  policy revision, and **one stream use**. A grant lasts at most **five minutes**, renewal
  re-evaluates every fact, and one continuous chain lasts at most **thirty minutes**.
  → The pane draws a **grant clock**, not an "always on" terminal. Approaching expiry is a visible
  state, and renewal is a real request that can be refused. A pane that keeps painting after its
  grant lapsed is asserting authority it does not have.
- **INV-92 / AC-CON-04 — output is bounded RESTRICTED custody with typed gaps.** Chunks are at
  most 16 KiB decoded, delivery and replay each bounded to 1 MiB/minute, pending bytes to 256 KiB,
  and *"every unprovable range, truncation, rate limit, or slow consumer appends a gap before it
  is signalled."*
  → **Gaps are rendered inline, in the stream, as a first-class row.** A terminal that silently
  drops bytes and one that saw everything are different claims, and the gap event is the only
  thing that distinguishes them. This is D1 applied to a byte range.
- **AC-CON-05 — plaintext and key values appear in no ordinary row, response, URL, error, log,
  telemetry, or export**, recoverable only through the NOLOGIN `console_output_reader` role, with
  every recovery appending an access fact.
  → The pane offers **no download, no copy-all, no export**. A "copy transcript" button is a
  custody hole with a friendly label.
- **AC-CON-03 — the SSE URL carries no credential**, returns `Cache-Control: no-store`,
  `X-Accel-Buffering: no`, no compression and no CORS authority, and the route accepts only the
  configured exact private Origin, secure human-session cookie, and matching CSRF proof.
- **AC-CON-06 — revocation, expiry, any replacement fence, and the global kill switch close every
  affected stream with a typed reason within five seconds**, and repeated denials suspend the
  Actor.
  → The close reason is **shown**, not swallowed into a blank pane. "The stream stopped" and "your
  grant was revoked" and "the kill switch is on" are three different facts an operator must be
  able to tell apart without opening developer tools.

**What the pane must never do**, stated as the design's own refusals — each one is a line item
absent from AC-CON-07's evidence chain, which is to say each one would invalidate the console
candidate if it appeared:

1. **Never accept a keystroke.** No typing authority (`SPEC.md:14`), no pane write, no shell
   execution, no generic process route (AC-CON-07). Steering goes through the composer as a
   durable input command with a client command ID — §4.2 — never through keystrokes into a pane.
   The pane has no input element at all; there is nothing to disable, because there is nothing.
2. **Never source evidence.** `AC-HAD-06`: no terminal capture, pane text, or session existence
   can fill an evidence slot. A `Create PR` or a proof verdict that reads the terminal is
   forbidden by the same rule that makes `collect` refuse a dirty tree.
3. **Never serve as liveness truth.** `AC-HAD-03` refuses a seat self-report as serving truth;
   `liveness` reads its declared evidence sources or reports `unknown` by name.
4. **Never be reachable other than privately.** AC-CON-07 requires a literal loopback or Tailscale
   bind with an `ss -tlnp` inventory proving no wildcard or public Console listener; Funnel and
   public routes are named absent.
5. **Never show a Commander session.** INV-91 says *non-Commander* engagement. This is a
   discovery-level fact, so the cockpit's rail must not render a Commander terminal tab even
   greyed — a greyed tab discloses that the session exists.

Two smaller pane decisions inherited from what already exists: it keeps **one fixed dark palette
in both app themes** (`src/surfaces/terminal/TerminalPane.tsx` already does this and records why
beside the CSS), and it carries its **redaction mark** inline, because a stream that had a
credential shape redacted out of it and one that never contained one are different claims.

The tab strip mirrors Conductor's `Setup · Run · ● Terminal · +`, but every tab is a *reading*, so
all of them stay live in read-only v1 — the same reason the Chat/Raw and File/Diff switches are
live today.

---

## 5. The crew page: steal the IA, refuse six of the semantics

Paperclip's agent detail is a **nine-tab strip under a persistent identity header** — `Dashboard ·
Instructions · Skills · Configuration · Secrets · Tools · Runs · Audit · Budget` — with the header
carrying `☆ · + Assign Task · ▷ Run Heartbeat · ⏸ Pause · [idle] · ⋯` and a breadcrumb
(`Agents › Commander › Tools`). That skeleton is right and ctower should take it: one persistent
identity, one horizontal tab strip, actions in the header, one breadcrumb. What is wrong is the
semantics, in six specific ways, each of which is a named anti-pattern from the operator's
critique cycle.

Evidence note: §5.1–5.5 are read from the operator's screenshot corpus, and the Configuration tab
is read **first-hand from the live instance** at `http://127.0.0.1:3100/JAK/agents/commander/configuration`
(that tab is absent from the corpus; the operator's grant to browse the live app is what closes
it). Its screenshot is archived beside the corpus as
`live-paperclip-commander-configuration.png`.

### 5.1 Anti-pattern: the hollow-by-default hire, with every page reporting green

Across the corpus the seeded Commander holds **0 skills** (`0 of 5 enabled`, `Enabled on this
agent: 0`), **0 tools** (`Allowed tools — 0 tools`), **0 secrets** (`No secrets are bound to this
agent yet`), **no budget** (`Disabled`, `No cap configured`) — and every one of those pages
reports a positive state: `Saved` on Skills, a green-check `Effective access` banner on Tools,
`HEALTHY` on Budget. The live Configuration tab adds `Configuration Revisions · 0`.

There is no view anywhere that answers *may this agent actually run?* "Saved" answers whether the
form persisted. It is not a readiness claim, but it is the only green on the screen, so it reads
as one.

**ctower's fix — a Readiness verdict that is composed, not asserted.** ctower already has every
component; they have never been assembled into one view:

| Readiness cell | Source of truth |
| --- | --- |
| Survey answered → configure-or-provide decided | the `HarnessSpec` `survey` block; an unanswered survey is a **refusal** (`harness-survey-incomplete`), not a gap, and the candidate does not enter the conformance suite |
| Never both | `AC-HAD-01` — a binding declaring a native layer *and* enabling ctower's own for that layer refuses `harness-layer-conflict` |
| Composition pinned | `HarnessSpec` `key` + `revision` + `artifact_digest` + `config_digest`; unknown, incompatible, revoked or digest-mismatched ⇒ zero dispatch (`AC-HAD-09`) |
| Credential pool selectable | `AC-HAD-10`'s three orthogonal axes, all three clear |
| Guard current | a versioned CommandGuard decision for the exact normalized plan at the final pre-dispatch boundary (`AC-HAD-09`) |
| Liveness observable | the spec's declared `liveness_sources`, or `liveness` returns **unknown by name** (`AC-HAD-03`) |
| Project scope bound | `AC-HAD-05`; a foreign project key returns `project-scope-denied` with zero disclosure |
| Spend priceable | `AC-HAD-12`'s versioned per-model per-direction weight table; stale or missing **refuses rather than silently mispricing** |

Any cell unproven ⇒ the seat is not ready, and the page names which cell and what closes it.
Green is earned by evidence or it is not shown. This is the same discipline as the board's
declared-absence blocks, applied to a seat.

### 5.2 Anti-pattern: the Tools page contradicts itself, on one screen, under a green check

`cmux-drop-60d6d6f1…png`, verbatim, top to bottom:

- ✓ **Effective access** — *"This is exactly the tool set Paperclip will accept for Commander…
  The agent's prompt can narrow this list but **cannot expand it** — everything else is blocked by
  default."*
- **Installed apps** — `Saved` · *"No permitted apps yet. Bind an access profile to make apps
  available here."*
- **Allowed tools** — `0 tools` · *"No tools are allowed for this agent. Bind a tool profile to
  grant access."*
- **Why these tools?** → ACCESS PROFILES: *"No active profile applies to this agent, so it has no
  allowed tools."* → UNAVAILABLE TOOLS: *"**Every known tool this agent could name is allowed.**"*

The last two sentences are in the **same card**, four lines apart: *no allowed tools* and *every
known tool is allowed*. Add the green check at the top and deny-by-default in the banner, and one
viewport carries four statements of which at most two can be true. The final one is almost
certainly an empty-set rendering bug — an empty *unavailable* list phrased as universal
permission — which is exactly why an authority screen must never compute its sentences
independently per card.

**ctower's fix.** One derived allow-list, one screen, one computation. Every row states the rule
that put it there and the rule that could remove it. An empty set renders as `no tools are
allowed` **in the same words in every panel on the page**, and the page has no second panel free
to disagree with the first. If two panels can disagree, the design is wrong, not the copy.

### 5.3 Anti-pattern: authority scattered across five systems, with dangerous toggles ON under a `Standard` preset

Where authority lives in paperclip today, counted:

1. **Trust preset** (`Standard`) — the hire form and the Configuration tab.
2. **Permission grants** — the Configuration tab's own `Permissions` block (`Can create new
   agents`, `Can create/import skills`, `Can assign tasks`), plus *"Advanced permissions remain
   editable through the EE permissions extension when installed."*
3. **Adapter toggles** — `Skip permissions`, `Bypass sandbox`, `Enable Chrome`, `Enable search`,
   on the adapter section of the same page.
4. **Tool profiles and access profiles** — the Tools tab.
5. **API keys** — a separate `API Keys` block, again on Configuration.

Nothing composes them. There is no screen that answers **what may this agent do right now**, and
the one screen that claims to — Tools · *Effective access* — is §5.2.

Worse, they disagree by construction, and the disagreement is live right now:

| Fact | Evidence |
| --- | --- |
| The committed hire default is `dangerouslySkipPermissions: true` | `ui/src/components/agent-config-defaults.ts:11` |
| The adapter reads an unset value as opt-**out**, not opt-in | `ui/src/adapters/claude-local/config-fields.tsx:239` — `config.dangerouslySkipPermissions !== false` |
| The running Commander has `Skip permissions` **on** | live read, `aria-checked="true"` on that switch at `/JAK/agents/commander/configuration` |
| …under a trust preset labelled | `Standard` — *"Company-visible collaboration. This is the default for normal work."* |
| The codex hire form ships the sandbox bypass toggled on | `cmux-drop-3e2ae66c…png` — `Bypass sandbox` green, under the same `Standard` preset |

So the safe-sounding preset ships with permissions off. A preset that names a trust level and a
toggle that silently overrides it are two authorities in one form, and the operator reads only the
one with the reassuring word on it.

**ctower's fix.** Authority is one screen and one word, and the dangerous toggle does not exist —
not defaulted off, *absent*. `AC-HAD-09` makes the guard non-optional: **every** `spawn` obtains
and enforces a current versioned CommandGuard decision for the exact normalized plan at its final
pre-dispatch boundary; `block` and `needs_operator` dispatch nothing; a changed plan, an expired
or replayed grant, or a direct bypass fails closed. A control that could turn that off is a
control ctower may not draw, so there is nothing to default correctly and nothing to get wrong.

### 5.4 Anti-pattern: instructions and config are unversioned walls that two live runs can disagree about

The Instructions tab is a file list (`AGENTS.md` · `ENTRY`) beside a free-text markdown pane
mixing strategy with operational detail (API endpoints, script paths). Its own caveat concedes the
problem: *"Saved instructions affect the next run. Active runs keep the instructions they started
with."* The Configuration tab says the same thing about adapter config — *"Saved adapter config
affects the next run. Active runs keep the config they started with, and config changes may start
a fresh adapter session"* — and then renders `Configuration Revisions · 0`.

So two runs can be executing different instructions and different config, the product knows it,
and nothing on screen names which run pinned which text. There is no version, no diff, no author,
and no link from a run back to the text it ran under. It rots, and nothing detects the rot.

**ctower's fix.** Instructions and config are revision-pinned like every other composition input,
an attempt records the revision it pinned, and the Runs view links each attempt to that exact
revision. This is not a new rule — it is the rule already applied to `HarnessSpec` revisions,
workflow component revisions, and execution policy revisions. Instructions are not a special case.
Paperclip is one field away from this; it already has a revisions counter, it just never
increments it.

### 5.5 Anti-pattern: budget `Disabled` rendering as `HEALTHY`

`cmux-drop-c7731c3f…png`: `AGENT Commander` · `Monthly UTC budget` · `OBSERVED $0.00 / No cap
configured` · `BUDGET Disabled / Soft alert at 80%` · `Remaining · Unlimited` — with a **full-width
progress track** under it and a **`HEALTHY`** badge in the corner. Unconfigured is being rendered
as fine, twice: once in the badge and once in a bar that reads as 100% remaining because there is
no denominator at all. The live dashboard repeats it: `$0.00 Month Spend · Unlimited budget`.

This is D1 with money attached. The third state class is missing, so the *absence* of a limit gets
the same colour as a limit being respected.

**ctower's fix.** No cap configured is `unknown`, not healthy, and it renders through
`--state-unknown` (D1) with no progress track, because a bar without a denominator is a picture of
a number nobody computed. Spend is metered the way `AC-HAD-12` requires: **provider-native credit
units** from the versioned per-model per-direction weight table, attributed **by model × account**,
so *which model on which account drained this plan* is answerable directly. A stale or missing
weight table **refuses rather than silently mispricing**, and a dollar figure computed from a
missing table is never shown at all.

### 5.6 The keepers — three things paperclip gets right

These are lifted, not re-litigated.

1. **Secrets by alias, fetched on demand, never in env.** The Secrets tab, verbatim: *"Env-var
   bindings are injected at run start; API-access bindings are fetched on demand via the run-bound
   agent API and never written to the environment"*, under a heading that says the quiet part —
   `API ACCESS (NO ENV VAR)` — and a footer naming the exact read: *"The agent reads them by alias
   through `GET /agents/me/secrets`."* That matches ctower's credential law directly, including
   `AC-HAD-10`'s *"the Interface exposes **no copy verb**"* and CT-I1-042's minted-never-copied.
   Keep the pattern **and keep the copy** — it is better written than most of ctower's own.
2. **"The prompt can narrow this list but cannot expand it."** That is the right allow-list
   sentence, in the right direction, in one line, and ctower should use it verbatim. Paperclip's
   failure in §5.2 is that its screen does not honour the sentence, not that the sentence is wrong.
3. **Model pinning works when the surface demands it.** The live Configuration tab renders
   `Primary model: Claude Fable 5` — a real pin — and the agents list renders `claude-fable-5` /
   `claude-opus-5` in monospace under each agent, which is Principle 6 applied correctly. The
   capability is present and right. It is simply not the *default*: the hire form ships
   `model: ""` (`agent-config-defaults.ts:8`), which renders as `Default`. Pinning is a defaults
   decision, and paperclip has already made it correctly once — on the page where an operator can
   see it.

### 5.7 The resulting tab strip

Keep the IA — persistent identity header, breadcrumb, one horizontal tab strip, actions in the
header — and rename the tabs to what ctower can actually prove:

| ctower tab | Replaces | Carries |
| --- | --- | --- |
| **Readiness** | Dashboard | the eight composed cells of §5.1; no aggregate green without all eight |
| **Authority** | Tools + trust preset + adapter toggles + permission grants | one derived allow-list: project scope, writeback fact classes (`capture` / `transition` / `evidence`), tool allow-list, guard decision |
| **Composition** | Configuration | `harness_ref` **and** the runtime/profile reference carrying credential lineage (CT-I1-043: a model is not a harness), pinned model, `revision` + both digests |
| **Credentials** | Secrets | pool entries by decoded identity, three axes, per-account reset clocks, aliases only, no copy verb |
| **Instructions** | Instructions | revision-pinned, with the attempts that pinned each revision |
| **Runs & evidence** | Runs + Audit | attempts with their pinned composition and their collected artifacts (committed refs only) |
| **Spend** | Budget | credits by model × account in native units, raw tokens alongside, refusal on a stale weight table |

Nine tabs to seven, and every one answers a question an operator actually has.

---

## 6. The harness setup wizard

The operator asked to *"run harness setup wizard"* in the UI. Paperclip's three New Agent forms
(`cmux-drop-57c873e0…` claude-code, `cmux-drop-3e674814…` hermes, `cmux-drop-3e2ae66c…` codex) are
the shape to avoid, and the reason is precise: same page, three adapters, and in every one of them
the operator is handed a **runtime configuration dump** — `Command`, `Execution engine (Auto (ACP
preferred))`, `Max turns per run`, `Timeout seconds`, `Interrupt grace period`, `Toolsets`,
`Prompt template`, `API URL`, `Extra args (comma-separated)`, `Environment variables`, plus
toggles: `Persist session`, `Checkpoints`, `Quiet output`, `Verbose output`, `Hermes worktree
mode`, `Enable Chrome`, `Enable search`, `Fast mode`, `Bypass sandbox`, `Skip permissions`.

Four defects, each already named:

1. **`Default` offered as a model.** An unpinned composition, shipped as the default
   (`model: ""`). ctower cannot dispatch an unpinned composition at all: `AC-HAD-09` fails closed
   on an unknown or digest-mismatched spec, and CT-I1-042's failover-as-new-attempt rule is
   meaningless without a pin to diff against.
2. **`Skip permissions` / `Bypass sandbox` defaulted ON under a `Standard` trust preset** (§5.3).
3. **A runtime-config dump instead of questions.** The form asks *what flags shall I pass*. The
   right question is *what is true about this harness*, and ctower already has that question set
   as authored contract data.
4. **No credential-pool concept anywhere.** The only credential surface on the hire form is
   `Environment variables`, with the hint *"Set the KEY to the env var name the process expects,
   for example GH_TOKEN"* — a per-seat env var, which is exactly the shape `API ACCESS (NO ENV
   VAR)` elsewhere in the same product correctly rejects.

A fifth, visible in the harness picker (`cmux-drop-282bb981…png`): nine cards — Claude Code,
Codex, Cursor, Cursor Cloud, Gemini CLI, Grok Build, Hermes, OpenCode, Pi — all rendered as
equally-real, equally-selectable harnesses, two of them badged `Recommended` and none of them
carrying any registration state. Offering a harness with nothing behind it is how a stub becomes
an Adapter by accident.

**What is right and should be lifted:** the entry modal's three honest paths — *"Ask the CEO to
create a new agent" / "Configure a runtime manually" / "Invite an external agent"* — and the
harness picker's card grid with icon, name and one-line description. That is good form ergonomics.
Drive it with ctower's questions instead of a flag dump.

### 6.1 The steps

**1 · Who.** Seat name, role, reports-to. Paperclip's `Agent name` / `Title (e.g. VP of
Engineering)` / `Reports to…` — unchanged, it works.

**2 · Harness.** The card grid, but every card carries its **registration state**, and a card that
cannot register is shown **refused with its reason** rather than hidden. CT-I1-044 supplies the
four classes and its own worked examples:

| Card state | Meaning | CT-I1-044's example |
| --- | --- | --- |
| registered | survey answered, binding implemented, conformance suite passed | `hermes`, `claude-code` |
| surveyed, not bound | answers exist, no Adapter yet | `openclaw` — gateway-routed, two approval planes, readiness proven by preflight assertions and *never inferred from a successful invite*; `qwen-code` — a legal baseline value with a weekly-plan quota and a known reset |
| stub | *"a table row is not an Adapter"* | `zcode` |
| not a harness | a model reached through a profile that already has both layers; the correct amount of adapter work is **zero** | `deepseek` |

An unsurveyed candidate is refused here, by name, with the missing answers listed — *"an
unanswered survey leaves that choice undecidable, which is a refusal rather than a gap."* Hiding
it would be worse: the operator would ask for it again next week.

**3 · The survey, if it is not already answered.** This is authored, revision-pinned contract data,
not free text, and the exact field set is `contracts/runner/harness-spec.schema.json`, whose
`survey` definition lists all eight as **required**:

`native_pool` · `native_fallback` · `config_surface` · `identity_proof` · `reset_semantics` ·
`rotation_cache` · `subagent_inheritance` · `egress_topology`

Two further answers CT-I1-044 counts in the same set live elsewhere in the contract and the step
must still collect them, because a spec without them cannot probe or price:

- **probe target** — its own required block: `product` · `endpoint` · `model_ref` ·
  `workload_shape` · `classified_on`. `AC-HAD-11`: a probe aimed at a different model reports
  `unknown` for the seats' rung rather than that rung's state.
- **per-model per-direction credit weights** — the registry's versioned weight table (`AC-HAD-12`),
  not a `HarnessSpec` field; a stale or missing table refuses rather than mispricing.

The answers, **never the harness's name**, decide whether ctower **configures** a layer or
**provides** it, and the step renders that derived `layers` table (`pool` / `fallback`, each
`configure` or `provide`) as it fills in. Two refusals fire live in this step, and both are already
deterministic registration vectors in `contracts/runner/harness-spec-vectors.json`:

- `harness-survey-incomplete` — remove one answer (the vector removes `survey.egress_topology`)
  and the role becomes undecidable.
- `harness-layer-conflict` — **never both**: declaring a native layer *and* enabling ctower's own
  for that layer refuses (`AC-HAD-01`). The vectors prove it in both directions, for `pool` and
  for `fallback`, and prove the mirror case too: an absent native layer declared as `configure`
  has nothing to configure.

Showing these refusals as the operator types is the whole point of the step. The wizard is not
collecting preferences; it is filling in a document that the registry will accept or refuse, and
it should refuse in the same words the registry will.

**4 · Composition.** Model is **required**; there is no `Default`. Reasoning effort and the
declared `context_window_percent` sit beside it. Where the survey answered `config_surface:
authored_config_only` — `hermes` spawns through a profile directory whose own config owns model
and reasoning effort — these fields render **read-only with their source named**, because an
editable control over a value ctower does not own is a lie (§4.2c). The step ends by showing the
`artifact_digest` and `config_digest` that will be pinned, in mono (D6).

**5 · Credentials.** A pool, not an env var. Entries keyed by **decoded identity, never by label**,
each showing its three orthogonal axes and its own reset clock:

- `auth ∈ {healthy, lineage-dead, chain-burned}`
- `quota ∈ {available, capped(reset_at), capped(reset_unknown), unfunded, unknown}`
- `reach ∈ {ok, edge-challenged, unknown}`

Selectable only when all three are clear, with **no path collapsing them** into one word. A
`discovered` identity renders non-selectable pending an explicit operator keep-or-evict. There is
**no copy control anywhere on this step**, because the Interface has no copy verb — this is the
same law as the Secrets keeper in §5.6, and it is the reason ctower can adopt paperclip's copy
without adopting its env-var habit. If no entry is selectable the wizard refuses here in the
`credential-pool-exhausted` shape — `observed`, `meaning`, `action`, per-entry three-axis states,
and the earliest known reset or an explicit `unknown` — rather than creating a seat that will fail
at its first `spawn`.

Note the axis that most UIs would collapse and `AC-HAD-10` forbids collapsing: an entry can be
`auth: healthy`, `quota: available`, `reach: edge-challenged`. It is not dead and it is not out of
credits; it cannot be reached. Routing it to a mint or a rotation because the badge said "problem"
is precisely the failure the three axes exist to prevent, so the pane shows three marks, never one.

**6 · Authority.** One screen, one allow-list: project scope, writeback fact classes
(`capture` / `transition` / `evidence`), tool allow-list — in the direction paperclip states
correctly, *the prompt can narrow this list but cannot expand it*. No permissions toggle exists
(§5.3). Facts outside the three classes refuse by name with zero mutation (`AC-HAD-05`), so the
list is closed, and the screen says so.

**7 · Review and register.** The composition digests, the `HarnessSpec` key and revision, the
survey answers and the `configure`-vs-`provide` roles they produced, the selected pool entry, and
the allow-list. The register control is a real `disabled` control until every cell is proven, and
it names the exact missing answers **on the control** (D5) — the treatment `New ticket` already
gets in read-only v1.

Paperclip's `Test Agent` button is a good idea and should be kept, with ctower's meaning: a
**dry run through the guard**. It obtains a CommandGuard decision for the normalized plan and
reports it, **dispatching nothing** — which is the honest version of "test", and is directly
buildable because `AC-HAD-09` already requires that decision at the final pre-dispatch boundary
for real dispatches.

The result is paperclip's ergonomics — a card grid, a short form, a review step, an explicit test —
carrying ctower's questions instead of a flag dump. Nothing in it is a new law, and every refusal
it can show is one the seam already owes.

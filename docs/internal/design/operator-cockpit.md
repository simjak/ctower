# The operator cockpit — design (R3109)

**Status:** design proposal. Non-normative.

This document proposes; it does not approve. `docs/internal/SPEC.md` remains the only place that
may activate scope, `docs/internal/DECISIONS.md` the only place that may record a decision, and
this file adds a row to neither. R3109 has no stable CT ticket, so nothing here is buildable
product behaviour yet — the constitution puts product behaviour out of scope until its ticket and
dependencies are active. What this file is for is that when R3109 does earn a ticket, the design
argument is already made, already checked against the seam contract, and already carries its
citations.

Companion artifact: `operator-cockpit.html` beside this file — one static mockup, openable
directly from disk with no build step and no network fetch. It carries three boards: the four-pane
cockpit; the crew page's seven tabs (§5.7) with its Readiness verdict rendered; and the mint's
**state sheet** (§6.1.1) — all eleven states and six typed failures at once. Both themes
are live; the theme toggle exists so a reader can check the one-seed `color-mix` claim of §3
rather than take it on faith. Every hard state the doc argues for is drawn deliberately — the
disabled composer, a turn in `durability pending`, a `capped` lane outranking its timer, a
`dead_auth` lane carrying its failing axis and its probe age with no `reap` control at all (D9),
a workspace `not reached`, the PR handoff naming its dirty paths, a console gap row,
the tenant-wide console kill switch in the top bar rather than in the pane it stops, and
`no cap configured` rendered as unknown with no progress track.

The mint is drawn as a *sheet* rather than a hero screenshot on purpose: the states this design
argues about — an unknown work-list, a ceremony stalled three days, a binding recorded but not
selectable, an observation that contradicts the binding — are exactly the ones a single chosen
frame leaves out. Drawing them together also makes the screen's one hard guarantee checkable by
reading the DOM: three kinds of string about a credential ever reach it — a provider key, a
decoded subscription identity, and an alias — and no state, refusal, tooltip or `title` attribute
carries a fourth.

**The mockup is deliberately hard to read cold, and that is D9.** After the operator's verdict it
was stripped of every sentence explaining why a state is drawn the way it is. Those sentences are
in this document, at the section that owns each screen; nine of them that an operator would need
at the pixel became one-line `(i)` affordances. Read the two together: the mockup shows what an
operator sees, and this file is where the argument lives.

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
`apps/ctower-web`, and §7.6 says why it may not arrive there by accretion.

**Three of the four panes land on that boundary unchanged. The console pane does not, and this is
the one structural constraint in this document that changes the build order.** Every read the
other three panes need authenticates with `bearerAuth` and can therefore be made server-side by a
browser holding nothing — `readPoolLimits`, `listSpawnRecords`, `listProjectSessions` and the
inbox operations are all in that class.

The console operations are **not one plane, and the path prefix is the split**. The authored
OpenAPI puts four operations under `/v1/console/…` with `"security": [{"browserSession": []}]`
plus the `ConsoleCsrf` header parameter — `listVisibleConsoleSessions` (`:120`),
`mintConsoleViewGrant` (`:136`), `renewConsoleViewGrant` (`:159`), `streamConsoleEvents`
(`:181`) — and three under `/v1/admin/console/…` with `"security": [{"bearerAuth": []}]` and no
CSRF parameter at all: `allowConsoleSession` (`:50`), `revokeConsoleSession` (`:75`),
`setConsoleKillSwitch` (`:99`). **The browser boundary belongs to the four-operation viewer
plane, not to all seven.** That is where `AC-CON-02` binds each grant to *"one exact Actor, human
role binding, browser session, policy revision, Project, and console session"*, consumed by **at
most one stream**; a browser that holds no session cannot be the browser a grant is bound to. §9's
slice 4 is where the viewer lands, and §7.2 is why the earlier reading of `AC-CON-03` was wrong.

The three admin operations sit in the same bearer class as the other three panes' reads, so the
correct statement is not "the console pane is blocked" but **which of its controls is blocked, and
why each one is**:

| Admin operation | Reachable server-side from the credential-free cockpit? | The actual constraint |
| --- | --- | --- |
| `setConsoleKillSwitch` | **Yes, today.** `bearerAuth`, and `ConsoleKillSwitchRequest` is only `{enabled, reason}` — no console session, no browser session, nothing the cockpit cannot supply. | None. This is the one console control the cockpit can build in slice 1. The same empty scope decides where it is drawn: it stops every stream in the tenant, so it belongs in the top bar rather than in the console pane — §4.4. |
| `revokeConsoleSession` | Authorized, but **id-starved**. `bearerAuth` and a `{reason}` body, but the `console_session_id` lives in the path. | A programmatic walk of the authored surface finds exactly two producers of a `console_session_id`: `listVisibleConsoleSessions` (browser plane) and `allowConsoleSession`'s own `201 ConsoleSessionAllowance` (the runner's registration echo). A credential-free browser can therefore authorize a revocation it cannot name. Revoke rides in with the viewer, not before it. |
| `allowConsoleSession` | Authorized, and **not an operator control at all**. | `ConsoleSessionAllowRequest` requires fifteen runner-side fields — `adapter_key: "tmux-v1"`, `runner_epoch`, `runtime_attempt_id`, `backend_incarnation`, `opaque_backend_ref`, `seat_principal_id`, `assignment_interval_sequence` and the rest. That is a registration payload the runner already holds; no cockpit screen composes it, and none should. It is excluded from this design as a non-UI operation, not deferred. |

So one control ships in slice 1, one rides with the viewer in slice 4, and one is out of scope.
That is a sharper build order than the pane-wide block, and it comes from reading the security
block per operation rather than per feature.

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
| Motion | Two tiers, and the rule is about **components**, not about tokens: *"Any new motion in the redesigned thread MUST reference one of these tokens — no hardcoded ms / cubic-bezier in components (enforced by a check script)."* Tier one is the primitives — `--motion-duration-{instant,fast,base,slow,deliberate}` = 80/160/240/360/520ms plus two house curves (`--motion-ease-out-expo: cubic-bezier(0.16,1,0.3,1)`, `--motion-ease-standard: cubic-bezier(0.4,0,0.2,1)`). Tier two is 21 scoped tokens, and the split is **counted, not characterised**: nine reference a primitive (`--motion-tool-enter`, `--motion-cot-collapse`, `--motion-diff-reveal`, …) and twelve carry a literal — ten durations (staggers `40ms` ×2, loops `1.6s`/`1.1s`, one-offs `380ms`, `240ms`, `4000ms`, `200ms`, `400ms`, `320ms`) and two scoped easing curves. The reduced-motion block is where the two tiers show: it zeroes the five **primitives**, *"Zeroing the primitives cascades to every scoped token that references them; the literal-valued scoped tokens (staggers, loops) are zeroed explicitly"*, and nine of the ten literal durations are in fact listed there — every one except `--motion-interstitial-dwell`. | `index.css:216–219` (the component rule), `223–231` (primitives), `233–254` (scoped), `551–573` (reduced motion) |
| Components | shadcn `new-york`, `baseColor: neutral`, `cssVariables: true`, lucide icons. | `ui/components.json` |

**What the source does not say — and the cockpit's own rule in its place.** `index.css` never
states *why* twelve scoped tokens hold a literal instead of referencing a primitive. It is not a
"no primitive fits" rule and this design does not claim one on the file's behalf: at least one
literal is numerically identical to a primitive — `--motion-line-scroll: 240ms` (`:248`) against
`--motion-duration-base: 240ms` (`:229`) — so that reading is disprovable from the same file. The
only stated intent around those values is mechanical and applies to both tiers equally: they are
*"tunable placeholders the human tunes live via the tweak panel, then pastes back"* (`:214–215`)
and the scoped block is *"grouped for the tweak panel"* (`:233`).

So the cockpit needs a rule of its own, and this is a **design decision made here, not a citation**:
a cockpit scoped token references a primitive by default, and may carry a literal only when the
value is not a movement duration at all — a stagger step, a loop period, or a pacing hold. Anything
that is "how long this thing takes to move" must resolve to `--motion-duration-*`, so that retuning
the five primitives retunes the cockpit. Owning this explicitly also fixes the maintenance cost the
counterexample exposes: a literal that duplicates a primitive silently stops tracking it. The
enforceable half is paperclip's, verbatim and already checked by a script there — no hardcoded
ms/cubic-bezier **in components** — and the cockpit adopts that check as-is.

One motion detail is worth carrying verbatim because the cockpit will hit it: paperclip's
reduced-motion block deliberately does **not** zero `--motion-interstitial-dwell`, and says why —
*"it is a pacing hold, not a movement — zeroing it would make the interstitial line churn faster
under reduced motion"* (`index.css:567–569`). The cockpit's own holds — how long a `durability
pending` chip sits before it resolves, how long a gap row stays legible before the stream scrolls
past it — are pacing, not animation, and a reduced-motion reader needs them *more*, not less.

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

**D9 · The copy budget — counted, not encouraged.** Operator verdict on the first mockup, verbatim
(2026-08-21): *"too much texts, which adds noise."* It is the only delta on this list sourced from
a look at the rendered artifact rather than from a law, and it is the one that changed the most
pixels.

The root cause is worth stating plainly because it is a trap any design doc with a companion
mockup will fall into: **the mockup was rendering its own rationale.** Every state carried the
sentence explaining why that state exists — reviewer-facing prose, shipped inside the
operator-facing artifact. That prose was written to survive a review, and it did; it just had no
business being on screen. D5 already forbade it in principle. A principle was not enough, because
each individual sentence looked justified as it was written. So D9 is a **budget**, and a budget is
countable:

| Element | Budget |
| --- | --- |
| Chip | **≤ 2 words.** `dead · auth`, `not reached`, `capped`, `discovered`. Not a sentence with a border on it. |
| Field hint | **≤ 1 line.** If the field needs two, the field is wrong. |
| Empty state | **1 sentence + 1 action.** Paperclip's own is the model: *"No secrets are bound to this agent yet."* followed by `+ Add API access`. |
| Error | **Fact + next action.** Zero philosophy. *"No binding by that alias. Check the name."* — not why aliases exist. |
| Rationale | **Never renders.** It lives in this document, or behind an `(i)`. |

**Two rules the operator's second pass added, both about words rather than counts.**

*Name a thing by what it does, not by the repository's word for it.* The change list grouped files
as **collectable** / **uncollectable** — correct against `AC-HAD-06`, and unreadable: the operator
asked what they meant. They are now **Committed** / **Uncommitted**, which is the fact an operator
already owns, and the consequence — *only committed work can be used as evidence* — is the `(i)`.
The dead lane's `Nudge` and `Re-mint` became **Wake** and **Sign in again ↗** for the same reason.
A label that needs the design doc to decode it has failed, however precise it is.

*A key is drawn once, not once per row.* The rail's state marks are **icon-only**; the legend at
the foot of the pane is the key. The word stays in the DOM for a screen reader and in `title` for a
pointer, so nothing is lost — it stops being drawn seven times. This is the general form: when a
vocabulary is small, closed, and legended, the glyph alone carries it in the list.

**The budget governs chrome, never content.** A transcript turn, a terminal pane's bytes, and a
lane's own prose are the *lane speaking*; they are the thing the operator opened the cockpit to
read, and truncating them would be the redaction the console design already forbids. What the
budget constrains is everything **ctower** says around them — labels, chips, hints, empty states,
errors, banners. The test is authorship: if ctower wrote the sentence, it is on the budget.

**What `(i)` is, and what it is not.** One affordance, one line, on hover or press. It is not a
disclosure triangle over a paragraph, and it is not a place to put the sentence that failed the
budget. **If the explanation does not fit one line, it is not UI — it is documentation**, and it
belongs in this file where a reader can follow its citations anyway. An operator at 3am needs
**state, fact, action**; the argument for why that state is drawn the way it is has a different
audience and a different artifact.

**The budget also settles a refusal question this document had left inconsistent.** §4.1 says the
dead row *"must not offer `reap`"*; the first mockup drew `reap` as a disabled button carrying
`AC-HAD-07`'s refusal as its label. Both cannot be right, and applying the budget decided it:

- **Refused by law, for this state, always** → **not a control.** It is a rule. Rules live in this
  document, with an `(i)` at the pixel if an operator would otherwise hunt for a control that is
  never coming. A permanently-refused action drawn as a disabled button is the rationale habit
  wearing a border — and worse, it teaches the operator that the action exists. `reap` on a
  `dead_auth` lane is this class.
- **Absent because something missing could arrive** — an operation not built, an authority not
  held, a precondition not met → **drawn disabled with its reason**, because the reason is
  actionable and the gap is a hole somebody will otherwise fill. The console `Terminal` tab in
  slice 1, the mint's state 4b, and the `not-authorized` refusal are this class.

The test between them: *could this control ever be enabled for this operator on this row?* If no,
it is a rule; if yes, it is a disabled control.

Two consequences worth naming, because they are what the budget costs:

1. **The mockup stops teaching.** It gets harder to read cold, and a reviewer must hold this
   document beside it. That is the correct trade — the mockup's job is to show what an operator
   sees, not to defend itself.
2. **Nothing is deleted, only moved.** Every sentence the budget removed from a screen is in this
   document at the section that owns that screen. The de-noising commit moved text; it lost no
   argument. Where a rule genuinely needed to stay reachable from the pixel, it became an `(i)`.

This delta binds the mockup and every surface built from it, including the three boards' own
future states. It is the one rule here an implementation can be checked against by counting — and
the mockup is checked that way rather than asserted. Parsing the rendered DOM with `<style>` and
`<script>` stripped, a separator glyph not counted as a word, and lane-authored regions
(`.bubble`, `.term`, `.think-body`, gap and redaction rows) excluded as content:

| Check | Result at `operator-cockpit.html` |
| --- | --- |
| Chips ≤ 2 words | 44 chips, **0 over** |
| ctower-authored strings > 60 chars | **0** |
| `(i)` titles | 9, longest **102 chars** — all one line |

Any surface built from this design should carry the same three counts, and a screen that cannot
pass them is a screen with an argument on it.

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

Five rules make this rail honest:

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
- **A dead lane is drawn as dead.** `dead_auth` is a first-class value in the seam's own
  vocabulary, and the rail owes it a distinct treatment — §4.1.1.
- **Every state carries the time it was observed**, and past its freshness bound it becomes
  `unknown` rather than stale — §4.1.2.

#### 4.1.1 The dead lane

`LivenessState` is a closed seven-value list — `working`, `idle`, `queued_stuck`, `saturated`,
`capped`, `dead_auth`, `unknown` — and `NOT_WORKING` holds six of them
(`packages/ctower-runner-sdk/src/ctower_runner_sdk/facts.py:28–36`). `dead_auth` is the one a
cockpit is most likely to draw wrong, because it is the one the substrate hides best: the
credential lineage behind the lane is gone, and the harness's own surface keeps rendering a
normal footer with an advancing timer. It is the same class of failure as the capped pane above,
and it needs the same rule — classification before motion.

It is a *fourth* thing, distinct from its three neighbours in the rail, and collapsing any pair
of them costs the operator the next action:

| The row says | What is true | What closes it |
| --- | --- | --- |
| `capped` | the account passed login and refused work; quota is spent for this window | nothing: *"wait for the provider's own reset — no ceremony adds quota"* (`credentials.py:68–71`) |
| `dead · auth` | login itself is gone: `auth: lineage-dead` (the grant expired, *"the shell may still say logged in"*) or `auth: chain-burned` (a copied file replayed a single-use refresh token and the provider revoked the whole chain) | a **mint** — and only ever this profile's own device flow, *"never copy another profile's file"* (`credentials.py:60–67`) |
| `not reached` | the read did not answer; this lane's state is **unknown**, not dead | a working probe (`AC-HAD-03`) |
| absent | there is no lane | nothing |

So the row carries four things: the state, the probe and its observation age, the failing axis of
the pool entry the lane was riding, and the action from the pool's own meanings table — never a
generic "error".

**What the row must not offer is `reap` — and not as a disabled control either (D9).** `AC-HAD-07` is explicit: `reap` *"refuses a `dead_auth`
lane, which is preserved for resume, with one nudge offered before any replacement."* A dead lane
still holds uncollected work, and a UI whose first affordance on a dead row is *kill and respawn*
is drawing an action the seam refuses — the same error as a spinner over a capped pane, one step
more destructive. The primary control is the nudge; the mint is the real fix; a replacement
control appears only after the nudge has been offered and declined. The refusal itself is a rule
rather than a disabled button: it reaches the pixel as the row's `(i)`, and the row's two controls
are the two that work.

**Both controls are labelled by what they do, not by ctower's word for it.** The operator asked
what *Nudge* and *Re-mint* meant, which is the label failing rather than the operator: `nudge` and
`mint` are this repository's internal vocabulary. They render as **Wake** and **Sign in again ↗**.
The arrow is load-bearing — it says the login happens outside ctower, which is D72's ask-never-
perform rule showing up as a glyph instead of a sentence.

**And the composer's capability rule alone does not cover this case.** `input_refusal`
(`policy.py:144–159`) refuses only when the lane is `working` and the binding declares no
`INTERRUPT_AND_RESUME` — `dead_auth` is in `NOT_WORKING`, so the capability check returns *no
refusal* and would let a message through into a lane that cannot serve it. That check is
necessary and not sufficient. The composer's derived state (§4.2a) therefore reads capability ×
liveness *and* the selected entry's `auth` axis, and on a dead lane it disables send with the
mint action on the control. This is a design decision rather than a law, and it is marked as one:
the seam refuses a destructive delivery, not a futile one.

#### 4.1.2 Every state carries when it was observed

A liveness state without its observation time is a claim about *now* made from evidence of unknown
age, and the rail is the surface where that costs the most: it is a wall of state chips an
operator scans in one glance and trusts by default. The merged seam already carries what is
needed — `LivenessFact.observed_at` and `probe`, plus a `served_model` with its own `source`,
`proves` and `observed_at` (`facts.py:40–47`, `55–68`) — and the fact's own comment names the
reason freshness is a classification input rather than a display detail: *"a lane past its window
cannot be trusted to still hold the evidence it cites"* (`facts.py:31–36`).

Three rendering rules follow:

- **Every positive state names its source and its age**, on the chip's hover rather than in the
  row (D5 — a number's derivation lives in that number's hover). `working · gateway_log · 4s` and
  `working · gateway_log · 6m` are different claims about the same word.
- **Past its freshness bound, a state becomes `unknown` — it does not become stale.** This is
  §7.5 applied to time: an old observation is a source that answered once and is not answering
  now, which is exactly the shape `AC-UX-03` sends to `STATE UNKNOWN`. The rail never draws a
  greyed or faded `working`; there is no such state.
- **The freshness classification is server-applied**, arriving in the read as part of the fact's
  own basis, never computed by the browser from a timestamp. The same rule as the composer's
  enabled state (§4.2a): one function, one source. A browser-side staleness clock is a second
  classifier for a fact the seam already owns, and two classifiers over one fact is the
  disagreement this repository refuses everywhere else.

`served_model` gets the same treatment for a different reason: `ModelObservation.proves` is
`serving | request | observation`, and `AC-HAD-03` records a source proving only the *request* as
a **conflict, never as serving truth**. So the model chip renders what was served, its source, and
its age — and when `proves` is not `serving`, it renders the conflict rather than the value.

### 4.2 Centre — the transcript, and the steer question the brief asked

**Backend: neither of the two verbs a first reading reaches for.** This is the pane whose backend
mapping is easiest to get wrong, so it is stated before anything is drawn.

- **Not `writeback` for outgoing turns.** `writeback(attempt, seat, seat_credential, facts)` files
  `capture` / `transition` / `evidence` facts **as the seat**, and `AC-HAD-05` refuses an adapter
  presented with an operator or commander credential. An operator message routed through it would
  invert the credential boundary and forge a seat's own filing. `input_refusal` is a **policy
  predicate**, not a transport.
- **Not `collect` for incoming ones.** `collect` returns an `ArtifactSet` — `branch`, `head_sha`,
  `pushed`, gate-output paths, an optional status path, a `Handoff`
  (`packages/ctower-runner-sdk/src/ctower_runner_sdk/facts.py:113–127`). No turns, no text, no
  thinking, no tool rows, no interrupts. There is no "`collect` transcript path"; that phrase was
  wrong in an earlier draft of this document.

What *does* exist, one layer below the seam: D10's Supervisor Interface already owns process
control — *"`probe`, `launch`, `observe`, `deliver_input`, `interrupt`, `terminate`, `snapshot`,
`adopt` — and that vocabulary is not reopened here"* (`seam.py:1–9`). `spawn` already delivers the
initial brief through `deliver_input` and keeps the durable command ID it answers with
(`apps/ctower-runner/src/ctower_runner/hermes/binding.py:108`), and `observe` already returns
captured pane text — *harness-private* text that `AC-HAD-08` forbids any kernel, projection, CLI
or Board path from parsing.

So the centre pane's two backends are both **real work at the seam layer, not routes over merged
verbs**, and §8.2's G3 and G4 say what each one costs. The design below is written against what
those two would have to provide, which is the useful thing a design can do before the contract
exists: it constrains the vocabulary rather than inventing it.

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
`packages/ctower-runner-sdk/src/ctower_runner_sdk/policy.py:144–159` — `input_refusal` returns
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
(`policy.py:162+`) carries the reason: *"A fix that is not committed is not a fix, and an audit
that reads the working tree cannot tell the difference."* Therefore:

- The change list separates **committed** from **uncommitted** rows visibly. They are different
  claims, and only one of them a successor can read.
- The `Checks` tab shows the gate verdicts that exist and `not reached` where a gate was not run.
  It does not compose an aggregate "passing" out of a partial set. (D1.)

#### `Create PR` is a handoff, not a ctower mutation

Conductor draws `Create PR` in the window chrome and it reads as a button that makes a pull
request. ctower may not draw that button, and the reason is a law rather than a missing route:
its GitHub connector holds **no pull-request authority in either direction**. `AC-GH-03` scopes
every installation token to *"only Issues write and Metadata read"* and fails closed on broader
grants; `AC-GH-07` states *"Only issues are ingested. Pull requests are excluded"*
(`SPEC.md:4817`, `SPEC.md:4821`). The authored HTTP surface agrees — across all 104 operations
the only change/PR-adjacent mutation is `recordTicketChangeReference`, which records a reference
that **already exists**. §8.2 prices the alternative rather than leaving it implied.

So the control is designed as what it can honestly be:

- **It opens the provider's own compare page** for the collected branch and head, in a new tab.
  ctower creates nothing and asserts nothing about the outcome.
- **Two independent facts gate it, and they fail differently.** The tree must be *clean* —
  `AC-HAD-06`, where a dirty tree returns `checkpoint-uncollectable` naming the dirty paths —
  **and** the branch must be *pushed*, which is `ArtifactSet.pushed` beside `branch` and
  `head_sha` (`packages/ctower-runner-sdk/src/ctower_runner_sdk/facts.py:113–127`). A clean but
  unpushed tree and a dirty tree are different failures with different next actions, so they are
  two disabled reasons, never one. Each is named *on the control* (D5) — the treatment
  `New ticket` already gets in read-only v1 — not in a page banner.
- **After the operator opens the PR, its reference is recorded** through
  `recordTicketChangeReference` and rendered through §7.1's durability discipline:
  `ChangeReferenceResult` carries `durability_state` and `command_id`, so the row reads
  `durability pending` until the projection folds, and never "PR opened" because the composer
  cleared.
- **No read exists for the pull request's state**, and the cockpit does not invent one. It
  renders the recorded reference and nothing more. `AC-UX-06`'s forbidden words — done,
  released, live — have no source on this surface at all (§7.6), which is the cheapest possible
  way to satisfy that rule.

### 4.4 Right-bottom — the terminal, and who it may speak for

The brief called this pane maximum-risk and asked what it must never do. **SPEC has already
settled it**, in more detail than the question assumed, and the answer is not "design a terminal" —
it is "render the console foundation that already exists, and add nothing to it."

The governing sentence is `docs/internal/SPEC.md:885`: *"Structured events and durable commands
are authoritative. The raw terminal is a compatibility view."* The implementation reality note at
`SPEC.md:15` is blunter: *"The console foundation has no browser UI and grants no typing
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

1. **Never accept a keystroke.** No typing authority (`SPEC.md:15`), no pane write, no shell
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
5. **Never draw a terminal tab for any lane discovery did not return.** INV-91 says *non-Commander*
   engagement, so a Commander terminal tab must not be rendered even greyed — a greyed tab
   discloses that the session exists. The same rule covers every other lane, and it is worth
   stating because it looks like a designer's choice and is not: `AC-CON-01` requires that *"only
   an operator-allowed, standard-loop, RESTRICTED, current non-Commander engagement appears in
   discovery"* and that *"every mismatch is a typed no-disclosure refusal or absence"*, and the
   only browser discovery operation is the collection `listVisibleConsoleSessions` — there is no
   per-lane existence probe and there may not be one. So the client **cannot** distinguish "no
   backend session exists" from "a session exists and this Actor may not see it", and drawing a
   `not reached` terminal for an absent lane would leak exactly the difference the refusal
   erases. Absent from discovery ⇒ no tab, for every lane, Commander included.
   `not reached` is correct only after an *authorized* read was attempted and its source failed
   (§4.1) — which is why the two look similar and are not the same fact.
   One thing this rule does **not** forbid, because it is a different kind of absence: the
   pane-wide "this boundary cannot reach the console at all" treatment of §9's slice 1. That
   states a fact about *this surface* and discloses nothing about any lane — no lane list, no
   existence claim, no per-lane difference. Per-lane silence and surface-wide disclosure of the
   surface's own limits are compatible, and keeping them apart is what lets the cockpit be honest
   about the boundary without leaking a single session.

Two smaller pane decisions inherited from what already exists: it keeps **one fixed dark palette
in both app themes** (`src/surfaces/terminal/TerminalPane.tsx` already does this and records why
beside the CSS), and it carries its **redaction mark** inline, because a stream that had a
credential shape redacted out of it and one that never contained one are different claims.

The tab strip mirrors Conductor's `Setup · Run · ● Terminal · +`, but every tab is a *reading*, so
all of them stay live in read-only v1 — the same reason the Chat/Raw and File/Diff switches are
live today.

One scheduling fact belongs with this pane rather than only in §9, and it applies to the **viewer**
rather than to the pane's whole operation set. The four `/v1/console/…` operations — discovery,
grant, renewal, stream — each require a browser holding a human session and a CSRF token, which
this cockpit's boundary withholds (§2, §7.2). Everything drawn above is therefore implementable
today as *operations* and not today as a *viewer*. Until that decision lands, the `Terminal` tab is
drawn present and declared-absent with the reason on it — §9's slice 4 states the options and their
cost. Nothing in the pane's design changes either way; only when it can run.

**The kill switch is the exception, and it ships first.** `setConsoleKillSwitch` is
`bearerAuth` with a `{enabled, reason}` body and no session of either kind in it (§2's table), so
it is reachable from the credential-free boundary in slice 1 — before any viewer exists.

**Where it goes is decided by its request body, not by its subject matter.**
`ConsoleKillSwitchRequest` is `{enabled, reason}` — it names no console session, no lane, no
Project. It stops every console stream in the tenant. So it is drawn in the **cockpit's own top
bar**, beside the instance identity, and *not* in the console pane: a tenant-global stop placed
inside one lane's fourth pane reads as scoped to that lane, and an operator who believes a global
control is local will use it wrongly in exactly the situation it exists for. The rule generalises
past this one control — **a control's blast radius is whatever its request body scopes it to, and
that is where the design must place it.** It carries its current state, its reason, and who set
it, with `AC-CON-06`'s five-second close semantics stated on the confirm. Two rules come with
shipping it early. It is a
**mutation with a required reason**, so it follows `AC-UX-09`'s pending-until-durable rule (§4.2b) like every
other write — an operator who flips it must see `durability pending` and then the accepted state,
never an optimistic toggle. And when it is on, the declared-absent `Terminal` tab says *the kill
switch is on*, not *no boundary* — an operator turning off every stream and then reading "this
pane cannot run here" would be told the wrong cause of their own action.

Revocation does **not** ship with it. It is bearer-authorized but needs a `console_session_id` the
credential-free boundary has no way to obtain (§2), so its control is drawn only in slice 4
alongside the discovery list that names the session. `allowConsoleSession` gets no screen at all:
its request is a fifteen-field runner registration payload, which is the runner's to compose.

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
| Credential pool selectable | `AC-HAD-10`'s three orthogonal axes, all three clear **on at least one entry**. `acquire` *"fails only when every entry is unselectable"*, and the criterion's own fixture is a mixed pool that acquires from its healthy entry and reports three distinct clocks — so this cell is proven at `selectable_entry_count > 0`, and a blocked sibling entry keeps its own warning without lending it to the verdict |
| Guard current | a versioned CommandGuard decision for the exact normalized plan at the final pre-dispatch boundary (`AC-HAD-09`) |
| Liveness observable | the spec's declared `liveness_sources`, or `liveness` returns **unknown by name** (`AC-HAD-03`) |
| Project scope bound | `AC-HAD-05`; a foreign project key returns `project-scope-denied` with zero disclosure |
| Spend priceable | `AC-HAD-12`'s versioned per-model per-direction weight table; stale or missing **refuses rather than silently mispricing** |

Any cell unproven ⇒ the seat is not ready, and the page names which cell and what closes it.

One trap inside that rule, because a composed verdict is exactly where it bites: **composing is
not aggregating.** The credential cell is the case — a pool holding one healthy entry beside two
blocked ones is *ready to acquire*, and rendering it as a failure teaches the pool-level
collapse `AC-HAD-10` forbids and the `PoolLimitsView` schema names in its own description
(*"a pool holding two exhausted entries and one near-full entry is not one word"*). Each entry
keeps its own warning; the cell answers only its own question. A verdict that inherits every
sibling's worst state is the mirror image of paperclip's `HEALTHY` — pessimism instead of
optimism, and wrong in the same way: not derived from the rule it claims to apply.
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
| **Credentials** | Secrets | pool entries by decoded identity, three axes, per-account reset clocks, aliases only, no copy verb; the drift list with each `missing` row's enactment path, and the mint ask, reference binding and keep-or-evict decision that close it (§6.1.1) |
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

#### 6.1.1 · Step 5b — the mint, which is the wizard's most safety-critical screen

Selecting from a pool that already has an entry is the easy half. A setup wizard whose job is to
stand up a *new* seat will routinely meet a pool that has nothing selectable for the model this
seat needs, and the brief asks for **credential-reference mints** by name. That screen is where
the credential law is either kept or lost, so it is designed explicitly rather than left to the
refusal above.

**The seam already fixes almost all of it, and the constraint is unusual: ctower asks, and never
performs.** `CredentialPool` exposes `request_mint(identity) -> MintRequest` and no copy verb
(`packages/ctower-runner-sdk/src/ctower_runner_sdk/credentials.py:1–7`, `193–199`, `293–294`), and D72 states the
rule twice: new credential material enters *"only through `request_mint`, which the pool may ask
for and never perform"*, and *"Pool membership stays operator-owned in every class: ctower
acquires, meters, and reports, and never mints an entry, refills credits, or raises a plan;
reaching a credential is not entitlement to it."* So this screen is not a form that creates a
credential. It is a screen that states a request, hands the ceremony to the operator, and then
waits for an observation to prove it happened.

**What the screen reads.** The work-list is already served: `readPoolLimits` returns
`PoolProfileLimits.drift`, and each `PoolDriftFinding` carries `finding ∈ {missing, unregistered}`,
`provider_key`, `subscription_identity`, `enactment` and `detail`. `AC-HAD-12` fixes the meaning —
a desired-but-absent subscription is `missing` and *"routed to its declared enactment path
(`operator-ceremony` for OAuth grants, `secret-reference` for API keys), never reported as
ordinary unavailability or silently dropped from the chain"*. The wizard therefore does not invent
a mint list; it renders the reconciliation the registry already computed, in the registry's own two
classes.

**Two ceremonies, drawn differently, because their custody differs.**

| `enactment` | What the operator does | What ctower's browser ever holds |
| --- | --- | --- |
| `operator-ceremony` | performs that profile's **own** device flow, in the harness's own tooling, on the host | nothing. No code, no token, no file path carrying material. The screen shows which provider and which decoded identity is wanted, and a *done* control that **re-reads `readPoolLimits` and nothing more** |
| `secret-reference` | supplies a **reference** — the alias the secret already has in the secret store | the alias string only. The field is typed as a reference and rejects a value-shaped input by name rather than accepting and storing it |

**The `operator-ceremony` path's *done* control cannot start an observation, and the screen must
not imply it does.** The only observation operation on the authored surface is
`recordPoolObservation` (`POST /v1/pools/observations`), whose `PoolObservationRequest` is
`harness_key`, `profile_key`, `observed_at` and the full observed `entries` list — a report by
whoever exercised the pool. A browser has observed nothing and must never compose one; a cockpit
that POSTs an observation it did not make is inventing the fact the whole three-axis design exists
to protect. So *done* re-reads `readPoolLimits`, and the screen states the truth on it: the
identity appears when the pool is next observed, with `PoolProfileLimits.observed_at` rendered as
the age of the last sweep. **That is why the OAuth path needs no new operation at all** — and it
is also why the screen's terminal state is a wait rather than a success.

The `secret-reference` field is the single most dangerous input in the whole cockpit, and it gets
the wizard's only typing-time refusal: a value that parses as credential material is refused with
*"secrets are references, never values"* rather than saved. §5.6's keeper is the same rule in
paperclip's better words — bindings are *"fetched on demand via the run-bound agent API and never
written to the environment"*, read *"by alias"*.

**The command that field submits to is not `request_mint`, and an earlier draft of this section
conflated the two.** `CredentialPool.request_mint(identity) -> MintRequest` takes the subscription
identity and nothing else, and `MintRequest` is exactly `provider_key`, `subscription_identity`,
`enactment` (`credentials.py:193–199`, `293–294`). It is a **question** — *what ceremony does this
identity need?* — and the answer is already served: `PoolDriftFinding` carries that same triple on
every drift row. So the request content was never the gap. The gap is that **the alias has no
consuming command anywhere on the authored surface** — a walk of all 104 operations finds only
`readPoolLimits` and `recordPoolObservation` touching the pool, and neither accepts a reference.
A field whose value nothing consumes is not an input; it is decoration on a safety-critical screen.

Two operations follow from that, and they are separate because they are different acts with
different failure modes — not because two is tidier:

- **G8 · record the mint ask.** The drift row already says what is needed; what it cannot say is
  whether anyone has been asked for it. "Nobody has looked at this" and "an operator was asked
  three days ago and it still has not landed" are different operational states, and a **stalled
  ceremony** is one of the states this screen must draw. G8 carries no material in either
  direction, which is what makes it addable at all.
- **G8b · bind a secret reference.** The `secret-reference` path's only consuming command, and the
  one that makes the screen end-to-end. It accepts `{provider_key, subscription_identity,
  secret_alias}` and returns a typed outcome or a typed refusal.

**G8b's shape, stated so it can be reviewed rather than assumed:**

| | |
| --- | --- |
| **Request** | `provider_key`, `subscription_identity` (the decoded identity, never a label), `secret_alias`. **Body only** — never a path segment or query parameter, because those reach access logs, and a reference in a log is a pointer to a secret with a permanent breadcrumb next to it. |
| **Authority** | Operator principal over ctower's own API. Explicitly **not** a seat credential: `AC-HAD-05` refuses an operator credential presented *at an adapter*, and the mirror of that rule is that a seat's credential has no business performing an operator's pool registration. This is the same principal class as G8's ask and G9's keep-or-evict, and those three are the pool's only operator writes. |
| **Idempotency** | Re-submitting the same `(identity, alias)` pair is the same fact, not a second entry — the pool is keyed by decoded identity, so a repeat is a no-op that returns the existing binding. Submitting a *different* alias for an already-bound identity is a **replacement**, and it is refused rather than silently applied: replacing a reference is a decision with a `chain-burned` failure mode behind it (§6.1.1's rule 1), so it is G9's evict-then-bind, not an edit. |
| **Outcome** | `bound` — carrying back the stored alias, the decoded identity, and the resulting `registration_state: discovered`. **The alias shown on the screen after submit is the one the server echoed, never the one the browser still holds in its input**, so what the operator reads is what was actually recorded. |
| **Refusals** | Typed and named, never a generic failure — enumerated in the failure table below. |
| **What it never returns** | Any credential material, any part of one, or any indication of whether the alias resolves to a working secret. That last one is deliberate and is the subtlest rule here: *"does this alias work?"* is only answerable by exercising the credential, which is an observation, and this operation performs none. Answering it would turn a binding into an oracle. |

**The screen, end to end.** Every state below is drawn, including the ones a default UI skips.
The two enactment paths share the first three states and the last three; only the middle differs.

| # | State | What is on screen | How it is reached / left |
| --- | --- | --- | --- |
| 0 | **Work-list unknown** | `drift: unknown` with the probe named — *not* an empty list. | `readPoolLimits` did not answer. This is D1's `unknown` applied to a work-list: an unanswered read and a proven-empty pool are different facts and a mint screen that shows an empty table for both will let an operator conclude there is nothing to do. |
| 1 | **Empty, and proven** | *"No missing subscriptions in this profile · pool observed 40s ago"*, with `PoolProfileLimits.observed_at` as the age. Never *"All clear"* (`AC-UX-03`). | `drift` returned and contains no `missing` row. The observation age is what makes the emptiness meaningful — an empty drift list computed twenty minutes ago is a weaker claim than one computed now, and the screen shows which it has. |
| 2 | **Needed, unasked** | one row per `missing` drift finding: provider, decoded identity, and the `enactment` badge that decides which ceremony follows. Primary control: *What does this need?* | `AC-HAD-12` routes a desired-but-absent subscription to its declared enactment path. The screen renders the registry's reconciliation; it never computes its own. |
| 3 | **Asked** | the ceremony instructions for that row's `enactment`, plus `asked 3d ago by <actor>`. | G8. The `asked` stamp is the whole reason G8 exists; without it state 3 and state 2 look identical forever. |
| 3s | **Asked, stalled** | the same row, with the age promoted from a caption to a stated condition: *"asked 3d ago · still missing at the last observation"*. No new fact — the same two timestamps, drawn as the operational state they add up to. | Left by the identity arriving at state 6, or by an operator abandoning the row. A ceremony that quietly never completes is the most likely real failure on this screen and the one no error state would ever fire for. |
| 4a | **`operator-ceremony` · waiting** | which provider, which decoded identity, and that the ceremony runs in the harness's own tooling on the host. A *done* control that re-reads and nothing more. **No code, no URL, no file path is displayed** — the device flow is not ctower's to render. | Left by an observation reporting the identity. |
| 4b | **`secret-reference` · reference wanted** | one field, labelled *alias in the secret store*. It is a **plain text field, never a masked one.** Masking is the tell that a UI expects a value; this field expects a name, and a password dot-mask would teach the operator to paste the wrong thing. Helper text names the format the store uses, and the submit control is disabled until the field is non-empty. | Left by submit, or by the typing-time refusal below, which never leaves the browser. |
| 5 | **Submitting** | `durability pending` on the row, with one stable client command ID preserved across reload (`AC-UX-09`, §7.1). The field is read-only, not cleared — a cleared field on a pending write is how an operator retypes a reference they already sent. | G8b acknowledged, or a typed refusal, or the durability timeout in the failure table. |
| 6 | **Bound — the reference is shown, and it is not a success** | the **echoed alias**, the decoded identity, and `registration_state: discovered`. The row states plainly: *"recorded · not selectable · awaiting first observation"*. There is no green, no check mark, and no word *minted*. | The pool's next observation. |
| 7 | **First observation** | the identity appears as a real `PoolEntryState` with all three axes and its own `observed_at`. **Only `auth` may have moved** (`AC-HAD-10`); if `quota` is still `capped`, the row says so and stays non-selectable, naming the axis that is now blocking. | G9. |
| 8 | **Keep or evict** | the `discovered` entry with both decisions offered, keyed by decoded identity. | G9 records it: `enrolled` and selectable, or removed. **This** is the screen's success state, and it is three states after the operator finished typing. |

**The failures, each typed and each drawn.** A safety-critical screen with one generic error state
has no failure design at all.

| Failure | Where it fires | What the screen does |
| --- | --- | --- |
| **value-shaped input** | in the browser, as the operator types | Refuse with *"secrets are references, never values"*. **The input is never sent, never stored, and never echoed back into the DOM** — including into the error message, which is the classic way a rejected secret ends up in a screenshot, a log, or a bug report. The message names the shape that matched, not the text that matched it. |
| **alias-unknown** | G8b | *"the secret store has no binding by that alias"*. The row stays at state 4b with the field editable. This is the one refusal an operator can fix by retyping. |
| **enactment-mismatch** | G8b | this identity's declared enactment is `operator-ceremony`; a reference is not what it wants. The screen should make this unreachable by never drawing the field on such a row — it is enumerated because a refusal that is only prevented client-side is not prevented. |
| **already-bound** | G8b | a different alias is already bound to this identity. Refused, not applied, with the existing alias named and the exit stated: evict through G9, then bind. |
| **not-authorized** | G8b / G8 | the principal is not an operator. Stated as an authority refusal on the control, not as a failed submit — a control an operator may not use is drawn disabled with its reason (D5, D9) — this is the class that could become enabled, so it is a control rather than a rule. |
| **durability not acknowledged** | after state 5 | the row stays `durability pending` and says so. It does **not** flip to bound, and it does **not** silently retry — §7.1, and the live P1 that rule comes from. |
| **observation reports `chain-burned`** | state 7 | the ceremony completed and the chain was already consumed — the copied-`auth.json` failure in rule 1 below, arriving three states after the mistake. The row names the axis and offers no re-bind, because re-binding the same reference reproduces it. |
| **observation reports a different decoded identity** | state 7 | the alias resolved to material for another identity. This **cannot** be caught at submit — nothing but an observation decodes the identity — so it is drawn here rather than promised earlier, and the binding is surfaced for evict. A screen that claimed to validate the alias at submit time would be claiming exactly this check. |

**Five things this screen must never draw**, each absent because a verb is absent:

1. **No paste-an-`auth.json`, no upload, no "copy from another entry".** There is no copy verb, and
   the reason is in the Interface's own docstring: *"OAuth refresh tokens here are single-use
   chains, so installing a copied auth file replays a consumed token and the provider revokes the
   whole chain — every grant derived from that login dies at once."* A copy control is not a
   convenience here; it is the `chain-burned` state with a button on it.
2. **No mint control on an `edge-challenged` entry.** `AC-HAD-10`: a mint moves **only the `auth`
   axis**, *"so an `edge-challenged` entry is never routed to a mint, rotation, or restart"*. The
   control is absent with its reason, not present-and-failing.
3. **No claim that the mint fixed quota or reach.** Same rule, drawn: after a mint the screen
   re-renders all three axes and only `auth` may have moved. An entry that is now `auth: healthy`
   and still `quota: capped` is not ready, and the screen says which axis is still blocking.
4. **No "minted" success state.** The ceremony completing is the operator's claim, not an
   observation. The entry enters as `registration_state: discovered`, which `AC-HAD-10` makes
   **non-selectable pending an explicit operator keep-or-evict**, and it is keyed by *decoded
   identity, never by label*. So the screen's terminal state is `awaiting first observation`, and
   the seat cannot be registered on it — which is the same discipline as §7.1's `durability
   pending`, applied to a credential.
5. **No secret value, anywhere, in any state.** Not in a field, not in a confirmation, not in an
   error message, not in a tooltip, not in a `title` attribute, and not masked-but-present in the
   DOM. The screen renders exactly three kinds of string about a credential: a **provider key**, a
   **decoded subscription identity**, and an **alias**. That list is closed, and it is short enough
   to check by reading the rendered DOM — which is how it should be checked, because the one
   guarantee worth having here is one an implementation can be tested against rather than promised.

**Three operations do not exist for this, and §8.2 counts them.** The read half is served
completely — work-list, ceremony class, entry axes, observation ages. All three missing writes are
operator-owned: recording the ask (G8), binding the reference (G8b), and the keep-or-evict that
turns a `discovered` identity into an `enrolled` one or removes it (G9). The `operator-ceremony`
path needs none of them to *reach* an observation, because its ceremony happens entirely outside
ctower — it needs only G8 to stop looking identical to an untouched row.

**Until G8b exists, state 4b renders the field disabled with its reason on it**, not absent and not
enabled-and-failing: *"recording a reference needs an operation this API does not have yet"*. That
is the same treatment as the console `Terminal` tab in slice 1 — both are D9's could-arrive class,
and it is chosen for the same reason — an absent control is a hole somebody fills, and an enabled
control over a missing command is a lie the operator only discovers after typing a reference.
Everything else on this screen is drawable today: states 0, 1, 2, 4a, 6 and 7 all read from
`readPoolLimits` alone, so the screen is usable and honest before any of the three land.

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

---

## 7. The laws that bind this UI

Six. Each one has already changed a drawing decision above; this section is where they are stated
once so a later reader does not have to re-derive them from the panes.

### 7.1 Projection lag — a send is pending until the projection folds

A write is invisible to every read API until durability is accepted **and** the projection is
folded. A surface that mutates and re-renders once will not show its own write, and rendering the
pending answer as sent is a live P1 in this codebase's history, not a hypothetical.

`AC-UX-09` is the binding form: a browser command remains visibly `unsent` or `durability
pending` until authoritative acceptance, preserves one stable command ID across disconnect and
reload, and **never paints optimistic state as accepted**; retry, refusal and quarantine must be
distinguishable without inspecting developer tools.

The contract already carries the field — `SessionReceipt` has `durability_state` alongside
`command_id` — so this is a rendering discipline, not a new backend concept. Two consequences the
cockpit must honour: no chat runtime with optimistic local echo (D7), and the harness's own
`ack_predicate` (`composer_cleared`) is **not** ctower's acceptance (§4.2b).

### 7.2 Record-tier isolation — the browser talks only to the API

The constitution: *"Runner, provider, web, CLI, extension, and YAML packs never connect to
record-tier persistence."* `apps/ctower-ui` goes further than required, and should keep going
further: its browser *"receives no API bearer, no session and no credential of any kind; every
read happens server-side."*

It is why D8 stops the paperclip port at the token layer: paperclip's client-fetching data layer
assumes a browser that holds a credential, and this one does not.

**And it is the constraint that decides the console pane's schedule, which an earlier draft of
this document got wrong.** `AC-CON-03` says the *"SSE URL contains no credential"* — that is a
rule about the **URL**, not about the browser. The same criterion requires, in the same sentence,
*"the configured exact private Origin, secure human-session cookie, and CSRF proof matching its
cookie and persisted digest."* A cookie and a CSRF token are credentials the browser holds. So
"credential-free URL" and "credential-free browser" are two different claims, and only the first
one is true of the console contract. §9's slice ordering is derived from this, not from the
console pane's risk profile alone.

### 7.3 TypeScript is browser-only

The constitution's hard boundary: *"Python: trusted control plane, runner, CLI, release helper.
TypeScript: browser only."* So the cockpit's dependencies (D7) are browser dependencies, and
nothing in this design proposes a TypeScript service, a Node data layer, or a second process. The
`liveness` classifier, the guard, the pool, and the transcript collector are Python on the control
plane; the cockpit renders their answers.

### 7.4 The phase ladder — design against the seam contract, not against tmux

`tools/checks/expected-suites.toml` states the ladder, and the numbers matter:

| Phase | Position in `phase_order` | Status |
| --- | --- | --- |
| `CT-I1-013` (shared authentication foundation) | 18 of 38 | **before** the active phase — active |
| `CT-I1-021` (console foundation) | 26 of 38 | **before** the active phase — active |
| `CT-I1-027` | 28 of 38 | `active_phase` |
| `CT-I1-041` (seam + `hermes`) | 37 of 38 | merged, phase not active |
| `CT-I1-042` (`claude-code`) | 38 of 38 | merged, phase not active |
| `CT-I1-043`, `CT-I1-044` | absent from the ladder | not started |

Read that column again, because it is half the sequencing argument in §9 in one table: **the
terminal pane's backend is already activated, and the chat pane's backend is nine phases out.**
Suite status is derived from the ladder rather than chosen, so the seam's conformance suites are
deferred today; they prove the adapter *code*, not a live dispatch path.

The other half is not in this table, and reading only this table is what put the console pane
second in an earlier draft. `CT-I1-013` is active too, so the *human session* the console routes
require is a solved and shipped foundation — but it is shipped for a browser that holds a session,
and this cockpit's browser holds nothing (§2, §7.2). A phase being active makes an operation
callable; it does not make it callable *from here*.

The design consequence: the cockpit is designed against the **seam contract** — the five verbs,
the capability vocabulary, the refusal names — and never against the mission-control tmux
plumbing that currently runs live crews. Building against tmux would produce a surface that has to
be rewritten the day the phase advances, and would tempt exactly the shortcuts (`pane text as
truth`, `keystrokes as steer`) that `AC-HAD-03` and `AC-HAD-06` exist to forbid.

### 7.5 A read that did not answer is not a read that returned zero

`AC-UX-03`: degradation flips the relevant views to `STATE UNKNOWN`, and *no test case displays
"All clear."* ctower-ui already enforces the distinction structurally — a `Reading` is unwrapped
only in `frame/Declared.tsx`, so *"a source that exists and did not answer is never rendered as one
that does not exist."*

This is D1's law form, and it is the single rule that most of §5's anti-patterns violate:
paperclip's `HEALTHY` over `No cap configured`, its `Every known tool this agent could name is
allowed` over an empty set, its unbounded `Remaining` bar. Every one of them is an absent
denominator rendered as a satisfied one.

### 7.6 The cockpit is not a sixth primary route

`AC-UX-01` fixes the product's primary-surface inventory at exactly Home, Board, contextual/direct
Ticket detail, Fleet, and Analytics, with global navigation holding only the four non-contextual
destinations. The cockpit lands on `apps/ctower-ui`, which is explicitly a non-product boundary
(§2). If it is later proposed for the product surface it enters as Fleet's contextual detail or as
a SPEC amendment. **It may not arrive by accretion.**

Related copy law for anything the cockpit renders about delivery: `AC-UX-06` requires the exact
facts `merged`, `staging verified`, `production verified`, `rolled back`, `incident`, and forbids
calling a merge-only state done, released, or live. The `Create PR` / `Checks` corner of §4.3 is
where a cockpit would be most tempted to say "shipped".

---

## 8. Gap list: what exists, and what is genuinely new work

The contract holds **104 operations** today (`tests/contracts/http/test_codegen.py:29` —
`_EXPECTED_OPERATION_COUNT = 104`). This section splits them against the four panes so nobody
scopes a build without knowing which half they are in.

### 8.1 What already exists and is reused

| Cockpit need | Existing operation / schema | Notes |
| --- | --- | --- |
| Terminal pane, end to end | viewer plane: `listVisibleConsoleSessions`, `mintConsoleViewGrant`, `renewConsoleViewGrant`, `streamConsoleEvents` · admin plane: `setConsoleKillSwitch`, `revokeConsoleSession`, `allowConsoleSession` | Seven operations, already active (§7.4), and **no new operation is needed**. It is *not* pure UI work, but the blocker is per-plane rather than pane-wide: the four `/v1/console/…` viewer operations carry `"security": [{"browserSession": []}]` and the `ConsoleCsrf` parameter, so they need a browser holding a human session — which this cockpit's boundary deliberately does not give it (§2, §7.2). The three `/v1/admin/console/…` operations are `bearerAuth` with no CSRF parameter and are in the same reachable class as every other pane's reads; `setConsoleKillSwitch` is buildable in slice 1, `revokeConsoleSession` waits only for an id the viewer produces, and `allowConsoleSession` is a runner registration payload with no screen. For the viewer, the missing piece is a boundary, not a route. |
| Left-rail lane rows | `listSpawnRecords` / `getSpawnRecord` (`GET /v1/spawn-records`, filterable by `project_key`, `status`) | `SpawnRecord` already carries `project_key`, `seat_key`, `crew_name`, `worktree_path`, `harness`, `model`, `effort`, `workspace_id`, `status` — the row shape the rail needs |
| Lane state transitions | `appendSpawnTransition` (`POST /v1/spawn-records/{spawn_id}/transitions`) | |
| Crew session registry | `listProjectSessions`, `listTicketSessions`, `startTicketSession`, `recordTicketSessionFact` | `TicketSession` carries `crew_name`, `harness_ref`, `model_ref`, `branch_ref`, `state`, `outcome`, token counts |
| Durability rendering (§7.1) | `SessionReceipt.durability_state` + `command_id` | the field exists; the UI has to respect it |
| **Credentials tab and wizard step 5 — the whole *read* half** | `readPoolLimits` (`GET /v1/pools`) | `PoolEntryState` already carries `auth_state`, `quota_state`, `quota_reset_at`, `reach_state`, `selectable`, `registration_state`, `subscription_identity`, `credit_state`, `metered_millicredits`. `PoolProfileLimits` adds `selectable_entry_count`, `earliest_known_reset_at`, and `drift`, whose `PoolDriftFinding` rows already carry `finding` and `enactment` — so even the *mint work-list* is served. The schema's own description states the no-aggregate rule: *"a pool holding two exhausted entries and one near-full entry is not one word."* **No new operation needed to read.** The three writes the wizard needs are G8, G8b and G9 (§6.1.1) — and only G8b carries anything the operator typed. |
| **Spend tab** | the same `readPoolLimits` — `weights` (`PoolModelWeight`) + `topology_revision` | the versioned weight table `AC-HAD-12` requires is already in the read |
| Pool observation write | `recordPoolObservation` | |
| Chat plane, correspondents, threads | `listInboxThreads`, `readInboxThread`, `sendInboxMessage`, `ingestInboxNotification`, `listInboxCorrespondents`, `readInboxMessageState`, `acknowledgeInboxMessage`, `promoteInboxThread` | the existing composer/thread surfaces in `surfaces/chat/` bind to these today |
| Board, tickets, timeline, evidence | `getBoard`, `getTicket`, `getTicketTimeline`, `listTicketAuditEvents`, proof and workflow operations | the right-hand pane's ticket context |
| Shell, tokens, marks, tree badges | `apps/ctower-ui` (§2) | |

The honest headline: **the terminal pane, the spend surface and every *read* the credentials
surface needs already exist as operations.** That is not a small finding — it is most of the
wizard's hardest step and the whole of the highest-risk pane. Two qualifications keep it honest,
and both are elsewhere in this document rather than buried here: the credentials surface still
needs three operator-owned **writes** (G8, G8b, G9 — §6.1.1), and the terminal pane's **four viewer
operations** are unreachable from this cockpit's *current* browser boundary, which is a boundary
problem rather than an operation problem (§9, slice ordering). The pane's other three operations
are `bearerAuth` and reachable today; §2 says which of them earns a control and when.

### 8.2 What does not exist — ten operations, and what each one costs

Each row is real work, because the contract is a **closed world**. Adding one operation to
`contracts/http/openapi.yaml` is not the single edit point it looks like; it requires:

1. `tools/codegen/_inventory.py` → `EXPECTED_OPERATIONS` (and `EXPECTED_SCHEMAS` per new component
   schema), or `tools.codegen --write` aborts with an unexpected-operation-set error;
2. `tests/contracts/http/test_openapi.py` → `_EXPECTED_OPERATION_METADATA`, the exact
   cli/mutation/spool/principal/refusal-only tuple;
3. `tests/contracts/http/test_codegen.py` → `_EXPECTED_OPERATION_COUNT` (currently `104`);
4. `tests/contracts/http/test_scalar_profile_codegen.py` → `AUTHORED_OPERATION_COUNT` (currently
   `97`) — the one that is updated separately and fails on its own afterwards;

plus, wherever the operation carries a non-null `x-ctower-cli`, a real `ctowerctl` command (parser
subparser, name list, and the area module's query/mutation builders). The console operations are
the precedent for the alternative: all seven carry `x-ctower-cli: null` and
`x-ctower-spool: "forbidden"`, which is the correct shape for a browser-facing cockpit read.

| # | Missing operation | Pane | Why nothing existing covers it |
| --- | --- | --- | --- |
| G1 | **Read a lane's liveness** — the whole `LivenessFact`: `state`, `probe`, **`observed_at`**, `context_used_pct`, `conflict`, `ladder`, `evidence`, and a `served_model` carrying its own `source`, `proves` and `observed_at` | left rail (§4.1), composer gating (§4.2a) | `SpawnRecord.status` is a durable lifecycle status, not an observation of the substrate. `AC-HAD-03`/`AC-HAD-04` semantics — precedence, `substrate-unobservable:<probe>`, conflict-not-truth — have no HTTP surface at all. This is the single most load-bearing gap: without it the rail cannot honour "capped outranks working." **Carry the timestamps or the rail cannot tell current evidence from old motion**: `LivenessFact.observed_at` and `ModelObservation.{source, proves, observed_at}` already exist on the merged fact (`facts.py:40–47`, `55–68`), and dropping them is how a five-minute-old `working` keeps painting as now — §4.1.2. |
| G2 | **Read the harness registry** — registered `HarnessSpec` key, revision, digests, declared `capabilities`, `context_window_percent`, `liveness_sources`, survey answers and derived `layers` | composer gating (§4.2a), Readiness (§5.1), Composition tab, wizard steps 2–4 | The specs exist as Python constants and contract JSON. Nothing serves them over HTTP, so the browser cannot derive the composer's enabled state from declared capability — and a UI-local guess is exactly what §4.2a forbids. |
| G3 | **Read a lane transcript** — ordered turns with role, thinking blocks, tool rows, interrupt facts, elapsed, and each turn's durability state. **Two layers, not one: a seam-side typed turn fact set, then the HTTP read over it.** | centre (§4.2) | No transcript operation exists, and no *seam* path exists either. `collect` returns an `ArtifactSet` (`facts.py:113–127`) — branch, head, pushed, gate outputs, handoff — with no turn in it, and `observe` returns harness-private pane text that `AC-HAD-08` forbids any kernel/projection/CLI/Board path from parsing. `listTicketAuditEvents` is a typed audit stream, not a harness transcript. So the binding must first project typed turn facts across the seam — which is open question 1's vocabulary and a **contract decision** — and only then does a route have anything to serve. Costing this as a route alone is the mistake this row exists to prevent. |
| G4 | **Send input to a lane** — a durable input command with a client command ID, refused per `input_refusal` when the lane is `working` and the spec declares no `INTERRUPT_AND_RESUME`. **Two layers again: a seam-level post-spawn input path composed over D10's `deliver_input`, then the HTTP route.** | composer (§4.2) | The five merged verbs have no lane-input method: `spawn` launches *and* delivers the initial brief, `writeback` files seat-authored facts (`AC-HAD-05` refuses an operator credential at an adapter), and `input_refusal` is a policy predicate rather than a transport. What already exists is one layer down — `SupervisorPort.deliver_input(attempt, text) -> durable command id` (`hermes/substrate.py:39`), which `spawn` already uses. The new path must **compose over it, never duplicate it**: `seam.py:1–9` names a second process-control vocabulary at the harness layer as the two-authorities-for-one-fact mistake. It also needs the ACK rule (`AC-HAD-02`: steer counts as acknowledged only on the returned durable command ID) and the principal decision of open question 2. `sendInboxMessage` is not a substitute: it is the tenant-wide comms plane, never evaluates a project grant, and would bypass the capability check entirely. |
| G5 | **Read a workspace change set** — per-file `+N −N`, committed vs uncommitted separated, dirty paths named, plus the `ArtifactSet` triple `branch` / `head_sha` / `pushed` and the repository's own web origin | right-top (§4.3) | `recordTicketChangeReference` is a write. The `+N −N` badges in `apps/ctower-ui` today come from server-side git reads in `src/read/sources/`, which is fine for an operator surface over a local checkout and is not an API. `AC-HAD-06`'s committed-only rule needs to be enforced *in the read*, not in the renderer. The push state and the web origin are what gate and address the `Create PR` handoff below; without them the control cannot tell a clean-unpushed branch from a clean-pushed one, which are different failures. |
| G6 | **Register a harness / submit a survey** — the wizard's write, returning `harness-survey-incomplete` / `harness-layer-conflict` / `harness-spec-incompatible` verbatim | wizard step 3 and 7 (§6) | The refusal vectors exist as test data (`harness-spec-vectors.json`); no operation performs the registration. Blocked on CT-I1-044 regardless. |
| G7 | **Dry-run the guard** — obtain a CommandGuard decision for a normalized plan and return it, dispatching nothing | wizard step 7's `Test Agent` (§6.1) | The guard is invoked at the pre-dispatch boundary inside `spawn`. Exposing a decision-only path is a deliberate new operation, and it is the one place a "test" button can be honest. |
| G8 | **Record that a mint was asked for** — stamp a `missing` drift row as asked, by whom and when | wizard step 5b (§6.1.1), Credentials tab (§5.7) | Not the request *content*: `PoolDriftFinding` already carries the whole `MintRequest` triple (`provider_key`, `subscription_identity`, `enactment`), so `request_mint`'s answer is served today. What has no HTTP surface is the **ask itself** — `request_mint` is an Interface method on `CredentialPool` (`credentials.py:293`) with none, and `recordPoolObservation` is a sweep of observed entries rather than a record of a request. Without it, an untouched row and a three-day-stalled ceremony render identically forever (§6.1.1 states 2, 3, 3s). D72 constrains its shape hard — ctower asks and never performs — so this is an operator-principal write whose result is a *stated request*, never material. It carries no secret in either direction, which is what makes it addable at all. |
| G8b | **Bind a secret reference to a pool identity** — `{provider_key, subscription_identity, secret_alias}` in the body, returning the echoed alias and `registration_state: discovered`, or a typed refusal | wizard step 5b (§6.1.1) | The `secret-reference` enactment path's only consuming command, and the reason an earlier draft's mint screen was not end-to-end: it asked the operator for an alias that **nothing on the authored surface accepts**. A walk of all 104 operations finds exactly two touching the pool — `readPoolLimits` and `recordPoolObservation` — and neither takes a reference. `request_mint` is not it either: its signature is `request_mint(identity)` and its return is the triple (`credentials.py:193–199`, `293–294`), so it is the question, not the answer's destination. Distinct from G8 in authority failure mode, idempotency and refusal set (§6.1.1). Carries a *reference*, never material — which is the only reason a credential write belongs on an HTTP surface at all. The `operator-ceremony` path needs no counterpart: its ceremony completes outside ctower and arrives through the pool's next observation. |
| G9 | **Keep or evict a `discovered` identity** — the operator decision that turns an observed identity into an `enrolled` entry or removes it | wizard step 5b, Credentials tab | `AC-HAD-10` makes a `discovered` identity *"non-selectable pending operator keep-or-evict"* and `AC-HAD-12` says the same of a present-but-undesired `unregistered` entry. No operation records that decision, so today the state is reachable and its exit is not. Operator-only, keyed by **decoded identity** rather than label — a keep-or-evict routed by label is the mislabelled-entry fixture that criterion exists to catch. |

Two of the ten (G6, G7) are blocked on tickets that have not started. Three (G8, G8b, G9) are
operator-owned credential writes that carry no secret in either direction and depend on no
unstarted ticket — they are gated only by the pool's own phase.

The remaining five split, and the split matters more than the count. **G1, G2 and G5 are routes
over facts the merged seam already produces** — `LivenessFact`, `HarnessSpec`, `ArtifactSet` — so
for them, phase activation genuinely is the only gate. **G3 and G4 are not.** Each needs a seam-
layer capability that does not exist yet, and each carries an unresolved decision underneath it:

| Gap | What the merged seam supplies today | What must exist first |
| --- | --- | --- |
| G3 transcript | nothing at turn level — `collect` returns artifacts, `observe` returns harness-private text `AC-HAD-08` forbids anyone else parsing | a typed turn/thinking/tool/interrupt fact vocabulary crossing the seam — **open question 1**, a contract decision |
| G4 lane input | `deliver_input` at D10's Supervisor layer, already used by `spawn`; `input_refusal` as a predicate; `STEER_DURABLE_COMMAND_ID` as a declared capability | a seam-level post-spawn input path composing over `deliver_input` (never a second process-control vocabulary), its ACK-on-durable-command-ID behaviour, and the driving-principal ruling — **open question 2**, an authority decision |

Both also need their conformance behaviour in the shared suite that `AC-HAD-01` requires of every
binding, since a fake that cannot fail-inject an input refusal or a missing turn proves nothing
about either.

**The mutation this list deliberately does not add: creating the pull request.** A reader
counting Conductor's panes against this table will look for a create-PR operation and not find
one, so the absence is stated rather than left to inference. There is no such operation today
(the 104 authored operations contain exactly one PR-adjacent mutation, `recordTicketChangeReference`,
which records an already-existing reference), and this design does not propose one, because
adding it is not a route — it is a new provider authority:

1. `AC-GH-03` (`SPEC.md:4817`) scopes every GitHub installation token to *"only Issues write and
   Metadata read"* and fails closed on *"unapproved auth, ingress, or broader grants"*. Creating
   a pull request needs Pull requests: write, which that criterion currently refuses.
2. `AC-GH-07` (`SPEC.md:4821`) states *"Only issues are ingested. Pull requests are excluded"*.
   A create-PR path makes pull requests a first-class provider object in both directions.
3. So the cost is a SPEC amendment to two accepted acceptance criteria, a re-run of the
   least-privilege registration evidence, an idempotency/read-back design for a mutation whose
   provider outcome ctower cannot currently observe, and only *then* the four-inventory work
   above.

That is a real feature with a real decision behind it, and it belongs to whoever owns the GitHub
connector — not to a UI design smuggling it in as a button. §4.3 therefore designs the control as
a **handoff**: gated on clean-and-pushed, opening the provider's compare page, and recording the
resulting reference through the operation that already exists.

### 8.3 One gap that is not an operation

The left rail's `+N −N` badges and the change list currently read the local filesystem
server-side. That works for `apps/ctower-ui` over a local development instance and does not
generalise: a cockpit over a remote instance needs G5 as a real read, and until it has one, the
rail must render `not reached` rather than a `+0 −0` for any workspace it cannot observe (§4.1).
Naming this now avoids shipping a surface whose numbers are silently local-only.

---

## 9. Sequencing: smallest end-to-end slice first

The principle from the constitution: *grow the system in layers; start from the smallest version
that works end to end, and add each new capability on top of a product that already works; never
trade a working product for unfinished complexity.*

Applied here, the ordering is not the one the brief's pane list implies. The obvious first slice is
"the chat pane, read-only", and it is the wrong one: §7.4's table says the chat pane's backend is
the last phase in a 38-phase ladder. **Build downward from what is already true.**

But "already true" has two axes, and an earlier draft of this document counted only one of them.
A slice is cheap when its **operations** exist *and* when its **boundary** exists. The console
pane scores full marks on the first and — for its **viewer** — zero on the second: seven active
operations, of which the four `/v1/console/…` ones require a browser that holds a human session and
a CSRF token (§2, §7.2, `AC-CON-02/03`), which this cockpit's boundary deliberately withholds. The
credentials/spend surface scores full marks on both: `readPoolLimits` is `bearerAuth`, so a browser
holding nothing reads it server-side, exactly as `apps/ctower-ui` reads everything today. So the
console **viewer** moves from second to fourth, and the surface that needs neither a new operation
nor a new boundary moves up to second.

The score is per operation, not per pane, and that is what keeps this from being a story about
features. The three `/v1/admin/console/…` operations are `bearerAuth` and score full marks on both
axes; they do not move to slice 4 for company. `setConsoleKillSwitch` needs nothing the credentials
surface does not already have and lands in slice 1; `revokeConsoleSession` scores full marks on
authority and fails on *data* — no bearer operation yields the `console_session_id` its path
requires — so it waits for discovery rather than for a boundary, which is a third failure mode this
ordering had to learn to name.

The console pane does **not** move to last, and the original reason still stands: a terminal pane
bolted on at the end is the one that gets a keystroke handler "just for debugging." It moves to
exactly as early as its boundary allows, and its tab is drawn from slice 1 onward as a declared
absence so nothing can quietly grow into the hole.

### Slice 1 — the shell and the rail, over what exists

Four resizable panes, the token migration of §3, and the left rail as project → seat → workspace
over `listSpawnRecords` + `listProjectSessions`. No liveness (G1 does not exist): a lane shows its
durable `SpawnRecord.status` and nothing more, and any workspace whose git read did not answer
shows `not reached` (§8.3). No new API operations. Ends as a working product: an operator can see
every registered lane in one place, which is more than any current surface offers.

The fourth pane's tab strip is drawn in this slice with **`Terminal` present and unreachable**,
carrying the reason: this boundary's browser holds no human session, and the console contract
binds a grant to one. That is `AC-UX-03`'s rule applied to a whole pane rather than to a value,
and it is deliberate scheduling insurance — an empty hole where a terminal belongs is the thing
somebody fills with a tmux read.

**One console control does ship here: the global kill switch.** `setConsoleKillSwitch` is
`bearerAuth` over a `{enabled, reason}` body (§2), so it is reachable from this boundary on day
one, and it is the one console operation whose value does not depend on being able to watch a
stream — an operator needs to be able to stop every console session precisely when they cannot see
what is happening. It carries `AC-UX-09`'s `durability pending` state like any other write, and
when it is on, the declared-absent `Terminal` tab names *the kill switch* as the reason rather
than the boundary (§4.4). This makes slice 1 the first slice with a real mutation in it, which is
also why the durable-write rendering rule gets proved this early rather than in slice 3.

**Proves:** the geometry, the tokens, the `unknown` state class, D2's no-elevation rule, that a
declared-absent pane is drawable, and `AC-UX-09`'s pending-until-durable rendering on a real
mutation.

### Slice 2 — Credentials, Spend, Readiness — as far as they go without dispatch

The largest working surface reachable with **no new operation and no new boundary**.
`GET /v1/pools` answers every read it needs and authenticates with `bearerAuth`, so it is read
server-side by a browser that holds nothing — the boundary this cockpit already has. The
Credentials tab renders three axes per entry with per-account reset clocks and no copy verb, plus
the `drift` list with each `missing` row's enactment path; Spend renders credits by model ×
account against `weights` + `topology_revision`, refusing on a stale table. Readiness (§5.1)
renders every cell it can prove and marks the rest **unproven by name** — which, before the
seam's phase activates, is most of them. That is the correct output, and it is the anti-`HEALTHY`.

This slice is **read-only on purpose**: G8, G8b and G9 (§6.1.1) are the mint ask, the reference
binding and the keep-or-evict, and all three are wizard-side writes. So a `discovered` identity
renders here with its pending decision *named and not takeable* — which is honest, and is also the
cheapest possible argument for landing G9 next.

**Proves:** that a composed verdict is honest when it is mostly negative, which is the hardest
thing about §5.1 and the thing paperclip never attempted.

### Slice 3 — the change list and the PR handoff

Right-top over G5, with committed and uncommitted separated, and the PR control genuinely
disabled on a dirty tree *or* an unpushed branch, naming which of the two it is on the control.
First new operation. Ends with an operator able to see what a lane produced and reach its
compare page in one click — **ctower does not create the pull request** (§4.3: `AC-GH-03` scopes
the connector's token to Issues write and Metadata read, `AC-GH-07` excludes pull requests), and
the cockpit shows no PR until its reference is recorded through `recordTicketChangeReference`,
pending until the projection folds.

**Proves:** `AC-HAD-06`'s committed-only rule enforced in a read rather than a renderer, and that
a handoff can be drawn without the surface claiming the outcome.

### Slice 4 — the terminal tab strip, whole — and the boundary it costs

The console **viewer** end to end, on the four already-active `/v1/console/…` operations:
discovery, grant with its five-minute clock, renewal, the bounded SSE stream, inline gap rows,
typed close reasons, and the five never-dos of §4.4 — plus `revokeConsoleSession`, which is
`bearerAuth` and was only ever waiting on discovery for the `console_session_id` it needs in its
path (§2). The kill switch is not here; it shipped in slice 1, because nothing in it needs a
browser session. **Still no new operations, and one new boundary** — which is the whole content of
this slice and the reason it is not slice 2.

**What the boundary is, and exactly which operations it covers.** The four viewer operations
authenticate with the `browserSession` scheme and carry the `ConsoleCsrf` parameter
(`openapi.yaml:120, 136, 159, 181`); the three `/v1/admin/console/…` operations do not, and this
boundary is not about them. `AC-CON-03` requires *"the configured exact private
Origin, secure human-session cookie, and CSRF proof matching its cookie and persisted digest"*;
`AC-CON-02` binds one grant to *"one exact Actor, human role binding, browser session, policy
revision, Project, and console session"* and lets **at most one stream** consume it. That session
foundation exists and is active — `CT-I1-013` sits at position 18 of 38 in `phase_order`, before
the active phase, and `AC-SEC-12` states its browser rule outright: *"UI uses only an opaque
session cookie while direct APIs use Bearer credentials."* What does not exist is that session
**on this surface**: `apps/ctower-ui`'s defining property is a browser holding nothing.

**Why the obvious shortcut is not available.** Proxying — the Next server holds a session, opens
the SSE, and re-broadcasts to a browser that holds nothing — fails the contract in three separate
places, not one:

1. The grant binds to a **browser session** and is consumed by **one stream** (`AC-CON-02`). Two
   readers behind one server share one grant, so the binding that is supposed to name a viewer
   names a process instead.
2. Console output is RESTRICTED, recoverable only through the NOLOGIN `console_output_reader`
   role, *"with every recovery appending an access fact"* (`AC-CON-05`). A fan-out hop appends its
   access facts in the server's name; the human who read the bytes appears nowhere.
3. `AC-CON-06` requires revocation, expiry, fencing and the kill switch to close **every affected
   stream with a typed reason within five seconds**. A proxy is a second stream that must
   propagate a typed close inside the same budget — new failure surface on the exact path whose
   job is to fail safely.

So the choice is a real one and it belongs to whoever owns the boundary:

| Option | What it costs | What it gives |
| --- | --- | --- |
| **A — land the cockpit's console pane on the authenticated boundary** (the CT-I1-013 human session, same-origin with the console routes) | a recorded decision that this operator surface gains a human session, reversing `apps/ctower-ui`'s stated *"no credential of any kind"* posture; login/session handling on the surface; the exact-Origin configuration | the pane, exactly as §4.4 designs it, on a backend that already passed AC-CON-01..07 |
| **B — keep the boundary and keep the pane declared-absent** | nothing | three honest panes and a fourth that says why it is empty (slice 1's treatment, kept) |

The recommendation is **A, scheduled here rather than deferred**, precisely because option B is
stable enough to be tempting: a permanently empty terminal tab is how a "temporary" pane-text read
gets proposed. But A is a boundary decision with a security posture attached, not a designer's
call, so it is stated as an option with its cost rather than assumed. **Open question 3 (§10)
carries it.**

**Proves:** the highest-risk pane, on a backend that already passed AC-CON-01..07, with its
authority model still fresh — and, before any of that, that the cockpit knows the difference
between an operation it lacks and a boundary it lacks.

### Slice 5 — the transcript, read-only

G2 + G3 land together, because the transcript is unrenderable without the spec that says how to
classify its turns. Centre pane renders turns, thinking, tool rows, interrupt chips and elapsed —
**with the composer present and its send control disabled**, carrying the capability's own words
(§4.2a). G1 lands here too, so the rail finally shows `capped` outranking `working`.

**Requires two things, and phase activation is the smaller one.**

1. **An accepted turn-level typed fact vocabulary** — open question 1. `AC-HAD-08` forbids every
   kernel, reporter, projection, CLI and Board path from parsing a harness-private transcript, and
   no contract names the turn / thinking / tool-call / interrupt / elapsed fact set that would
   cross the seam instead (§8.2, G3). This is a contract decision with a conformance obligation
   attached, not a footnote after a buildable-sequencing claim: without it there is nothing for
   the route to serve, and a UI that fills the gap by parsing harness output violates the exact
   criterion it is trying to honour.
2. **The seam's phase active.** Before that, this slice can be built against the conformance
   fixtures but must not claim a live dispatch path.

The ordering follows: the vocabulary can be decided *before* the phase activates, and should be,
because it is the item on this whole list with the longest lead time and the least UI content.

### Slice 6 — the composer sends

G4. `unsent` → `durability pending` → accepted, one stable command ID across reload, refusal shown
as refusal. Idle-lane input only, because that is what today's two bindings declare. The day a
binding declares `INTERRUPT_AND_RESUME`, mid-turn steer lights up with no cockpit change (§4.2a) —
which is the test of whether §4.2a was designed right.

**Requires an accepted operator-input authority model** — open question 2 — **before the seam
path, and the seam path before the route.** `AC-HAD-05` binds every `writeback` fact to one seat's
own project-seat credential and refuses an operator or commander credential presented to an
adapter; an operator message to a lane is, by construction, an operator action. Whether it arrives
as an operator-principal command the runner converts, or as something else, is a credential-law
question, and getting it wrong is a violation rather than a UI bug. Phase activation does not
answer it, and no amount of UI care compensates for answering it wrong.

So slice 6's gates are, in order: the authority ruling, the seam-level input path composed over
`deliver_input` with its ACK-on-durable-command-ID behaviour and its conformance fixtures, the
HTTP route with its four inventories, and only then this pane's rendering.

### Slice 7 — the hire wizard

G6 + G7, blocked on CT-I1-044 and gated by CT-I1-043. Steps 1, 2, 5 and 6 are partially buildable
earlier (the card grid, the pool step, the allow-list); steps 3, 4 and 7 are CT-I1-044's
deliverable rendered, and building them before it exists would mean inventing the survey's
semantics in a UI — which is how the classification ends up living in two places.

**Step 5b — the mint (§6.1.1) — is the part of this slice that does *not* wait for CT-I1-044.**
G8, G8b and G9 are operator-owned pool writes over a read that already exists and a reconciliation
the registry already computes; none of the three needs the survey. They can land with slice 2, and they should,
because until they do, the Credentials tab can show an operator a `discovered` identity and offer
no way to resolve it.

### The dependency summary

Two kinds of gate, kept apart on purpose — a missing operation and a missing boundary are not the
same blocker and do not clear the same way.

- **CT-I1-041** (seam + `hermes`) — merged (#533); phase 37 of 38, not active.
- **CT-I1-042** (`claude-code`) — merged (#538); phase 38 of 38, not active.
- **Phase activation** — *a* gate on slices 5 and 6, and by itself insufficient for either.
- **An accepted turn-level typed fact vocabulary** (open question 1) — the gate on slice 5's G3,
  and the longest-lead item on this list. Decidable today; nothing waits on it but everything
  transcript-shaped waits behind it.
- **An accepted operator-input authority model** (open question 2) — the gate on slice 6's G4,
  ahead of both the seam path and the route. A credential-law decision, not a scheduling one.
- **CT-I1-043** (`codex`), **CT-I1-044** (survey + classification) — not started, absent from the
  ladder; the gate on slice 7 — but *not* on step 5b's G8/G8b/G9, which need neither.
- **CT-I1-021** (console) — phase 26 of 38, **active**. All seven operations are ready today, and
  three of them are also *reachable* today: `setConsoleKillSwitch` is used in slice 1. Slice 4 does
  not ride on the four `/v1/console/…` viewer operations until the boundary below exists, and
  `revokeConsoleSession` waits with them for the session id rather than for the boundary (§2).
- **The authenticated-browser boundary** — the gate on slice 4, and the only gate in this list
  that is a *decision* rather than a phase. `CT-I1-013` (position 18 of 38, active) already
  supplies the human-session foundation; what is undecided is whether this operator surface takes
  a session at all (§9 slice 4, options A and B; open question 3).

Slices 1–3 are buildable now, with no new boundary and one new operation between them. Slice 4 is
buildable the moment its boundary decision lands, and needs no new operation at all. R3109 does not
change the harness-adapter epic's finish line; it is what the finish line is for.

---

## 10. Open questions the seam design does not settle

Per the brief's stop-and-report instruction, three questions this document could not answer from
the seam contract, SPEC, or source. Neither of the first two blocks slices 1–3; the third is the
gate on slice 4.

An earlier draft carried a fourth — whether a lane absent from console discovery should draw a
`not reached` terminal or no tab at all — and it was not an open question. `AC-CON-01` settles it:
discovery returns only allowed engagements and *"every mismatch is a typed no-disclosure refusal
or absence"*, and the only browser discovery operation is a collection rather than a per-lane
probe, so the client cannot tell the two apart and must not appear to. The ruling now lives where
it belongs, in §4.4's never-do list, as a contract consequence rather than an operator decision.
It is recorded here because "the design could not decide this" and "the design had not read the
criterion" are different admissions.

1. **What is the transcript's typed fact vocabulary?** `AC-HAD-08` forbids any kernel, reporter,
   projection, CLI or Board path from parsing a harness-private transcript format, so the binding
   must project typed facts across the seam. The five verbs name `collect` for *artifacts*; no
   contract names the turn-level fact set (turn, thinking, tool call, interrupt, elapsed) that G3
   would serve. Designing the centre pane's rows implies proposing that vocabulary, which is a
   contract decision, not a design one.

2. **Which principal drives the cockpit's writes?** `AC-HAD-05` requires every `writeback` fact to
   attribute to one seat's own project-seat credential and refuses an operator or commander
   credential presented to an adapter. G4's input command is an *operator* action against a lane.
   Whether that is an operator-principal command that the runner then converts, or something else,
   is a boundary question the seam design does not state, and getting it wrong is a credential-law
   violation rather than a UI bug.

3. **Does this operator surface take a human session?** This is the one question with a slice
   behind it. `apps/ctower-ui`'s defining property is a browser holding no credential of any kind;
   the four `/v1/console/…` viewer operations require a browser holding a human-session cookie and
   a CSRF token (`AC-CON-02/03`), and §9's slice 4 shows why proxying is not a legal substitute.
   The question is scoped to those four: the three `/v1/admin/console/…` operations are
   `bearerAuth`, so answering "no" costs the viewer and costs neither the kill switch nor — once
   the viewer names a session — revocation. The foundation
   exists and is active (`CT-I1-013`, position 18 of 38; `AC-SEC-12`'s *"UI uses only an opaque
   session cookie"*), so this is not a build question — it is whether this boundary's stated
   posture changes, which is a recorded decision belonging to whoever owns that README and
   `AC-CON-03`'s Origin configuration. Until it is answered, the terminal tab is drawn present and
   declared-absent (slice 1), and the answer changes no other pane.

---

## 11. Evidence index

Every non-obvious claim above is traceable to one of these. Where a claim rests on a screenshot
rather than source, it says so in place.

### ctower source and contract

| Subject | Where |
| --- | --- |
| Acceptance criteria | `docs/internal/SPEC.md` — AC-HAD-01..12 at 4872–4883; AC-UX-01..09 at 4794–4802; AC-CON-01..07 at 4599–4605 |
| GitHub connector authority | `SPEC.md:4817` (AC-GH-03, *"only Issues write and Metadata read"*), `SPEC.md:4821` (AC-GH-07, *"Only issues are ingested. Pull requests are excluded"*) — why §4.3's PR control is a handoff |
| Terminal authority | `SPEC.md:885` (*"Structured events and durable commands are authoritative. The raw terminal is a compatibility view."*) and `SPEC.md:15` (*"The console foundation has no browser UI and grants no typing authority."*) |
| Console invariants | `SPEC.md` INV-91 at 1570, INV-92 at 1571 |
| Tickets | `SPEC.md` CT-I1-021 at 5309; CT-I1-041..044 at 5336–5342 |
| Capability vocabulary | `contracts/runner/harness-capability.schema.json` — the closed nine-value list |
| Spec shape, survey, probe, layers | `contracts/runner/harness-spec.schema.json` — `$defs.survey` (eight required), `$defs.probe` (five required), `$defs.layers` |
| Registration refusals | `contracts/runner/harness-spec-vectors.json` — `harness-survey-incomplete`, `harness-layer-conflict`, `harness-spec-incompatible` |
| Declared capabilities per binding | `apps/ctower-runner/src/ctower_runner/hermes/spec.py:38–49`; `apps/ctower-runner/src/ctower_runner/claude_code/spec.py:45–55` |
| Steer and collect enforcement | `packages/ctower-runner-sdk/src/ctower_runner_sdk/policy.py` — `input_refusal` at 144–159, `collect_refusal` at 162+ |
| HTTP surface | `contracts/http/openapi.yaml` — 104 operations; console operations under `/v1/console/…` and `/v1/admin/console/…` |
| Pool read shape | `PoolLimitsView`, `PoolProfileLimits`, `PoolEntryState`, `PoolModelWeight`, `PoolDriftFinding` (`finding` + `enactment`) |
| Mint and its custody | `credentials.py:1–7` (no copy verb, and why), `59–88` the meanings table, `193–199` `MintRequest` — exactly `provider_key`, `subscription_identity`, `enactment`, `293–294` `request_mint(identity)` — the identity is its only argument, so no alias enters through it; `DECISIONS.md` D72 §2 (*"which the pool may ask for and never perform"*, *"Pool membership stays operator-owned in every class"*) |
| The mint screen's served half, and its gap | `contracts/http/openapi.yaml` — a programmatic walk of the authored surface finds exactly two operations touching the pool: `readPoolLimits` (`GET /v1/pools`) and `recordPoolObservation` (`POST /v1/pools/observations`), both `bearerAuth`. `PoolProfileLimits` carries `entries`, `drift`, `selectable_entry_count`, `earliest_known_reset_at`, **`observed_at`**; `PoolEntryState` carries the three axes, `registration_state`, `quota_reset_at`, `credit_state`, `metered_millicredits` and its own **`observed_at`**; `PoolDriftFinding` carries `finding`, `provider_key`, `subscription_identity`, `enactment`, `detail`. `PoolObservationRequest` is `harness_key`, `profile_key`, `observed_at`, `entries` — a report by whoever exercised the pool, which is why a browser can neither compose one nor trigger one. **No operation on the surface accepts a secret reference**, which is G8b |
| Closed-world inventories | `tools/codegen/_inventory.py`; `tests/contracts/http/{test_openapi,test_codegen,test_scalar_profile_codegen}.py` (`104` / `97`) |
| Phase ladder | `tools/checks/expected-suites.toml` — `active_phase`, `phase_order` (`CT-I1-013` at 18, `CT-I1-021` at 26, `CT-I1-027` active at 28) |
| Browser authentication boundary | `contracts/http/openapi.yaml` — the four `/v1/console/…` operations carry `"security": [{"browserSession": []}]` plus the `ConsoleCsrf` parameter (`:120` list, `:136` grant, `:159` renew, `:181` stream), while the three `/v1/admin/console/…` operations carry `"security": [{"bearerAuth": []}]` and no CSRF parameter (`:50` allow, `:75` revoke, `:99` kill switch) — the same bearer class as `readPoolLimits` and the rest. Request bodies place each admin control: `ConsoleKillSwitchRequest` is `{enabled, reason}`; `ConsoleSessionRevocationRequest` is `{reason}` behind a path `console_session_id`; `ConsoleSessionAllowRequest` requires fifteen runner-side fields. A programmatic walk of the authored surface finds `console_session_id` returned by exactly two operations, `listVisibleConsoleSessions` (`ConsoleSessionList`) and `allowConsoleSession` (`201 ConsoleSessionAllowance`). `SPEC.md:4600` (AC-CON-02's one-Actor/one-browser-session/one-stream grant), `SPEC.md:4601` (AC-CON-03's Origin + cookie + CSRF), `SPEC.md:4776` (AC-SEC-12, *"UI uses only an opaque session cookie while direct APIs use Bearer credentials"*), `SPEC.md:4037–4039` (CT-I1-013's scope) |
| UI boundary and shell | `apps/ctower-ui/README.md`; `apps/ctower-ui/src/app/conductor.css:1–14, 55–58`; `apps/ctower-ui/design-reference/app.css:5, 10, 51–56`; `apps/ctower-ui/src/surfaces/**` |

### paperclip source

`/srv/projects/paperclip-eval/DESIGN.md` (product stance, eight principles, enforcement);
`ui/src/index.css` (tokens: `23–24` type, `59–74` radius ladder and semantic core, `155–165`
status hues, `214–215` the tunable-placeholder/tweak-panel note, `216–219` the no-hardcoded-ms
component rule, `223–231` motion primitives, `229` vs `248` the `240ms` primitive/literal
duplicate, `233–254` scoped motion tokens — nine referencing, twelve literal, counted rather
than characterised, `551–573` the reduced-motion collapse and its deliberate dwell exception at
`567–569`, `1951–1959` the `.status-chip` recipe, `289+` the `.dark` block);
`ui/components.json`;
`ui/src/components/agent-config-defaults.ts:8, 11`;
`ui/src/adapters/claude-local/config-fields.tsx:239`;
`ui/src/adapters/codex-local/config-fields.tsx:40`;
`ui/src/components/ui/resizable-panels.tsx`; `ui/src/pages/DesignGuide.tsx`.

### Screenshots

`/srv/projects/mission-control/board/r3109-reference/` (97 files; the remainder are unrelated
drops that landed in the same directory).

| Subject | File |
| --- | --- |
| Conductor cockpit — the target | `cmux-drop-a58d9154-1d3f-4135-9ef7-6d0b860dd121.png` |
| ctower board UI as-is | `cmux-drop-f71694a6-2796-42b3-84c8-ef7efded0b38.png` |
| JAK-1, the R3109 brief | `cmux-drop-4b2b745d-fa8f-4ef0-9e57-b38cbf40c13a.png` |
| Paperclip tasks list | `cmux-drop-f7b67672-d058-4f94-a93c-64d578d3db8c.png` |
| Agents list (pinned models, mono) | `cmux-drop-52cc20d0-551f-40b5-97fc-e618eab13fd7.png` |
| Agent · Dashboard | `cmux-drop-4d80140a-19f2-47f0-ae65-ea0aa1b65bad.png` |
| Agent · Instructions | `cmux-drop-a1c3fe69-c594-42aa-86a4-b69f7d62e509.png` |
| Agent · Skills | `cmux-drop-6688645d-50c9-4acc-b46e-c6943644152e.png` |
| Agent · Secrets | `cmux-drop-4bfdb30b-e8ba-4e2d-b646-c748ba66b40e.png`, `cmux-drop-dae7e9c4-5b81-4614-936f-5caa4158aafa.png` |
| Agent · Tools | `cmux-drop-60d6d6f1-fb3e-4321-baa2-023d7b91c54c.png` |
| Agent · Budget | `cmux-drop-c7731c3f-57ec-4e0f-a1cc-94da5847d9a6.png` |
| **Agent · Configuration** | **not in the corpus** — captured live under the operator's grant as `live-paperclip-commander-configuration.png` |
| Add-a-new-agent, entry modal | `cmux-drop-31186ca7-ecef-4b93-bb24-97108bd0bc2c.png` |
| Harness picker (nine cards, no registration state) | `cmux-drop-282bb981-1803-44a3-8470-b04e2feb13e3.png` |
| New Agent · claude-code | `cmux-drop-57c873e0-15ae-4961-a2b3-6a118c8b7cb0.png` |
| New Agent · hermes | `cmux-drop-3e674814-6e3c-4414-a7c1-1e7a0b4c6966.png` |
| New Agent · codex (`Bypass sandbox` on) | `cmux-drop-3e2ae66c-07ba-46e3-89a7-b184c7d965df.png` |

### Live reads

`http://127.0.0.1:3100` under the operator's browsing grant, 2026-08-20:
`/JAK/agents/commander/configuration` — the Configuration tab's full field set, `Primary model:
Claude Fable 5`, the `Permissions` and `API Keys` blocks, `Configuration Revisions · 0`, and the
switch states (`Skip permissions` = `aria-checked="true"`, `Enable Chrome` = false, `Can create
new agents` = false, `Can create/import skills` = true, `Can assign tasks` = true); `/JAK/agents`
— pinned models in monospace; `/JAK/dashboard` — `$0.00 Month Spend · Unlimited budget`.

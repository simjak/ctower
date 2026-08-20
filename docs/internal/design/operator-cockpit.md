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

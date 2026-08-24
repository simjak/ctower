# Design System — ctower-web

Approved by the operator 2026-08-21 via /design-consultation (rendered preview, both
themes). This file is law for every visual decision in ctower-web. Deviations need the
operator's explicit approval.

**Precedence.** A later operator directive outranks this file. When the two conflict, the
directive wins and this file is amended in the same PR that builds it — an unamended
DESIGN.md is a stale law, not a veto. Everything the directive does not speak to still
holds: the grid, the palette, the marks, the copy budget.

## Product Context
- **What this is:** the operator console for ctower — the control plane commanding AI
  crews across the company's repositories.
- **Who it's for:** one user: the operator. Desktop, tailnet-private, daily-driver.
- **Project type:** dense operational web app (shell + pages), React + Vite + Tailwind.
- **The memorable thing:** **"Everything here is real."** Every number, state, and button
  is wired to truth. Nothing decorates, nothing pretends.

## Architecture of the surface (binds IA, not just pixels)
- **One app, one shell.** Permanent 200px left sidebar holding **two workspaces**, each a
  list of named sections. The split is what a destination is *about*:
  - **COMPANY** — true of the tenant however many projects it runs:
    Company · Projects · Crews · Inbox · Harnesses · Admin.
  - **PROJECT** — only ever about one project, and the **ProjectSwitcher dropdown at the
    head of the section says which**: Tickets · Board · Workflows · Requests · Lanes.
  A workspace holds *sections*, not a flat list — a section may name entity instances
  (an agent list) as its rows. A project is a **scope**: choosing one re-points every
  destination below it. An entity that is a **destination** is a rail row that navigates.
  Both idioms are deliberate; neither is a draft of the other.
- **The address carries both.** `?at=board&project=…` is where the operator is, so a
  project screen is a link and the project survives being sent to someone else. A
  company-workspace screen carries no project, because none would be true of it.
- **One surface per read.** The rail's `Tickets` opens the project's own screen on its
  Tasks tab. A tab bar inside a screen is that screen's local navigation, never a second
  navigation system beside the rail.
- **Projects are not runtime and not a harness.** They live in the company workspace,
  listed as cards with a `New project` pop-up. The harness screen is the runtime the staff
  run on and holds no project.
- **First run** (no company): every destination locked; a **full-screen guided wizard**
  runs — five steps, **one question per screen**, thin progress bars, big type, an obvious
  Next. The order follows the runtime, not the org chart: **1 Name your organization → 2
  Connect harness adapters → 3 Create your first agent** (created *on* the chosen harness;
  the pairing renders) **→ 4 Mission** (one screen, skippable) **→ 5 Review**. Each step
  authors a real bundle document — harness, persona, agent profile, and a goal when a
  mission is given — and Review runs **one** validate + plan + apply before `Get started`
  lands in the shell. The full bundle editor is the Company page, not the first-run screen.
- **Unbuilt destinations render honestly** (dimmed, "not built yet" on focus) — never a
  dead route, never a pretend page. Labels are the operator's jobs, never API operations.

## Aesthetic Direction
- **Direction:** industrial-utilitarian, calm-cockpit. An operator console has no hero
  section and no marketing voice.
- **Decoration level:** minimal — typography and real data do all the work.
- **Mood:** a flight deck at night: quiet, dense, legible; amber only where a real state
  earns attention.

## Typography (two families, total)
- **UI / Body / Data:** Geist — 15px base, weights 400/500/600/700,
  `font-feature-settings:"tnum"` everywhere a number renders (counts, diffs, seats).
- **Machine-owned text:** JetBrains Mono — keys, shas, ports, refs, terminal, code.
- **No display font.** Headings are Geist 600/700 with tight tracking (−0.02em).
- **Loading:** bunny.net CSS (self-host at the production gate).
- **Scale:** 12 / 12.5 / 13.5 / 15 / 18 / 22 / 28 px. Nothing larger exists.

## Color (restrained; color is earned)
- **Ink:** `#0A0A0A` · **Paper (light bg):** `#FAFAF7` · **Dark bg:** `#111110` ·
  **Dark card:** `#1A1A18` · **Lines:** `#E7E5E0` / dark `#2A2A27` ·
  **Muted:** `#6B6B66` / dark `#8A8A84`
- **THE accent — the amber ramp:** `#F59E0B` (amber) → `#EA580C` (amber-strong).
  ALL interactive and signal work: focus rings, active nav, working states, primary
  buttons, progress. On light surfaces, amber TEXT uses `#7C3A00` (AA); on dark,
  `#FCD34D`. Never yellow body text on light.
- **Semantic, narrow:** success `#16A34A` ONLY for proven/ok/merged; danger `#DC2626`
  ONLY for dead/refused/removed. No info-blue: **blue does not exist in this product.**
- **Dark mode:** true dark surfaces (not inverted paper); same amber; identical layout.

## Marks (shared vocabulary with the CLI — non-negotiable)
The six glyphs `ctowerctl` prints are the web's state marks too:
`●` done/proven · `○` idle · `⟳` working · `⛔` dead/refused · `⏸` parked · `⚠` warn.
They change in both places or neither, by an authored decision — never a UI restyle.
A state without a recorded fact draws NO mark (unknown is first-class; never borrow a
neighbor's mark).

## No technical text (operator, 2026-08-24 — binding on every screen)
Nothing machine-owned renders. No component keys, no `@revision` tags, no digests, no
schema names, no wire enums, no uuids, no `repository:` references, no file paths. A value
the record needs but the operator did not type is **derived** (a key and a ticket prefix
come from the name) or **hidden behind an explicit developer affordance** (a receipt's
identifiers sit in a closed disclosure). What renders is the name a person gave the thing;
a thing the record does not name renders as what kind of thing it is.

This does not delete the operator's own inputs. A repository he typed renders as a link he
can follow (`github/acme/widgets`), never as the reference behind it; a folder he chose
renders by name. The ban is on machine syntax, not on his data. Product names a person says
out loud — "Claude Code", a model's name — are words, not wire, and stay.

An affordance the record cannot honour yet is drawn **inert** — dimmed, dashed, not a
control, with its reason on hover and on focus — the same law unbuilt destinations follow
in the rail. It is never an input: a box that takes an answer and drops it is worse than
an absence.

## Copy budget (D9 — the aesthetic in words)
Chips ≤ 2 words. Field hints ≤ 1 line. Empty state = 1 sentence + 1 action. Errors =
what happened + the one next action. Rationale NEVER renders — it lives in docs or
behind a focusable (i) disclosure. Reasons are reachable, never rendered-by-default.

## Spacing & Layout
- **Base unit:** 4px. **Density:** compact (Conductor-grade).
- **Shell grid:** 200px rail + fluid content, max content 1200px, desktop-first.
- **Radius:** sm 4px (inputs/buttons/chips-square), md 8px (cards), 999px (state chips).
- **Tables:** 13.5px, header 12px muted, row borders only (no zebra).

## Motion (reserved — stillness is the brand)
- **Default: none.** No entrance animations, no hover choreography, no skeleton shimmer.
- Motion exists ONLY when real work moves: state transitions (150–250ms ease-out) and
  the workflow conveyor (the product's single expressive moment, when its feature lands).
- A page that isn't receiving new facts is perfectly still.

## Interaction laws
- Focus: 2px amber outline, offset 2 — on every focusable, keyboard-reachable.
- One primary button per screen. Destructive actions name their consequence at the point
  of action ("Retires on apply"), never bare.
- Loading/error/empty states are honest and compact; no invented data, ever.
- The screenshot gate: no screen reaches the operator until its own render passes
  side-by-side against this system.
- **No wire vocabulary renders** — its own section above, because it governs every screen
  rather than one interaction.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-21 | Initial system: amber/black, two fonts, CLI-glyph parity, reserved motion, shell-first IA | /design-consultation with the operator; preview approved both themes |
| 2026-08-21 | No blue anywhere | Every dev tool is blue; ctower's face is amber on black |
| 2026-08-21 | First-run = 30-second company moment inside the shell | The operator's stated mental model; the full bundle editor is the Company page |
| 2026-08-21 | **Superseded:** first run is the reference console's 5-step guided wizard, full-screen | Operator asked for the reference console's wizard and organization/tenant UI in ctower: its structure, ctower's amber/black skin |
| 2026-08-21 | Wizard order puts the harness before the staff | Operator: it is the runtime the team runs on, so the agent is created *on* a chosen adapter rather than assigned one afterwards |
| 2026-08-21 | Mission is one screen and skippable | It authors a goal document when given; a company with no stated mission is a real state, not an incomplete one |
| 2026-08-21 | The org switcher sits at the sidebar top: current org + prefix chip, "Create new organization…" honest-unbuilt | The reference console's pattern; no invite and no sign-out for a tailnet-private v1 |
| 2026-08-21 | The browser mints component digests itself (RFC 8785 + SHA-256, not `crypto.subtle`) | Every wizard step authors a real component and the registry recomputes the digest; proven against the live API at 5 of 5 checks |
| 2026-08-22 | Workflows joins WORK, between Board and Requests | The operator's workflow mockup puts it in the sidebar and the T-004 brief issues the page; it is where work's shape is declared, so it sits beside where work is watched |
| 2026-08-22 | The six marks draw nowhere on the Workflows page | A workflow's publication state and a component's lifecycle are closed sets of the record's own, not members of the CLI glyph vocabulary; borrowing the done glyph for `published` would assert a proven-ness the record never claimed. Chips carry them instead |
| 2026-08-22 | `Select` enters the component vocabulary | Every set this console offers is closed by the authored contract, so the control that offers one is the native control that already has a keyboard and a screen reader |
| 2026-08-22 | WORK gains **Tickets** beside Board and Requests — awaiting the operator's ratification | His own ticket mockup (`mockups/ctower-ui/shot-ticket-*.png`) puts Tickets in WORK. A board and a list of tickets are two ways of reading the same record, and only one of them carries a ticket's own page |
| 2026-08-22 | Where the operator is lives in the address (`?at=…&project=…&ticket=…`) | A screen has to be a link: a reload comes back to it, Back means back, and a screenshot is reproducible from its URL |
| 2026-08-24 | **Zero technical text on any rendered surface** | The operator's rule, made law here. He asked for staff, not wiring: "I dont need any machine backend language here." A key or a revision on screen is the console asking him to hold the record's addressing in his head |
| 2026-08-24 | A harness is picked from a card, and a harness ctower cannot start is drawn rather than dropped | The choice is a thing he knows the name of; hiding an absent one would answer "where is Pi" with silence, and this system draws unbuilt things honestly |
| 2026-08-24 | An agent row carries the CLI's mark **and** the word; an agent with no recorded state carries neither | The six glyphs are shared with `ctowerctl`, so a row's dot is the terminal's dot. Unknown stays first-class: no borrowed glyph, and the pill says `unknown` |
| 2026-08-24 | Components are built and screenshotted on a bench (`gallery.html`) before any page adopts them | `vite build` never sees the bench and no destination points at it, so a component can be reviewed as itself, in both themes, in every state — including the states a live tower will not produce on demand |
| 2026-08-24 | **Superseded:** the five groups become two workspaces, COMPANY and PROJECT, the switcher governing the second | Operator directive (T-024): "namespace the pages by projects, basically company workspace and inside project workspace", pointing at the reference console's ORGANIZATION/PROJECT split |
| 2026-08-24 | Projects leave RUNTIME for the company workspace, as cards | Operator: "projects are not runtime… projects are not harness". A project is a thing the company has, not machinery its work runs on |
| 2026-08-24 | A project is made in a pop-up over the card list, document-style, with key and ticket prefix derived from the name | Operator's Paperclip New-project reference, verbatim "make the same". A key is machine text; asking for one is asking a question with no right answer |
| 2026-08-24 | Schema errors surface inline on the field, and Review is unreachable while any remain | Operator: "this must be on the fly error not next page". The browser validates against the authored contract it imports, so the dead page is only ever a server refusal |
| 2026-08-24 | A project has its own screen: Tasks · Overview · Configuration · Budget | Operator's three Paperclip project-home screenshots. Tasks is the project's tickets read, so the rail's Tickets opens it rather than growing a second list |
| 2026-08-24 | A later operator directive outranks this file, and amends it in the same PR | Director ruling on this ticket. The design system is law until he says otherwise; a stale file is not a veto |
| 2026-08-24 | A row names the thing and nothing that addresses it: no key, no revision, no `key@revision`, and a count of bindings rather than a list of principals | Operator walk: "I dont need to see any Key @ tags or `commander.protected-cli · local.generated-client@1`". The record's own vocabulary is how this console finds a row, never what an operator reads once it is drawn |
| 2026-08-24 | A repository renders as its own name and opens as a link, carrying GitHub's own mark on `github/*` and none on any other host | Operator walk: "please make a real clickable link to github with github icons". `lucide-react` ships no brand glyph, so the mark is one authored path beside the row rather than a new dependency. The scheme and the pinned commit stay in the reader — neither the label, the hover nor the address carries them — and a host this console cannot address gets no link at all, because inventing a domain is worse than plain text |
| 2026-08-24 | The four ticket screens say lanes, stages, priorities and times in words: `backlog` is *Waiting*, `implement` is *Build*, `P1` and `P2` render as nothing, and `14:02Z` is *2:02pm* | Operator on T-027: "I need nice non technical UI". A lane enum and a stage key are the record's vocabulary for finding a row, never what an operator reads once it is drawn. Urgent is the one priority that renders, because it is the only one the record treats as authority |
| 2026-08-24 | A recorded time renders as a clock without its zone marker, and the clock is still UTC | The directive removed the machine spelling, not the property that two operators comparing screens read the same number |
| 2026-08-24 | A ticket is raised in a pop-up over the list, document-style: one heading you type, one sentence of who/where/how urgent, one button | Operator's Paperclip New-task reference, frozen 2026-08-24. Raising one is a moment, not a place, so it stays out of the address — the same idiom the Projects screen uses to make a project |
| 2026-08-24 | The list and the columns are one read behind a toggle inside the screen, and the rail's Board stays a destination of its own | Two ways of reading one project's tickets may not become two reads that can disagree. The rail's Board is a different question: any project, not this one |
| 2026-08-24 | **Superseded:** a ticket's ladder draws the steps ahead of it | The stages were thought unreadable. A workflow is a component of the company document, which `exportCompanyBundle` already answers with, so the whole ladder is knowable and the move control offers the declared next steps rather than asking for a typed stage |
| 2026-08-24 | `Developer details` is the one affordance a machine-owned value may sit behind, and it is named for who opens it | The company header's digest and the company's key are both real and both unreadable to an operator. Deleting them would lose the record's identity; hiding them behind a friendly word would only move the noise. The disclosure says who it is for, so an operator who never opens it never meets a hash |

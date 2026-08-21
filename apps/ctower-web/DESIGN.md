# Design System — ctower-web

Approved by the operator 2026-08-21 via /design-consultation (rendered preview, both
themes). This file is law for every visual decision in ctower-web. Deviations need the
operator's explicit approval.

## Product Context
- **What this is:** the operator console for ctower — the control plane commanding AI
  crews across the company's repositories.
- **Who it's for:** one user: the operator. Desktop, tailnet-private, daily-driver.
- **Project type:** dense operational web app (shell + pages), React + Vite + Tailwind.
- **The memorable thing:** **"Everything here is real."** Every number, state, and button
  is wired to truth. Nothing decorates, nothing pretends.

## Architecture of the surface (binds IA, not just pixels)
- **One app, one shell.** Permanent left sidebar with exactly five groups:
  LIVE (Lanes, Inbox) · WORK (Board, Requests) · TEAM (Crews, Company) ·
  RUNTIME (Harnesses, Projects) · SYSTEM (Admin).
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

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-21 | Initial system: amber/black, two fonts, CLI-glyph parity, reserved motion, shell-first IA | /design-consultation with the operator; preview approved both themes |
| 2026-08-21 | No blue anywhere | Every dev tool is blue; ctower's face is amber on black |
| 2026-08-21 | First-run = 30-second company moment inside the shell | The operator's stated mental model; the full bundle editor is the Company page |
| 2026-08-21 | **Superseded:** first run is paperclip's 5-step guided wizard, full-screen | Operator: "read the paperclip wizard and UI of organizations/tenants — I want the same in ctower". Paperclip's structure, ctower's amber/black skin |
| 2026-08-21 | Wizard order puts the harness before the staff | Operator: it is the runtime the team runs on, so the agent is created *on* a chosen adapter rather than assigned one afterwards |
| 2026-08-21 | Mission is one screen and skippable | It authors a goal document when given; a company with no stated mission is a real state, not an incomplete one |
| 2026-08-21 | The org switcher sits at the sidebar top: current org + prefix chip, "Create new organization…" honest-unbuilt | Paperclip's pattern; no invite and no sign-out for a tailnet-private v1 |
| 2026-08-21 | The browser mints component digests itself (RFC 8785 + SHA-256, not `crypto.subtle`) | Every wizard step authors a real component and the registry recomputes the digest; proven against the live API at 5 of 5 checks |

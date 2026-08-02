# ctower CLI TUI — design direction (operator, 2026-07-30)

Operator: *"the TUI of CLI must be like github issues project and workflows process dag with colors
and statuses."* Two reference images: a GitHub Projects table grouped by priority with status pills and
label chips, and a Mission Control web console.

Glyph vocabulary — one set, used everywhere:
`●` working/done · `○` not started · `⟳` in flight · `⛔` blocked · `⏸` parked · `⚠` needs you

---

## View 1 — `ctowerctl board` (GitHub Projects shape)

```
 ctower · Board                                    tenant: jakit    ⟳ 3  ⛔ 1  ⚠ 2
 ─────────────────────────────────────────────────────────────────────────────────
 P0  1
   #  TITLE                                    STAGE           PR      LABELS
   1  ● Enforce tenant scoping on call_id      ●resolve-close  #322    security  bug
 P1  3
   2  ⟳ Make workflow lifecycle reachable      ⟳staging-qa     #84     cli  P1
   3  ⛔ Record fresh-start authority           ⛔merge          #86     docs   ← blocked by #87
   4  ○ Project Delivery contract closure      ○intake         —       contract
 P2  2
   5  ⏸ Private VPS evidence packet            ⏸plan           #36     deploy ceiling
 ─────────────────────────────────────────────────────────────────────────────────
 ↑↓ move   enter open   / filter   g group by   s status   q quit
```

Rules: group by priority like the reference · one glyph column that is the *stage* status, not a
free-text word · labels are chips · a blocked row says **what** blocks it inline.

---

## View 2 — `ctowerctl ticket show <id>` (workflow DAG)

```
 #84 · Make workflow lifecycle reachable                      P1 · custodian: commander
 ─────────────────────────────────────────────────────────────────────────────────────
  ● intake ─▶ ● think ─▶ ● plan ─▶ ● design ─▶ ● implement
                                                    │
                    ┌───────────────────────────────┘
                    ▼
  ● local-qa ─▶ ● review ─▶ ● documentation ─▶ ● release-preflight ─▶ ⟳ merge
                                                                        │
                    ┌───────────────────────────────────────────────────┘
                    ▼
  ○ staging-deploy ─▶ ○ staging-qa ─▶ ○ production-deploy ─▶ ○ prod-smoke-qa
                                                                        │
                    ┌───────────────────────────────────────────────────┘
                    ▼
  ○ retro ─▶ ○ resolve-close
 ─────────────────────────────────────────────────────────────────────────────────────
 ⟳ merge   evidence 2/3 filled
   ● code-review-verdict   sha:9f2a…  review@sol-max   2026-07-30 09:41
   ● local-qa-transcript   sha:7c11…  engineer@sol     2026-07-30 09:12
   ○ merge-receipt         REQUIRED — stage cannot close without it
 ─────────────────────────────────────────────────────────────────────────────────────
 e evidence   g gates   t timeline   ← back
```

Rules: the DAG **is** the 16 declared `engineering.software-factory` stages, read from the pack — never
a hand-drawn list · the selected stage expands to its **evidence slots**, filled and unfilled · an
unfilled REQUIRED slot is why the stage cannot close, stated on the row · four deploy/QA stages render
`○ no infrastructure` until staging and production exist, rather than pretending.

---

## View 3 — `ctowerctl board --waiting` (what needs a human)

```
 Waiting on you  2
 ⚠ #86  merge blocked            gate red — R2456 fix in #87        [open] [why]
 ⚠ R2448 authority shape         operator decision recorded ✔        [view]
```

---

## Build notes
- Read-only first: `board`, `ticket show`, `--waiting`. Mutations stay on today's explicit commands.
- Everything rendered comes from the projection and the workflow pack, so a new stage or label appears
  without a code change. **No hand-maintained list of stages, statuses or labels** — that is the defect
  class this project has hit ten times.
- Colour is additive; every state is legible in monochrome via its glyph, so logs and CI stay readable.

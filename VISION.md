# ctower vision

**Status: non-normative north star.** This document explains where the product is going and why.
It never overrides `SPEC.md` (the contract), `DECISIONS.md` (the history), or `ARCHITECTURE.md`
(the atlas). When vision and SPEC disagree, SPEC wins until a decision changes it. Sources: the
operator's own rulings, 2026-08-15 → 2026-08-17, quoted where they are load-bearing.

## What ctower is

ctower runs the company's own coordination — tickets, workflows, messages, schedules, crews —
inside the product, instead of in files and cron jobs only agents can read.

The failure it exists to end, in the operator's words: *"I was blind for 10 days."* Every status
a human receives today exists because an agent chose to type it. When the work lives in records,
the human reads the system directly, and anything nobody typed is still visible.

## The decidable test of "working"

Not a demo, not a spec: **one real ticket walked through all sixteen stages of the
engineering.software-factory workflow on the live instance** — real gates, frozen criteria,
attached evidence, an independent verdict, formal admission — reaching `resolve-close` with
every receipt durable. This happened on 2026-08-17 (ticket R3051). Every future capability
holds itself to the same standard: proven by a walk, not by an explanation.

## Product principles

1. **Every work item is a ticket.** (Operator: *"every single work item must be a ctower
   ticket."*) The system records its own work, including its own defects.
2. **One API, two skins.** CLI for agents, UI for humans, both speaking the same authored
   contract. The UI never gains authority the API lacks; the CLI never needs a human.
3. **This is the end customer's setup.** Every feature is built as if a non-coder will
   configure it: workflows, rules, and the entire company setup are data authored through a
   visual Setup Studio that emits the same packs and bundles agents use, applied through the
   same validate → plan → apply ceremony with a human-readable diff.
4. **Refusal is information.** The kernel refuses wrongly-ordered things — stale versions,
   self-review, un-admitted work, unearned transitions — and every refusal names its reason.
   A refusal is a finding, never a crash and never a silence.
5. **Runs pin their bytes.** A workflow run freezes the exact content of its workflow and
   policies at start. Editing a workflow can never change the rules under work already in
   flight. This is what makes hand-editable workflows safe to give to customers.
6. **Loops are first-class.** Review and QA stages carry return belts (review → implement,
   qa → implement) — bounded by spin budgets (max nonpassing rounds, max repairs per lineage,
   max candidate generations). A work item that exhausts its budget escalates to a human; it
   never circles silently.
7. **Only P0 interrupts.** (Operator's severity ruling.) P1 and info are durable inbox records
   consumed by scheduled routines; push is reserved for the single interrupt class. Durable
   pull loses nothing; push everywhere turns every delivery failure into silent loss.
8. **Independent judgment is structural.** The author of a proof may not verdict it
   (`self_review: forbidden`); reviewer independence is enforced by the kernel, not by
   convention. Cross-family review rules are policy, applied at dispatch.
9. **Knowledge lives in the product.** Plans, rulings, verdicts, and reports are records with
   an admission boundary — not files on a side channel. The engineering constitution (SPEC,
   DECISIONS, ARCHITECTURE) stays in git, versioned with the code it governs.
10. **No side doors.** Pack registration is a deploy ceremony, seats are minted credentials,
    secrets are references. Anything that changes authority is a ceremony with a recorded plan.

## The screen test

Every operator-facing surface answers, in order: **what is happening → does it need me → what
do I do about it.** A screen that cannot answer all three is not done.

The flagship expression is the **Conveyor Board**: the workflow drawn as a moving line —
zoom out to the portfolio, zoom mid to one workflow with tickets as parcels and protected
gates that pulse when they wait on a human, zoom in to one ticket's proof chain and its
refusal history. Return belts render the loops; round counters render the spin budget.

## The edge, and what we borrow

ctower's edge is **chats + workflows**: conversation and execution in one system, with
kernel-grade gates underneath. From adjacent control planes (Paperclip) we borrow furniture,
not spine: budgets with hard stops on autonomy-cost, reviewer routing, reusable company
templates, and the screen test above.

## Sequencing stance

Grow in layers; never trade a working product for unfinished complexity. Migrations move lane
by lane — custody, requests, messages, routines, crew-spawning — each wave proven by its own
read-back before the old path dies, never big-bang.

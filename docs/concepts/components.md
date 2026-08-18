# Every component, with examples from two industries

[The whole picture](map.md) shows the moving parts **in the order work passes through them**. This
page lists the components in the design, says what each one is for, and gives a worked example from
two very different kinds of work: **software engineering** and **accounting**.

> **Status convention — read this before the examples**
>
> **Status: BUILT** means the current repository contains the named behavior and its own checks
> exercise it. It does not mean a supported production service exists.
>
> **Status: NOT BUILT — SPECIFIED ONLY** means the idea is part of the design or a useful target
> example, but the current repository does not implement it. This label is part of the component
> name, not a footnote.
>
> A component with both kinds of work is split into separate built and not-built statements. The
> software and accounting cells are domain examples; they do not claim that ctower currently runs
> accounting work or an autonomous software factory.

The two-industry test is deliberate. If a component only makes sense for software, it is a
developer tool wearing a general name. The shared record and workflow ideas below have an honest
answer in both columns; the status label says which part of that idea is real today.

---

## The spine: what every industry has in common

```
   REQUEST  ────►  TICKET  ────►  STAGES  ────►  EVIDENCE  ────►  CLOSED
   what was        the work       the steps      the proof        with the
   asked for       promised       it follows     it produced      proof kept
```

| | Status | Software engineering | Accounting |
|---|---|---|---|
| Request | **Status: BUILT** | "Customers can't log in with their company account" | "We need the Q3 books closed for the German entity" |
| Ticket | **Status: BUILT** | Add single sign-on to the login page | Close Q3 for entity DE-01 |
| Stages | **Status: BUILT — four-stage development fixture** | think → plan → build → verify → review → ship *(illustrative target sequence)* | collect → reconcile → adjust → review → approve → file *(illustrative target sequence)* |
| Evidence | **Status: BUILT — criterion/digest/verdict proof** | Tests passing, a security review, a deploy record *(worked example)* | Bank reconciliation, adjusting entries, the approver's sign-off *(worked example)* |
| Closed | **Status: BUILT — proof-gated close in the fixture** | The feature is live and proven *(target outcome, not a current deploy)* | The return is filed and the file is complete *(target outcome)* |

Same record vocabulary. Different stage names and evidence. The shipped workflow is the four-stage
development fixture described below; the longer sequences are examples of how a future compatible
workflow could be authored, not current workflow records.

---

## Group 1 — Work

### Ticket

**Status: BUILT.**

The permanent record of one promised outcome. It carries the request it serves, the workflow it
follows, its acceptance criteria, its evidence, its history and its comments.

- **Software:** *Add single sign-on.* Acceptance: a user with a company account signs in without a
  password, and a user without one is refused.
- **Accounting:** *Close Q3 for DE-01.* Acceptance: every bank account reconciled to the statement,
  every accrual posted, the trial balance balances, and a second person approved it.

### Request

**Status: BUILT.**

Captured intent, in the asker's words, recorded in one step with no scoping. Never renumbered,
never reused. May correctly produce no ticket at all.

- **Software:** "Login is confusing for enterprise customers." Might become three tickets, or one,
  or none if it turns out to be a documentation problem.
- **Accounting:** "Can we pay the Berlin supplier in euros instead of dollars?" Might become a
  ticket, or might be answered *no* by a policy that already exists.

### Board and board stages

**Status: BUILT.**

The board is the *view* of tickets grouped by where they are. Board stages are columns.

- **Software example:** backlog · in progress · in review · complete
- **Accounting example:** open · reconciling · in review · approved · filed

> **The rule that prevents a common failure:** board stages must render the *workflow's* stages, not
> keep an independent list. Two lists drift the first time one is edited, and then two screens
> disagree about where the work is.

### Milestone

**Status: BUILT — represented by the configured checkpoint vocabulary.**

A set of tickets that complete together and mean something as a group.

- **Software:** "Version 2.0" — eleven tickets that ship as one release
- **Accounting:** "FY2026 year-end" — every entity's close, the audit pack, the tax filings

---

## Group 2 — Process

### Workflow and workflow stages

**Status: BUILT — generic evaluator plus the development fixture.**

A workflow is the **declared shape of a process**: its stages, the legal moves between them
including any declared failure routes, where the gates sit, and what "closed" is allowed to mean.

```
  CURRENT DEVELOPMENT FIXTURE (BUILT)
  capture ──► frame ──► verify ──► close
```

The current fixture is the generic engine reading one staged workflow record. The following
domain-shaped drawings are illustrative only:

**Status: NOT BUILT — SPECIFIED ONLY.** A software-delivery workflow with think, plan, build,
verify, review and ship stages, or an accounting month-end workflow with collect, reconcile,
adjust, review, approve and file stages, has not been published as an executable current workflow.
Neither target drawing is code.

The shipped fixture has an empty failure-route set; a workflow schema that can declare failure
routes is not evidence that this fixture has a loop-back path.

### Execution policy

**Status: BUILT — pinned and digest-checked record.** The interpretation of the powers in the
table below is **Status: NOT BUILT — SPECIFIED ONLY**.

The second layer, and the one that removes most confusion. The workflow says **what the process
is**. The design says an execution policy may select or narrow what the workflow already declares;
the current engine pins the policy but does not interpret the execution powers in the table below.

| Declared policy power | Status | Software example | Accounting example |
|---|---|---|---|
| Who may execute a stage | **Status: NOT BUILT — SPECIFIED ONLY** | Only a security-skilled reviewer may do the review stage | Only a licensed accountant may do the approve stage |
| Which optional gates are on | **Status: NOT BUILT — SPECIFIED ONLY** | Turn on an extra security gate for payment code | Turn on a second-approver gate above €50,000 |
| How many repair rounds | **Status: NOT BUILT — SPECIFIED ONLY** | Three review rounds, then escalate | Two correction rounds, then escalate to the controller |
| Budgets and timeouts | **Status: NOT BUILT — SPECIFIED ONLY** | Stop a run that exceeds its cost ceiling | Stop a close that has not moved in two days |
| Where the work runs | **Status: NOT BUILT — SPECIFIED ONLY** | Choose an agent and environment | Choose an agent and the entity's ledger system |

**Status: BUILT.** A ticket binds exact workflow and policy reference/digest pairs when the run
starts. For the shipped fixture the real workflow reference is
`ctower.trust-spine-four-stage@1`; editing a process does not silently change an already pinned run.
The names `month-end-close@7` and similar domain revisions are illustrative, not installed records.

### Gates and checklists

**Status: BUILT — gate predicates and proof-gated transitions.** A gate is a check that allows or
refuses a move between stages. In the shipped fixture, current proof guards the move into the final
stage and resolve/close.

- **Software:** the review gate refuses a move to *ship* if the tests did not run on this exact
  version *(illustrative target rule; the current fixture's `proof.current@1` guards `verify` → `close`)*.
- **Accounting:** the approve gate refuses a move to *file* if the reconciliation is missing for
  even one bank account *(illustrative target rule)*.

### Per-stage checklists and typed evidence slots

**Status: NOT BUILT — SPECIFIED ONLY.** The stricter design in which every stage carries named,
typed evidence slots is not the current runtime. The shipped fixture has criterion/digest/verdict
proof and does not require a separate evidence contract at every stage.

---

## Group 3 — Team

```
   ┌──────────────────────────────────────────────────────────────┐
   │  TEAM  ── holds a goal                                        │
   │                                                               │
   │  COMMANDER  ── owns the goal, holds custody of the work       │
   │      │                                                        │
   │      ├── CREW ── one recorded assignment/session              │
   │      │     ├── harness   catalog reference                    │
   │      │     ├── model     recorded session/catalog metadata    │
   │      │     ├── account   [NOT BUILT — SPECIFIED ONLY]         │
   │      │     ├── usage     recorded session consumption facts   │
   │      │     └── session   the recorded fact that work happened │
   │      │                                                        │
   │      └── IDLE CHECK [NOT BUILT — SPECIFIED ONLY]              │
   └──────────────────────────────────────────────────────────────┘
```

| Component | Status | What it is | Software | Accounting |
|---|---|---|---|---|
| Commander | **Status: BUILT — accountable record/custody facts** | Owns a goal and custody of work toward it | Owns "ship version 2.0" | Owns "close the year on time" |
| Crew | **Status: BUILT — assignment/session records** | One recorded stretch of work | An agent implementing SSO *(example)* | An agent reconciling the bank feed *(example)* |
| Harness | **Status: BUILT — catalog/session reference** | The runtime identity may be recorded | A code runtime *(example)* | A ledger runtime *(example)* |
| Model | **Status: BUILT — recorded metadata** | The model identity may be recorded | A code-strong model *(example)* | An arithmetic-strong model *(example)* |
| Account | **Status: NOT BUILT — SPECIFIED ONLY** | Whose subscription pays for a run | Which provider account bills the run | The same |
| Usage | **Status: BUILT — session close facts** | What the recorded session consumed | Cost per ticket *(example)* | Cost per close *(example)* |
| Idle check | **Status: NOT BUILT — SPECIFIED ONLY** | A detector that notices work stopped without finishing | A build agent that died mid-task | A reconciliation left half-done on Friday |

Autonomous crew dispatch, harness launching, model selection, and subscription billing are **Status: NOT BUILT — SPECIFIED ONLY**. The records above preserve observed identity and usage facts; they do
not imply an active fleet.

### Persona

**Status: BUILT — catalog record only.** A persona component can carry an instructions digest and
be referenced by a catalog record. Declaring a persona does not start an agent.

### Persona file materialization

**Status: NOT BUILT — SPECIFIED ONLY.** The separate three-file persona model described by the
original version of this page is not a current ctower file model. In particular, a separate
human-preference `user.md` component does not exist here. The canonical portability decision names
future adapter materialization, while the current persona schema requires an `instructions_digest`;
it does not expose those files as a running worker contract.

The future portability examples remain useful as design examples: a worker's standards, human
preferences, and house rules should not be conflated. They are not present files that this revision
of ctower reads.

---

## Group 4 — Time

### Routines

**Status: BUILT — fixed routine definitions, occurrences, gates, and dispatch effects.**

Scheduled work carrying its instructions. A routine does not interrupt anyone: it creates a work
item/dispatch effect for an external consumer, which survives a scheduler scan; completion is not
inferred from the effect.

```
  ROUTINE fires ──► occurrence + immutable dispatch effect ──► external consumer may act
       │
       └── suppression while the last occurrence is unconsumed: Status: NOT BUILT —
           SPECIFIED ONLY (the receipt/suppression design in the decision log and the
           pending routine-items ticket); today every fire emits an occurrence
```

- **Software:** every night, check dependencies for new security advisories. Every Monday, produce
  the release readiness summary.
- **Accounting:** on the fifth working day, prepare the VAT return. Every Monday, list invoices over
  60 days unpaid. On the last day of the quarter, open the close checklist for every entity.

### Activity gate

**Status: BUILT — closed set of typed activity gates.**

The condition deciding whether a scheduled run is worth doing at all.

- **Software:** skip the nightly audit if no dependency changed
- **Accounting:** skip the unpaid-invoice sweep if no invoice aged past the threshold

### Review cycle

**Status: BUILT — fixed review routine definitions.**

A recurring pass that looks for what was *missed* rather than what failed.

- **Software:** overnight, propose refactors for code that keeps causing incidents
- **Accounting:** overnight, scan the ledger for entries that look unlike anything posted before

### Watchdog/alarm detector

**Status: NOT BUILT — SPECIFIED ONLY.** A routine occurrence can be skipped or degraded, and an
emitted effect proves only that the routine fired. The current repository has no detector that raises
an alarm merely because a completion receipt did not arrive within a window.

---

## Group 5 — Knowledge

| Component | Status | What it is | Software | Accounting |
|---|---|---|---|---|
| Knowledge base | **Status: BUILT — scoped aggregate/catalog record** | What the organisation knows, with source and date | "Why we chose this database" | "Which costs we capitalise and why" |
| Skills / playbooks | **Status: BUILT — catalog and grant record** | Procedure as a record, so it can be granted rather than remembered | "How to run a security review" | "How to reconcile a bank statement" |
| Rulings | **Status: BUILT — dated ledger record** | Dated, exact agreements that stay decided | "We do not support that browser" | "We recognise revenue on delivery, not on order" |

The difference between a playbook and a document folder is that a playbook can be recorded and
granted as a capability. **Status: NOT BUILT — SPECIFIED ONLY** for execution: granting one does
not start a worker or make the work automatically follow it.

---

## Group 6 — Boundaries

```
   COMPANY ──► PROJECT ──► the work inside it
      │           │
      │           └── a person or agent reads a project only if they hold a
      │               recorded grant to it — not because they typed its name
      │
      └── IDENTITY AND ACCESS: who someone is, what role they hold,
          and the moment that stops being true
```

| Component | Status | Software | Accounting |
|---|---|---|---|
| Company | **Status: BUILT** | One product company in a group | One legal entity in a group |
| Project | **Status: BUILT** | A product or service line | A fiscal year, or a client engagement |
| Identity and access | **Status: BUILT — recorded grants and refusal boundary** | Who may merge to the main branch *(example boundary)* | Who may approve a payment — and the rule that the preparer may not *(example boundary)* |
| Ending access | **Status: BUILT — revocation facts; deployment action is Status: NOT BUILT — SPECIFIED ONLY** | A revoked principal loses its recorded grant | A revoked approver loses its recorded role |

> A boundary exists only where something **refuses** a violation. A boundary that lives in a policy
> document and not in a refusal is an intention.

### Working workspace
**Status: NOT BUILT — SPECIFIED ONLY** for materializing an isolated working environment. A
workspace record/catalog reference may be recorded. The materializer that creates an isolated
checkout or mounts an entity ledger is **Status: NOT BUILT — SPECIFIED ONLY**.

Where a crew's work would physically happen, bound to the work rather than to the person.

- **Software:** an isolated checkout of the code at a known version, with only the credentials that
  task needs
- **Accounting:** a working folder for the Q3 close of one entity, with that entity's ledger
  mounted and no access to the others

---

## Group 7 — Surfaces

The current API/CLI are the authoritative command surfaces. The local browser is a development
shadow surface that reads record-backed state and exposes only the narrow controls that exist. A
surface never owns a second copy of work. The table labels read surfaces and target surfaces
separately; an unbuilt surface is not implied by a route name or a mockup.

| Surface | Status | What it is for | Software | Accounting |
|---|---|---|---|---|
| Board | **Status: BUILT — read-only projection** | Work by stage | Where each feature is | Where each entity's close is |
| Requests view | **Status: BUILT — Request record/read contract and the dedicated read-only shadow Requests surface (`apps/ctower-ui/src/app/requests`, in the navigation rail; the five primary surfaces stay closed)** | What was asked, and its outcome | The backlog of asks | The finance team's inbox of requests |
| Inbox | **Status: BUILT — development controls** | Work items addressed to you | "Review this change" | "Approve this payment run" |
| Chat | **Status: BUILT — two-person Inbox thread** | Talking to a commander where the work is | "Why is this ticket blocked?" | "Why is this invoice held?" |
| File explorer | **Status: BUILT — read-only shadow surface** | Finding the artefacts | The repository tree | Working papers and supporting documents |
| File editor | **Status: NOT BUILT — SPECIFIED ONLY** | Changing an artefact in place | Editing code or a document | Editing a schedule or a reconciliation |
| Terminal | **Status: NOT BUILT — SPECIFIED ONLY** | Running something as an operator surface | Running the tests | Running a reconciliation script |
| Metrics | **Status: BUILT — shadow route; metric definitions are Status: NOT BUILT — SPECIFIED ONLY** | How the work behaves over time | Time per stage, review rounds per ticket | Days to close, corrections per cycle |
| UI and CLI | **Status: BUILT — CLI/API plus narrow shadow UI** | Look at or script the operations that are actually implemented | — | — |

The Console viewer server foundation is **Status: BUILT — private, read-only server boundary**. It
does not provide a product browser terminal, safe renderer, terminal input, or a command runner.
Those are **Status: NOT BUILT — SPECIFIED ONLY**. The local file surface's Save and Revert controls
are intentionally disabled; it is not an in-place editor.

---

## Group 8 — Edges

| Component | Status | What it is | Software | Accounting |
|---|---|---|---|---|
| Connectors | **Status: BUILT — narrow fixed issue-connector registry** | A bounded outside source can become records | Code hosting or issue trackers *(fixed supported scope)* | Bank feeds or tax portals *(design example; not a current provider)* |
| Webhooks | **Status: NOT BUILT — SPECIFIED ONLY** | Generic outside events update the record automatically | A merged change updates its ticket | A cleared payment updates its invoice |
| Notifications | **Status: BUILT — narrow authenticated Inbox notification command; generic outbound delivery is Status: NOT BUILT — SPECIFIED ONLY** | A recorded notification enters the native Inbox | A message about a release *(example)* | A message about a filed return *(example)* |
| Tools and scripts | **Status: BUILT — catalog record; arbitrary execution is Status: NOT BUILT — SPECIFIED ONLY** | Small named capabilities a crew may use | A test runner, a linter | A currency converter, a depreciation calculator |

Events arrive as facts and update the record. The record is never reconstructed from notifications.

---

## The workflow that runs today

**Status: BUILT — development fixture only.** The current executable path is
`ctower.trust-spine-four-stage@1`:

```text
capture ──► frame ──► verify ──► close
```

`capture` records the admitted ticket, `frame` freezes criteria, `verify` records current evidence
and a protected verdict, and `close` re-checks proof before resolving/closing. This does not start
a worker, deploy software, file an accounting return, or provide the longer workflows below.

## Two illustrative workflows, one machine

**Status: NOT BUILT — SPECIFIED ONLY** for the named domain workflows in these walkthroughs. They
show how the same component vocabulary could describe software and accounting work; they are not
installed workflow records and do not claim that the current runtime executes every step.

**Software — "customers can't log in with their company account"**

```
 request captured ─► ticket "add single sign-on" admitted, criteria frozen
   ─► an illustrative software-delivery workflow is selected
   ─► think: what breaks today?          evidence: the failing case, written down
   ─► plan: which provider, what changes  evidence: the approach, reviewed
   ─► build                               evidence: the change itself
   ─► verify ──fails──► back to build     evidence: the failing test, then the passing one
   ─► review (security gate in the example) evidence: a reviewer's signed verdict
   ─► ship                                evidence: the deploy record
   ─► closed, with every step's proof attached to the ticket
```

**Accounting — "close Q3 for the German entity"**

```
 request captured ─► ticket "close Q3 DE-01" admitted, criteria frozen
   ─► an illustrative month-end-close workflow is selected
   ─► collect: statements, invoices        evidence: the documents themselves
   ─► reconcile each account               evidence: the reconciliation, per account
   ─► post adjustments                     evidence: each entry and its source document
   ─► review ──fails──► back to adjustments evidence: what was wrong, then corrected
   ─► approve (second-approver gate in the example) evidence: the approver, who is not the preparer
   ─► file                                  evidence: the filing receipt
   ─► closed, with every step's proof attached to the ticket
```

The stages differ. The gates differ. The people and the evidence differ. The generic engine and
record boundary are shared by design, but the per-stage proof, execution-policy powers, deploy, and
filing guarantees shown in these walkthroughs are **Status: NOT BUILT — SPECIFIED ONLY** for the
current repository. That is why the workflow is separated from the thing that evaluates it.

---

## Where does a new idea belong?

1. **Is it work?** → a request, or a ticket. Nothing else stores work.
2. **Does it decide how work moves?** → a workflow package, or an execution policy. Not code, not a
   screen.
3. **Does it do work?** → a crew, a skill, or a routine.
4. **Is it something we know?** → knowledge, or a ruling.
5. **Does it decide who may see or approve?** → a boundary, and it needs a refusal path.
6. **Does it only display?** → a surface, and it must own nothing.

If a proposal fits none of these, pause: it is usually either a second place for work to live, or
two components wearing one name.

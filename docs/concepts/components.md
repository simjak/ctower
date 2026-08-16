# Every component, with examples from two industries

[The whole picture](map.md) shows the moving parts **in the order work passes through them**. This
page lists **every component**, says what each one is for, and gives a real example from two very
different kinds of work: **software engineering** and **accounting**.

The two-industry test is deliberate. If a component only makes sense for software, it is a
developer tool wearing a general name. Everything below has an honest answer in both columns —
that is what makes ctower a system for running work rather than a system for running code.

---

## The spine: what every industry has in common

```
   REQUEST  ────►  TICKET  ────►  STAGES  ────►  EVIDENCE  ────►  CLOSED
   what was        the work       the steps      the proof        with the
   asked for       promised       it follows     it produced      proof kept
```

| | Software engineering | Accounting |
|---|---|---|
| Request | "Customers can't log in with their company account" | "We need the Q3 books closed for the German entity" |
| Ticket | Add single sign-on to the login page | Close Q3 for entity DE-01 |
| Stages | think → plan → build → verify → review → ship | collect → reconcile → adjust → review → approve → file |
| Evidence | Tests passing, a security review, a deploy record | Bank reconciliation, adjusting entries, the approver's sign-off |
| Closed | The feature is live and proven | The return is filed and the file is complete |

Same spine. Different stage names, different evidence, same guarantees.

---

## Group 1 — Work

### Ticket
The permanent record of one promised outcome. It carries the request it serves, the workflow it
follows, its acceptance criteria, its evidence, its history and its comments.

- **Software:** *Add single sign-on.* Acceptance: a user with a company account signs in without a
  password, and a user without one is refused.
- **Accounting:** *Close Q3 for DE-01.* Acceptance: every bank account reconciled to the statement,
  every accrual posted, the trial balance balances, and a second person approved it.

### Request
Captured intent, in the asker's words, recorded in one step with no scoping. Never renumbered,
never reused. May correctly produce no ticket at all.

- **Software:** "Login is confusing for enterprise customers." Might become three tickets, or one,
  or none if it turns out to be a documentation problem.
- **Accounting:** "Can we pay the Berlin supplier in euros instead of dollars?" Might become a
  ticket, or might be answered *no* by a policy that already exists.

### Board and board stages
The board is the *view* of tickets grouped by where they are. Board stages are columns.

- **Software:** backlog · building · in review · shipped
- **Accounting:** open · reconciling · in review · approved · filed

> **The rule that prevents a common failure:** board stages must render the *workflow's* stages, not
> keep an independent list. Two lists drift the first time one is edited, and then two screens
> disagree about where the work is.

### Milestone
A set of tickets that complete together and mean something as a group.

- **Software:** "Version 2.0" — eleven tickets that ship as one release
- **Accounting:** "FY2026 year-end" — every entity's close, the audit pack, the tax filings

---

## Group 2 — Process

### Workflow and workflow stages
A workflow is the **declared shape of a process**: its stages, the legal moves between them
including failure routes, where the gates sit, and what "closed" is allowed to mean.

```
  SOFTWARE DELIVERY                        MONTH-END CLOSE
  ─────────────────                        ───────────────
  think                                    collect documents
    ▼                                        ▼
  plan ─────────┐                          reconcile accounts ──┐
    ▼           │                            ▼                  │
  build ◄───┐   │                          post adjustments ◄─┐ │
    ▼       │   │ loop back                  ▼                │ │ loop back
  verify ───┘   │ when a stage              review ───────────┘ │
    ▼           │ fails                       ▼                 │
  review ───────┘                           approve ────────────┘
    ▼                                         ▼
  ship                                      file with the authority
    ▼                                         ▼
  closed                                    closed
```

Both drawings are the *same engine* reading two different workflow records. Neither is code.

### Execution policy
The second layer, and the one that removes most confusion. The workflow says **what the process
is**. The execution policy says **who runs it and how hard** — and it may only select or narrow what
the workflow already declares. It can never add power.

| Execution policy decides | Software example | Accounting example |
|---|---|---|
| Who may execute a stage | Only a security-skilled reviewer may do the review stage | Only a licensed accountant may do the approve stage |
| Which optional gates are on | Turn on the extra security gate for payment code | Turn on the second-approver gate above €50,000 |
| How many repair rounds | Three review rounds, then escalate | Two correction rounds, then escalate to the controller |
| Budgets and timeouts | Stop a run that exceeds its cost ceiling | Stop a close that has not moved in two days |
| Where the work runs | Which agent, which environment | Which agent, which entity's ledger system |

> **Pin the revision, not the name.** A ticket follows `month-end-close@7`, frozen when it was
> admitted. Editing the process creates revision 8 for *new* work. Otherwise, changing a process
> silently rewrites the rules that in-flight work is being judged against — and last month's
> evidence stops meaning anything.

### Gates and checklists
A gate is a check that allows or refuses a move between stages. Each stage carries a checklist and
must produce evidence.

- **Software:** the review gate refuses a move to *ship* if the tests did not run on this exact
  version.
- **Accounting:** the approve gate refuses a move to *file* if the reconciliation is missing for
  even one bank account.

---

## Group 3 — Team

```
   ┌──────────────────────────────────────────────────────────────┐
   │  TEAM  ── holds a goal                                        │
   │                                                               │
   │  COMMANDER  ── owns the goal, holds custody of the work       │
   │      │                                                        │
   │      ├── CREW ── one agent doing one recorded stretch of work │
   │      │     ├── harness   which runtime it runs in             │
   │      │     ├── model     which engine serves it               │
   │      │     ├── account   whose subscription pays for it       │
   │      │     ├── usage     what it actually consumed            │
   │      │     └── session   the recorded fact that work happened │
   │      │                                                        │
   │      └── IDLE CHECK ── notices a crew that stopped            │
   └──────────────────────────────────────────────────────────────┘
```

| Component | What it is | Software | Accounting |
|---|---|---|---|
| Commander | Owns a goal and the custody of work toward it | Owns "ship version 2.0" | Owns "close the year on time" |
| Crew | One agent doing one stretch of work | An agent implementing SSO | An agent reconciling the bank feed |
| Harness | The runtime the agent runs inside | — | — |
| Model | The engine serving it | A code-strong model for building | A careful, arithmetic-strong model for ledgers |
| Account | Whose subscription pays | Which provider account the run bills to | The same |
| Usage | What was actually consumed | Cost per ticket, so a feature has a price | Cost per close, so a month has a price |
| Idle check | Notices work that stopped without finishing | A build agent that died mid-task | A reconciliation left half-done on Friday |

### Persona files: `soul.md`, `user.md`, `agents.md`
Three kinds of standing instruction, kept separate because they change at different speeds and for
different reasons.

| File | What it holds | Software | Accounting |
|---|---|---|---|
| `soul.md` | Who this agent *is* — its judgement, standards, and what it refuses | "Never weaken a test to make it pass" | "Never post an entry without a source document" |
| `user.md` | Who the human is and how they want to be worked with | "Give me the diff, not a summary" | "Flag anything over €10,000 before posting" |
| `agents.md` | House rules for every agent in this place | "All work goes through review" | "Segregation of duties: preparer ≠ approver" |

Keeping them separate matters: changing how one person likes to be spoken to should not edit what
every agent is forbidden to do.

---

## Group 4 — Time

### Routines
Scheduled work carrying its instructions. A routine does not interrupt anyone: it creates a work
item in the right inbox, which survives being missed.

```
  ROUTINE fires ──► creates a WORK ITEM ──► someone does it ──► closes with a receipt
       │                                                              │
       │  suppressed while the last item is still unconsumed          │
       └──────── a window ending with no receipt raises an alarm ─────┘
```

- **Software:** every night, check dependencies for new security advisories. Every Monday, produce
  the release readiness summary.
- **Accounting:** on the fifth working day, prepare the VAT return. Every Monday, list invoices over
  60 days unpaid. On the last day of the quarter, open the close checklist for every entity.

### Activity gate
The condition deciding whether a scheduled run is worth doing at all.

- **Software:** skip the nightly audit if no dependency changed
- **Accounting:** skip the unpaid-invoice sweep if no invoice aged past the threshold

### Review cycle
A recurring pass that looks for what was *missed* rather than what failed.

- **Software:** overnight, propose refactors for code that keeps causing incidents
- **Accounting:** overnight, scan the ledger for entries that look unlike anything posted before

---

## Group 5 — Knowledge

| Component | What it is | Software | Accounting |
|---|---|---|---|
| Knowledge base | What the organisation knows, with source and date | "Why we chose this database" | "Which costs we capitalise and why" |
| Skills / playbooks | Procedure as a record, so it can be granted rather than remembered | "How to run a security review" | "How to reconcile a bank statement" |
| Rulings | Dated, exact agreements that stay decided | "We do not support that browser" | "We recognise revenue on delivery, not on order" |

The difference between a playbook and a document folder: a playbook can be *given* to a crew as a
capability, and the work then follows it.

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

| Component | Software | Accounting |
|---|---|---|
| Company | One product company in a group | One legal entity in a group |
| Project | A product or service line | A fiscal year, or a client engagement |
| Identity and access | Who may merge to the main branch | Who may approve a payment — and the rule that the preparer may not |
| Ending access | A leaver stops being able to deploy the moment they leave | A leaver stops being able to approve the moment they leave |

> A boundary exists only where something **refuses** a violation. A boundary that lives in a policy
> document and not in a refusal is an intention.

### Working workspace
Where a crew's work physically happens, bound to the work rather than to the person.

- **Software:** an isolated checkout of the code at a known version, with only the credentials that
  task needs
- **Accounting:** a working folder for the Q3 close of one entity, with that entity's ledger
  mounted and no access to the others

---

## Group 7 — Surfaces

Every surface **reads the spine and writes through the same commands**. A surface never holds work
of its own — the moment it does, "what is the state?" depends on which screen you opened.

| Surface | What it is for | Software | Accounting |
|---|---|---|---|
| Board | Work by stage | Where each feature is | Where each entity's close is |
| Requests view | What was asked, and its outcome | The backlog of asks | The finance team's inbox of requests |
| Inbox | Work items addressed to you | "Review this change" | "Approve this payment run" |
| Chat | Talking to a commander where the work is | "Why is this ticket blocked?" | "Why is this invoice held?" |
| File explorer | Finding the artefacts | The repository tree | Working papers and supporting documents |
| File editor | Changing an artefact in place | Editing code or a document | Editing a schedule or a reconciliation |
| Terminal | Running something and seeing the output | Running the tests | Running a reconciliation script |
| Metrics | How the work behaves over time | Time per stage, review rounds per ticket | Days to close, corrections per cycle |
| UI and CLI | The same operations, one to look at and one to script | — | — |

---

## Group 8 — Edges

| Component | What it is | Software | Accounting |
|---|---|---|---|
| Connectors | Outside systems become records | Code hosting, issue trackers | Bank feeds, invoicing systems, tax portals |
| Webhooks | Outside events update the record automatically | A merged change updates its ticket | A cleared payment updates its invoice |
| Notifications | Delivery outward, *after* the record exists | A message that a release shipped | A message that a return was filed |
| Tools and scripts | Small named capabilities a crew may use | A test runner, a linter | A currency converter, a depreciation calculator |

Events arrive as facts and update the record. The record is never reconstructed from notifications.

---

## Two walkthroughs, one machine

**Software — "customers can't log in with their company account"**

```
 request captured ─► ticket "add single sign-on" admitted, criteria frozen
   ─► workflow software-delivery@4 pinned, execution policy "product code"
   ─► think: what breaks today?          evidence: the failing case, written down
   ─► plan: which provider, what changes  evidence: the approach, reviewed
   ─► build                               evidence: the change itself
   ─► verify ──fails──► back to build     evidence: the failing test, then the passing one
   ─► review (security gate ON)           evidence: a reviewer's signed verdict
   ─► ship                                evidence: the deploy record
   ─► closed, with every step's proof attached to the ticket
```

**Accounting — "close Q3 for the German entity"**

```
 request captured ─► ticket "close Q3 DE-01" admitted, criteria frozen
   ─► workflow month-end-close@7 pinned, execution policy "entity DE-01"
   ─► collect: statements, invoices        evidence: the documents themselves
   ─► reconcile each account               evidence: the reconciliation, per account
   ─► post adjustments                     evidence: each entry and its source document
   ─► review ──fails──► back to adjustments evidence: what was wrong, then corrected
   ─► approve (second-approver gate ON)     evidence: the approver, who is not the preparer
   ─► file                                  evidence: the filing receipt
   ─► closed, with every step's proof attached to the ticket
```

The stages differ. The gates differ. The people and the evidence differ. **The engine, the record,
and the guarantees are identical** — and that is the whole point of separating the workflow from the
thing that runs it.

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

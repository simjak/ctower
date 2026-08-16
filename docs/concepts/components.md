# The components, grouped

[The whole picture](map.md) shows every moving part **in the order work passes through them**. This
page shows the same parts **grouped by what they are for**, which is the view you want when you are
deciding where something belongs rather than following a piece of work.

Both pages describe one system. If they ever disagree, the flow map is the one to trust for
sequence, and the [Tickets](tickets.md), [Stages](stages.md) and [Gates](gates.md) pages are the
ones to trust for meaning.

---

## The spine: everything else attaches to this

```
   REQUEST  ────►  TICKET  ────►  STAGES  ────►  EVIDENCE  ────►  CLOSED
   what was        the work       the steps      the proof        with the
   asked for       promised       it follows     it produced      proof kept

   many-to-many    one ticket     declared by    bound to the     a close is
   one request     is one         a workflow,    stage that       a claim the
   can become      end-to-end     not improvised produced it      evidence
   many tickets    outcome                                        supports
```

Work only ever travels this line. Every other component either feeds it, runs it, informs it,
bounds it, or shows it. Nothing else stores work.

### Requests — what was asked for

A [Request](requests.md) is captured intent, in the asker's words, recorded in one step with no
scoping required. It is never renumbered and never reused. A request can legitimately end without
producing any work at all: already done, will not do, superseded, or answered with a no.

### Tickets — what was promised

A [Ticket](tickets.md) is one end-to-end outcome someone committed to deliver. It carries the
request it serves, the workflow it follows, its acceptance criteria, its evidence, its custody, and
its history. A ticket cannot be closed by deciding not to want it — that is a request outcome, not
a ticket outcome.

### Stages and gates — how it moves

[Stages](stages.md) are the steps. [Gates](gates.md) are the checks that allow or refuse a move
between them. A gate refusing is the system working; a stage advancing without its evidence is the
failure this design exists to prevent.

---

## Group 1 — Work: the record of what is being done

```
  ┌──────────┐   serves    ┌──────────┐   grouped by   ┌───────────────┐
  │ REQUEST  │◄────────────│  TICKET  │───────────────►│ MILESTONE     │
  └──────────┘             └────┬─────┘                │ (a set of     │
                                │                       │  tickets that │
        ┌───────────────────────┼──────────────┐        │  ship together)│
        ▼                       ▼              ▼        └───────────────┘
  ┌───────────┐          ┌───────────┐   ┌──────────┐
  │ CRITERIA  │          │ EVIDENCE  │   │ COMMENTS │
  │ frozen at │          │ produced  │   │ + linked │
  │ admission │          │ per stage │   │ changes  │
  └───────────┘          └───────────┘   └──────────┘
```

| Component | What it is | Why it is separate |
|---|---|---|
| Request | Captured intent | Can exist before anyone knows how, or whether, to do it |
| Ticket | A promised outcome | Needs scope and acceptance before it can honestly exist |
| Criteria | What "done" means, frozen | If it can change during the work, it proves nothing |
| Evidence | What each stage produced | A claim without it is an assertion |
| Board | A view of tickets by stage | It renders the workflow's stages; it does not own them |

---

## Group 2 — Process: how work is allowed to move

This is the part most often misunderstood, because it is **two layers, not one**.

```
  ┌────────────────────────────────────────────────────────────────┐
  │ WORKFLOW PACKAGE — "what the process IS"                       │
  │ versioned - shared - referenced by many tickets                │
  ├────────────────────────────────────────────────────────────────┤
  │ • the stage graph                                              │
  │       think ─► plan ─► implement ─► verify ─► review ─► docs   │
  │              ─► ship ─► release ─► staged check ─► close       │
  │ • legal edges, including failure routes                        │
  │       verify ──fails──► implement    review ──fails──► implement│
  │ • where the gates sit                                          │
  │ • what "closed" is allowed to mean                             │
  └────────────────────────────────────────────────────────────────┘
                              ▲ selects or narrows, never adds
  ┌────────────────────────────────────────────────────────────────┐
  │ EXECUTION POLICY — "who runs it, and how hard"                 │
  ├────────────────────────────────────────────────────────────────┤
  │ • who may execute each stage                                   │
  │ • which optional gates are switched on                         │
  │ • how many repair rounds before it escalates                   │
  │ • timeouts and budgets                                         │
  │ • which harness, model and environment the work runs on        │
  │ • escalation and waiver rules                                  │
  └────────────────────────────────────────────────────────────────┘
```

**A workflow is configuration, not code.** One engine evaluates any package. A software delivery
process is simply the first package; another package can declare completely different stages and
participants, and the same engine still guarantees that advancement is fail-closed and that
consumption of a pinned revision is immutable.

**A ticket pins the revision, not the name.** A ticket follows `some-process@7`, frozen when it was
admitted. Editing the process creates revision 8 for *new* tickets. Without this, editing a workflow
silently rewrites the rules that in-flight work is being judged against, and evidence gathered under
the old rules stops meaning anything.

**Board stages are a view; workflow stages are the process.** Keep one list. If the board carries its
own independent stage list, the two drift the first time either is edited, and then two screens
disagree about where the work is.

---

## Group 3 — People: who does the work

```
   ┌──────────────────────────────────────────────────────────┐
   │  TEAM                                                     │
   │                                                           │
   │   COMMANDER ──── owns a goal, holds custody of the work   │
   │       │                                                   │
   │       ├── CREW ── an agent doing one stretch of work      │
   │       │     ├─ profile: persona · harness · skills · tools│
   │       │     ├─ session: a recorded stretch, not a process │
   │       │     └─ usage: what it consumed                    │
   │       │                                                   │
   │       └── SKILLS / PLAYBOOKS ── what a crew knows how to  │
   │                                  do, as records           │
   └──────────────────────────────────────────────────────────┘
```

| Component | What it is |
|---|---|
| Commander | Holds a goal and the custody of work against it |
| Crew | One agent doing one recorded stretch of work |
| Profile | Which persona, harness, skills and tools a crew may use |
| Session | The recorded fact of work happening — start, state, close, outcome |
| Skills / playbooks | Reusable procedure, stored as records rather than folklore |
| Workspace | Where a crew's work physically happens, bound to the work |

**Harness and model are placement, not identity.** Which harness runs a crew and which model serves
it belong to execution policy and to the crew's profile. They are recorded because a claim about who
did the work is only checkable if the substrate is recorded too — but they are not what makes the
work legitimate. The evidence is.

---

## Group 4 — Time: what makes things happen without a human

```
   ROUTINE ──fires──► creates a WORK ITEM in a seat's inbox ──► a person or
   scheduled work      (never types into a running session)      crew picks it up
   with instructions            │                                      │
                                │                                      ▼
                    suppressed while the previous              done, with a receipt
                    item is still unconsumed                   naming what it produced
                                │
                    a window that ends with no receipt raises an alarm
```

| Component | What it is |
|---|---|
| Routine | Scheduled work carrying instructions, scoped to a company or project |
| Activity gate | The condition that decides whether a scheduled run is worth doing |
| Work item | What a routine produces: durable work in an inbox, not an interruption |
| Idle check | Notices when something that should be moving is not |
| Review cycle | A recurring pass that looks for what was missed rather than what failed |

**Why routines produce items rather than messages:** a message into a running session interrupts
whatever is in progress, competes with it, and leaves no record of whether the work was ever done. An
item survives being missed, and a missed window is visible.

---

## Group 5 — Knowledge: what the organisation knows

| Component | What it is | Why it is not a document folder |
|---|---|---|
| Knowledge base | What is known, with where it came from and when | Searchable by everyone and every agent, in one place |
| Rulings | Dated, exact agreements | A decision stays decided; chat does not remember |
| Skills / playbooks | Procedure as records | A capability can be granted, not just described |

---

## Group 6 — Boundaries: who may see what

```
   COMPANY  ──► PROJECT ──► the work inside it
      │            │
      │            └── a person or agent reads a project only if they hold
      │                a recorded grant to it — not because they named it
      │
      └── identity and access: who someone is, what role they hold,
          and when that stops being true
```

Boundaries only exist where a line of code refuses a violation. A boundary that lives in
documentation and configuration alone is an intention.

---

## Group 7 — Surfaces: how you see it

```
   ┌──────────────────────────────────────────────────────────────┐
   │  UI            board · requests · chat · inbox · file explorer│
   │                editor · terminal · metrics                    │
   │  CLI           the same operations, scriptable                │
   └──────────────────────────────────────────────────────────────┘
              every surface READS the spine and WRITES through the
              same commands. A surface never holds work of its own.
```

A surface that stores something the record does not have becomes a second source of truth, and then
the answer to "what is the state?" depends on which screen you opened.

---

## Group 8 — Edges: what it connects to

| Component | What it is |
|---|---|
| Connectors and webhooks | Outside events become records: code changes, issues, alerts |
| Notifications | Delivery outward, after the record exists — never instead of it |

Events from outside arrive as facts. They update the record; the record is not reconstructed from
them.

---

## How to place something new

When a new idea arrives, ask in this order:

1. **Is it work?** Then it is a request, or a ticket, and nothing else.
2. **Does it decide how work moves?** Then it belongs in a workflow package or an execution policy —
   not in code, and not in a screen.
3. **Does it do work?** Then it is a crew, a skill, or a routine.
4. **Is it something we know?** Then it is knowledge or a ruling.
5. **Does it decide who may see?** Then it is a boundary, and it needs a refusal path.
6. **Does it only display?** Then it is a surface, and it must own nothing.

If a proposal does not fit any of these, that is worth pausing on: it is usually either a second
place for work to live, or a component that is really two components wearing one name.

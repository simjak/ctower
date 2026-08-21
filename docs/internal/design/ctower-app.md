# ctower as a product: the navigation map and the read inventory

Companion to `ctower-app.html` beside this file — a clickable navigation shell,
openable from disk with no build step and no network fetch. Every top-level screen is reachable
and each one shows either the shape its reads can serve or a declared absence naming the read that
does not exist.

This is **not** a second architecture document and does not extend `docs/internal/SPEC.md`. It is
one design artifact answering one question the cockpit design raised and could not answer from
inside a single screen: *which parts of ctower can have a browser at all?* `docs/internal/design/operator-cockpit.md`
remains the design of R3109's four-pane cockpit; this file is the map that cockpit sits in.

**Status: proposal.** No ticket authorises product behaviour here, no SPEC row is claimed, and no
operation is proposed as approved. The gap identifiers below (`G11`, `G12`) continue
`operator-cockpit.md` §8.2's numbering so a reader is not holding two schemes.

---

## 1. The finding that decides everything

The authored surface at `contracts/http/openapi.yaml` is **104 operations: 35 reads and 69
writes.** A user interface is almost entirely reads.

That ratio is not a defect. It is what a control plane built for a CLI and a runner looks like:
things are *done* to ctower by trusted callers, and the record is written. But it means the
question that decides whether ctower can have a browser product is not *what should the screens
look like* — it is **which screens can be served at all**, and that is answerable exactly, today,
by counting.

| Area | Reads | Writes | Consequence for a browser |
| --- | ---: | ---: | --- |
| `/tickets` | 6 | 18 | Rich detail, **no list** — see G11 |
| `/projects` | 5 | 0 | The most readable object in the product |
| `/inbox` | 4 | 4 | Fully serveable |
| `/console` | 2 | 2 (+3 admin) | Serveable, behind a browser-session boundary |
| `/knowledge` | 2 | 1 | Serveable |
| `/rulings` | 2 | 1 | Serveable |
| `/spawn-records` | 2 | 2 | Serveable; liveness is still G1 |
| `/migrations` | 2 | 13 | You can run an import and barely watch one |
| `/request-maintenance` | 2 | 3 | Serveable |
| `/requests` | 1 | 7 | List only |
| `/company` | 1 | 3 | One read, and it is an *export* rather than a view |
| `/pools` | 1 | 1 | Serveable — the cockpit uses it |
| `/board`, `/digests`, `/health`, `/control` | 1 each | 0–1 | Single-read screens |
| `/attention` | **0** | 2 | G12 |
| `/intake` | **0** | 2 | G12 |
| `/admin` (seat credentials, console) | **0** | 5 | G12 |
| `/outbox` | **0** | 1 | G12 |
| `/bootstrap` | **0** | 1 | One-time, no screen needed |
| **harness** | **—** | **—** | No path exists at all — G2 |

## 2. The three shapes of absence, which are not the same problem

Walking every area produced three distinct failures, and conflating them is how a UI plan becomes
a wishlist:

**(a) No object at all.** The harness registry has *no `/v1/harness` path* — not one operation,
read or write. `HarnessSpec` is real: key, revision, digests, declared capabilities,
`context_window_percent`, `liveness_sources`, survey answers, derived layers. It lives as Python
constants and contract JSON and is served nowhere. This is the widest gap in the product and it is
already `operator-cockpit.md`'s **G2**; what this map adds is that it is not only the composer's
problem — it is an entire top-level screen that cannot exist.

**(b) Writes without reads.** Four areas can be *acted on* and never *seen*:

| Area | What you can do | What you cannot see |
| --- | --- | --- |
| Attention | file a finding; record its disposition | the outstanding findings |
| Intake | submit; promote an event | the intake stream |
| Seat credentials | issue; revoke | which seats hold credentials |
| Outbox | record a poison disposition | the poisoned messages |

This is the shape worth naming loudest, because each one is **a queue with no way to see the
queue**, and the seat-credential case is security-relevant: an operator cannot audit who holds
what. Note the register genuinely exists — a `project_seats` row is created *only* by issuing a
credential — so this is an unserved read rather than an unrecorded fact.

**(c) Detail without enumeration.** Every ticket read requires a `ticket_id` you must already
possess: `getTicket`, `getTicketTimeline`, `listTicketSessions`, `listTicketAssignments`,
`listTicketAuditEvents`, `listReviewDispatchEffects`. **Nothing enumerates tickets.** `getBoard` is
the single portfolio read on the entire surface, which makes the board not one view among several
but *the only door*: a ticket absent from the board is unreachable by any read in the product.

## 3. The two gaps this map adds

| # | Missing operation | Screens | Why nothing existing covers it |
| --- | --- | --- | --- |
| G11 | **List tickets** — enumerate a tenant's tickets with enough per-row state to triage, filterable by project, custodian and workflow state | Tickets (§2c) | Six ticket reads exist and all six are keyed by an id the caller already has. `getBoard` returns the board's own projection, not a ticket query, and `listTicketMovement` is a per-project movement read rather than an inventory. Today a browser can render a ticket it was handed and cannot find one it was not. |
| G12 | **Read the write-only queues** — outstanding attention findings, the intake stream, the seat-credential register, poisoned outbox messages | Attention, Intake, Seat credentials (§2b) | Nine writes across four areas with zero reads between them. Each is a queue whose contents are unobservable from any client. These are grouped as one gap deliberately: they share a cause (operations authored for a trusted writer, never for a reader) and should be decided together rather than one screen at a time. |

Both are **reads over facts the system already stores.** Neither needs a new seam capability, a new
authority, or an unstarted ticket — which distinguishes them from `operator-cockpit.md`'s G3 and G4
and makes them substantially cheaper than their absence suggests.

## 4. The navigation itself

Three groups, taken from paperclip's shape because it is the correct shape and the operator named
it as the target:

- **Work** — Board, Tickets, Ticket detail, Requests, Inbox, Knowledge, Rulings, Morning digest
- **Crews** — Cockpit, Crew page, Harness, Credentials, Spawn records, Console
- **Company** — Org, Projects, Costs, Migrations, Attention, Intake, Seat credentials, Health

One rule the shell enforces that is worth carrying into any implementation: **a screen with no read
behind it is marked in the navigation, not only on the screen.** Four entries carry the `unknown`
mark in the sidebar. An operator should learn that a destination is empty *before* walking into it;
discovering it by arrival is how a product teaches people to distrust its own menu.

The cockpit and the crew page are not redrawn here — they are designed in full in
`operator-cockpit.html`, and this shell links to them rather than keeping a second, drifting copy.

## 5. What this does not claim

- It does not design the twenty screens. It establishes which of them can exist, and the shape of
  the ones whose reads are already served.
- It does not approve `G11` or `G12`, or re-open the R3109 scope. Adding either operation carries
  the full closed-world cost `operator-cockpit.md` §8.2 enumerates — codegen inventory, three
  contract counters, and a real CLI command wherever `x-ctower-cli` is non-null.
- It does not measure the write-heavy ceremonies. Company bundle apply, migrations and intake are
  drawn as destinations only; their flows would each need the same treatment §6.1.1 gave the mint.
- The counts are from the authored surface at the head this file was written against. They are
  cheap to re-derive and should be re-derived rather than trusted, exactly like every other number
  in `operator-cockpit.md`.

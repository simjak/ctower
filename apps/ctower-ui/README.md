# ctower-ui — the operator surface

This is **not** `apps/ctower-web`. It is a separate, explicitly non-product boundary: an
operator surface over a running development instance, built against the approved screen set
vendored under `design-reference/`.

Reader's guide to this file: it is the boundary's own engineering notes — why each screen reads
what it reads, and which claims it refuses to make. For how to run and use the surface, see
[the operator surface guide](../../docs/guides/operator-surface.md).

## What it is, and what it is not

|        |                                                                                                                                                                                                                                       |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Is     | A Next.js server that reads the shadow instance's existing read API and renders the approved screen set.                                                                                                                              |
| Is     | A chat workspace with three controls that ask existing server-authoritative operations: a composer over `POST /v1/inbox/messages`, a new-conversation control over `POST /v1/inbox/notifications`, and a link control over `POST /v1/inbox/threads/{thread_id}/promotion`. |
| Is not | The browser product. `apps/ctower-web` remains untouched, and its own stack selection (React Router + Vite, static, no SSR) still governs it.                                                                                         |
| Is not | An authority. The browser receives no API bearer, no session and no credential of any kind; every read happens server-side. The instance's API origin _is_ printed, deliberately, in the provenance foot of every screen — see below. |

Two repository facts this boundary deliberately does **not** decide, and which need a recorded
decision before it counts as anything more than an operator surface:

- The planned increment authorizes no browser implementation, route or placeholder. This boundary
  is a browser implementation. It exists because the operator asked for one; it consumes no
  browser acceptance criterion and claims none of their evidence.
- The browser product selected React Router + Vite. Next.js here is a **second** frontend stack in
  the repository. That selection is not rewritten by this boundary — this is not the browser
  product — but a second stack is a real fact that belongs in a recorded decision.

## Layout

```
design-reference/   the approved mockups, vendored verbatim; app.css is imported by the app,
                    so the rendered screens and the design reference read the same bytes
src/read/           the record-read contract and its one implementation
src/frame/          the chrome every screen shares: mark, nav, theme, provenance foot
src/surfaces/       one directory per screen family
src/app/            the routes
```

### What the browser is and is not given

No bearer, no session cookie, no CSRF token and no credential reaches the page: `src/read/` and
the Inbox server action run only on the server. What the page _does_ carry is the instance's API origin, printed in the
provenance foot next to the posture and the render time. That is deliberate — a capture from one
instance would otherwise be indistinguishable from a capture from another, which is the failure
mode the foot exists to prevent. The origin is not a credential and grants a reader nothing; if a
future deployment wants it hidden, `frame/RecordFoot.tsx` is the one place to change.

### Bounded server requests (O10)

`src/read/bounded.ts` is the only module in `apps/` that names `fetch`. Every record read and the
three Inbox commands go through it under a bounded policy: a per-attempt timeout, a finite attempt count _and_ a finite
elapsed deadline, full-jittered exponential backoff capped and clamped to the remaining deadline, a
typed transient/permanent predicate with no catch-all branch, and a typed `ReadExhausted` outcome
that preserves the attempt count, elapsed time and last classified failure and is counted and
written once to stderr. Each command supplies one `Idempotency-Key` before any attempt and reuses it
unchanged for retries. `src/mutate/command.ts` holds what all three commands share — the headers, the
strict response readers, and the one validated refusal sentence. `src/mutate/inboxPromotion.ts`
accepts only the thread and an optional target-ticket identifier. `src/mutate/inboxCompose.ts` accepts
only the message and one of the addresses the server itself listed, re-reads that list before making
any command, and names no thread at all — the server derives one per seat pair. `src/mutate/inboxSend.ts` accepts
only the thread, the message text and the answer the box last received, and reads the recipient back
from the server's own recipient-scoped projection rather than taking one from a form: a recipient is an
identity, and this surface asserts none. Neither sends a claimed actor, scope, custody, or authorization
fact. The API authenticates and authorizes the server-held bearer, and every refusal is rendered from the
server problem document's human `detail`, never raw JSON.

The send box reads `durability_state` for which of two things the record just said. `accepted` draws the
message; `durability_pending` means the durable acknowledgement acceptance requires has not committed, so
no message is drawn at all — the words stay in the field, the line under the box says the server has not
confirmed them, and `Retry` sends that same message under the identity the first attempt minted. The one
field read back out of the previous answer is that identity, and it is read strictly: anything that is not
a UUID is refused before a read or a command is made. Editing the words first mints a new identity,
because one key for two different requests is a conflict rather than a retry.

`tests/repository/test_browser_network_chokepoint.py` derives the call-site denominator from the
repository tree — not from a hand-kept endpoint list — and fails closed when a network-capable
construct appears outside an approved policy holder, when the chokepoint loses one of its required
bounds, or when an application value-imports the generated client's single-shot runtime.

### The data adapter

`src/read/interface.ts` declares every read this surface makes as a typed function returning
`Reading<T>` — `present`, `absent` (with the work item that will land the source), or
`unavailable`. `src/read/httpRecordAdapter.ts` implements it against `/v1/board`,
`/v1/tickets/{id}`, `/v1/tickets/{id}/audit`, and the recipient-scoped inbox projection
(`GET /v1/inbox/threads`, `GET /v1/inbox/threads/{id}`, `GET /v1/inbox/correspondents`). The Inbox actions
use the already-authored `POST /v1/inbox/notifications`, `POST /v1/inbox/messages` and
`POST /v1/inbox/threads/{thread_id}/promotion` paths.
`src/read/adapter.ts` binds the one that is active.

Two board reads are declared, not one. `board` joins every card to the ticket read behind it, so a
card can show its recorded source and age; `boardCards` returns the cards alone. The Portfolio
counts four hundred cards across three projects and shows neither, so it takes the second — the
join would be four hundred requests spent on nothing that reaches the screen.

Swapping to a typed feed changes `adapter.ts` and nothing else: no screen constructs a client,
and no screen knows a URL.

### Wave 2 — every screen on a live source

| Screen              | Source today                                                                                                                                   | Swaps to                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Board · Ticket      | ctower read API (`/v1/board`, `/v1/tickets/{id}`, `/audit`, `/sessions`)                                                                       | a typed feed, through `adapter.ts` alone                                       |
| Portfolio           | ctower read API (`/v1/board` once per configured project, `/v1/inbox/threads`)                                                                 | the same typed feed, through `adapter.ts` alone                                |
| Inbox               | ctower read API (`/v1/inbox/threads`, `/v1/inbox/threads/{id}`, `/v1/inbox/correspondents`)                                                    | —                                                                              |
| Files               | this repository's git tree at a committed revision                                                                                             | —                                                                              |
| Workspace · Feed    | tmux `list-sessions` / `list-panes` / `capture-pane -p -J`                                                                                     | recorded session facts                                                         |
| Explorer            | `git worktree list` + `git diff <resolved trunk>...HEAD`                                                                                       | recorded worktree facts                                                        |
| Metrics (S9)        | `git log --first-parent` per project trunk                                                                                                     | a recorded deploy event, incident pair and metric-definition file              |
| Org (the who layer) | live `tmux list-sessions` (liveness and `@project`) + the fleet's append-only session log + its declared seat directory                        | recorded session facts and a seat registry                                     |
| Crew profile        | the Org sources for one name, plus that crew's own status files, the escape ledger, and each project's first-parent trunk history              | a recorded ladder state                                                        |

Nothing in the "swaps to" column is cited as a work item unless one is filed for it; see
**Citations are facts** below.

These are **interim** adapters, and they name a third boundary this repository does not otherwise
cross: the fleet's own coordination state is migration or research provenance, not a runtime
dependency. Wiring Workspace, Feed and Org to its live state makes it one for those screens. It
exists because the operator asked for it, every path is overridable, and nothing outside
`src/read/sources/` knows any of them — but it belongs in a recorded decision beside the two
boundaries above.

Three hard lines hold across all of them, and each is enforced structurally rather than promised:

- **Read-only, including other repositories' files.** No module under `apps/` may call a filesystem
  write; `test_browser_network_chokepoint.py` fails the gate if one appears.
- **Redaction before render.** Every interim source must import `./redact`; the check fails closed
  on one that does not. Coordination text and terminal panes are the most exposed strings on this
  surface, and nothing guarantees a seat never pasted a credential into one.

### The frame, and the who layer

The navigation is the operator-approved sidebar: a 244px rail on the desk, a drawer behind the
menu button on the phone, both CSS-only so they work with scripting off. It **replaced** the
horizontal section nav rather than joining it — two navigations for one set of pages is the
duplication a frame exists to remove. `design-reference/app.css` is re-vendored from the approved
mockup set byte-for-byte, so the rendered app and the design reference still read the same file.

The rail carries no live badge. The mockup's counts came from one read of the whole fleet; putting
that read behind every page would make ten screens depend on a source none of them needs, and a
badge whose read failed would have to either lie or shout on a page about something else. The counts
live on Org, where they are measured and sourced. **A missing badge claims nothing; a wrong one
claims a number.**

Org joins three sources and keeps their failures apart. `tmux` says who is alive — if it does not
answer there is no roster at all, because an empty roster reads as "nobody is working", which is the
opposite claim. The crew log says what each crew is doing; a crew it has never mentioned is `none`,
and a log that could not be read makes those fields `unread`. The seat directory declares the
seats; a crew whose name matches no declared seat is counted and still shown, never filed under a
seat this surface invented. The grid sums to the rows beneath it, the summary strip counts those
same rows, and the crew log's status vocabulary is someone else's, so the classification into the
three marks is stated on the page rather than hidden in a component. Model strings stay
unnormalised: two spellings of one family stay two rows rather than merging into a count nobody
recorded.

The rail still offers no per-seat entry — a nav item that leads nowhere is a dead control, and the
seat page (`seat.html`) is not built. Org carries both dimensions as filters that work instead, and
each filter chip counts what clicking it would reveal _under the other filter_, not the fleet-wide
number.

### One crew in full — `/crew/<name>`

Every roster row opens the crew's own profile, a 1:1 port of the approved `crew.html`. It answers the
question the roster cannot: what has this one crew done, and who stands behind it. Identity, the
bound task and liveness, the lifecycle the crew log holds, the changes it claims, the signatures it
wrote, and where its seat stands on the autonomy ladder.

Four things about it are worth knowing before reading the code:

- **A crew that is not running is an answer, not a failure.** tmux was reached and lists no such
  session, so the lookup stays `present` and the page says what _was_ checked — including whether the
  crew log has ever recorded the name, which is how a reaped crew is told apart from one that never
  existed. It never renders the panels above with nothing in them: a shell with empty fields reads as
  a crew with no work rather than as a crew that is not there.
- **A change reference is a claim; the trunk is the verdict.** A crew names its own changes in its
  status files and crew-log lines. Each reference is joined to the first-parent trunk history of the
  project _its own record was filed under_ — not the crew's current project, because a long-lived
  crew moves and `#1` on one repository is a different change from `#1` on another. Where the record
  named no project, the crew's is used and the row says so. `landed`, `not on trunk` and `no trunk
read` are three different claims and are never drawn as each other. No forge is reached: this
  surface holds no credential for one and would have to invent a host to build a link.
- **The ladder rung is derived, and says so.** `board/accountability.md` puts tiers in
  `board/crew-kpis.md`; that file carries a model scoreboard, not a rung. So the rung comes from
  counting `state/escapes.jsonl` against the ladder's own entry thresholds, and a seat the ledger
  charges nothing is TRUSTED **by default** — the panel names that, because the ladder is entered by
  five consecutive verified-clean ships and no record on this fleet counts ships.
- **Session cost is read, and a crew with none says so.** It sums the sessions the record files
  under this crew's own name; a crew the record holds none for reads `— · —` as an answered
  emptiness. An invented cost is the one number an operator would believe without checking.

### Metrics, and the rule about numbers

This is the page where a wrong number would be believed, so it carries a stricter version of the
same rule. A card either states a measurement **and names the derivation it came from**, or it
states that there is nothing to measure and names what would land the record. There is no third
rendering, and in particular no zero standing in for absence.

Measured: changes per day and change failure rate, both from `git log --first-parent <trunk>` —
one entry per change that reached a trunk, so a squash and a merge commit count alike. Not
recorded, and rendered as such: deploy frequency, lead time and MTTR all need a deploy event or an
incident pair no project keeps; the drain burn-down exists only as prose in a status note, and
reading a series out of prose would be a guess with a chart around it.

The project scope control is the mockup's own CSS-only mechanism — four radios at body level and
one `.mtscope` block per project — so switching a tab swaps every card, bar and legend at once and
a number can never belong to a project the tab does not name.

### The ticket bar, and the difference between a name and a position

The approved operator cockpit puts one line above everything else on a ticket, because *what is
this work for* precedes every other question on the screen and the surface was not answering it.
`src/surfaces/ticket/TicketBar.tsx` renders it in the frame's second header row: the key, the
session, the stage, and nothing else.

The two facts it added are two different kinds of claim, and keeping them apart is the whole point.
**`display_key` is a name** — the per-project `CTW-12` an operator quotes — and it is
server-assigned and nullable, so a ticket written before the instance assigned one has none. That
ticket still has an identifier, and the bar shows it under the label `ticket` rather than under the
label `key`: printing a UUID where a key belongs would be spelling one fact as another.
**`SessionState` is a position** — `dispatched → briefed → working → gated`, a closed enum — so the
position is real and is drawn as four segments, with only the current one named. A state outside
that ladder draws no segments at all, because putting an unknown value at an invented position is
the guess this whole surface refuses.

The stage is the third thing, and it is a name and never a position. `stage` is nowhere on
`TicketResource`, but the board projection folds `workflow.changed` server-side and serves the
result as the card's `stage_key`, so the ticket's *current* stage is a served fact and is shown as
one. What no read carries is the **ordered stage list** a `workflow_ref` declares — and `stage` is
an open string qualified by that ref, so stages are per-workflow and a fixed stepper drawn here
would be a guess about someone else's workflow definition. There is therefore no "third of five" to
draw, the stage gets a word while the session gets the segments, and a ticket the board holds no
stage for says *not recorded* rather than borrowing the shape of an answer.

The bar has no vendored mockup — the approved ticket page predates the cockpit — so its rules live
in `app/conductor.css` beside the chat workspace's and the pools screen's, built only from the
vendored sheet's own variables. `newestSession` and `stageOf` are read-layer functions rather than
component-local ones precisely so `tests/repository/test_surface_semantics.py` can drive them:
which of several sessions the line stands for, and whether a stage is served, absent or unread, are
decisions about what may be claimed, not rendering details.

### Limits, and the field the read has no place for

`/limits` renders `GET /v1/pools`: the latest credential-pool sweep per harness profile. It is the
one read on this surface whose *source* sits beside credential material, so it is also the one with
a security argument rather than only an honesty one — and that argument is the authored contract's,
not this boundary's. `PoolObservedEntry`, the write, may carry a fingerprint. `PoolEntryState`, the
read this page asks for, is a closed object with no field a token, key or fingerprint can occupy at
all. `read/poolLimits.ts` reads it one named field at a time, so the projection is a boundary rather
than an intention: a payload that arrives carrying a credential field loses it here, and
`tests/repository/test_limits_ui.py` asserts the field set against the contract itself rather than
against a list typed into a test.

Nothing on the page is aggregated. The record deliberately answers per entry — one account, its own
three axes, its own reset clock — and a profile holding two capped accounts and one available one
is not one word. So `auth`, `quota` and `reach` are three chips rather than one status, `unknown`
carries a neutral treatment on both axes that have one because an axis nobody could observe is not
an available axis, and the only pool-level number on the screen is `selectable_entry_count`, which
the server states. The rows are never re-sorted or recounted here.

This screen has no vendored mockup: the approved set predates the pools read. Its rules live in
`app/conductor.css` beside the chat workspace's and are built only from the vendored sheet's own
variables, so both themes and every token stay the frame's.

### Portfolio, and the three ways a zero can lie

The per-project Board answers one project's question; an operator supervising several was reading
git, the forge and tmux to get the fleet's. `/portfolio` asks the same record the Board asks — one
card-only board read per configured project, plus one inbox read — and folds the answers into
tickets by lane per project, the escalations waiting on a human, and the unread seat comms. The
project list is `read/projects.ts` and nowhere else, so a fourth project is one entry there and one
more row here, with no screen edit.

The fold is `read/portfolioProjection.ts`, and it is pure: `tests/repository/
test_portfolio_projection.py` drives it over fixed payloads and recounts every number in Python
rather than re-running the same expression. Three rules in it are worth knowing, because each is a
place where the convenient number and the true one differ.

- **A board that did not answer is not a project with no work.** Its row draws one spanning
  not-reached cell rather than six dashes across the lanes — six dashes read as six zeroes — it is
  excluded from every total, it takes no unread attribution (without its cards there is nothing to
  attribute a thread by), and the page says `N of 3 project boards answered`.
- **`unaddressable` is not an empty inbox.** The inbox projection resolves its recipient from the
  project-seat registry and names a principal with no seat row `unaddressable`. This surface's
  credential is one today, so its unread total is `0` for an address that cannot receive. The tile
  reads `—`, the panel says so in a sentence, and the per-project split is not drawn at all — a row
  of zeroes there would put back exactly the reading the dash removes. The same fact decides the
  Inbox compose box: a principal with no seat has no address to send *from* either, so the record
  offers it nobody and the box draws itself switched off with that reason rather than a picker whose
  every choice would be refused.
- **A thread belongs to a project only where a card says so.** Attribution is the board card's own
  `inbox_thread_ids` and nothing else; mail on threads no card links is counted apart, so the
  per-project numbers plus the unlinked number equal the projection's own total.

Columns are the record's lanes, for the same reason the Board's are (deviation 1 below), and the
panel prints how many of the counted cards carry a recorded workflow stage so the reader can see
why. The Portfolio is read-only by scope: the operator's UI-may-mutate ruling permits controls and
this view carries none, which the suite asserts rather than assumes.

### Honest empty states — and the difference between empty and unreachable

Board, Ticket and Inbox render live record facts. Feed session facts, Files, Workspace
and Explorer have no source in ctower today, so each renders its approved layout and
an explicit block naming what is missing. No screen invents a number, a name, a duration or a
token count.

Two panels stopped citing future work in this round, because the record began answering for
them: the ticket **work timeline** reads `/v1/tickets/{id}/sessions`, and the crew profile's
**session cost** reads `/v1/projects/{key}/sessions` filtered by the crew's own name. A ticket or
crew that holds none of those is now a *silence* — the record answered and holds none — which is
a different claim from the missing capability those panels used to declare.

The block also says **which kind of nothing** it is. `ticket.comment_added`, `proof.changed`,
`workflow.changed` and `work.changed` are recorded kinds: a ticket carrying none of them is a
record that answered and holds none, not a capability ctower lacks, and it says so rather than
naming work that would land something already landed.

### Citations are facts

Every `lands with …` line comes from `src/read/futureSources.ts` and nowhere else. A review of an
earlier revision found nine panels across three screens all citing one work item that covered none
of them — a pointer that points everywhere points nowhere, and these panels are only worth
something if the pointer is right. So each entry carries the sentence saying how that work item
covers _that exact fact_, and that sentence is the chip's hover; where nothing is filed, the panel
reads **no work item is filed for this yet** rather than borrowing the nearest number.
`tests/repository/test_declared_sources.py` fails closed on a citation minted outside the table
and on one work item standing behind two unrelated facts.

**A source that exists and did not answer is never rendered as one that does not exist.** These are
opposite claims to an operator, so they are different states, different blocks and different words:
`no data source yet` versus `the record was not reached`, the latter carrying the classified
failure and the bounded attempts that were spent. A `Reading` is unwrapped only in
`frame/Declared.tsx` — `Resolved` for a panel, `InlineReading` for a row — so no surface can
flatten a failed read into an empty one, and the structural test above fails closed if one tries.
Inline, the two read `not recorded` and `not reached` rather than a bare dash.

### The chat workspace, and the controls that stay inert

`/inbox` is the surface's write screen and is laid out as the operator's approved shape:
conversations on the left with unread carried by an accent bar rather than a word, the transcript in
the middle with the operator's own turns on their own side of the column, the work the conversation
is about on the right — the promoted ticket's state, its recorded change references, its labels and
attention finding — and that seat's live pane under it. Below 1100px the three panes become one at a
time, chosen by the route, and the frame's back link returns to the list; no pane is dropped at any
width.

Its three controls are live and ask existing authenticated server operations. The composer can only
offer what the record can deliver to, so under a credential holding no project seat it draws itself
switched off and names the command that mints one (see `unaddressable` above).

The steering composer (Feed), the Save/Revert controls (Files), the define-metric save (Metrics) and
the sidebar's `New ticket` render as visibly disabled affordances — a real `disabled` control and a
short verdict chip on the control itself, never as a page banner and never as a dead-looking
control. `New ticket` shows the command that does work, `ctowerctl ticket capture`, as the command
rather than as a sentence about it; the fuller caveat is the control's hover, which is where a
caveat belongs. View switches — Chat/Raw, File/Diff, the board source filter, the work pane's tabs —
choose a reading rather than issue a command, so they stay live.

### Meaning by element, not by prose

The operator's binding amendment to the approved set is that a screen must be understandable through
its elements, not through text: *remove unnecessary text; a screen that needs a paragraph to explain
itself fails the gate*. Applied here that means the per-screen explanatory lede is gone, the declared
absence blocks are a mark plus the fact plus a citation chip rather than a repeated paragraph, the
derivation notes that explain a number are the hover of the number they explain, and a control's
caveat lives on the control. Nothing was removed from the record's side of the screen: every datum
the approved set carries is still rendered, and the reduction is measured per screen as prose text
nodes rather than as total text.

Counts carry their unit. `surfaces/Count.tsx` is the only place the `.n` pill is written and its
type pairs every number with what it counts, so Inbox unread-message counts and Board card counts
cannot appear as bare, ambiguous numbers.

## Running it

```text
apps/ctower-ui/serve-development.sh          # builds nothing; serves the built output on :3117
```

The script resolves the operator credential from the Secret Service reference the instance
already uses and exports it for the life of the Node process. It is never written to a file,
never passed as an argument, and never reaches the browser. The server uses it for reads and for the
three Inbox commands; the API remains the sole authority for identity and scope.

| Variable                      | Default                        | Meaning                                                         |
| ----------------------------- | ------------------------------ | --------------------------------------------------------------- |
| `CTOWER_UI_API_BASE_URL`      | `http://127.0.0.1:8091`        | The loopback read API.                                          |
| `CTOWER_UI_API_TOKEN`         | —                              | Bearer for the read path. Required; there is no anonymous read. |
| `CTOWER_UI_INSTANCE_LABEL`    | `shadow`                       | Shown in the header chip.                                       |
| `CTOWER_UI_INSTANCE_POSTURE`  | `SHADOW_ONLY_CP3_D_NOT_PROVEN` | Shown in the provenance foot.                                   |
| `CTOWER_UI_INSTANCE_REVISION` | served commit                  | Shown beside the instance label.                                |
| `CTOWER_UI_PORT`              | `3117`                         | Listen port.                                                    |

Build first with `pnpm --filter @ctower/ui build`. The repository gates
(`pnpm run format:check`, `pnpm run lint`, `pnpm run typecheck`) cover this boundary and are
run by `just check`.

## Deviations from the approved mockups

Each is a fact the record does not carry, not a design preference. They are listed in full in
the phase-1 status note; the two structural ones are:

1. **Board columns are the record's lanes**, not the mockup's seven pipeline stage names. The
   shadow instance runs `ctower.trust-spine-four-stage@1` and every card carries `lane`;
   painting stage names over lane data would have been an invented mapping.
2. **Project is the primary Board dimension; `source.kind` is its secondary filter.** Every
   `/v1/board` read is scoped by required `project_key`, every returned card carries that same project
   fact, and the adapter refuses a mismatched card instead of rendering it under the selected tab.

The section nav carries every screen this phase built, and only those. `Workflow` is not built
here, and a nav entry that leads nowhere would be a dead control.

3. **The rail's ticket entry is `Latest ticket`**, not `Tickets`. `/ticket` opens the most
   recently created ticket on record: that is one record, not a list, and the previous label
   promised an index the route never showed. The route now renders that ticket in place with the
   rule and the ticket's own stable link stated above it, rather than redirecting to an id the
   operator never chose. The board is the list. `src/frame/rail.ts` is the contract, and
   `tests/repository/test_declared_sources.py` reads it.
4. **The true-empty-project block no longer promises a portfolio view "below" it.** The only
   portfolio-view element on this page is the link in `src/surfaces/board/TrueEmptyProject.tsx` —
   nothing renders below the banner — so the copy now describes that link instead of claiming an
   embedded view the DOM never carried. The project-fact work that would make an embedded view
   composable has not landed, so this is the honest fallback rather than the preferred direction.
   That block's link still points at `/board`, and its panel still renders the default project's
   entries rather than the fleet's; the cross-project view lives at `/portfolio`, and repointing
   that block is its own change to settle.

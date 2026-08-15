# Requests — proposed operator surface (S11)

Two screens, rendered on the real ctower frame at `origin/main` 50d72c7f:

| File | Shows |
|---|---|
| `requests.html` | The queue in its order, and the box that files a new request. |
| `requests-rerank.html` | The same screen mid-drag: one request moved to the top, every consequence drawn, the command armed. |

**Not built. Nothing here is wired.** This is the mockup the operator approves
before anything is implemented. Both files link `../../design-reference/app.css`
— the exact stylesheet the running app imports — so this proposal cannot drift
from the product's tokens, chips, glyphs, panels or fields.

## What each control does

| Control | What it does | Where it lands |
|---|---|---|
| **Project tabs** (`all · manibo · bh-loop · ctower · mission-control`) | Picks the scope. A known set, so it is a picked control and never typed. The number on each tab is that project's open count. | `GET /v1/requests?project_key=…` |
| **Project select** in the File box | The project the new request belongs to. Required — a request cannot be captured without one. | `RequestCaptureRequest.project_key` |
| **Ask field** | The request, in his words. The one field on the screen that is free text, because it *is* the request. | `RequestCaptureRequest.text` |
| **File** | Captures it. The record answers with a permanent `R` reference immediately. | `POST /v1/requests` |
| **Pending row** (dashed, `—` where a rank would be) | A capture the record has committed but not yet accepted off host. It has no position because `GET /v1/requests` genuinely does not return it yet — drawing it as ranked would be the lie #390 already cost us once. | `durability_state: durability_pending` |
| **Grip** | Drag the row to a position. | one exact permutation |
| **Rank field** | The same move, typed — the keyboard equivalent of the grip, and the only way to reach it without a pointer. | the same permutation |
| **Reference · state glyph · state word** | `R2816`, `⛔`, `blocked`. The six marks are the product's own; the word carries `NEW` vs `TRIAGED`, which one glyph cannot. | `RequestRow.reference`, `.state` |
| **`P2` chip, dashed** | The priority no one has ever set. Every imported request carries the capture default, and the dashed border is the difference between a decision and a default. | `RequestRow.priority`, `.priority_default` |
| **Owner · age** | Who holds it, and how long it has been open. Honest units, never rounded up. | `RequestRow.owner`, `.age_seconds` |
| **Chevron** | Opens the request's own record facts: captured, last changed, owner, content digest. | `RequestRow` |
| **Blocker strip** | On a blocked row only, the recorded reason, on the row rather than behind a click. | `RequestRow.blocker` |
| **Confirm order** | Records the order as one command bound to the civil date, the artifact key, the content digest of the exact permutation, and the source watermark. Disabled while the order is unchanged; armed the moment it is not. | AC-PM-02 |
| **`not dispatched`** | Confirming records an order. It does not start work. AC-PM-02 keeps those two apart, and so does the screen. | AC-PM-02 |

## What was chosen, and what was rejected

Priority is a **class**, order is a **decision**, and this screen only lets him
set the second: four requests can honestly be `P0`, which is exactly how "four
things were top priority at once" happens, so the row he actually manipulates is
the rank and the `P0/P1/P2` chip stays a read. I rejected putting a priority
selector on each row (`POST /v1/requests/{id}/priority` demands a written
`reason` per change, which turns one drag into eleven small essays) and rejected
putting one in the File box (capture accepts only `project_key` and `text`, so a
priority at filing would be a second command dressed as one field). I rejected
clamping the ask to two lines with an ellipsis — the operator has to recognise
his own request to rank it, and a request ending in `…` is one he must open
first — so the ask is never clipped and the chevron reveals record facts
instead, which keeps it from being a control that does nothing on a short row. I
rejected adding a `title` field to the Request record to make rows scannable:
that is a contract change, not a design choice, and it belongs in a spec
candidate rather than in a mockup. And I rejected showing the just-filed request
as an ordinary ranked row: the record has not accepted it yet, the list really
does answer without it, so it is drawn above the order in the frame's own dashed
"nothing here yet" shape.

## What is real and what is drawn

Every row is the operator's own open ctower request, read from
`/srv/projects/mission-control/state/requests.jsonl` — the ledger
`tools/migration/operator_requests/README.md` names as the Request cutover source
— at 2026-08-15T21:30Z: eleven rows, their exact text, state, owner and age, and
the per-project counts on the tabs. The proposed order is AC-PM-03's fold with
the facts that exist (no week goal recorded, every priority at the same default,
then oldest first, then stable identity). The content digests and both order
digests are computed, not drawn: moving one row changes the number on the button.

Drawn: `R3038` and its pending state — the ask is his own words, quoted verbatim
inside ledger row `R3031`, and `R3038` is the next reference the ledger would
mint. `P2 / default` on every row, because the legacy ledger records no priority
at all and ctower's capture defaults to exactly that.

## What the operator should know before saying yes

- The rail gains a twelfth item. Everything else in the frame is the product's,
  sliced byte for byte from a production build of `apps/ctower-ui` at
  `origin/main` 50d72c7f.
- `apps/ctower-ui` is the dogfood surface, and today it holds no write authority.
  Filing and re-ranking are writes. That is a boundary decision for the
  commander, not a design one: `CT-I1-025` builds the confirm/re-rank command on
  the API and CLI, and `CT-I2-011` is where a browser Request view lands, behind
  `CT-I2-005`.
- The sidebar still reads **New ticket · cli only**. That is the real control and
  it is still true: a *ticket* is captured with `ctowerctl`. A request is not a
  ticket, and this screen files requests. If that reads as a contradiction on the
  same screen, the fix is the ticket surface, not this one.
- The `53` in the foot is real: fifty-three of his open requests carry no
  project, and ctower cannot capture a request without one. They have to be
  assigned before the cutover, which is what `tools/migration/operator_requests`
  already fails closed on.

Rebuild: `/srv/projects/mission-control/mockups/ctower-requests/` —
`python3 _build.py && node _drive.mjs shots`.

# The operator surface

`apps/ctower-ui` is a small Next.js server that renders a ctower instance's read
API as a set of operator screens, and sends inbox messages back through the
instance's own authorized command paths.

!!! warning "Development-only"
    Browser surfaces are development-only and unsupported. This one runs on
    loopback against a development instance. It publishes no package and is not
    part of any deployment.

## What it is

| | |
| --- | --- |
| Renders | The board, one ticket in full, the delivery metrics, the cadence registry, the portfolio, the org roster, the harness credential limits, and a chat workspace over the durable inbox. |
| Writes | Three things, all through the instance's own operations: a message on a conversation, a new conversation, and a link from a conversation to a ticket. |
| Holds | Nothing. Every read and every command runs on the server; no bearer, session or token reaches the browser. |

## Running it

The server needs an instance to read and a credential to read it with.

```bash
pnpm install --frozen-lockfile
pnpm --filter @ctower/ui build

CTOWER_UI_API_BASE_URL=http://127.0.0.1:8091 \
CTOWER_UI_API_TOKEN=<bearer> \
  pnpm --filter @ctower/ui start
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `CTOWER_UI_API_BASE_URL` | `http://127.0.0.1:8091` | The instance's API origin. |
| `CTOWER_UI_API_TOKEN` | — | Bearer for every read and command. Required; there is no anonymous read. |
| `CTOWER_UI_INSTANCE_LABEL` | `shadow` | Shown in the header chip. |
| `CTOWER_UI_INSTANCE_POSTURE` | `SHADOW_ONLY_CP3_D_NOT_PROVEN` | Shown in the provenance line. |
| `CTOWER_UI_INSTANCE_REVISION` | — | The served commit, shown beside the label. |
| `CTOWER_UI_PORT` | `3117` | Listen port. |

Every screen prints which instance it read, on which origin, and when. That is
deliberate: without it, a screenshot of one instance is indistinguishable from a
screenshot of another.

## The chat workspace

`/inbox` is the one screen that writes. It is laid out as three panes:

```text
┌──────────────┬────────────────────────────┬──────────────────┐
│ conversations│  transcript                │  work            │
│              │                            │  (ticket, changes│
│  unread bar  │  their turns left          │   checks, review)│
│  age         │  your turns right          ├──────────────────┤
│  preview     │  ────────────────────────  │  terminal        │
│              │  composer                  │                  │
└──────────────┴────────────────────────────┴──────────────────┘
```

Below 1100px the three become one at a time: the conversation list until you
open one, then that conversation with its work pane under it, and the frame's
back link returns you to the list. No pane is dropped at any width.

Three controls do real work:

| Control | Operation |
| --- | --- |
| The composer | `POST /v1/inbox/messages` |
| `+` on the conversation list | `POST /v1/inbox/notifications` |
| `Link` in the work pane | `POST /v1/inbox/threads/{thread_id}/promotion` |

None of them asserts an identity. The composer has one field — the message. The
recipient of a reply is resolved by the server from the thread; the recipient of
a new conversation is chosen from the seats the server itself listed, and is
resolved again server-side before the command is made. The sender is always the
credential's own principal, and is never sent.

### What happens when the record does not accept

A send has three outcomes and they are drawn as three different things.

* **Accepted** — the message appears in the transcript immediately, drawn from
  the command's own answer, because the thread projection is folded from events
  *after* the command commits and lags it by a moment.
* **Not confirmed** (`202`) — the durable acknowledgement acceptance requires has
  not committed. No message is drawn at all. Your words stay in the field, the
  line under the box says the server has not confirmed them, and pressing send
  again retries *that same message* under the identity the first attempt minted.
  Editing the words first mints a new identity, because one key for two
  different requests is a conflict rather than a retry.
* **Refused** — the server's own explanation is shown, and your words are kept.

## Giving the server an address

The inbox is recipient-scoped: the instance resolves a seat from the principal
behind the bearer. A principal with no seat row is `unaddressable` — it can
neither receive a message nor address one, so the workspace shows no
conversations and its compose control is switched off.

That is not an empty inbox and the screen does not draw it as one. To make the
surface able to hold conversations, issue a seat credential and run the server
under it:

```bash
ctowerctl credential seat issue \
  --project-key <project> \
  --seat-key <seat> \
  --display-name "<name>"
```

Issuing a seat credential mints a principal *and* its seat row, which is what an
address is. Do this once for the seat the surface runs as, and once for each
seat you want to hold a conversation with. Issuing credentials is an
administrative operation; the surface itself never performs one.

## Reading without inventing

Every screen distinguishes three states, and never draws one as another:

| State | What it means | How it reads |
| --- | --- | --- |
| a value | the record answered and holds this | the value |
| `not recorded` | ctower records no fact of this class yet | an outline mark, the fact named, and the work that would land it — or that nothing is filed |
| `not reached` | a source exists and this read did not reach it | a warning mark, the classified failure, and the bounded attempts spent |

The third is never collapsed into the second. "We could not read it" and "the
record does not hold it" are opposite claims, so an unreachable source is never
rendered as an empty one, and a screen that could not read something never looks
like a screen with nothing to show.

Numbers follow the same rule. A measure with no record behind it says so and
names what would land it, rather than showing a zero that reads as a
measurement.

## How it reads its data

`src/read/interface.ts` declares every read as a typed function returning a
three-state `Reading`. `src/read/adapter.ts` binds one implementation per
screen, and no screen constructs a client or knows a URL — so changing where a
screen's data comes from is an edit to that one file.

`src/read/bounded.ts` is the only module in `apps/` that names `fetch`. Every
read and every command goes through it under a bounded policy: a per-attempt
timeout, a finite attempt count *and* a finite elapsed deadline, jittered
backoff capped and clamped to the remaining deadline, a typed
transient/permanent predicate, and a typed exhaustion outcome. Each command
supplies one idempotency key before its first attempt and reuses it unchanged
for retries.

Some screens read facts the instance does not record — a session's live pane, a
worktree's diff, the repository's own file tree. Those come from local,
read-only sources under `src/read/sources/`, every one of which passes its text
through a redaction list before a screen can see it. No module under `apps/`
may write to the filesystem, and a test derived from the source tree fails the
build if one appears.

## Styling

`design-reference/app.css` is the approved screen set's stylesheet, vendored
byte for byte, and is not edited. `src/app/conductor.css` adds the one layout
that set has no rule for — the chat workspace — and is built only from the
first sheet's variables, so it inherits both themes and introduces no token of
its own.

Both themes render identical page geometry; only variables change between them.
The sun/moon control swaps a class on the document and stores the choice, and an
inline script applies it before first paint so a dark-theme reader never gets a
white flash.

## Tests

| Suite | What it proves |
| --- | --- |
| `tests/repository` | The read layer's decisions, as pure functions over fixed values, plus structural rules over the source tree — the network chokepoint, the redaction rule, and where a read may be unwrapped. |
| `tests/dogfood` | What a real browser renders and does. It stands a stub record source on a loopback port, builds and serves this surface against it, and drives Chromium at 375/768/1440: the copy on screen, and both write boxes actually submitted through the server action. |

The dogfood suite needs a browser on the host. The repository suite does not.

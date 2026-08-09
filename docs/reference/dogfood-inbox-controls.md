# ctower-ui dogfood Inbox controls

`apps/ctower-ui` is a local shadow-instance dogfood server, not the `ctower-web` product and not a
supported browser UI. [D41, D42, D44 and D45](https://github.com/simjak/ctower/blob/main/DECISIONS.md)
permit it to present two existing Inbox commands, and activate one verification suite for them, while
`CT-I2-005` remains the first product-browser checkpoint.

## What the controls do

**Send.** At the foot of an Inbox thread, the send box asks the existing protected
`POST /v1/inbox/messages` operation to append one message to that thread. The browser submits the message
text and the answer it last received, and nothing else:

- the thread comes from the route the Server Action was bound to;
- the recipient is read back from the server's own recipient-scoped projection at submit time, because a
  recipient is an identity and a form field is not where an identity belongs;
- the sender is never sent — the API derives it from the bearer it validates;
- the previous answer is read for exactly one field, the command identity of a send the server has not
  confirmed, so pressing the box again retries that message instead of sending a second one.

The record answers in one of three ways, and the box renders each as what it is.

An **accepted** message re-renders the thread in place, so the message you just sent appears without a
reload. A **`202` / `durability_pending`** answer means the command committed but the durable
acknowledgement acceptance requires has not: no message is drawn, your words stay in the box, the line
underneath says the server has not confirmed the message, and the button offers `Retry`, which sends the
same message under the same command identity. Editing the words first makes it a new message, so it gets a
new identity. A **refusal** — an unaddressable principal, a thread you do not participate in, or a
mismatched participant — refuses by the API's own stable code, and the box renders that refusal's human
sentence and hands your words back.

Closing or reloading the page discards an unconfirmed draft and its command identity; that draft is held
for the lifetime of the document you typed it in. Origin-scoped draft persistence belongs to the product
browser command path, which is deferred to `CT-I2-005`.

**Promote.** On an unpromoted thread, the promote control asks the existing protected
`POST /v1/inbox/threads/{thread_id}/promotion` operation to either create one P2 ticket from the immutable
thread head, or link one in-scope ticket selected by its ID.

Neither control sends an actor, project, scope, custody, or authorization fact. The browser has no API
bearer, session credential, or direct network client; a Server Action holds the development-server bearer,
and the API authenticates and authorizes each operation as usual.

## Retry and refusal behavior

The server generates one `Idempotency-Key` before making each request and reuses it for every attempt, and
a send the record has not confirmed keeps that same key when the sender presses `Retry`. The request has a
finite attempt count, per-attempt timeout, full-jittered capped backoff, and total deadline. Responses
`408`, `425`, `429`, and the declared transient `5xx` statuses retry within that budget. A `202` is not one
of them: it is the record's own answer about durability, not transport noise, so it ends the request and is
shown as an unconfirmed message rather than retried inside the loop. A permanent problem document does not
retry; the UI displays its validated human `detail`, never raw JSON.

The sidebar's **New ticket** control remains disabled. Its copy describes only the unavailable direct-capture
path; it does not describe either Inbox control. The Feed composer likewise stays inert: steering a session
is a different capability with no authored command behind it.

## How it is verified

D42 as amended by D44 activates exactly one required suite for this boundary, `dogfood-inbox-controls`.

Each control's transport is proved against the real module with the network boundary stubbed: retry,
exhaustion, one reused `Idempotency-Key`, a transient status arriving as `text/plain` or with no body at
all, the exact request shape, and a refusal that reaches the operator as the server's own sentence.

The rendered claims are proved in a browser. The suite builds this dogfood server, serves it on an ephemeral
loopback port against a local stub record source, and reads the Inbox surface out of headless Chromium at
375, 768 and 1440 pixels. At each width it also *uses* the send box: it stamps the document, types, submits,
and proves the stamp survived — which is the only way to show that the message appeared without a reload. On
a thread the stub answers `202` for, the same three widths prove the other half: no message row is drawn,
the draft is still in the box, the unconfirmed sentence is on screen, and pressing the box again reaches the
stub under the same command identity. It never submits the promotion form from a browser, never addresses a
running instance, and never holds a credential.

## Boundaries that remain

- This does not activate a product route, product-browser session/CSRF design, or the product Playwright
  suite: `browser-e2e` stays deferred to `CT-I2-005`, and no browser evidence here counts toward it.
- This does not change the `ctower-web` React/Vite product decision or `CT-I2-005` sequencing.
- This does not grant browser authority or create a new mutation endpoint; both controls call commands the
  contract already authored.
- This is limited to low-value, reconstructible shadow dogfood. It is not a deployment or support promise.

See the [HTTP API reference](http-api.md#inbox), [CLI reference](cli.md#inbox), and the canonical
[specification](https://github.com/simjak/ctower/blob/main/SPEC.md).

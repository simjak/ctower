# ctower-ui dogfood Inbox controls

`apps/ctower-ui` is a local shadow-instance dogfood server, not the `ctower-web` product and not a
supported browser UI. [D41, D42 and D44](https://github.com/simjak/ctower/blob/main/DECISIONS.md) permit it
to present two existing Inbox commands, and activate one verification suite for them, while `CT-I2-005`
remains the first product-browser checkpoint.

## What the controls do

**Send.** At the foot of an Inbox thread, the send box asks the existing protected
`POST /v1/inbox/messages` operation to append one message to that thread. The browser submits the message
text and nothing else:

- the thread comes from the route the Server Action was bound to;
- the recipient is read back from the server's own recipient-scoped projection at submit time, because a
  recipient is an identity and a form field is not where an identity belongs;
- the sender is never sent — the API derives it from the bearer it validates.

An accepted message re-renders the thread in place, so the message you just sent appears without a reload.
An unaddressable principal, a thread you do not participate in, or a mismatched participant refuses by the
API's own stable code, and the box renders that refusal's human sentence.

**Promote.** On an unpromoted thread, the promote control asks the existing protected
`POST /v1/inbox/threads/{thread_id}/promotion` operation to either create one P2 ticket from the immutable
thread head, or link one in-scope ticket selected by its ID.

Neither control sends an actor, project, scope, custody, or authorization fact. The browser has no API
bearer, session credential, or direct network client; a Server Action holds the development-server bearer,
and the API authenticates and authorizes each operation as usual.

## Retry and refusal behavior

The server generates one `Idempotency-Key` before making each request and reuses it for every attempt. The
request has a finite attempt count, per-attempt timeout, full-jittered capped backoff, and total deadline.
Responses `408`, `425`, `429`, and the declared transient `5xx` statuses retry within that budget. A
permanent problem document does not retry; the UI displays its validated human `detail`, never raw JSON.

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
and proves the stamp survived — which is the only way to show that the message appeared without a reload. It
never submits the promotion form from a browser, never addresses a running instance, and never holds a
credential.

## Boundaries that remain

- This does not activate a product route, product-browser session/CSRF design, or the product Playwright
  suite: `browser-e2e` stays deferred to `CT-I2-005`, and no browser evidence here counts toward it.
- This does not change the `ctower-web` React/Vite product decision or `CT-I2-005` sequencing.
- This does not grant browser authority or create a new mutation endpoint; both controls call commands the
  contract already authored.
- This is limited to low-value, reconstructible shadow dogfood. It is not a deployment or support promise.

See the [HTTP API reference](http-api.md#inbox), [CLI reference](cli.md#inbox), and the canonical
[specification](https://github.com/simjak/ctower/blob/main/SPEC.md).

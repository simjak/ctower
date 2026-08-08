# ctower-ui dogfood Inbox promotion

`apps/ctower-ui` is a local shadow-instance dogfood server, not the `ctower-web` product and not a
supported browser UI. [D40](https://github.com/simjak/ctower/blob/main/DECISIONS.md) permits it to present
one existing Inbox promotion command while `CT-I2-005` remains the first product-browser checkpoint.

## What the control does

On an unpromoted Inbox thread, the control asks the existing protected
`POST /v1/inbox/threads/{thread_id}/promotion` operation to either:

- create one P2 ticket from the immutable thread head; or
- link one in-scope ticket selected by its ID.

The browser sends no actor, project, scope, custody, or authorization fact. It has no API bearer, session
credential, or direct network client. A Server Action holds the development-server bearer and forwards only
`{}` or `{"ticket_id":"<UUID>"}`; the API authenticates and authorizes the operation as usual.

## Retry and refusal behavior

The server generates one `Idempotency-Key` before making the request and reuses it for every attempt. The
request has a finite attempt count, per-attempt timeout, full-jittered capped backoff, and total deadline.
Responses `408`, `425`, `429`, and the declared transient `5xx` statuses retry within that budget. A
permanent problem document does not retry; the UI displays its validated human `detail`, never raw JSON.

The sidebar's **New ticket** control remains disabled. Its copy describes only the unavailable direct-capture
path; it does not describe the Inbox promotion control.

## Boundaries that remain

- This does not activate a product route, product-browser session/CSRF design, or Playwright suite.
- This does not change the `ctower-web` React/Vite product decision or `CT-I2-005` sequencing.
- This does not grant browser authority or create a second mutation endpoint.
- This is limited to low-value, reconstructible shadow dogfood. It is not a deployment or support promise.

See the [HTTP API reference](http-api.md#inbox), [CLI reference](cli.md#inbox), and the canonical
[specification](https://github.com/simjak/ctower/blob/main/SPEC.md).

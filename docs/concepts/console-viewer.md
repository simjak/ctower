# Console view grants

The Phase-1 Console viewer is a private, read-only server boundary for following one current crew terminal.
It does not make a tmux pane authoritative. Instead, it joins durable work facts to live runtime identity,
mints a short-lived viewing grant, and streams encrypted cursor-addressed output to one authenticated browser
session.

This page explains the design. See [How to deploy and verify the Phase-1 Console
viewer](../operations/console-viewer.md) for the operator procedure and the [HTTP API
reference](../reference/http-api.md#console-viewer) for exact routes.

## The problem

A tmux name is convenient but unsafe as identity. A session can be renamed, removed, or recreated under the
same name. A runner can restart while a browser still holds old state. A direct terminal reader also cannot
prove which human session was authorized, whether bytes were durably ordered, or who recovered restricted
output.

The viewer therefore separates three concerns:

- Record facts say which Project, seat, crew engagement, assignment interval, and work session are current.
- A trusted current-registration reader supplies runtime/runner/epoch/backend identity, and the registered
  Adapter reports the live Project and tmux incarnation for that backend.
- A `ConsoleViewGrant` authorizes one exact human browser session to claim one bounded stream.

No one concern can substitute for the others.

## The authority join

An operator first appends one allowance for an exact `ConsoleSessionRef`. The reference binds:

- tenant and Project;
- non-Commander seat principal and crew name;
- assignment ticket, assignment kind, and interval sequence;
- recorded work-session and runtime-attempt identities;
- runner identity and epoch;
- Adapter kind, opaque registered backend reference, and backend incarnation.

The allowance is eligibility, not a bearer credential. Discovery, mint, renewal, stream open, and every
stream poll recheck the applicable durable facts and current Adapter observation. The Adapter resolves the
opaque backend through its injected current-registration reader on every inspection, so replacing or
withdrawing the runtime/runner/epoch registration fences the old reference without process restart. On the first stream open,
the service rechecks the current human session and role binding, Project scope, policy revision, global
switch, assignment, work session, and revocations before it appends the stream claim and consumes the newest
grant. A stale assignment, closed work session, replaced runtime, advanced runner epoch, changed `@project`,
or recreated tmux session fences the reference instead of rebinding it.

The final grant, stream-open, encrypted-output, and custody-access decisions use one database-owned
anchor-lock primitive. Console-owned append-only authority changes share one tenant advisory lock; each
decision then locks the exact assignment, work session, Actor/target, human binding/session, and allowance
rows in the order compatible with canonical Work changes. The locks remain through persistence, so an
overlap finishes before the recheck or after the persisted fact without a handoff gap or inverse lock cycle.
Output and gap facts commit before their SSE event is returned, and a quiet poll releases its transaction
and collection lock before it waits.

```text
operator allowance ------+
current Record facts -----+--> exact grant decision --> one stream claim
live Adapter observation -+              ^
                                         |
human role binding + browser session ----+
```

Commander authority is deliberately absent on both sides of the join: a Commander-owned target engagement
cannot receive an allowance, and a Commander Actor cannot discover, mint, or claim a stream. Viewers and
operators still need an exact Project grant. Three denials inside the configured five-minute window append
an immutable suspension fact and suspend the Actor for the fact's full fifteen-minute interval.

## Grant lifetime

The control plane issues an unpredictable one-use grant bound to the Actor principal, human role binding,
human browser session, tenant, Project, allowance, full session reference, and policy revision. A grant
expires after at most five minutes. Renewal creates a new grant only after re-evaluating the complete join
and keeps the original continuous-view start. One renewal chain cannot exceed thirty minutes.

Grant state stays server-side. The SSE URL contains only the allowed session identity; every query string is
refused before authority or output access, so no grant, nonce, cookie, cursor, or token can ride in the URL.

## Restricted output custody

The Adapter reads bytes from an existing registered pipe-pane log. Before broadcast, the service divides
the bytes into independently decodable chunks of at most 16 KiB, assigns durable cursors, and encrypts each
object under a fresh AES-256 data key. That data key is wrapped under a referenced key-encryption key.
Database rows keep ciphertext, nonces, a distinct data-key reference, and the wrapping-key reference, never
the wrapping-key value.

The ordinary application role can insert encrypted output and read its metadata, but cannot select content
or wrapped-key columns. The dedicated NOLOGIN, NOINHERIT `console_output_reader` owns the fixed-search-path
recovery function. Each authorized recovery attempt appends and commits its access fact before invoking that
reader-owned content query; the function consumes that ID into an immutable recovery fact and returns only
the joined object. An access ID cannot recover content twice, and a reader failure cannot erase the attempt
fact. Decryption happens only after the one-use query succeeds.

The browser receives base64 output bytes and metadata. Phase 1 does not provide the contextual browser panel
or safe terminal renderer, so the server foundation is not a claim that hostile terminal control sequences
are safe to display in a product UI.

## Bounded streaming and gaps

One grant can claim at most one SSE stream. The policy caps decoded chunks at 16 KiB, delivery at 1 MiB per
minute, replay at 1 MiB per minute, and pending bytes at 256 KiB. A bounded ASGI producer continues the
one-object-per-authority-check loop while a network send is blocked, but never queues more than that decoded
cap. Crossing it replaces only still-unsent chunks with a durable `slow_consumer` gap and typed close; each
send is also bounded by the at-most-five-second authority poll interval. A durable cursor exists before its
chunk is broadcast. A per-allowance database lock serializes both Adapter output and gap commits across
processes. When the source truncates, the gap advances a source generation so the same numeric source cursor
can be recorded again without collision while SSE cursors remain monotonic.

Reconnect uses the `Last-Event-ID` header. If the source was truncated, a requested range cannot be proved,
or a rate/queue limit is reached, the server appends a gap fact and emits a typed `gap` event. The strict SSE
schema includes `rate_limited` alongside the cursor, truncation, unprovable-range, and slow-consumer gap
reasons. It never skips uncertain bytes silently. Expiry, session revocation, replacement fences, or the
global kill switch emit a typed `closed` event within the five-second polling ceiling.

## Private browser and process boundaries

Every browser request needs all three of these proofs:

1. the configured exact HTTPS `Origin`;
2. the secure HttpOnly human-session cookie;
3. the same CSRF value in the secure CSRF cookie, `X-Ctower-CSRF` header, and stored SHA-256 digest.

The supported listener entry point is `ctower_api.console_server.serve_console`. It derives its bind host
and port from the same validated exact HTTPS Origin, enables TLS directly, and disables proxy-header
authority. The listener accepts only an explicit literal loopback or Tailscale address. Hostname defaults,
wildcard binds, public addresses, CORS, Tailscale Funnel, and response compression are outside the boundary.

The Adapter uses bounded argument arrays to inspect one registered tmux target and reads only its configured
log beneath an allowlisted root. It has no Record-tier client, shell execution, pane-write or key-injection
operation, generic process endpoint, or fallback discovery.

## What Phase 1 does not activate

Phase 1 contains no browser UI and no terminal input. The Q3 typed-input verdict remains a separate,
controlled Phase-2 prerequisite. The older `apps/ctower-ui` terminal reader uses a different direct capture
and refresh path; it is neither an implementation nor evidence of this viewer boundary.

## Related material

- [Phase-1 operator procedure](../operations/console-viewer.md)
- [Phase-1 security verification](../security/console-phase1-verification.md)
- [Current terminal read](terminal-read.md), which documents the separate dogfood reader
- [Authored Console source specification](../specs/crew-console.md)
- [Console Q3 typed-input verdict](../security/console-q3-typing-cso.md)

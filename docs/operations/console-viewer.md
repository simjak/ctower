# How to deploy and verify the Phase-1 Console viewer

This procedure composes the read-only viewer on a private HTTPS origin, grants one exact current crew
session, and captures evidence without copying terminal bytes or credentials into ordinary artifacts.

The foundation is a pre-alpha server boundary. It is not a supported general deployment and it does not
provide the contextual browser UI.

## Prerequisites

You need:

- the repository candidate with migrations through `0065_console_view_grants.sql`;
- PostgreSQL with the cluster migration applied by a role allowed to create `console_output_reader`;
- an existing CT-I1-013 human identity provider and secure browser session;
- one current non-Commander assignment and open recorded work session;
- one existing tmux target with an exact `@project` option and an existing pipe-pane log;
- an HTTPS certificate for a literal loopback or Tailscale listener;
- one 32-byte wrapping-key value resolved in process and one `secret-service:`, `vault:`, or `kms:` reference
  identifying it;
- `ss`, `tailscale`, Docker, and the repository verification tools.

Never put the wrapping-key value, browser cookie, CSRF value, raw output, or grant nonce in a config file,
command history, evidence file, URL, status report, or log.

## 1. Provision database roles and migrations

Apply the signed migration chain using the repository's normal migration procedure. The cluster step creates
the exact NOLOGIN, NOINHERIT `console_output_reader` or refuses an unsafe pre-existing role with unexpected
attributes, membership, settings, ownership, or grants. Database migration `0065` creates the append-only
Console facts, the fixed-search-path reader-owned recovery function, and exact privileges.

Verify the reader boundary through the named acceptance test:

```bash
uv run pytest tests/acceptance/increment-1/test_console_reader_role_adoption.py::test_console_output_reader_role_has_only_the_authored_custody_surface -q
```

Do not grant the application service direct SELECT access to encrypted content or wrapped-key columns.

## 2. Register one exact backend

Read the live Project and incarnation from the same tmux socket the Adapter will use:

```bash
tmux -L mc show-options -t mc:engineer-console-p1 -v @project
tmux -L mc display-message -p -t mc:engineer-console-p1 '#{session_id}:#{session_created}'
```

Make the trusted current backend registry return one `ConsoleBackendRegistration` for the opaque reference,
using that exact target, the existing output-log path, runtime attempt ID, runner ID, and positive runner
epoch. Inject its lookup as `registration_reader` and set `allowed_log_root` to the narrow directory
containing the registered logs. The log must be an absolute regular-file path with no symlink component.
Every inspect/read resolves the registry again, and each read rechecks the complete registry and live tmux
identity both before and after reading from its already-open no-follow descriptor. The Adapter refuses a
withdrawn or malformed backend, a log outside that root, a changed Project, or a changed incarnation; it
never discovers, follows, persists bytes from, or silently rebinds replacements.

## 3. Compose the explicit policy and viewer

Construct `ConsolePolicy` with every value present. There are no defaults. The maximum Phase-1 values are:

| Field | Maximum |
|---|---:|
| Grant TTL | 300 seconds |
| Continuous view | 1,800 seconds |
| Revocation poll | 5 seconds |
| Decoded chunk | 16,384 bytes |
| Delivery window | 1,048,576 bytes / 60 seconds |
| Replay window | 1,048,576 bytes / 60 seconds |
| Pending bytes | 262,144 bytes |
| Denials | 3 / 300 seconds |
| Suspension | 900 seconds |

Compose `PostgresConsoleAuthority`, `PostgresConsoleOutputStore`, `TmuxConsoleAdapter`,
`AesGcmConsoleCipher`, and `ConsoleViewer`, then pair the viewer with one exact HTTPS origin:

```python
app = create_app(
    record,
    oidc=oidc,
    console=ConsoleRuntime(viewer, "https://100.84.252.114:8443"),
)
```

`ConsoleRuntime` makes the viewer/origin pair indivisible. Resolve the wrapping-key value directly into
`AesGcmConsoleCipher`; persist only its reference.

## 4. Bind the HTTPS listener privately

Start the direct-HTTPS listener through its supported entry point:

```python
from pathlib import Path

from ctower_api.console_server import serve_console

serve_console(
    app,
    runtime,
    certificate_file=Path("/run/ctower/console.crt"),
    private_key_file=Path("/run/ctower/console.key"),
)
```

It derives the literal host and port from `ConsoleRuntime` after the runtime has admitted only `127.0.0.1`,
`::1`, or an address in Tailscale's `100.64.0.0/10` or `fd7a:115c:a1e0::/48` ranges. It serves TLS directly,
disables proxy-header authority, and has no separate hostname, wildcard, public, proxy-derived, or
omitted/default host argument.

After start, capture the Console port from the live listener inventory:

```bash
ss -tlnp
tailscale funnel status
```

The declared port must appear exactly once on the configured private address. `inspect_ss_sweep` must return
that listener in `private_listeners` and return an empty `wildcard_listeners`. Funnel must not publish the
origin.

## 5. Append the allowance

Use the operator bearer route `POST /v1/admin/console/sessions` with the exact current reference and the
fixed Phase-1 values `adapter_key=tmux-v1`, `loop_kind=standard`, and
`sensitivity_class=restricted`. The server independently checks the current assignment/session join and live
Adapter observation before appending the allowance.

Keep the response's `console_session_id`; it is non-secret metadata. A second allowance for the same work
session refuses instead of replacing the first.

## 6. Prove the same-origin browser flow

From the private origin, use the secure browser session plus matching CSRF cookie/header to:

1. list `/v1/console/sessions` and confirm only the allowed current session appears;
2. mint `/v1/console/sessions/{id}/grants` and confirm `maximum_uses` is `1` and expiry is no later than five
   minutes;
3. open `/v1/console/sessions/{id}/events` without any query parameters; the boundary refuses the entire
   query string before stream authority or output access;
4. confirm `Content-Type: text/event-stream`, `Cache-Control: no-store`, and
   `X-Accel-Buffering: no`, with no content encoding or CORS authority;
5. record only cursor, decoded-byte count, ciphertext/object digest, event type, and elapsed time.

Never archive the `data` value of an output event. For reconnect, send only the last durable cursor in the
`Last-Event-ID` header as a non-negative signed-64-bit integer. Treat `chunk`, `gap`, and `closed` as the
complete event set. A `gap` reason may be
`cursor_unavailable`, `source_truncated`, `unprovable_range`, `slow_consumer`, or `rate_limited`; a null
`next_cursor` means continuity cannot be asserted and must not be replaced with a guessed cursor.

The HTTP transport prefetches only within the configured decoded pending-byte cap. If a client blocks ASGI
delivery past that queue, the server discards only the still-unsent queue, commits a `slow_consumer` gap and
typed close, and bounds each send by the authority poll interval (never more than five seconds).

## 7. Prove expiry, revocation, and fences

Use distinct grants for each case:

- Let one test-policy grant expire and confirm one typed `closed` event with `expired` within the configured
  poll ceiling.
- Revoke the allowance through `POST /v1/admin/console/sessions/{id}/revocation` and confirm the active stream
  closes with `revoked` within five seconds.
- Change one registered runtime fact in a controlled shadow registration, or present a stale exact reference,
  and confirm grant/open refuses with its specific runtime, runner, epoch, backend, Project, or incarnation
  fence code and reveals no output.
- Activate `POST /v1/admin/console/kill-switch` and confirm new admission refuses and active streams close with
  `globally_disabled`; clear it only through a later operator fact with a reason.
- Cause three controlled denied grant decisions in the configured five-minute window and confirm one
  append-only suspension fact retains the denial count, start, and full fifteen-minute expiry. Stop the
  probe there; do not generate additional denials during the suspension.

## 8. Run the named gates

```bash
uv run pytest tests/contracts/console -q
uv run pytest tests/modules/console -q
uv run pytest tests/acceptance/increment-1/test_console_collection_lock.py \
  tests/acceptance/increment-1/test_console_reader_role_adoption.py \
  tests/acceptance/increment-1/test_console_view_grants.py \
  tests/acceptance/increment-1/test_console_view_grant_races.py -q
just check
just verify
```

The exact candidate head must also retain a clean generated manifest, the same documentation candidate, and
the listener/direct-path inventory.

## Verification record

The archived digest-only record should name:

- candidate commit and migration/schema manifest digests;
- Project, crew, registered backend reference, runtime attempt, runner/epoch, and incarnation digests or
  non-secret identifiers;
- allowance/grant/stream/object/access/gap/close/suspension fact IDs, plus source generation and durable
  cursor metadata;
- output byte count and cryptographic digest, never output content;
- exact Origin and private bind endpoint;
- `ss` private/wildcard classification and Funnel result;
- typed expiry, revocation, fence, and kill-switch outcomes with measured elapsed time;
- named suite and full gate outcomes.

## Troubleshooting

| Refusal | Check |
|---|---|
| `console-origin-refused` | The `Origin` must equal the one configured HTTPS origin byte-for-byte. |
| `console-stream-query-refused` | Remove the entire query string; reconnect state belongs only in `Last-Event-ID`. |
| `console-csrf-invalid` / `auth-csrf-invalid` | Header, secure cookie, and stored digest must represent the same CSRF value. |
| `console-session-join-stale` | The assignment interval is current and the recorded work session is open and exact. |
| `console-project-fence-mismatch` | Live tmux `@project` still equals the allowed Project. |
| `console-incarnation-fenced` | The tmux session ID and creation time still match; append a new allowance for a legitimate replacement. |
| `console-grant-already-used` | Mint a new grant; a grant cannot claim a second stream. |
| `console-actor-suspended` | Stop repeated probes and wait for the explicit suspension interval. |
| `gap` event | Preserve its fact/cursor, stop assuming continuity, and reconnect only from a provable cursor. |

## Related material

- [Console view grants](../concepts/console-viewer.md)
- [HTTP API reference](../reference/http-api.md#console-viewer)
- [Phase-1 security verification](../security/console-phase1-verification.md)

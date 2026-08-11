# Console Phase-1 security verification

This page defines the evidence boundary for CT-I1-021. It covers only the read-only viewer server foundation.
It does not approve a browser renderer, terminal input, public exposure, or a production authority epoch.

## Security claim

An authenticated non-Commander human can view output from one exact operator-allowed current crew session
through a private, bounded, revocable stream. Runtime identity replacement fails closed. Exact output remains
RESTRICTED, envelope-encrypted, and recoverable only through the dedicated audited reader.

The pre-existing `apps/ctower-ui` terminal reader is outside this claim and cannot supply evidence for it.

## Trust boundaries

```text
browser session       control plane + Record             runtime Adapter
Origin + CSRF   --->  allowance/grant/cursor/custody ---> live tmux identity
                             |                                  |
                             +--> dedicated output reader <-----+ existing log only
```

The browser may ask for discovery, mint, renewal, and SSE. It cannot mint authority from payload fields,
connect to Record, select output rows, or address arbitrary backends. The Adapter may inspect one registered
tmux target and read one registered log. It cannot authorize, access Record, write a pane, inject a key, or
execute a shell.

## Required controls

| Control | Required proof |
|---|---|
| Exact identity join | Project, enabled non-Commander target and non-Commander Actor, seat, crew, assignment interval, work session, runtime attempt, runner/epoch, backend, live `@project`, and incarnation match at every decision point. Discovery, grant, renewal, first open, and each active poll rejoin the current target kind and disabled fact plus the exact current human session and role binding. Every Adapter call follows a side-effect-free durable authority preflight and precedes the final transactional recheck; a known refusal invokes the Adapter zero times. One fixed-search-path database primitive combines a tenant-scoped Console advisory lock with exact assignment-first row locks through grant, stream-open, encrypted-output, or custody-access persistence; canonical human binding/session revocations take that same tenant lock before appending their fact. An overlapping authority mutation therefore cannot commit inside the handoff, invert binding/principal locks, or create the canonical Work inverse-lock cycle. The Adapter rereads the trusted current backend registry and live identity before and after each no-follow descriptor read; replacement bytes are never persisted. |
| Human grant binding | Grant binds Actor, human role binding, browser session, allowance, full session reference, and policy revision; one stream use; five-minute TTL; thirty-minute chain. |
| Browser boundary | Exact HTTPS Origin, secure HttpOnly session cookie, matching secure CSRF cookie/header/persisted digest, no CORS, and refusal of every SSE query string before authority/output access. |
| Output custody | RESTRICTED classification, fresh per-object data-key reference, wrapped key under an unresolved reference, ordinary-service content SELECT denied, and a committed access-attempt fact consumed by one immutable recovery fact for every reader-owned content query. Unsafe pre-existing reader roles refuse adoption; envelope authentication failure appends a custody gap and typed close. |
| Stream bounds | 16 KiB decoded chunks, 1 MiB/min delivery, 1 MiB/min replay, a transport-owned 256 KiB decoded pending queue, one-object-per-authority-check recovery, durable cursor before broadcast, per-allowance single-writer output and gap commits, source generations across truncation, and a typed gap before uncertainty. A gap transaction commits before its SSE event is returned; an empty Adapter poll releases its connection and collection lock before waiting. ASGI production runs ahead only to that queue bound, replaces unsent chunks with the durable gap, and enforces the authority-poll deadline on every network send. |
| Containment | Typed expiry, revocation, replacement fence, and persistent global kill switch close within five seconds; repeated denials append an explicit bounded suspension fact. |
| Private network | Direct TLS through `serve_console`, with host and port derived from the exact Origin; literal loopback or Tailscale bind, disabled proxy-header authority, empty wildcard sweep, no Funnel/public DNS/Caddy route, and no public negative-probe success. |
| Direct-path absence | No shell, pane write, key injection, generic process route, Record-tier Adapter client, current-reader fallback, compression, or alternate stream transport. |

## Evidence handling

Console output may contain secrets or other restricted material. Verification artifacts may record only
non-secret identifiers, byte counts, hashes, cursors, typed outcomes, timestamps, and elapsed durations.
They must not record:

- raw or decoded output;
- ciphertext, wrapped data keys, nonces, or wrapping-key values;
- session cookies, CSRF values, bearer tokens, grant nonces, or browser storage;
- screenshots containing terminal content;
- URLs containing credentials or credential-like query parameters.

The evidence file itself is not the authority. Append-only database facts and the exact candidate digest
remain the re-checkable sources.

## Required negative probes

Run and retain typed outcomes for:

1. unauthenticated, expired-session, missing-CSRF, wrong-CSRF, and foreign-Origin requests;
2. Commander, foreign-Project, unallowed, revoked, stale-assignment, and closed-work-session discovery/mint;
3. changed live Project, runtime attempt, runner identity, runner epoch, backend reference, and tmux incarnation;
4. repeated grant claim, expired renewal, continuous-view exhaustion, invalid reconnect cursor, source
   truncation with numeric cursor reuse in a new generation, concurrent collectors, replay overflow,
   delivery overflow, and slow consumer;
5. ordinary application-role attempts to select output content, direct attempts to assume the dedicated
   reader role, and an injected reader failure after the access-attempt fact commits but before content is
   selected;
6. wildcard/public/hostname binds, Docker proxy wildcard listeners, Funnel publication, public-origin reach,
   and an unexpected Console port;
7. import/process inventory checks for Record-tier Adapter access, shell execution, pane write, generic
   process endpoints, and the old terminal-reader path.

Every negative must disclose zero output and create no grant/stream/content mutation beyond the explicitly
required denial, observation, access-attempt, gap, close, suspension, revocation, or containment fact.

## Required positive proof

The same candidate must run against real PostgreSQL and a real registered live tmux/log target over HTTPS on
a literal private bind. The proof must show:

- an operator allowance for the exact current session;
- same-origin browser discovery and one-use grant mint;
- real crew output observed through the new Adapter/custody/SSE chain, represented only by byte count and
  digest;
- distinct output data-key references and an append-only dedicated-reader access fact;
- typed expiry, session revocation, and stale-reference fence outcomes within the five-second close ceiling;
- a live `ss -tlnp` sweep with the expected private listener and no wildcard Console listener;
- no Funnel or public route;
- the three named Console suites plus `just check` and `just verify` on the exact head.

## Phase boundary

The Phase-1 output stream is one-way. Output bytes, SSE IDs, reconnect cursors, URLs, and browser state cannot
be interpreted as terminal commands. The Q3 typed-input verdict remains mandatory for Phase 2 and must be
implemented through its durable command, exact-byte custody, final-admission, race, and containment controls.
CT-I1-021 satisfies only the Q3 prerequisite that a proven Phase-1 viewer foundation exist; it activates no
typing route or grant.

## Related material

- [Console view grants](../concepts/console-viewer.md)
- [Phase-1 operator procedure](../operations/console-viewer.md)
- [Console Q3 typed-input verdict](console-q3-typing-cso.md)
- [Authored Console source specification](../specs/crew-console.md)

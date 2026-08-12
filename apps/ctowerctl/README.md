# ctowerctl boundary

`ctowerctl` and its shorter `ctl` alias are thin development Adapters over the generated Python client.
They expose only explicit authored command families: bootstrap; ticket, Work, Proof, and Workflow commands;
Board and health reads; protected outbox disposition; CompanyBundle validate/plan/apply/export; and local
spool inspection/recovery. Thread-first intake uses only the authored
`discussion|create_ticket|link_ticket` commands and one-time discussion promotion through that same
generated-client and encrypted-spool path. There is no arbitrary operation dispatcher or client-side
authorization engine.
Knowledge is the closed `knowledge add|list|get` family. `add` names `--scope org|project` and, for project
scope, an explicit `--project-key`; it accepts either `--body-file` plus `--title` or one `--source-ref`.
Add uses the protected spool, while list/get call the generated client directly. Persisted project seats and
the server-side static-source mount remain authoritative.
Native agent messaging is the closed `inbox send --to <agent> [--thread <id>] <text>`, `inbox ack
--state delivered|read <message>`, `inbox list [--unread]`, `inbox read <thread>`, and `inbox read-state
<thread>` family, plus `inbox notify --to <agent> <text>` and `inbox promote <thread> [--ticket <id>]`.
`notify` uses the stable notification delivery UUID as `--command-id`, derives sender identity server-side,
and groups both directions of a seat pair into one thread. Mission Control's production `tools/notify`
appends its durable row first, then invokes this protected command; refusal, retry exhaustion, or local
unavailability remains an explicit non-blocking rail-2 outcome. Promotion creates a P2 ticket from the
thread head when `--ticket` is absent and links the named existing ticket otherwise. Send, recipient-only
acknowledgement, and promotion use the protected spool. The three reads call the generated client directly
and never queue; opening a thread never records a read fact.

`ticket workflow list` is the one local Workflow read: it enumerates coherent active revisions from the
installed pack tree without a network request. With exactly one revision, omitted start pins expand to that
exact installed revision before enqueue. The existing resolve operation derives an omitted ref from the
persisted run. Complete explicit pins and refs remain supported and server validation remains authoritative.
`ticket review-dispatch list` reads the emitted review intent, consumption, and verdict links, while
`ticket review-dispatch consume` records routing for the authenticated principal's registered model identity
through the same encrypted-spool path as other protected Work mutations. Neither command accepts model-family
labels or launches a reviewer.

`dream-dispatch list` reads only the authenticated project seat's nightly effect and output custody; an
operator reads all Project effects plus the operator-only fleet effect.
`dream-dispatch consume <effect> --output-digest <sha256>` is spool-protected and accepts no lane, crew,
harness, model, family, effort, or tier labels; those facts come from the authenticated substrate binding.
Foreign-Project and non-operator fleet consumption refuse as `project-scope-denied` before any custody is
recorded.
The online-only `dream-lane bind` command is the operator ceremony that creates that authenticated
principal's immutable binding exactly once. It uses the closed codex/primary/fallback/effort/tier selection
declared by the authored contract; it never accepts a principal or model-family label, and it is not queued
for later execution.

`beat-dispatch routines` lists the five registered fleet-beat revisions, exact timezone-local schedules,
pinned prompt digests, fixed DIRECTOR target, and next fires. Digest and sprint retain literal
Europe/Vilnius hours across DST. Corrected digests replace only the active trigger, so the command continues
to list exactly five while prior revision/effect facts remain immutable. `beat-dispatch list` returns the immutable full-prompt
effects. Both are online-only operator reads: they do not queue, mutate server custody, or accept caller
schedule/prompt/target labels. Mission Control's sibling beat consumer performs ledger-deduplicated tmux
delivery while a beat-specific lane-binding ceremony remains unapproved.

`beat-dispatch retire <routine_ref> --command-id <uuid>` is the online-only operator mutation for one exact
versioned fleet beat. It reads the credential only from stdin, sends no request body, never enters the local
spool, and prints the generated immutable retirement receipt. A replay with the same body/key returns that
same receipt; later keys refuse as `beat-routine-already-retired`, unknown and foreign-only references as
`beat-routine-not-found`, and every non-operator as `beat-routine-retire-forbidden` before target disclosure.

The same installed-policy rule closes the Proof input loop. Criteria freeze accepts either an explicit
candidate digest or literal candidate content, hashing the latter as exact UTF-8 bytes, and defaults omitted
criteria to the sole installed gate policy. Evidence add accepts literal content or a bounded content file,
computes an omitted artifact digest over the exact UTF-8 content, defaults the sole installed criterion, and
lets Proof resolve an omitted candidate digest only to the frozen current candidate. Verdict does the same
current-candidate and sole-criterion resolution. Proof receipts name the resolved candidate digest and name
the artifact digest for evidence. Explicit values are never replaced; server validation still refuses a
stale candidate or a content/digest mismatch.

`--base-url` may be omitted. When it is, `ctowerctl._discovery` resolves the one instance declared in the
owner-only `~/.config/ctower/cli-instances.json` catalog — never an environment variable. Zero declared
instances or more than one both refuse by name (usage exit `64`) instead of guessing; an explicit
`--base-url` always takes priority and skips discovery entirely. `ctower-private-vps expose-cli` writes
that catalog from the installed runtime's own configuration and links `ctowerctl`, `ctl`, and
`ctower-shadow-ctl` onto `~/.local/bin`, so any crew or operator on the box can run them from any directory
with no repo checkout.

Bearer authority and the one-use bootstrap capability are read as one bounded line from stdin. They are
never accepted as arguments or environment configuration, written to the spool, or echoed. Server
authentication, authorization, validation, idempotency, CAS, and durability decisions remain authoritative.

Request capture and the explicit priority, triage, owner, Ticket-relation, blocker, and closure-evaluation
commands use the same protected generated-client/spool path. Request list is online-only. The CLI supplies
neither Actor nor owner/source/state authority and creates no Ticket implicitly.

`digest morning [--date YYYY-MM-DD] [--output text|json]` is an online-only operator read. Text is the
default deterministic STE projection; JSON is the exact generated boundary. Both keep unknown totals,
unreached scopes, and unresolved relation targets explicit. The command sends no notification and enters no
spool; the existing Mission Control caller owns notify-rail delivery and scheduling.

A mutation is encrypted and durably appended before its first network send only when the generated operation
behind it carries `spool_policy: allowed`. Reads, `bootstrap first-tenant`, and the authenticated online-only
`migration ctower-project` operations carry `spool_policy: forbidden`: they are never appended, and they fail
rather than queue when the server is unreachable. The spool is origin-scoped, owner-only, sequence/hash
chained, and keyed only through an allowlisted operating-system credential backend. On Linux the development
path requires an active D-Bus session, Secret Service, and an unlocked collection. There is no plaintext,
file, environment, or `keyrings.alt` fallback. A missing or locked keyring exits `74` before enqueue/send and
does not change existing ciphertext; reads and the unspooled commands can continue.
Each command also carries only a keyed opaque identity for the stdin credential used at enqueue. Replay
compares the current stdin credential before every send. Rotation or a different principal quarantines the
old command with zero network sends; restore the original identity and explicitly retry, or discard and
re-enqueue under the new identity.

A server that permanently rejects a command has named its refusal, so the quarantine receipt keeps that
name and nothing else: the mutation output and every later `spool list` / `spool quarantine list` row carry
`server_refusal` with the refusal `status` and one `name` taken from the authored contract's refusal codes.
No response `title`, `detail`, or other body text is ever persisted or listed, because the CLI cannot tell
authored server prose from whatever a reachable origin chose to send. A refusal the allowlist does not name
is recorded as the content-free sentinel `unrecognized_refusal`, carrying nothing derived from the refusing
input, so the durable name is always one of the authored codes or that sentinel. The replay executor is a
caller's own object, so a refusal crossing that boundary is re-derived from the allowlist before it reaches
a receipt rather than trusted for having been validated once already. A locally quarantined command carries
its `reason_code` and no `server_refusal`, because no server named anything.

Corrupt command ciphertext remains visible as a bounded quarantine row with its sequence, byte count, and
artifact digest. It blocks replay until an operator discards that exact sequence and digest. The disposition
is authenticated and append-only; the corrupt ciphertext remains as local audit evidence.

Exit meanings are stable: `0` read/accepted, `64` usage/input, `69` permanent rejection or quarantine,
`74` local/keyring/integrity failure, and `75` queued, unreachable, `durability_pending`, or bounded retry
exhaustion. Notification mirroring uses at most four attempts within ten seconds with capped exponential
jitter; exhaustion leaves the same encrypted pending command and sequence available for explicit
reconciliation. Exit `75` never
claims server acceptance. Mutation output always identifies the stable command ID and local state. `control
health` is the one read whose exit reflects its content rather than request success alone: a `DEGRADED` or
`STATE_UNKNOWN` status exits `69` even though the read itself succeeded.

The E2 private-VPS install adds `ctower-shadow-ctl`, a local wrapper that resolves one operator or Commander
reference from Secret Service and calls this exact public CLI in-process; it adds no operations or
authorization. The wheel and Secret Service paths remain development artifacts, not a published package or
production recovery promise. See the
[protected CLI guide](../../docs/guides/protected-cli.md) and
[CompanyBundle guide](../../docs/guides/company-bundle.md).

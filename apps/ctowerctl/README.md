# ctowerctl boundary

`ctowerctl` and its shorter `ctl` alias are thin development Adapters over the generated Python client.
They expose only explicit authored command families: bootstrap; ticket, Work, Proof, and Workflow commands;
Board and health reads; protected outbox disposition; CompanyBundle validate/plan/apply/export; and local
spool inspection/recovery. Thread-first intake uses only the authored
`discussion|create_ticket|link_ticket` commands and one-time discussion promotion through that same
generated-client and encrypted-spool path. There is no arbitrary operation dispatcher or client-side
authorization engine.

`ticket workflow list` is the one local Workflow read: it enumerates coherent active revisions from the
installed pack tree without a network request. With exactly one revision, omitted start pins expand to that
exact installed revision before enqueue. The existing resolve operation derives an omitted ref from the
persisted run. Complete explicit pins and refs remain supported and server validation remains authoritative.

The same installed-policy rule closes the Proof input loop. Criteria freeze accepts either an explicit
candidate digest or literal candidate content, hashing the latter as exact UTF-8 bytes, and defaults omitted
criteria to the sole installed gate policy. Evidence add accepts literal content or a bounded content file,
computes an omitted artifact digest over the exact UTF-8 content, defaults the sole installed criterion, and
lets Proof resolve an omitted candidate digest only to the frozen current candidate. Verdict does the same
current-candidate and sole-criterion resolution. Proof receipts name the resolved candidate digest and name
the artifact digest for evidence. Explicit values are never replaced; server validation still refuses a
stale candidate or a content/digest mismatch.

Bearer authority and the one-use bootstrap capability are read as one bounded line from stdin. They are
never accepted as arguments or environment configuration, written to the spool, or echoed. Server
authentication, authorization, validation, idempotency, CAS, and durability decisions remain authoritative.

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

Corrupt command ciphertext remains visible as a bounded quarantine row with its sequence, byte count, and
artifact digest. It blocks replay until an operator discards that exact sequence and digest. The disposition
is authenticated and append-only; the corrupt ciphertext remains as local audit evidence.

Exit meanings are stable: `0` read/accepted, `64` usage/input, `69` permanent rejection or quarantine,
`74` local/keyring/integrity failure, and `75` queued, unreachable, or `durability_pending`. Exit `75` never
claims server acceptance. Mutation output always identifies the stable command ID and local state.

The E2 private-VPS install adds `ctower-shadow-ctl`, a local wrapper that resolves one operator or Commander
reference from Secret Service and calls this exact public CLI in-process; it adds no operations or
authorization. The wheel and Secret Service paths remain development artifacts, not a published package or
production recovery promise. See the
[protected CLI guide](../../docs/guides/protected-cli.md) and
[CompanyBundle guide](../../docs/guides/company-bundle.md).

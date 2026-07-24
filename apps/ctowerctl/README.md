# ctowerctl boundary

`ctowerctl` and its shorter `ctl` alias are thin development Adapters over the generated Python client.
They expose only explicit authored command families: bootstrap; ticket, Work, Proof, and Workflow commands;
Board and health reads; protected outbox disposition; CompanyBundle validate/plan/apply/export; and local
spool inspection/recovery. There is no arbitrary operation dispatcher or client-side authorization engine.

Bearer authority and the one-use bootstrap capability are read as one bounded line from stdin. They are
never accepted as arguments or environment configuration, written to the spool, or echoed. Server
authentication, authorization, validation, idempotency, CAS, and durability decisions remain authoritative.

Every non-bootstrap mutation is encrypted and durably appended before its first network send. The spool is
origin-scoped, owner-only, sequence/hash chained, and keyed only through an allowlisted operating-system
credential backend. On Linux the development path requires an active D-Bus session, Secret Service, and an
unlocked collection. There is no plaintext, file, environment, or `keyrings.alt` fallback. A missing or
locked keyring exits `74` before enqueue/send and does not change existing ciphertext; reads can continue.

Exit meanings are stable: `0` read/accepted, `64` usage/input, `69` permanent rejection or quarantine,
`74` local/keyring/integrity failure, and `75` queued, unreachable, or `durability_pending`. Exit `75` never
claims server acceptance. Mutation output always identifies the stable command ID and local state.

The wheel and Secret Service paths are verification artifacts for the pre-alpha development slice, not a
published package, supported deployment, or production recovery promise. See the
[protected CLI guide](../../docs/guides/protected-cli.md) and
[CompanyBundle guide](../../docs/guides/company-bundle.md).

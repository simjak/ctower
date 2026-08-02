# Isolated restore and enablement denial

Create a fresh root-signed installation identity. It must differ from the source installation and be
verified outside the restored database. Restore into an isolated network with effects disabled and
ordinary database reads denied.

Perform and record these checks in the only legal order:

1. recover database bytes and WAL;
2. recover versioned object access;
3. recover exact key references;
4. reapply durable erasure tombstones;
5. verify the migration manifest and schema;
6. verify command/event/acceptance chains;
7. verify contiguous external anchors;
8. verify every object after decryption by plaintext digest;
9. verify tombstones and absence of erased bytes;
10. verify the signed expected-source inventory;
11. reconcile every active root-supervisor, effect, and provider journal;
12. run the fixed synthetic verification.

The I1 inventory always names all three source kinds. Until a kind is activated it must have an explicit
`not_exercised`, `zero_source`, count-zero entry. Missing entries never mean empty success. Once active,
the entry must carry a trust-root reference, trusted cursor, activation event, and matching
reconciliation evidence.

Accepted-record RPO must be zero, artifact RPO at most five minutes, and RTO at most four hours. Record
all failed checks as unresolved findings and retain quarantine. A green report still does not enable
reads: one authenticated enablement receipt must bind the exact tenant, new installation identity,
restore run, and report digest after the persisted report and findings are re-read. Wrong or stale
digests fail closed. I1 effects remain disabled even after ordinary reads are enabled.

To prove restart behavior, construct a new process and database connection before checking the gate.
No in-memory decision counts as enablement evidence.

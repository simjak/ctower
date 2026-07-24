# Recovery evidence capture

Each local drill produces one immutable, digest-addressed evidence directory outside human-facing
runtime lists. Capture:

- candidate commit and migration-manifest digests;
- tool binary and secret-free config digests;
- tenant, backup, restore-run, and new installation identifiers;
- repository/object versions and ciphertext/plaintext digests;
- key references, key versions, wrapped/public-key digests, and external verification outcomes;
- anchor range, previous/current anchor digests, signature verification, and readback;
- signed inventory revision plus all three I1 source declarations;
- all 12 ordered restore-step outcomes and evidence digests;
- accepted and artifact RPO, RTO, unresolved findings, denial attempts, enablement receipt, and
  post-restart gate result;
- start/end timestamps and the operator/recovery authority references.

Do not capture tokens, passwords, private keys, wrapped key bytes, recovered plaintext, customer content,
or full process environments. Canonicalize each JSON artifact, compute SHA-256, upload it immutably, read
it back, and record the returned object version. A screenshot or exit code is supporting context, not
proof of recovered bytes.

The terminal report must distinguish local CP3-C evidence from CP3-D production evidence. Until real
off-host targets and destructive drills exist, report production activation, measured production RPO/RTO,
alerts, and `cutover-rpo0` as deferred.

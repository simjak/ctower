# ctower-systemd-vps boundary

Future narrow `systemd-vps/v1` integration inside the internal Effects boundary, paired with a separately
supervised root release helper. The application may submit only an allowlisted, short-lived grant and desired
artifact identity; that intent never authorizes an install.

The root helper independently verifies the fetched bytes and digest, signature/attestation subjects, and
trusted builder/workflow identity against root-owned trust and provenance policy before installation. Any
missing, mismatched, revoked, or untrusted evidence performs no install. The helper emits a hash-chained,
cursor-reconcilable receipt for each terminal disposition. Its live implementation and fault-injection
implementation must pass the same internal contract before Increment 2 exits. This pair does not create a
general public Effect Provider Seam.

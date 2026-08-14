# Secret handling

ctower records secret-binding names and vault or operating-system credential reference classes. It must not
persist credential values, bearer tokens, login sessions, or private keys in tickets, logs, artifacts,
configuration bundles, reusable images, caches, checkpoints, or generated files.

## Runtime boundary

Credentials are resolved just in time only after authorization, projected into a fenced execution or effect
boundary, and then revoked and scrubbed. An agent, workflow, pack, provider adapter, or extension receives no
standing credential merely because it can request work.

Secret references are metadata, not proof that the credential is valid or that an effect succeeded. External
mutations still require idempotency, receipts, and reconciliation.

For the development-shadow procedure that binds only a digest and reference to one project identity, see
[Self-hosting boundary](../self-hosting.md).

## Protected CLI boundary

The CLI reads current bearer/bootstrap authority from one bounded stdin line and never persists it. Its
offline mutation spool keeps only redacted request fields in AES-GCM records and stores the random master
key in an allowlisted operating-system credential service. Linux requires an active D-Bus Secret Service
session with an unlocked collection. Missing, locked, null, or unapproved keyring state fails before
enqueue/send and leaves ciphertext unchanged; there is no plaintext, file, environment, or `keyrings.alt`
fallback. CompanyBundle carries secret-binding names and reference classes only.

## Repository boundary

- Keep local values in ignored environment or vault tooling; never commit them.
- Use synthetic values in tests and documentation.
- Do not place credentials in command examples, issue reports, screenshots, or fixture archives.
- Treat generated output and Git history as part of the scan surface.
- Never waive a secret-detection failure.

Local ignore rules and pre-commit hooks are convenience layers. Required CI and history scanning remain the
release gate because hooks can be bypassed.

## Suspected exposure

Stop work, preserve only a redacted incident trail, rotate or revoke the value at its provider, quarantine
affected artifacts, and scan both the worktree and history before resuming. Do not paste the value into a
public issue while asking for help. Report a ctower vulnerability using the private process in
[SECURITY.md](https://github.com/simjak/ctower/blob/main/SECURITY.md).

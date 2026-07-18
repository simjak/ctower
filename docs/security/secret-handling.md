# Secret handling

Ctower persists secret-binding names and vault/OS credential reference classes, never credential values or login sessions. Credentials are resolved just in time only after authorization, projected into a fenced execution/effect boundary, then revoked and scrubbed. Reusable images, caches, checkpoints, logs, artifacts, and configuration bundles cannot contain standing credentials or PII.

A suspected secret is non-waivable: stop, quarantine exposure, rotate at the provider, preserve a redacted incident trail, and rerun worktree plus history scans.

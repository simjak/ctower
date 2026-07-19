# Runtime compatibility contracts

This directory is the CT-L0-007 authored compatibility contract. It does **not** select or pin ctower's
Python runtime. D6 remains authoritative until complete product evidence is produced in an approved
execution boundary and the operator records an append-only supersession.

## What is implemented

- `ct-l0-007-matrix.json` fixes the reviewed candidates, dependencies, observations, and immutable Linux
  image identities.
- `matrix-input.schema.json` rejects any unreviewed matrix value.
- `matrix-result.schema.json` accepts only the exact six-leg topology and closed evidence vocabulary.
- `tools.compatibility` validates an externally produced report, binds it to the authored matrix, scans the
  exact output bytes for credentials, PII, URLs, and private paths, then publishes atomically without
  following symlinks.

The validator can be invoked when an approved external runner supplies a report:

```bash
python3 -m tools.compatibility \
  --matrix contracts/compatibility/ct-l0-007-matrix.json \
  --report /path/from/an/approved-external-runner.json \
  --output /path/to/validated-result.json
```

The public package intentionally has no `ExecutionPort`, local process adapter, Docker adapter, probe CLI,
or execution opt-in. POSIX process groups are lifecycle controls, not a security boundary. Native package
installation and probe execution are deferred until a disposable runner or VM adapter provides real
containment, secret isolation, resource limits, cleanup, and attestable provenance. Reports in the current
contract are marked `external-runner-noncanonical` and cannot earn canonical runtime-selection credit.

## Historical diagnostic retained for audit

On 2026-07-19 an earlier local implementation exercised standard-GIL CPython 3.12.13, 3.13.14, and 3.14.6
on an unconfined Darwin `arm64` host and in Linux `arm64` containers. Each row reported all ten observations.
That implementation and its executable surface were removed after review found that host subprocesses could
escape the claimed containment and evidence strings could disclose local data.

The historical input digest was
`sha256:6be418a9ff3bb346678ec15b0c7b616c93389507aec61813a4019fd532f4cd84`; the historical report digest was
`065e42bcbf3bf9c1f4ce5f4c68c4ab012ab88464ae63e1d9390c51867920574d`. These digests are audit references,
not accepted evidence, and the old report does not cross the current closed result contract.

## Honest residuals

- No approved disposable compatibility runner or VM adapter exists.
- The release-helper wheel and generated clients do not exist, so product-artifact evidence remains
  `not_exercised` with reason `artifact_absent`.
- Linux `amd64` product evidence and external provenance remain unproven.
- No accepted project lock, `.python-version`, fallback selection, or D6 supersession exists.

Therefore the matrix remains useful for designing the future runner, but it is insufficient for selecting
ctower's runtime.

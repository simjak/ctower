# Runtime compatibility evidence

This directory is the CT-L0-007 compatibility contract. It does **not** select or pin ctower's Python
runtime. D6 remains authoritative until the operator reviews complete product evidence and accepts an
append-only supersession.

## Reproduce the preflight

The runner bootstraps the exact reviewed uv version once into a matrix-scoped tool root, creates
uv-managed macOS environments, and creates disposable containers from immutable Linux image
digests. It never uses a Homebrew/Pyenv candidate interpreter, never accepts a mutable image tag, and
removes every temporary environment/container after the run. Every external command has a bounded
deadline and process-group termination policy.

```bash
python3 -m tools.compatibility \
  --matrix contracts/compatibility/ct-l0-007-matrix.json \
  --allow-unconfined-host-diagnostic \
  --output "${TMPDIR:-/tmp}/ctower-compatibility-result.json"
```

Native execution is denied by default because changing `HOME`, `PATH`, and temporary directories is not
host containment. The explicit flag enables an **unconfined diagnostic only**. Every v1 report carries
`evidence_scope: unconfined-diagnostic` and cannot earn canonical passing credit. Canonical native evidence
requires the repository's disposable, no-secret, least-privilege GitHub Actions boundary and its external
workflow provenance; a local flag or environment variable is never an attestation.

The diagnostic result is strict JSON. Commands use `$BOOTSTRAP_UV`, `$PINNED_UV`, `$DOCKER`,
`$CTOWER_MATRIX_ROOT`, `$CTOWER_COMPAT_ROOT`, `$CTOWER_CONTAINER[...]`, and
`$CTOWER_CONTAINER_ID[...]` placeholders; the writer fails closed if a macOS/Linux home or temporary path
survives normalization. Raw, host-specific reports are not committed because telemetry identities,
durations, and machine identities are observations rather than authored contracts. This README retains the
sanitized durable summary; reviewers can reproduce the preflight from the versioned matrix.

## 2026-07-19 historical diagnostic

Every row used standard-GIL CPython and passed all ten required observations: exact runtime/ABI,
dependency resolution, strict Pydantic extra denial, FastAPI/OpenAPI, psycopg3, OpenTelemetry, Ruff,
the Pydantic mypy plugin, JSON Schema generation/validation, and minimal wheel build/install/import.

The historical local report bound to input digest
`sha256:6be418a9ff3bb346678ec15b0c7b616c93389507aec61813a4019fd532f4cd84` and had report SHA-256
`065e42bcbf3bf9c1f4ce5f4c68c4ab012ab88464ae63e1d9390c51867920574d`. Its exact ordered topology was:

| Python | Environment | Observed architecture | Required observations | Resolved-lock SHA-256 | Probe duration |
|---|---|---|---:|---|---:|
| 3.12.13 | macOS unconfined diagnostic | Darwin `arm64` | 10/10 observed | `3e4a86744310ea58fe20b628fd6c7750ed4c50db467bfcc1c271bfe7b8bccf2c` | 13,606 ms |
| 3.12.13 | Linux container | Linux `aarch64` / image `arm64` | 10/10 passed | `73462d17ec677a20bb7ec9e1071339ed62ca4446abc5fa277f3695a202a3d6a6` | 12,543 ms |
| 3.13.14 | macOS unconfined diagnostic | Darwin `arm64` | 10/10 observed | `3e4a86744310ea58fe20b628fd6c7750ed4c50db467bfcc1c271bfe7b8bccf2c` | 30,198 ms |
| 3.13.14 | Linux container | Linux `aarch64` / image `arm64` | 10/10 passed | `36bcc5290317fe1bc5617672a3fd1ed5eb23113244e0384b721b7fb97593444b` | 19,718 ms |
| 3.14.6 | macOS unconfined diagnostic | Darwin `arm64` | 10/10 observed | `3e4a86744310ea58fe20b628fd6c7750ed4c50db467bfcc1c271bfe7b8bccf2c` | 10,463 ms |
| 3.14.6 | Linux container | Linux `aarch64` / image `arm64` | 10/10 passed | `36bcc5290317fe1bc5617672a3fd1ed5eb23113244e0384b721b7fb97593444b` | 26,572 ms |

The old report crossed the then-current schema and models, but it is not accepted evidence: macOS execution
was unconfined, output truncation was not terminal, and Docker cleanup authority came from create output
rather than an independent exact-name/owner inspection. The corrected runner fails closed on all three.

The immutable Linux identities are recorded in `ct-l0-007-matrix.json`. Official Python release metadata
and gzipped-source checksums are also pinned there: 3.12.13 is the current D6-line representative, while
3.13.14 and 3.14.6 are the June 10, 2026 maintenance releases. The exact dependency surface is pinned in
the same input; each result additionally records the complete resolved freeze and its digest.

## Honest residuals

- The ctower release-helper wheel and generated clients do not exist, so every run records both as
  `not_exercised` with reason `artifact_absent`; the fixture builds only its own minimal wheel smoke.
- Linux evidence currently covers the available `linux/arm64` Docker host. An `amd64` artifact run remains
  required before claiming architecture-wide Linux compatibility.
- Official source URLs/checksums are recorded, but this preflight exercises uv-managed macOS distributions
  and Docker Official Images rather than rebuilding CPython from those source tarballs.
- No accepted project lock, `.python-version`, fallback selection, or D6 supersession is created here.
- No canonical six-leg report exists yet; the historical table is retained for audit, not passing credit.

Therefore the dependency preflight supports keeping 3.14.6 as the leading candidate, but the evidence is
**insufficient for final runtime selection** until the absent product artifacts and remaining Linux
architecture are exercised and the operator accepts the decision.

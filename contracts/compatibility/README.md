# Runtime compatibility evidence

This directory is the CT-L0-007 compatibility contract. It does **not** select or pin ctower's Python
runtime. D6 remains authoritative until the operator reviews complete product evidence and accepts an
append-only supersession.

## Reproduce the preflight

The runner creates disposable uv-managed macOS environments and disposable containers from immutable
Linux image digests. It never uses a Homebrew/Pyenv candidate interpreter, never accepts a mutable image
tag, and removes every temporary environment/container after the run.

```bash
python3 -m tools.compatibility \
  --matrix contracts/compatibility/ct-l0-007-matrix.json \
  --output "${TMPDIR:-/tmp}/ctower-compatibility-result.json"
```

The public result is canonical JSON. Commands use `$BOOTSTRAP_UV`, `$DOCKER`,
`$CTOWER_COMPAT_ROOT`, and `$CTOWER_CONTAINER` placeholders; the writer fails closed if a macOS/Linux
home or temporary path survives normalization. Raw, host-specific reports are not committed because
durations and machine identities are observations rather than authored contracts. This README retains the
sanitized durable summary; reviewers can reproduce the exact report from the versioned matrix.

## 2026-07-19 preflight result

Every row used standard-GIL CPython and passed all ten required observations: exact runtime/ABI,
dependency resolution, strict Pydantic extra denial, FastAPI/OpenAPI, psycopg3, OpenTelemetry, Ruff,
the Pydantic mypy plugin, JSON Schema generation/validation, and minimal wheel build/install/import.

| Python | Environment | Observed architecture | Required observations | Resolved-lock SHA-256 | Probe duration |
|---|---|---|---:|---|---:|
| 3.12.13 | macOS isolated | x86_64 | 10/10 passed | `3e4a86744310ea58fe20b628fd6c7750ed4c50db467bfcc1c271bfe7b8bccf2c` | 19,312 ms |
| 3.13.14 | macOS isolated | x86_64 | 10/10 passed | `3e4a86744310ea58fe20b628fd6c7750ed4c50db467bfcc1c271bfe7b8bccf2c` | 13,330 ms |
| 3.14.6 | macOS isolated | x86_64 | 10/10 passed | `3e4a86744310ea58fe20b628fd6c7750ed4c50db467bfcc1c271bfe7b8bccf2c` | 13,987 ms |
| 3.12.13 | Linux container | aarch64 | 10/10 passed | `73462d17ec677a20bb7ec9e1071339ed62ca4446abc5fa277f3695a202a3d6a6` | 6,401 ms |
| 3.13.14 | Linux container | aarch64 | 10/10 passed | `36bcc5290317fe1bc5617672a3fd1ed5eb23113244e0384b721b7fb97593444b` | 4,421 ms |
| 3.14.6 | Linux container | aarch64 | 10/10 passed | `36bcc5290317fe1bc5617672a3fd1ed5eb23113244e0384b721b7fb97593444b` | 5,992 ms |

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

Therefore the dependency preflight supports keeping 3.14.6 as the leading candidate, but the evidence is
**insufficient for final runtime selection** until the absent product artifacts and remaining Linux
architecture are exercised and the operator accepts the decision.

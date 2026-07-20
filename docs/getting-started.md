# Getting started

There is no supported installable ctower service yet. Today, getting started means reading and validating
the repository and its development-only durable-ticket walking slice, then contributing to the remaining
system.

## Clone the repository

```bash
git clone git@github.com:simjak/ctower.git
cd ctower
```

HTTPS also works:

```bash
git clone https://github.com/simjak/ctower.git
```

## Understand the source-of-truth map

Read these in order:

1. [`README.md`](https://github.com/simjak/ctower/blob/main/README.md) for scope and current status.
2. [`ARCHITECTURE.md`](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md) for the compact topology.
3. [`IMPLEMENTATION-ROADMAP.md`](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md) for the
   walking-skeleton sequence.
4. Relevant sections of [`SPEC.md`](https://github.com/simjak/ctower/blob/main/SPEC.md) before changing a
   contract or invariant.
5. [`DECISIONS.md`](https://github.com/simjak/ctower/blob/main/DECISIONS.md) before revisiting a locked choice.

Exact authored schemas belong in `contracts/`; concrete versioned workflows and policies belong in
`packs/`; generated outputs belong in `generated/`. The specification owns human semantics, while the
declared executable artifact owns exact representation.

## Run the frozen verification gates

ctower's product runtime remains unresolved, but the verification host is frozen independently. Install the
hash-locked Python verification dependencies and the frozen JavaScript workspace without lifecycle scripts:

```bash
python3 -m pip install --require-hashes -r requirements/verify.txt
pnpm install --frozen-lockfile --ignore-scripts
```

Run the warm gate while developing, then run the full gate from a clean candidate commit:

```bash
just check
just verify
```

The verification locks and CI pins do not select ctower's product runtime or supersede D6. Do not add
`.python-version` or `uv.lock`; update verification inputs only through the reviewed lock process in the
[development guide](contributing/development.md).

## Inspect the L0 compatibility contracts

The first implemented slice is a strict compatibility contract validator, not an executable preflight or a
ctower runtime. Its versioned matrix covers standard-GIL CPython 3.12.13, 3.13.14, and 3.14.6. The recorded
2026-07-19 local run remains historical diagnostic evidence, not a canonical pass.

The public command validates an externally produced report and publishes only closed, sanitized fields:

```bash
python3 -m tools.compatibility \
  --matrix contracts/compatibility/ct-l0-007-matrix.json \
  --report /path/from/an/approved-external-runner.json \
  --output /path/to/validated-result.json
```

No public compatibility API or CLI executes native dependencies, Docker, package installers, or probes on
the developer host. Executable and canonical evidence remains deferred until a real disposable runner or VM
adapter supplies containment and attestable provenance. Current reports are explicitly
`external-runner-noncanonical` and cannot select the product runtime.

Read [`contracts/compatibility/README.md`](https://github.com/simjak/ctower/blob/main/contracts/compatibility/README.md)
before interpreting a result. The contract does not cover the absent release-helper wheel and generated
clients, and it does not authorize a runtime pin or lockfile.

Contract traceability has a separate deterministic source-to-output path. Edit the authored map, regenerate
the index, then verify that committed bytes match:

```bash
python3 -m tools.checks.traceability --root . --write
python3 -m tools.checks.traceability --root . --check
```

The source is `contracts/traceability/sources.json`; the generated output is
`generated/traceability-index.json`, with hashes recorded in `generated/.generated-manifest.json`. This is
the current code-truth generation path. It does not generate narrative documentation.

## Preview the documentation

GitHub Pages is the chosen low-operations public documentation UI. The site uses MkDocs Material with
built-in search and no analytics or remote fonts. Pull requests build the site strictly; trusted `main`
deploys it after Pages is configured for GitHub Actions. After installing `mkdocs-material` in an isolated
development environment:

```bash
mkdocs serve
```

Open the local address printed by MkDocs. A documentation change is ready only when `mkdocs build --strict`
passes and every internal link resolves.

## Choose a contribution

Start with the [development guide](contributing/development.md), then select work from a repository issue.
Early implementation should strengthen one complete vertical path rather than add speculative providers,
plugins, or UI breadth. The project intentionally defers remote execution and extension surfaces until the
local durable path proves the interface they need.

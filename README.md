# ctower

ctower is a greenfield, durable control tower for human operators and replaceable AI-agent runtimes. The canonical product, architecture, workflow, verification, and build contract is [`SPEC.md`](SPEC.md). Historical design rationale is append-only in [`DECISIONS.md`](DECISIONS.md). The terminal-safe [`ARCHITECTURE.md`](ARCHITECTURE.md) is a derived operator/implementer atlas and never overrides the SPEC. The proposed dogfood sequence lives in [`IMPLEMENTATION-ROADMAP.md`](IMPLEMENTATION-ROADMAP.md); it is non-normative and does not authorize work or override the SPEC.

This repository is currently in the **docs-first L0 bootstrap**. It contains the repository boundaries, authored contracts, declarative component examples, and executable repository-quality policy. It does not yet contain control-plane, runner, CLI, release-helper, or browser product behavior.

## Architecture at a glance

- Python owns the trusted control plane, runner, CLI, and separately isolated release helper.
- TypeScript owns the browser application; no frontend framework has been selected.
- `contracts/` is the only authored schema home; `generated/` is machine-owned.
- `packages/ctower-kernel` is the modular-monolith authority boundary.
- `packages/ctower-runner-sdk` defines replaceable harness/supervisor/target/workspace/telemetry seams without record-tier authority.
- `packs/` contains versioned desired-state components; prose and YAML never advance runtime state by themselves.
- `tools/checks` is one deep Repository Policy Module used by hooks, local commands, and CI.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the control/record/worker/effect and heartbeat/cron views,
then read the boundary READMEs under `apps/`, `packages/`, `contracts/`, `packs/`, and `deploy/`
before adding files.

## Runtime pin status

There is intentionally no `.python-version`, `uv.lock`, or Python image pin yet. Decision D6 retains Python 3.12 as the exact historical authority until CT-L0-007 records a compatibility matrix for 3.12, 3.13.14, and standard-GIL 3.14.6 and the operator accepts an append-only supersession. Adding an exact runtime file before that decision would misrepresent durable decision history.

The root `pyproject.toml` therefore declares the compatibility window `>=3.12,<3.15` and configures tools against the 3.12 language floor. The compatibility evidence belongs under `contracts/compatibility/`. Lockfiles are generated and committed only after one exact runtime/toolchain is accepted. The Node patch and pnpm lock are similarly deferred to the browser L0 toolchain review; this does not select a browser framework.

## Quality contract

After the development tools are installed from the accepted locks:

```text
just check    # warm, non-mutating gate
just verify   # full, non-mutating gate including clean-diff proof
```

The dependency-light bootstrap validation available now is:

```bash
python3 -m compileall -q tools/checks
python3 -m unittest discover -s tests/repository -v
python3 -m tools.checks --root . --profile full
python3 -m tools.checks --root . --profile full --expected-suites
uv run --no-project --with 'jsonschema>=4.25,<5' python -m tools.checks --root . --profile full --execute-suites
uv run --no-project --with 'jsonschema>=4.25,<5' python -m unittest discover -s tests/contracts/l0 -v
```

`tools/checks/expected-suites.toml` is the versioned verification-scope source. Current suites must contain executable, unskipped tests and their shell-free argv commands must pass within the declared timeout; later increment suites remain visibly `not_yet_required` and are never executed or presented as passes.

Repository limits, exceptions, typing, observability, generation, and review laws are normative in [`docs/contributing/CODING_STANDARDS.md`](docs/contributing/CODING_STANDARDS.md).

## Bootstrap boundaries

Do not add live ticket-state files, another architecture/diagram document, another implementation roadmap,
a `Factory` service, a generic plugin host, raw secrets, mutable `latest` references, or provider-specific
authority. `ARCHITECTURE.md` is the sole derived atlas and must stay subordinate to `SPEC.md`.
`IMPLEMENTATION-ROADMAP.md` is the sole proposed sequencing document and remains subordinate to the SPEC.
Implementation begins from the stable IDs in SPEC's bootstrap backlog after the L0 contracts are reviewed.

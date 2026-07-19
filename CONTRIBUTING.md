# Contributing to ctower

Thank you for helping build durable, inspectable work orchestration. ctower is pre-alpha and being developed
in public; clear problem reports, design challenges, documentation, tests, and narrowly scoped code changes
are all valuable.

## Before you start

- Read the [project status](https://simjak.github.io/ctower/project-status/) and confirm the capability exists
  before reporting runtime behavior.
- Search existing issues and pull requests.
- Discuss large domain, architecture, persistence, security-boundary, or public-interface changes before
  implementation.
- Read the canonical [`SPEC.md`](SPEC.md), [`DECISIONS.md`](DECISIONS.md), and relevant
  [coding standards](docs/contributing/CODING_STANDARDS.md).

## Development workflow

1. Fork the repository and create a focused branch from `main`.
2. Make one cohesive change. Preserve the authoritative homes described in the
   [development guide](https://simjak.github.io/ctower/contributing/development/).
3. Add or update tests, exact contracts, and public documentation together with changed behavior.
4. Run the dependency-light checks from the [getting-started guide](https://simjak.github.io/ctower/getting-started/).
   Once the accepted toolchain lands, run `just check` and `just verify`.
5. Open a pull request using the repository template and respond to independent review.

Do not hand-edit files under `generated/`. Do not add a second specification, architecture atlas, roadmap,
or task board. Do not introduce a plugin/provider abstraction without two real implementations that need it.

## Pull-request expectations

A merge candidate must be:

- scoped, typed, tested, observable, and documented;
- compliant with Module ownership, dependency, complexity, nesting, and source-size policy;
- free of secrets, private infrastructure details, generated drift, and untracked runtime artifacts;
- explicit about failure, authorization, restart, idempotency, rollback, and residual risk;
- independently reviewed by someone other than its author.

Local hooks help, but required CI is authoritative and must pass without waivers hidden in source. Temporary
policy exceptions must use the repository's exact expiring exception mechanism.

## Issues and security

Use the issue forms for reproducible bugs, focused feature proposals, and documentation problems. Use
[GitHub Discussions](https://github.com/simjak/ctower/discussions) for open-ended questions when available.
Do not disclose a vulnerability in an issue, discussion, or pull request; follow [SECURITY.md](SECURITY.md).

By contributing, you agree that your contribution is licensed under the repository's Apache License 2.0.
All participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

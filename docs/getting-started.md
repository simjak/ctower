# Exercise the development slice

The [Quickstart](quickstart.md) is the product-oriented first use. This page places that tour inside the
repository development loop.

## Start with the disposable tour

Complete [Repository setup](start-here/repository-setup.md), then run:

```bash
just quickstart
```

This proves that the current wheel, generated client, protected CLI, API, Workflow, Proof path, and
PostgreSQL fixture work together. It leaves no runtime or database behind.

## Run the warm gate

While editing:

```bash
just check
```

The warm gate checks formatting, lint, types, public documentation, workflows, version mirrors, repository
policy, authored contracts, generated drift, traceability, and the intended-tree secret scan. It does not
need a persistent database.

## Run the review gate

From a clean committed candidate:

```bash
just verify
```

The review gate repeats the warm checks, executes the required PostgreSQL-backed suites with branch
coverage, checks the expected-suite inventory, scans reachable history for secrets, and proves the tree is
still clean. A dirty tree is a refusal, not a warning.

These commands validate the repository. They do not install ctower, create a supported tenant, expose a
service, or prove production recovery.

## Inspect the exact surfaces

- [CLI reference](reference/cli.md) lists the closed installed command grammar.
- [HTTP API](reference/http-api.md) groups the authored operations and links the source contract.
- [Protected CLI and spool](guides/protected-cli.md) explains authority input, idempotency, local custody,
  and retry behavior.
- [Company configuration](guides/company-bundle.md) explains validation, planning, apply, and export.
- [Current availability](start-here/availability.md) separates development evidence from unsupported and
  planned behavior.

Use only synthetic or reconstructible data in development fixtures and the private shadow runtime.

# Durable work, not durable terminals

ctower is an open-source control plane for durable work performed by humans and replaceable AI agents. It
keeps ownership, workflow state, evidence, and audit facts authoritative when an agent process, terminal,
or machine disappears.

```text
request -> Work -> Workflow -> evidence -> gate -> outcome
             durable control plane       replaceable workers
```

!!! warning "Pre-alpha and development-only"
    ctower is not a supported install, deployment, hosted service, backup/restore product, browser UI,
    runner, or production release. Its current value is a tested development slice and a public design for
    earning those capabilities honestly.

## Start here

1. Read [Project status](project-status.md) for the capability boundary.
2. Follow [Repository setup](start-here/repository-setup.md) to validate a checkout.
3. Read [Exercise the development walking slice](getting-started.md) before running the full acceptance
   gate.
4. Check [What is deliberately unavailable](start-here/availability.md) before planning an integration or
   operational use.

## Navigate by need

- [Guides](contributing/development.md) explain repository development and verification.
- [Concepts](concepts.md) define the durable-authority vocabulary.
- [Operations](operations/current-boundary.md) state the present operational boundary.
- [Reference](https://github.com/simjak/ctower/tree/main/contracts) begins with authored contracts and the
  [development OpenAPI](https://github.com/simjak/ctower/blob/main/contracts/http/openapi.yaml).
- [Internals](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md) are deliberately behind the
  architecture atlas and specification.
- [Contributing](contributing/development.md) explains how to make a verified change.

The site orients readers; it does not duplicate the canonical [system specification](https://github.com/simjak/ctower/blob/main/SPEC.md),
[architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md),
[decision log](https://github.com/simjak/ctower/blob/main/DECISIONS.md), or
[implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md).

# Observability

ctower treats observability as part of correctness, not an optional dashboard layer. This page describes the
operating contract; it does not claim that the runtime telemetry implementation exists yet.

## Three-dimensional health

Health has three independent dimensions:

| Dimension | Question |
|---|---|
| **Availability** | Can the service accept and process work? |
| **Completeness** | Are required events, traces, receipts, and projections present? |
| **Correctness / integrity** | Do durable records, proofs, fences, and external observations agree? |

“All clear” is allowed only when all three are green for the requested scope. A healthy HTTP endpoint cannot
hide exporter loss, projection lag, an unknown effect outcome, or a broken audit chain.

## Telemetry contract

The authored cross-process context is `contracts/observability/telemetry-context.schema.json`. Application
composition roots own SDK and exporter wiring; domain Modules depend only on typed context and stable log
records. Asynchronous durable work uses trace links rather than pretending it is one synchronous call stack.

Public Interfaces and real adapter wrappers are expected to emit:

- structured typed logs with stable event names;
- OpenTelemetry-compatible spans across process and provider boundaries;
- low-cardinality operational and business metrics;
- explicit health signals for durability, reconciliation, projections, and evidence freshness.

Collector or exporter failure must never roll back a valid Record transaction, but it must make telemetry
completeness visibly unhealthy.

## Redaction and cardinality

Never place prompts, secrets, user content, artifact bytes, bearer values, credential-bearing URLs, or raw
high-cardinality identifiers in metric labels. Raw execution output belongs in access-controlled,
content-addressed artifacts, not application logs.

Protected effects, authorization denials, proof/gate denials, incidents, rollbacks, stale fences, and
reconciliation failures retain complete audit records. Public documentation and example dashboards must use
synthetic identifiers only.

## Operational evidence

Each dashboard and alert must identify the exact telemetry contract revision, the failure condition it
represents, and a named recovery role. Operational readiness is proven through failure injection and restore
drills, not the existence of a dashboard screenshot.

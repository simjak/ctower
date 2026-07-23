# Observability

ctower treats observability as part of correctness, not an optional dashboard layer. CP3-B implements the
authenticated stored health response and its durability, scheduler, outbox, projection, backup, anchor,
object, and synthetic contributor vocabulary. The broader collector/dashboard runtime described below
remains a target contract.

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

Unsupported CP3-B contributors report `STATE_UNKNOWN` with an explicit `not-applicable-in-cp3-b` reason;
they never inherit another contributor's watermark. A Board GET is read-only and cannot repair lag. Poison
recovery requires an authenticated append-only retry or tombstone disposition, while the poison and its
deduplicated Attention finding remain immutable evidence.

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

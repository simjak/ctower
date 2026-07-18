# Observability operating contract

Health has three independent dimensions: availability, completeness, and correctness/integrity. “All clear” is allowed only when all three are green for the requested scope. Collector/export failure marks completeness unhealthy and is never hidden behind API availability.

The authored telemetry contract is `contracts/observability/telemetry-context.schema.json`. Application composition roots own SDK/exporter wiring; domain Modules depend only on typed context and stable log records. Dashboards and alerts must link to the exact metric/log/trace contract revision and carry a named recovery owner.

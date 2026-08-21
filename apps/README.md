# Applications

Applications are separately deployable composition roots around authored contracts and public package Interfaces. They do not own domain authority.

- `ctower-api`: FastAPI command/query entry point and co-artifact control worker.
- `ctower-runner`: outbound worker-plane daemon and Adapter composition root.
- `ctowerctl`: generated-client CLI; only operations marked `spool_policy: allowed` use its encrypted local spool.
- `ctower-ui`: retained empty Next.js shell with the sole `/setup` route for the future company-creation wizard; it has no product reads, mutations, or browser dogfood controls.
- The read-only browser surfaces are removed until the separately activated product browser checkpoint; generated TypeScript remains an API client for contract coverage, not a product UI.

No application may import another application or connect around its declared package Interface.

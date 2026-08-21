# Applications

Applications are separately deployable composition roots around authored contracts and public package Interfaces. They do not own domain authority.

- `ctower-api`: FastAPI command/query entry point and co-artifact control worker.
- `ctower-runner`: outbound worker-plane daemon and Adapter composition root.
- `ctowerctl`: generated-client CLI; only operations marked `spool_policy: allowed` use its encrypted local spool.
- The browser surfaces are intentionally absent until the separately activated product browser checkpoint; generated TypeScript remains an API client for contract coverage, not a runnable UI.

No application may import another application or connect around its declared package Interface.

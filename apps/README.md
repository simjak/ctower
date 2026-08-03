# Applications

Applications are separately deployable composition roots around authored contracts and public package Interfaces. They do not own domain authority.

- `ctower-api`: FastAPI command/query entry point and co-artifact control worker.
- `ctower-runner`: outbound worker-plane daemon and Adapter composition root.
- `ctowerctl`: generated-client CLI; only operations marked `spool_policy: allowed` use its encrypted local spool.
- `ctower-web`: strict TypeScript browser client with exactly five primary surfaces.
- `ctower-ui`: phase-1 read-only operator dogfood surface over the shadow instance's read API. It is not `ctower-web`, claims none of that boundary's checkpoints, and makes no mutation.

No application may import another application or connect around its declared package Interface.

# Applications

Applications are separately deployable composition roots around authored contracts and public package Interfaces. They do not own domain authority.

- `ctower-api`: FastAPI command/query entry point and co-artifact control worker.
- `ctower-runner`: outbound worker-plane daemon and Adapter composition root.
- `ctowerctl`: generated-client online CLI; an encrypted offline spool remains deferred.
- `ctower-web`: strict TypeScript browser client with exactly five primary surfaces.

No application may import another application or connect around its declared package Interface.

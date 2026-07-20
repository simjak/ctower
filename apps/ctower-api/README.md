# ctower-api boundary

Python composition root for the development walking slice. Its FastAPI handlers validate generated HTTP
models and call the public Access, Work, and Record Interfaces for bootstrap, ticket create/read/timeline,
and protected custody transfer. Durable decisions remain in kernel Modules and the Postgres Record Adapter;
the API never connects around those Interfaces. Projections, health, and the control worker remain deferred.

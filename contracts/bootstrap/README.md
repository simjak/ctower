# First-tenant bootstrap contract

This directory defines the sole pre-tenant trust-root ceremony from SPEC v1.5 and D15. It is an authored contract only; no route, token issuer, database mutation, or runtime authority exists in this L0 scaffold.

The root-owned installer generates a random capability and persists only its digest, accepted local/private origin, absolute expiry of at most 15 minutes, revocation state, and unused state. Plaintext is delivered once through a root-readable channel. `ctowerctl bootstrap first-tenant --token-stdin` reads it from standard input and sends it in a protected authorization header; the token is never a request-body field, argument, URL, environment value, task, event, artifact, or log field. `Idempotency-Key` is a separate required header.

The request body contains only desired first-tenant identities and vault-binding references. It cannot define profiles, skills, workflows, credentials, sessions, tickets, verdicts, runtime facts, or secret values.

When implemented, the handler must use one serializable transaction to lock the singleton capability, prove that tenant count is zero, create exactly one tenant, disabled historical `bootstrap_installer` principal B0, the initial operator/platform administrator, the durable Commander, and vault-binding references, then append the canonical command result, events, outbox records, immutable receipt digest, capability consumption, and B0 disablement. Exact replay of the same token, idempotency key, and canonical body hash returns the original receipt without re-execution.

Wrong origin, expiry, revocation, changed-body replay, a consumed capability under another key/body, any existing tenant, concurrent loss, or crash must produce a typed refusal with zero partial or duplicate authority. After the first successful transaction, the route is permanently closed to new work; CompanyBundle and later administration use ordinary authenticated Admin/Catalog commands.

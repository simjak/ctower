# Authored contracts

This is the only authored schema home. Contracts are strict, versioned, immutable after publication, and fail closed on unknown fields. Generated Python/TypeScript models and clients belong under `generated/`; applications do not hand-maintain parallel wire types.

The current files are L0 schema skeletons, not an active runtime API. Every schema requires contract tests and deterministic generation before publication. The one-use first-tenant request body and its transport/atomicity constraints live under `bootstrap/`; the capability issuer and route do not exist yet.

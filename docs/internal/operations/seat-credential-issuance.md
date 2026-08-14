# Project-seat credential ceremony

This is the development-shadow ceremony for issuing and revoking a credential bound to one stable
`(project_key, seat_key)` identity. It closes the project-grant input gap recorded in the #185 plan review,
PR #189 §2 finding 4. It is not a production credential procedure: ctower remains pre-alpha, and real or
irreplaceable credentials remain outside the approved development boundary.

The operator authorizes the binding and scopes. The seat holder creates and retains the bearer value. Ctower
receives only its SHA-256 digest and a secret-manager reference; it never accepts, returns, logs, or stores the
bearer plaintext. The `owner` scope does not exist.

## Before issuance

Record the reviewed request in the controlling work item:

- tenant, project key, stable seat key, and human-readable seat name;
- the least set of `capture`, `transition`, and `evidence` scopes needed by the seat;
- the operator principal reference and a fresh idempotency command ID;
- the approved secret-manager reference class and the planned expiry or rotation point.

The seat holder generates at least 256 bits of randomness inside the approved secret manager or operating
system credential service. On the same trusted boundary, compute the SHA-256 digest of the exact bearer bytes.
Keep the bearer value there. Transfer only the lowercase `sha256:<64 hex>` digest and the opaque credential
reference to the operator through the reviewed control channel.

Do not put the bearer in a command argument, environment variable, issue, chat, screenshot, log, fixture,
request body, or repository file. See [Secret handling](../../security/secret-handling.md).

## Issue

Authenticate as the tenant's operator and call the generated client's `issue_seat_credential` operation with
a strict `SeatCredentialIssueRequest`. Supply the digest, reference, display name, project key, seat key, and
reviewed scopes. Supply the fresh command ID separately as the idempotency key.

Issuance is refused for Commander credentials with `credential-issuance-refused`. A request containing an
unknown scope such as `owner` is rejected at the HTTP boundary. Reusing the same command ID and exact request
returns the same receipt; changing the request under that command ID is refused by the ordinary idempotency
contract.

Record the returned credential ID, principal ID, event ID, project/seat binding, scopes, and durability state.
The append-only `access.seat_credential_issued` event repeats the reference and authority facts but contains
neither the bearer nor its digest. `durability_pending` is an honest committed-primary receipt, not proof of
off-host acknowledgement.

## Verify least authority

The seat holder may now present the bearer through ctower's protected authentication boundary. Verify one
allowed operation and one denied operation without recording the bearer itself:

| Grant | Intended mutation family | Missing-scope refusal |
|---|---|---|
| `capture` | ticket/intake capture and comments | `credential-scope-denied` |
| `transition` | custody, Work, and Workflow transitions | `credential-scope-denied` |
| `evidence` | criteria, evidence, and verdict commands | `credential-scope-denied` |

Project authority is independent of those capability scopes. The server derives the project grant from the
immutable seat binding on every authentication. A seat may create a ticket only with an eligible Commander
from its granted project, and a cross-project write is refused as `project-scope-denied` before a work fact or
version change is committed. Initial custody without a project grant is refused as `project-grant-required`.

## Revoke and confirm

Authenticate as the operator and call the generated client's `revoke_seat_credential` operation with the
credential ID, a fresh command ID, and the reviewed reason. Record the returned event ID and durability state.
The append-only `access.seat_credential_revoked` event retains the reason without credential material.

Immediately make one harmless authenticated call with the revoked bearer through the protected boundary. The
next call must return HTTP 401 with `credential-revoked`; do not retry or substitute a broader credential. An
exact revocation replay returns the stored receipt, while a second distinct revocation is refused as
`credential-already-revoked`.

Close the controlling work item only after the secret manager marks the bearer destroyed or retired, the two
Access event IDs and named next-call refusal are recorded, and no credential material appears in the ceremony
record. If plaintext may have escaped, follow
[Suspected exposure](../../security/secret-handling.md#suspected-exposure)
instead of continuing this ceremony.

# O10: bounded backoff for every network request

The repository-wide coding standards remain in
[contributing/CODING_STANDARDS.md](contributing/CODING_STANDARDS.md). This page defines the O10
network-resilience rule used during review.

Every outbound request that can cross a process or network boundary MUST execute under a bounded
retry policy. There are no single-shot network calls. This includes HTTP, database, container
daemon, object-store, provider API, and loopback-service requests.

Applying a retry policy does not mean retrying every failure. The policy MUST classify the first
result and fail immediately when that result is permanent.

## Required properties

Each network call site MUST satisfy all of these properties:

1. **Concrete bounds.** Every attempt has a timeout. The complete operation has both a finite
   maximum attempt count and a finite maximum elapsed-time or deadline. Backoff sleeps cannot
   exceed the remaining deadline.
2. **Exponential backoff with jitter.** Delay grows exponentially between retryable failures,
   includes jitter, and is capped. An unbounded retry loop, uncapped sleep, or policy without a
   finite age limit is a defect and a potential hang.
3. **A legible typed retry predicate.** The call site selects, or visibly inherits, a predicate
   that distinguishes transient failures from permanent failures. Timeouts, connection resets,
   rate limiting (`429` or its typed provider equivalent), and transient `5xx` responses may be
   retryable. Other `4xx` responses and typed permanent refusals are terminal. Catch-all retry
   predicates are defects.
4. **A typed exhausted outcome.** When either bound is spent, the operation stops with a named
   terminal result or exception that identifies exhaustion and preserves the attempt count,
   elapsed time, and last classified failure. Exhaustion is logged and counted. Returning an
   untyped empty value, hiding the last failure, or continuing in the background is a defect.
5. **Idempotency before retrying a mutation.** A mutating request may be sent only after its
   idempotency has been proved by operation semantics, reconciliation, or a stable
   idempotency/coordination key. Every attempt of one mutation MUST reuse the same key. Generating a
   fresh key per attempt, or retrying a mutation whose duplicate effect cannot be prevented or
   reconciled, is a defect.

## Generative call-site discovery

Coverage MUST be proved from repository structure, not from a hand-maintained list of known
endpoints, clients, or URLs. The check or review query MUST derive the denominator from
network-capable imports and invocations, client and adapter registrations, and code-generation
inputs and outputs across authored and generated source. It MUST then map every discovered call
site to an approved retry policy and fail closed when a new or unclassifiable call site appears.
A hand list can provide labels or ownership after discovery, but it cannot define coverage.

Until an automated structural check exists, reviewers MUST perform the same repository-wide
discovery and record its result. The absence of a common network chokepoint does not waive this
rule; it is a gap to close.

## Reviewer yes/no check

For every generatively discovered outbound call site, answer all of the following:

- Does the call execute under a retry policy rather than as a single-shot request?
- Are the per-attempt timeout, maximum attempts, and maximum elapsed time or deadline finite and
  visible?
- Is exponential backoff jittered, capped, and constrained by the remaining deadline?
- Does a legible typed predicate retry only transient failures and terminate permanent failures?
- For a mutation, is idempotency proved and is one stable coordination key reused on every
  attempt?
- Does exhaustion stop with a typed, observable terminal outcome?

Any **no** is a review defect.

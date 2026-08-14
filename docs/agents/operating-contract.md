# The agent operating contract

This page is written for an agent operating ctower. It states the rules literally, with no implied context.
If you follow only one rule, follow this one:

**A refusal is data. Read it. Do not retry until you have changed what it objected to.**

ctower refuses with typed, machine-readable codes precisely so that a caller can decide correctly. Blind
retry against a typed refusal is the failure mode this contract exists to prevent.

## Rule 1 — one intent gets one idempotency key

Every mutation carries a UUID idempotency key. Most commands require you to supply it:

- HTTP: the `Idempotency-Key` header.
- CLI: `--command-id`. `ticket capture`, `ticket create`, and `synthetic run` generate one client-side when
  you omit it and print it in their result.

The rules:

1. **Generate it once, before the first attempt.** Not per retry.
2. **Reuse the same key for every replay of the same intent.** Replaying a key with the same semantics
   returns the original result. This is how you recover from an unknown outcome without creating duplicates.
3. **Never reuse a key for different content.** That is refused as `idempotency-conflict`.
4. **A new attempt at the same intent is still the same key.** If a defaulted ticket command returns `75`,
   run `spool drain` or replay the printed `command_id` explicitly. Re-entering the create command without
   `--command-id` generates a new intent.

An omitted ticket command ID is safe for the CLI's own encrypted-spool replay. Supply one explicitly when
another process must coordinate the retry.

For `ticket capture` and `ticket create`, omitting `--initial-custodian-id` selects the authenticated
principal already resolved from stdin authority. A Commander may establish its own custody. An operator
must explicitly name an eligible Commander; omission is refused rather than silently putting the operator
in custody. Any explicit value is still an authorization request, not authority by itself.

## Rule 2 — you supply the expected version, and you read it back from refusals

Version-guarded mutations require `--expected-version` (HTTP: `expected_version` in the body). It is the
`version` field from your last read of the ticket.

If it does not match, the request is refused as `version-conflict` with **`current_version` in the problem
body**.

Correct handling:

```text
1. read the ticket        -> version = 4
2. mutate expected_version=4
3. refusal: version-conflict, current_version=6
4. re-read the ticket, decide whether your intent still applies
5. mutate expected_version=6 with the SAME command_id if the intent is unchanged
```

Do not loop step 2 with an incremented guess. The version moved because something else changed the ticket;
your intent may no longer be valid.

## Rule 3 — authority goes on stdin, once, per invocation

One line, maximum 8192 characters, trailing newline stripped.

```bash
printf '%s\n' "${authority}" | ctl --base-url http://127.0.0.1:8080 ticket query "${ticket_id}" --project-key ctower
```

Never place a credential in an argument, an environment variable, or a file the CLI reads. Missing or
oversized authority is exit `64`. Authority never appears in ctower's output.

Spooled mutations — the ones rule 7 lists — additionally require the local encrypted spool, which on Linux
needs an allowlisted Secret Service backend in an active D-Bus session. Reads and the unspooled commands work
without it; a spooled mutation fails closed with `keyring_unavailable` at exit `74`.

## Rule 4 — know what each exit code means

| Exit | Name | Means | Do |
|---:|---|---|---|
| `0` | success | Query returned, or mutation reached `accepted` | Continue |
| `64` | usage | Invalid command, invalid input, or missing stdin authority | Fix the invocation. Never retry unchanged |
| `69` | permanent | Typed server refusal, quarantine barrier, or a failed assertion | Read the problem `code`. Change something or escalate. **Never retry unchanged** |
| `74` | local failure | Spool, keyring, filesystem, or integrity failure on **your** machine | Fix the local environment. The command was not sent |
| `75` | temporary | Durably queued, server unreachable, or `durability_pending` | Retry the **same** `--command-id` after a delay |

The two that agents most often get wrong:

**`75` is not a failure.** The most common cause is `durability_pending`: the semantic result is committed
and the off-host acknowledgement has not landed yet. Your ticket exists. Creating another one is the bug.
See [Durability and acceptance](../concepts/durability.md).

**`69` is not retryable.** It is a decision, not a transient condition. `workflow-pin-mismatch` at exit `69`
will produce exactly the same refusal on every subsequent attempt until you supply the right digest.

## Rule 5 — read the problem document before deciding

Every refusal is a typed problem:

```json
{
  "type": "...",
  "title": "...",
  "status": 409,
  "code": "workflow-predicate-unsatisfied",
  "detail": "...",
  "command_id": "...",
  "unmet_facts": ["criteria.frozen"]
}
```

Three fields exist purely to let you recover without guessing:

| Field | Present on | Use it to |
|---|---|---|
| `current_version` | `version-conflict` | Re-issue with the correct expected version |
| `unmet_facts` | predicate and readiness refusals | Learn exactly which precondition is missing, then satisfy that |
| `command_id` | mutation refusals | Correlate the refusal with your original intent |

`unmet_facts` is the difference between "the transition failed" and "the transition failed because criteria
are not frozen". Satisfy the named fact; do not re-attempt the transition.

The complete refusal catalogue, grouped by what to do about each code, is on the
[refusals page](refusals.md).

## Rule 6 — mutation output tells you where the command actually is

A CLI mutation prints:

```json
{"command_id":"…","state":"queued","reason_code":"durability_pending","sequence":1,"result":{…}}
```

| `state` | Meaning |
|---|---|
| `accepted` | Sent, and the server accepted it off host |
| `queued` | Durably spooled locally; not yet accepted |
| `quarantined` | Spooled and blocked; requires an explicit operator disposition |
| `local_failure` | Never spooled; nothing was sent |

`result` carries the current server result when one is available. Its absence is not evidence that nothing
happened — check `state`.

## Rule 7 — the spool is durable-before-send, and it fails closed

Every `ticket` and `intake` mutation, plus `company bundle apply`, `ops outbox poison dispose` and
`synthetic run`, is encrypted and written to a local spool **before** any network send. That is why one of
these issued offline still returns a stable `command_id` at exit `75` instead of an error.

Three groups of commands never touch the spool, and offline they simply fail:

- every read;
- `bootstrap first-tenant`, the one-time tenant ceremony;
- every `migration ctower-project` command, which is authenticated and online-only.

The authoritative list is the `spool_policy` field on each operation in the generated registry
(`generated/python/ctower_client/operations.py`): only an operation marked `allowed` is ever written to the
spool. The [CLI reference](../reference/cli.md) marks each section.

Consequences you must handle for the spooled commands:

- The spool is scoped to the canonical `--base-url`. Use the same origin for every command, including local
  spool commands, or you will address a different spool.
- The spool records a keyed opaque identity for the authority used to enqueue each command. Before each
  send, `spool drain` compares the current authority against it. A rotated credential performs **zero**
  network sends and quarantines the command as `credential_identity_mismatch`. It does not silently rebind.
- `spool drain` stops at the first pending or quarantine barrier. Exit `69` means a barrier; exit `75` means
  entries remain pending; exit `0` means the spool is empty.
- A quarantined entry moves only through an explicit `spool retry` or `spool discard` with a `--reason`.

Never edit, copy between origins, or delete spool files.

## Rule 8 — do not treat dispatch as outcome

ctower is designed to record desired state and observed state separately, and so should you. A command that
was accepted means the control plane holds the fact. It does not mean an external effect occurred. At this
revision that gap is total rather than partial: no effect provider exists, so nothing ctower accepts reaches
anything outside it.

Similarly, a projection read is a fold with its own watermark. If a [Board](../concepts/board.md) view
reports `STATE_UNKNOWN`, that is an answer — do not re-read until it looks better and then act on the
prettier result.

## Rule 9 — you cannot approve the candidate you authored

If you ran `ticket criteria freeze`, you are the candidate's author and you cannot record a verdict on that
ticket. The attempt is refused as `proof-self-review-refused`. Recording a verdict also requires protected
operator authority, or it is refused as `proof-protected-authority-required`.

Know the exact edge of this, because it is narrower than it sounds: the server does **not** compare you with
whoever recorded the evidence. If you are not the candidate's author, you can record evidence and then
record a passing verdict on your own evidence, and nothing refuses you. The stronger rule is specified and
[not enforced at this revision](../concepts/proof.md#verdicts-and-independence). Treat producer/reviewer
separation as your obligation, not the server's guarantee.

Do not attempt to work around the check that *is* enforced by transferring custody to yourself; custody
transfer is a protected operation and is separately audited.

## A worked loop

For one-off interactive creation, let the client create the key:

```text
run: ticket create --priority P2 --project-key example --source-kind source-host --source-ref item-42 --title …
exit 0   -> accepted. record command_id and ticket_id. done.
exit 75  -> do not enter create again. run `spool drain` with the same origin and authority.
```

For caller-coordinated retries, create the key once and pass it explicitly:

```text
command_id := new UUID                      # once
attempt:
  run: ticket create --command-id $command_id …
  exit 0   -> accepted. record ticket_id. done.
  exit 75  -> committed or queued. WAIT (honour Retry-After if you have it).
              replay the SAME command_id. go to attempt.
  exit 69  -> read problem.code. this will not succeed unchanged. escalate or fix.
  exit 74  -> local environment problem. nothing was sent. fix keyring/spool. replay same command_id.
  exit 64  -> your invocation is wrong. fix it. a new command_id is fine here,
              because nothing was ever accepted.
```

Note the asymmetry in the last line: `64` is the only code where nothing can possibly have been recorded, so
it is the only one where starting over with a fresh key is safe.

## Source lookup and the mirroring race

The Board is the cross-ticket index. For source `source-host / item-42`, use this exact sequence:

```bash
printf '%s\n' "${authority}" |
  ctl --base-url "${base_url}" board query \
    example \
    --source-kind source-host --source-ref item-42

# Only when cards is empty:
printf '%s\n' "${authority}" |
  ctl --base-url "${base_url}" ticket create \
    --priority P2 \
    --project-key example \
    --source-kind source-host \
    --source-ref item-42 \
    --title "Mirror source item 42"
```

This lookup is a read capability, not a uniqueness or provenance claim. Two callers can both observe an
empty Board projection and create separate tickets for the same source pair. A caller that needs idempotent
mirroring must use one stable explicit command ID across its retries and must reconcile duplicates if
independent creators race. Source-pair uniqueness is not enforced by this revision.

## Related

- [Refusals](refusals.md) — every code, grouped by response.
- [Durability and acceptance](../concepts/durability.md) — why `75` is normal.
- [CLI reference](../reference/cli.md) — exact commands and flags.
- [Protected CLI and spool](../guides/protected-cli.md) — spool recovery procedures.

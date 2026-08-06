# Exercise the protected CLI

The `ctl`/`ctowerctl` wheel is a verified development artifact. It is not published, and this page is not a
production install or operations procedure. Use only synthetic data and a disposable verifier API.

## Instance discovery

`--base-url` is optional. Omit it and the CLI resolves the one instance declared in the owner-only
`~/.config/ctower/cli-instances.json` catalog — never an environment variable. `ctower-private-vps
expose-cli` writes that catalog from the installed runtime's own configuration and links `ctowerctl`, `ctl`,
and `ctower-shadow-ctl` onto `~/.local/bin`. A catalog with zero or with more than one declared instance
both refuse by name — usage exit `64` — rather than guessing; pass `--base-url` explicitly to reach a
different instance or to disambiguate.

## Security prerequisites

All commands read one bounded authority line from stdin. Spoolable mutations — the ones whose generated
operation carries `spool_policy: allowed` — additionally require the encrypted local spool; reads,
`bootstrap first-tenant`, and the `migration ctower-project` commands do not use it. On Linux that spool
supports only an allowlisted Secret Service backend in an active D-Bus session with an unlocked collection,
such as `gnome-keyring-daemon --components=secrets` under the user's normal login session.

Do not install `keyrings.alt`, choose a plaintext/file backend, place credentials in CLI arguments, or use
an environment/file fallback. The verifier runs a non-skipped `dbus-run-session` case against a real
temporary Secret Service. Its empty synthetic test collection is not an operator setup recipe.

Read authority without exporting or writing it:

```bash
read -r -s -p "Synthetic authority: " authority
printf '\n'
printf '%s\n' "${authority}" |
  ctl --base-url http://127.0.0.1:8000 control health
unset authority
```

Cleartext HTTP is accepted only for loopback; use HTTPS elsewhere.

## Command and output boundary

The CLI exposes explicit commands for bootstrap; ticket capture/query/timeline/audit/comment, assignment,
custody, priority, intents, blockers, relations, Proof, and Workflow; Board/health; protected outbox poison
disposition; CompanyBundle; and the local spool. The names are generated-contract checked, but handlers are
authored and closed—there is no operation-ID dispatcher.

`ticket workflow list` is local and does not read authority or contact the server. It enumerates exact
executable refs and digests from the installed pack tree. When the list contains one revision,
`ticket workflow start` may omit all eight pin flags; the CLI expands the exact installed values before
enqueue. `ticket resolve` may omit `--workflow-ref`; the server resolves it from the persisted run and
returns that exact ref.

Proof commands use the same exact-default rule. Freeze with `--candidate-content` to have the CLI hash the
literal UTF-8 bytes and use the sole installed gate policy, then add evidence with `--content` to have it
compute the artifact digest and bind to the server's frozen current candidate. The returned Proof receipts
state the candidate digest and, for evidence, the artifact digest. You can still supply explicit digests,
criteria files, and criterion keys; explicit values are authoritative, and mismatches refuse rather than
falling back to a default.

Every mutation carries a command ID. Omit `--command-id` and the CLI generates one client-side; supply it
explicitly to control replay identity yourself (for example to prove idempotent retry), and the explicit
value is always authoritative. A successful read or accepted mutation exits `0`, with one exception:
`control health` exits non-zero whenever its reported `status` is not `HEALTHY`, even though the read itself
succeeded — an absence of observations must never look like a healthy system.
Other stable exits are:

| Exit | Meaning |
|---:|---|
| `64` | Invalid command or bounded input |
| `69` | Permanent server rejection, quarantine barrier, or a `DEGRADED`/`STATE_UNKNOWN` `control health` result |
| `74` | Local spool, keyring, filesystem, or integrity failure |
| `75` | Durably queued, temporarily unreachable, or server `durability_pending` |

Mutation JSON reports `command_id`, `state`, `reason_code`, and `sequence`; a current server result is
included only when available. Exit `75` does not mean accepted.

When the server permanently rejects a command, the mutation JSON and every later spool listing also carry
`server_refusal` — the refusal `status` and the `name` the server gave it, taken from the authored contract's
refusal codes. A rejection is therefore still named long after the invocation that received it has exited.
The response body behind that name is never persisted or listed: the CLI keeps the allowlisted name only, and
a refusal the allowlist does not name becomes the content-free sentinel `unrecognized_refusal`, which carries
nothing derived from the refusing input.

## Inspect and recover the local spool

The spool is scoped to the canonical `--base-url`, so use the same origin on every local command:

```bash
ctl --base-url https://ctower.example spool status
ctl --base-url https://ctower.example spool list --state pending
ctl --base-url https://ctower.example spool quarantine list
ctl --base-url https://ctower.example spool doctor
```

`spool drain` needs current stdin authority and stops at the first pending or quarantine barrier. A
quarantined sequence moves only through an explicit operator action:

```bash
ctl --base-url https://ctower.example spool retry 7 --reason "server policy corrected"
ctl --base-url https://ctower.example spool discard 7 --reason "request intentionally abandoned"
```

The spool stores only a keyed opaque identity for the stdin authority used to enqueue each command. Before
every send, `spool drain` compares the current authority to that identity. A rotated credential or different
principal therefore performs zero network sends and visibly quarantines the command as
`credential_identity_mismatch`. Fail closed: either restore the original credential and explicitly retry,
or discard the old command and enqueue a new command ID under the rotated credential. The spool does not
silently rebind queued authority.

If `spool list --state quarantine` reports `corrupt_record`, it omits untrusted command fields and includes
only the exact sequence, byte count, and SHA-256 `artifact_digest`. Replay remains blocked. After inspecting
the local incident, dispose only the inventoried artifact:

```bash
ctl --base-url https://ctower.example spool discard 7 \
  --artifact-digest 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --reason "exact corrupt ciphertext reviewed"
```

A wrong sequence or digest, or a file changed after inventory, is refused. The authenticated disposition
preserves the command's chain relationship, and the corrupt ciphertext is retained as audit evidence.

The reader accepts legacy v1 encrypted records. A pre-alpha legacy discard tombstone that lacks the deleted
command's authenticated predecessor cannot satisfy the repaired chain contract and fails closed as
`format_incompatible`; do not reinterpret or delete that state with the newer build.

Retry/discard reasons are bounded metadata, never secret material. Do not manually edit, copy between
origins, or delete spool files. Missing/locked keyring evidence yields `STATE_UNKNOWN`; existing ciphertext
is left in place. This local quarantine boundary is not off-host backup or disaster recovery.

## Verification evidence

The repository builds the wheel from explicit package roots, installs it into an empty external virtual
environment from the hash-locked verifier set, runs both entry points outside the checkout, loads generated
contract resources, performs a read without keyring access, and queues a mutation through real Secret
Service. Run the canonical committed-candidate gate with `just verify`.

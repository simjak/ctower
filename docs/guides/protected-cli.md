# Exercise the protected CLI

The `ctl`/`ctowerctl` wheel is a verified development artifact. It is not published, and this page is not a
production install or operations procedure. Use only synthetic data and a disposable verifier API.

## Security prerequisites

All commands read one bounded authority line from stdin. Mutations additionally require the encrypted local
spool. On Linux that spool supports only an allowlisted Secret Service backend in an active D-Bus session
with an unlocked collection, such as `gnome-keyring-daemon --components=secrets` under the user's normal
login session.

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

Every non-bootstrap mutation requires `--command-id`. A successful read or accepted mutation exits `0`.
Other stable exits are:

| Exit | Meaning |
|---:|---|
| `64` | Invalid command or bounded input |
| `69` | Permanent server rejection or quarantine barrier |
| `74` | Local spool, keyring, filesystem, or integrity failure |
| `75` | Durably queued, temporarily unreachable, or server `durability_pending` |

Mutation JSON reports `command_id`, `state`, `reason_code`, and `sequence`; a current server result is
included only when available. Exit `75` does not mean accepted.

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

Retry/discard reasons are bounded metadata, never secret material. Do not manually edit, copy between
origins, or delete spool files. Missing/locked keyring evidence yields `STATE_UNKNOWN`; existing ciphertext
is left in place. This local quarantine boundary is not off-host backup or disaster recovery.

## Verification evidence

The repository builds the wheel from explicit package roots, installs it into an empty external virtual
environment from the hash-locked verifier set, runs both entry points outside the checkout, loads generated
contract resources, performs a read without keyring access, and queues a mutation through real Secret
Service. Run the canonical committed-candidate gate with `just verify`.

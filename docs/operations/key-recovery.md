# Key recovery

The database stores references and verification metadata, never long-lived secret values or signing
private keys. Recovery uses a separately controlled workload identity and the human ceremony owned by
the selected KMS/Vault provider.

1. Record the incident/drill ticket, isolated installation identity, operator identity reference, and
   start time.
2. From the isolated recovery host, authenticate using the root-owned recovery workload identity.
3. Resolve the exact backup, object, anchor-signing public-key, inventory-signing public-key, and
   installation-root references recorded in immutable metadata.
4. Ask the external authority to decrypt or verify one exact receipt. Bind the response to key
   reference, key version, public-key digest or wrapped-key digest, and recovered artifact digest.
5. Record only the typed receipt, timestamps, and digests in the restore report.

Unavailable, revoked, or mismatched references are critical findings. Do not substitute another key,
rewrite stored metadata, copy key material into environment variables, or mark the check successful.
Ordinary reads and effects remain disabled.

Erasure recovery is deliberately asymmetric: reapply every durable tombstone before serving, delete
the exact versioned ciphertext, and request destruction of the exact wrapped per-object key. A backup
that contains resurrected bytes does not override the tombstone.

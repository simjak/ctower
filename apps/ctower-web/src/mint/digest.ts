import { sha256 } from "@noble/hashes/sha2.js";
import canonicalize from "canonicalize";

/**
 * The one rule that lets this browser author a component at all.
 *
 * A component is pinned by `sha256` over the RFC 8785 canonical form of its
 * payload — `packages/ctower-kernel/src/ctower_kernel/catalog/_canonical.py`
 * does exactly this with `rfc8785.dumps` and `hashlib.sha256`. Getting it wrong
 * is not a silent failure: the registry recomputes the digest and refuses the
 * bundle with `digest.canonical`, so the only way a minted component is ever
 * accepted is if these bytes match the server's byte for byte.
 *
 * `crypto.subtle` is deliberately not used. It is a secure-context API and this
 * surface is served over plain HTTP on a private address, so it does not exist
 * here; a vetted implementation does the same arithmetic on any transport.
 */
export function canonicalBytes(value: unknown): Uint8Array {
  const text = canonicalize(value);
  if (text === undefined) {
    throw new TypeError("value is outside the RFC 8785 JSON domain");
  }
  return new TextEncoder().encode(text);
}

export function canonicalDigest(value: unknown): string {
  return `sha256:${hex(sha256(canonicalBytes(value)))}`;
}

function hex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

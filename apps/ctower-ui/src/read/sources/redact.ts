/**
 * Redaction applied to every byte this surface renders from an interim source.
 *
 * The inbox and the feed carry operator and commander coordination text written
 * by other seats. Nothing guarantees a seat never pasted a credential into a
 * subject line or a terminal pane, so the surface does not rely on that: every
 * string from a file, a git tree or a tmux pane passes through `redacted`
 * before it reaches a screen.
 *
 * The rule is deliberately loud rather than clever. A false positive costs a
 * reader one unreadable token; a false negative publishes a live credential to
 * everyone who can reach the tailnet.
 */

interface Pattern {
  readonly kind: string;
  readonly match: RegExp;
}

/* Each pattern is written as a shape, never as an example value. */
const PATTERNS: readonly Pattern[] = [
  { kind: "authorization-header", match: /\b(?:Authorization|Proxy-Authorization)\s*:\s*\S+/gi },
  { kind: "bearer", match: /\bBearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}/gi },
  { kind: "provider-key", match: /\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}/g },
  { kind: "github-token", match: /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}/g },
  { kind: "github-pat", match: /\bgithub_pat_[A-Za-z0-9_]{20,}/g },
  { kind: "slack-token", match: /\bxox[abposr]-[A-Za-z0-9-]{10,}/g },
  { kind: "aws-access-key", match: /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g },
  { kind: "google-api-key", match: /\bAIza[0-9A-Za-z_-]{30,}\b/g },
  { kind: "jwt", match: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g },
  {
    kind: "private-key-block",
    match: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
  },
  {
    kind: "assigned-secret",
    match: /\b(?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S{8,}/gi,
  },
  { kind: "url-credential", match: /\b[a-z][a-z0-9+.-]*:\/\/[^\s/@:]+:[^\s/@]+@/gi },
  // A bare 48+ hex token is credential-shaped. Anything introduced by a label
  // — `sha256:`, `sha1:` — is a digest this surface exists to show, and a git
  // commit sha is 40, so both survive.
  { kind: "bare-hex-secret", match: /(?<![:\w-])[0-9a-f]{48,}(?![\w-])/g },
];

/** Replace every recognised credential shape with a named, obvious marker. */
export function redacted(text: string): string {
  return PATTERNS.reduce(
    (carried, pattern) => carried.replace(pattern.match, `[redacted:${pattern.kind}]`),
    text
  );
}

/** Whether `redacted` would change this text — used to mark a row on screen. */
export function carriesRedaction(text: string): boolean {
  return redacted(text) !== text;
}

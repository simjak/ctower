/**
 * The registry's check vocabulary, said in words an operator owns.
 *
 * A code the registry emits and this map does not know is rendered verbatim.
 * That is deliberate: inventing a friendly name for an unrecognised code would
 * be the wizard claiming to know what the registry meant.
 */
const NAMES: Readonly<Record<string, string>> = {
  "schema.closed": "Document shape",
  "digest.canonical": "Digests match",
  "reference.exact": "References resolve",
  "compatibility.current": "Versions compatible",
  "security.secret-free": "No secrets inside",
};

export function checkName(code: string): string {
  return NAMES[code] ?? code;
}

/** One reader for a screen's query parameter, so no screen parses its own URL. */
export function readParam(
  params: Readonly<Record<string, string | string[] | undefined>>,
  name: string
): string | null {
  const value = params[name];
  return typeof value === "string" && value !== "" ? value : null;
}

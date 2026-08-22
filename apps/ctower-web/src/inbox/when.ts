/**
 * When something was recorded, at the precision an operator acts on.
 *
 * No "3 minutes ago". A relative stamp goes stale on a page that is still by
 * design, and two of them cannot be compared against a log or against the CLI,
 * which prints the instant. The shape is the sortable one the rest of this
 * repository prints — year first, 24-hour clock, no locale to disagree with —
 * in the reader's own zone, because that is the clock the operator is on. The
 * exact recorded value stays on the element's `title`.
 */
export function stamp(recordedAt: string): string {
  const at = new Date(recordedAt);
  if (Number.isNaN(at.getTime())) {
    return recordedAt;
  }
  const date = [at.getFullYear(), at.getMonth() + 1, at.getDate()].map(pad).join("-");
  return `${date} ${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

function pad(part: number): string {
  return String(part).padStart(2, "0");
}

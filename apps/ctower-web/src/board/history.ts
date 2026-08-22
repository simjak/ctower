/**
 * A recorded instant, as the record holds it: UTC, to the minute.
 *
 * Not the reader's locale. Two people looking at the same board must be looking
 * at the same instant, and the record's own zone is the only one both of them
 * can check against the log.
 *
 * This module also held `momentsOf`, which turned `getTicketTimeline`'s four
 * event kinds into the panel's history. The audit read answers those four and
 * five more, so the panel reads that instead and the mapping went with it — see
 * `audit/events.ts`, which does the same job over the wider union. A dead
 * mapping kept "for later" is the second answer to a question that now has one.
 */
export function instant(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : `${at.toISOString().slice(0, 16).replace("T", " ")}Z`;
}

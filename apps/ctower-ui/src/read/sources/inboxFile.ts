import { asRecord, asString, asStringOrNull } from "../json";
import { readJsonl } from "./jsonl";
import { inboxPath } from "./paths";
import { carriesRedaction, redacted } from "./redact";
import type { InboxMessage, SeatInbox, SeatSummary } from "../interface";

/**
 * Interim source: Mission Control's append-only `state/inbox.jsonl`.
 *
 * Read-only, and read whole on each request rather than cached, because the
 * file is appended to by other seats while this screen is open. A mid-write
 * tail is counted and stated on the surface, never silently dropped.
 *
 * Every rendered string passes through `redacted` first: this file carries
 * operator and commander coordination text, and nothing guarantees a seat never
 * pasted a credential into a subject line.
 */

const MESSAGE_CAP = 25;

interface Raw {
  readonly at: string;
  readonly from: string;
  readonly to: string;
  readonly severity: string;
  readonly project: string | null;
  readonly subject: string;
  readonly body: string | null;
  readonly read: boolean;
}

function shape(value: unknown): Raw | null {
  try {
    const row = asRecord(value, "inbox.line");
    return {
      at: asString(row.ts, "inbox.ts"),
      from: asString(row.from, "inbox.from"),
      to: asString(row.to, "inbox.to"),
      severity: asStringOrNull(row.severity, "inbox.severity") ?? "info",
      project: asStringOrNull(row.project, "inbox.project"),
      subject: asStringOrNull(row.subject, "inbox.subject") ?? "",
      body: asStringOrNull(row.body, "inbox.body"),
      read: row.read === true,
    };
  } catch {
    return null;
  }
}

function present(raw: Raw): InboxMessage {
  const subject = redacted(raw.subject);
  const body = raw.body === null ? null : redacted(raw.body);
  return {
    at: raw.at,
    from: redacted(raw.from),
    severity: raw.severity,
    project: raw.project,
    subject,
    body,
    read: raw.read,
    wasRedacted: carriesRedaction(raw.subject) || (raw.body !== null && carriesRedaction(raw.body)),
  };
}

function summaries(records: readonly Raw[]): readonly SeatSummary[] {
  const seats = new Map<string, { total: number; unread: number }>();
  for (const record of records) {
    const current = seats.get(record.to) ?? { total: 0, unread: 0 };
    seats.set(record.to, {
      total: current.total + 1,
      unread: current.unread + (record.read ? 0 : 1),
    });
  }
  return [...seats.entries()]
    .map(([seat, counts]) => ({ seat, total: counts.total, unread: counts.unread }))
    .sort((left, right) => right.unread - left.unread || right.total - left.total)
    .slice(0, 8);
}

/** The exact line that reaches a seat, quoted from Mission Control's notify tool. */
function addressingLine(seat: string): string {
  return `tools/notify --to ${seat} --from <your-seat> \\\n  --severity info --subject "..." --body "..."`;
}

export async function readSeatInbox(seat: string | null): Promise<SeatInbox> {
  const path = inboxPath();
  const scan = await readJsonl(path, shape);
  const seats = summaries(scan.records);
  const fallback = seats[0]?.seat ?? "";
  const selected = seat !== null && seats.some((entry) => entry.seat === seat) ? seat : fallback;
  const mine = scan.records.filter((record) => record.to === selected);
  return {
    seats,
    held: mine.length,
    selected,
    addressing: addressingLine(selected),
    messages: mine.slice(-MESSAGE_CAP).reverse().map(present),
    tail: {
      totalLines: scan.totalLines,
      malformed: scan.malformed,
      partialTail: scan.partialTail,
      sourcePath: path,
    },
  };
}

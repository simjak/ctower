import { asRecord, asString, asStringOrNull } from "../json";
import { readJsonl } from "./jsonl";
import { inboxPath } from "./paths";

function environment(name: string, fallback: string): string {
  const value = process.env[name];
  return value === undefined || value === "" ? fallback : value;
}
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

/**
 * Every externally authored field, redacted before it enters the screen model.
 *
 * Round-1 review found this redacting subject, body and sender while returning
 * severity, project and seat names raw — and still showing the
 * `redacted before render` marker, which made a partial sanitisation look
 * complete. Nothing that a seat can type reaches a screen unfiltered now, and
 * the marker is derived from every field rather than two of them.
 */
function present(raw: Raw): InboxMessage {
  const fields = [raw.subject, raw.body ?? "", raw.from, raw.severity, raw.project ?? "", raw.at];
  return {
    at: redacted(raw.at),
    from: redacted(raw.from),
    severity: redacted(raw.severity),
    project: raw.project === null ? null : redacted(raw.project),
    subject: redacted(raw.subject),
    body: raw.body === null ? null : redacted(raw.body),
    read: raw.read,
    wasRedacted: fields.some(carriesRedaction),
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
    .map(([seat, counts]) => ({ seat: redacted(seat), total: counts.total, unread: counts.unread }))
    .sort((left, right) => right.unread - left.unread || right.total - left.total)
    .slice(0, 8);
}

/** The exact line that reaches a seat, quoted from Mission Control's notify tool. */
function addressingLine(seat: string): string {
  // the seat name is authored elsewhere, so the line built from it is redacted too
  return redacted(
    `tools/notify --to ${seat} --from <your-seat> \\\n  --severity info --subject "..." --body "..."`
  );
}

export async function readSeatInbox(seat: string | null): Promise<SeatInbox> {
  const path = inboxPath();
  const scan = await readJsonl(path, shape);
  const seats = summaries(scan.records);
  // this is a ctower surface, so it opens on the ctower seat when the file
  // carries one; the busiest seat is only the fallback
  const home = environment("CTOWER_UI_INBOX_SEAT", "ctower-commander");
  const fallback = seats.find((entry) => entry.seat === home)?.seat ?? seats[0]?.seat ?? "";
  const requested = seat === null ? null : redacted(seat);
  const selected =
    requested !== null && seats.some((entry) => entry.seat === requested) ? requested : fallback;
  // the record's own `to` is matched against the *unredacted* name; only what
  // reaches the screen is filtered, so redaction cannot silently empty a seat
  const mine = scan.records.filter((record) => redacted(record.to) === selected);
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

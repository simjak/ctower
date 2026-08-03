import { noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
import { redacted } from "./redact";
import type { CrewRow } from "../interface";

/**
 * What a crew's name says about it, and how a seat is spelled on screen.
 *
 * Mission Control names every crew `<persona>-<request>-<slug>`, so the name
 * alone is supposed to say who is accountable, which request it serves and what
 * it does. This module is the one place that rule is read — and the one place
 * that decides nothing else: it is handed the declared seat list rather than
 * reading the personas directory, so it knows no source and can be exercised
 * against any seat set.
 *
 * A name that breaks the rule is parsed as far as it goes and flagged. It is
 * never normalised into looking compliant, because the roster exists partly to
 * show the operator where the convention has slipped.
 */

/** How a crew name's persona token maps to a declared seat file. */
const SEAT_ALIASES: Readonly<Record<string, string>> = {
  em: "engineering-manager",
  writer: "tech-writer",
  release: "release-manager",
};

/**
 * How a declared seat is spelled and abbreviated on screen. This is display
 * only: the seat list itself is whatever the personas directory holds, and a
 * seat missing from this table still gets a row — spelled from its file name.
 */
const SEAT_DISPLAY: Readonly<Record<string, readonly [string, string]>> = {
  ceo: ["CEO", "CE"],
  commander: ["Commander", "CM"],
  cso: ["CSO", "CS"],
  designer: ["Designer", "DS"],
  devops: ["DevOps", "DO"],
  engineer: ["Engineer", "EN"],
  "engineering-manager": ["Eng manager", "EM"],
  qa: ["QA", "QA"],
  "release-manager": ["Release", "RL"],
  review: ["Review", "RV"],
  "tech-writer": ["Writer", "WR"],
};

/** The prefix the Mission Control tmux socket adds to a crew's session. */
const MC_PREFIX = "mc-";

/** The crew as the fleet names it, with the mux prefix the socket adds. */
export function crewNameOf(session: string): string {
  return session.startsWith(MC_PREFIX) ? session.slice(MC_PREFIX.length) : session;
}

/** How a declared seat is spelled on screen; an undeclared one from its key. */
export function seatLabelOf(seat: string): string {
  const declared = SEAT_DISPLAY[seat];
  if (declared !== undefined) {
    return declared[0];
  }
  return seat
    .split("-")
    .map((word, index) =>
      index === 0 ? `${word.slice(0, 1).toUpperCase()}${word.slice(1)}` : word
    )
    .join(" ");
}

/** The seat's two-letter mark, so two seats never share one avatar. */
export function initialsOf(seat: string): string {
  const declared = SEAT_DISPLAY[seat];
  if (declared !== undefined) {
    return declared[1];
  }
  const parts = seat.split("-");
  const first = parts[0] ?? "";
  const second = parts[1];
  return (second === undefined ? first.slice(0, 2) : `${first.slice(0, 1)}${second.slice(0, 1)}`)
    .toUpperCase()
    .padEnd(2, "·");
}

/** Split `<persona>-<request>-<slug>`; a part the name omits says so. */
export function parseName(
  crew: string,
  seats: Known<readonly string[]>
): Pick<CrewRow, "seat" | "seatLabel" | "seatInitials" | "request" | "slug" | "flag"> {
  const parts = crew.split("-");
  const token = parts[0] ?? "";
  const declared = seats.known === "value" ? seats.value : [];
  const candidate = SEAT_ALIASES[token] ?? token;
  const seatKey = declared.find((entry) => entry === candidate);
  const seat: Known<string> =
    seats.known === "unread"
      ? unreadOf(seats.reason)
      : seatKey === undefined
        ? noneOf(`no seat named ${token}`)
        : valueOf(seatKey);
  const request = parts[1];
  const carriesRequest = request !== undefined && /^(?:r?[0-9]+|i[0-9]+|gh[0-9]+)$/iu.test(request);
  const slugParts = carriesRequest ? parts.slice(2) : parts.slice(1);
  return {
    seat,
    seatLabel: seat.known === "value" ? valueOf(seatLabelOf(seat.value)) : seat,
    seatInitials: seat.known === "value" ? valueOf(initialsOf(seat.value)) : seat,
    request: carriesRequest ? valueOf(redacted(request)) : noneOf("no request id"),
    slug: slugParts.length === 0 ? noneOf("no slug") : valueOf(redacted(slugParts.join("-"))),
    // the naming rule is Mission Control's, and a row that breaks it is flagged
    // rather than normalised into looking compliant
    flag: carriesRequest
      ? null
      : "this crew name carries no request id, so the name alone does not say which request it serves",
  };
}

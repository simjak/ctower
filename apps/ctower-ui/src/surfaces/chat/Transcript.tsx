import type { ReactElement } from "react";
import { clockText, dayText } from "@/read/elapsed";
import { initialsOf } from "@/read/sources/crewNaming";
import { NothingGlyph } from "./glyphs";
import type { InboxThreadMessage } from "@/read/interface";

/**
 * The conversation itself.
 *
 * The rejected screen drew every message as an identical card carrying `from`,
 * `to` and a position, so a reader had to *read* each row to learn whose it
 * was. Here the side of the column answers that: the operator's own messages
 * sit right in a bubble, the seat's sit left as named prose, and consecutive
 * messages from one sender share one header instead of repeating it. Nobody is
 * told who is speaking; they can see it.
 *
 * The position and the recipient are not lost — they are the group's `title`,
 * where a reader who wants the record's exact numbering can find them without
 * every row spending a line on it.
 */

interface Group {
  readonly from: string;
  readonly mine: boolean;
  readonly messages: readonly InboxThreadMessage[];
}

/** Consecutive messages by one sender, in the order the record holds them. */
export function groupsOf(
  messages: readonly InboxThreadMessage[],
  self: string | null
): readonly Group[] {
  const groups: Group[] = [];
  for (const message of messages) {
    const last = groups.at(-1);
    if (last?.from === message.from) {
      groups[groups.length - 1] = { ...last, messages: [...last.messages, message] };
      continue;
    }
    groups.push({ from: message.from, mine: message.from === self, messages: [message] });
  }
  return groups;
}

function Turn({ group }: { readonly group: Group }): ReactElement {
  const first = group.messages[0];
  const positions = group.messages.map((message) => message.position.toString()).join(", ");
  return (
    <div className={group.mine ? "cw-turn mine" : "cw-turn"}>
      <div className="by">
        {group.mine ? null : <i className="av">{initialsOf(group.from)}</i>}
        <span className="nm">{group.from}</span>
        <span className="at" title={`to ${first?.to ?? ""} · message ${positions} on this thread`}>
          {first === undefined ? "" : clockText(first.sentAt)}
        </span>
      </div>
      {group.messages.map((message) => (
        <div className="said" key={message.messageId}>
          {message.text}
        </div>
      ))}
    </div>
  );
}

export function Transcript({
  messages,
  self,
  children,
}: {
  readonly messages: readonly InboxThreadMessage[];
  /** The seat this surface's principal holds, as the record named it. */
  readonly self: string | null;
  /** Anything the composer has accepted that the projection has not folded yet. */
  readonly children?: ReactElement | null;
}): ReactElement {
  if (messages.length === 0) {
    return (
      <div className="cw-scroll">
        <div className="cw-nil">
          <NothingGlyph />
          <span>no message on record for this conversation</span>
        </div>
        {children}
      </div>
    );
  }
  const groups = groupsOf(messages, self);
  let day = "";
  return (
    <div className="cw-scroll">
      {groups.map((group) => {
        const at = group.messages[0]?.sentAt ?? "";
        const on = dayText(at);
        const rule =
          on === day ? null : (
            <div className="cw-day" key={`d${on}`}>
              {on}
            </div>
          );
        day = on;
        return (
          <div key={group.messages[0]?.messageId ?? on}>
            {rule}
            <Turn group={group} />
          </div>
        );
      })}
      {children}
    </div>
  );
}

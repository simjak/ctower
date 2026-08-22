import type { ReactElement } from "react";
import type { InboxMessage, InboxThread } from "@ctower/client";
import { cn } from "../ui/cn";
import { Mono } from "../ui/primitives";
import { stamp } from "./when";

/**
 * One thread, in the order ctower recorded it.
 *
 * Two facts do the work no decoration would do better. Whose message it is
 * comes from the sender against this address, so an answer reads as an answer
 * without a chat bubble; and the read line is drawn from the thread's own
 * `read_through_position`, which is derived from the oldest message still
 * unread — so it marks what is actually unread rather than what this tab
 * happens not to have scrolled past.
 */
export function Conversation({
  thread,
  me,
}: {
  readonly thread: InboxThread;
  /** This console's address, as the API named it. */
  readonly me: string;
}): ReactElement {
  const firstUnread = unreadFrom(thread, me)[0]?.message_id ?? null;

  return (
    <ol className="m-0 list-none p-0">
      {thread.messages.map((message) => (
        <li key={message.message_id}>
          {message.message_id === firstUnread ? <UnreadRule /> : null}
          <Message message={message} mine={message.from === me} />
        </li>
      ))}
    </ol>
  );
}

/** The incoming messages this address has not recorded a read for. */
export function unreadFrom(thread: InboxThread, me: string): readonly InboxMessage[] {
  return thread.messages.filter(
    (message) => message.to === me && message.position > thread.read_through_position
  );
}

function UnreadRule(): ReactElement {
  return (
    <div className="flex items-center gap-2 pt-4 pb-1">
      <span className="text-2xs text-amber-ink">unread</span>
      <span className="h-px flex-1 bg-amber" />
    </div>
  );
}

function Message({
  message,
  mine,
}: {
  readonly message: InboxMessage;
  readonly mine: boolean;
}): ReactElement {
  return (
    <article
      className={cn(
        "border-b border-line py-3 last:border-b-0",
        mine ? "pl-3" : "",
        mine ? "border-l-2 border-l-amber/40" : ""
      )}
    >
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <Mono className="text-sm font-semibold text-fg">{message.from}</Mono>
        <span className="text-2xs text-muted">to</span>
        <Mono className="text-2xs text-muted">{message.to}</Mono>
        <span className="flex-1" />
        <Severity level={message.severity} />
        <Mono className="text-2xs text-muted" title={message.sent_at}>
          {stamp(message.sent_at)}
        </Mono>
      </div>
      <p className="mt-1.5 mb-0 text-sm whitespace-pre-wrap text-fg">{message.text}</p>
    </article>
  );
}

const SEVERITY_INK: Readonly<Record<InboxMessage["severity"], string>> = {
  P0: "text-danger font-semibold",
  P1: "text-amber-ink",
  info: "text-muted",
};

/**
 * The recorded severity, in the contract's own three words.
 *
 * All three render. Drawing only the loud two would make `info` and "no
 * severity recorded" look identical, and severity is never absent.
 */
function Severity({ level }: { readonly level: InboxMessage["severity"] }): ReactElement {
  return <Mono className={cn("text-2xs", SEVERITY_INK[level])}>{level}</Mono>;
}

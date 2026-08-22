import { SquarePen } from "lucide-react";
import type { ReactElement } from "react";
import type { InboxThreadSummary } from "@ctower/client";
import { cn } from "../ui/cn";
import { Chip, Mono } from "../ui/primitives";
import { stamp } from "./when";

/**
 * The threads this address is a participant in, newest fact first.
 *
 * Every line is something ctower recorded: who the other agent is, when the
 * last message landed, what it opened with, and how many of them are still
 * unread. Nothing is summarised into a status the API did not state, and a
 * thread that has become a ticket says so rather than looking like any other.
 */
export function ThreadList({
  threads,
  openId,
  onOpen,
  onCompose,
}: {
  readonly threads: readonly InboxThreadSummary[];
  /** The thread being read, or `null` while a new message is being written. */
  readonly openId: string | null;
  readonly onOpen: (threadId: string) => void;
  readonly onCompose: () => void;
}): ReactElement {
  return (
    <nav
      aria-label="Threads"
      className="overflow-hidden rounded-md border border-line bg-card md:sticky md:top-[68px]"
    >
      <button
        type="button"
        aria-current={openId === null ? "true" : undefined}
        onClick={onCompose}
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 border-b border-line px-3 py-2.5 text-left text-sm",
          // The list clips its own corners, so a ring drawn outside these rows
          // is clipped with them. It goes inside instead: every focusable on
          // this page has to be able to show the one the law asks for.
          "focus-visible:-outline-offset-2",
          openId === null ? "bg-amber/14 font-semibold" : "hover:bg-raised"
        )}
      >
        <SquarePen className="size-4 shrink-0 text-muted" />
        New message
      </button>
      {threads.length === 0 ? (
        <p className="m-0 px-3 py-6 text-center text-sm text-muted">Nothing here yet.</p>
      ) : (
        <ul className="m-0 list-none p-0">
          {threads.map((thread) => (
            <li key={thread.thread_id}>
              <Row thread={thread} open={thread.thread_id === openId} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}

function Row({
  thread,
  open,
  onOpen,
}: {
  readonly thread: InboxThreadSummary;
  readonly open: boolean;
  readonly onOpen: (threadId: string) => void;
}): ReactElement {
  return (
    <button
      type="button"
      aria-current={open ? "true" : undefined}
      onClick={(): void => {
        onOpen(thread.thread_id);
      }}
      className={cn(
        "block w-full cursor-pointer border-b border-line px-3 py-2.5 text-left last:border-b-0",
        "focus-visible:-outline-offset-2",
        open ? "border-r-2 border-r-amber bg-amber/14" : "hover:bg-raised"
      )}
    >
      <div className="flex items-baseline gap-2">
        <Mono className={cn("min-w-0 truncate text-sm", open ? "font-semibold" : "text-fg")}>
          {thread.other_agent}
        </Mono>
        <span className="flex-1" />
        <Mono className="shrink-0 text-2xs text-muted" title={thread.last_message_at}>
          {stamp(thread.last_message_at)}
        </Mono>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-xs text-muted">
          {thread.last_message_preview}
        </span>
        {thread.promoted_ticket_id === null ? null : (
          <Chip title={thread.promoted_ticket_id}>ticketed</Chip>
        )}
        {thread.unread_count === 0 ? null : <Chip tone="amber">{thread.unread_count} unread</Chip>}
      </div>
    </button>
  );
}

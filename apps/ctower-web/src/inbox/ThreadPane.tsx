import { CheckCheck } from "lucide-react";
import type { ReactElement } from "react";
import type { InboxCorrespondentList, InboxThread } from "@ctower/client";
import type { Held } from "./reads";
import { Mark } from "../ui/marks";
import { Button, Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { ComposeBox } from "./Composer";
import { useMarkRead } from "./commands";
import { Conversation, unreadFrom } from "./Conversation";
import { Unanswered } from "./Unanswered";

/**
 * One open thread: what was said, whether this address has recorded reading it,
 * and the reply.
 *
 * Marking read is a write like any other, so it is a control the operator
 * presses rather than something this page does on the operator's behalf as a
 * side effect of scrolling. Opening a thread reads it; saying you have read it
 * is an act.
 *
 * The last thread ctower answered stays on screen while the next read is out
 * (`Held`), which is what keeps a write's receipt visible: sending re-reads the
 * thread, and a pane that emptied itself while that read was in flight
 * destroyed the very acknowledgement the operator was waiting to see.
 */
export function ThreadPane({
  thread,
  me,
  offered,
  onRecorded,
}: {
  readonly thread: Held<InboxThread>;
  readonly me: string;
  readonly offered: Held<InboxCorrespondentList>;
  readonly onRecorded: () => void;
}): ReactElement {
  const marked = useMarkRead(onRecorded);
  const held = thread.last;

  if (held === null) {
    return (
      <Card>
        <CardBody>
          <Unanswered
            answer={thread.answer}
            what="Reading this thread"
            action="Nothing was read. Open it again to ask ctower once more."
          />
        </CardBody>
      </Card>
    );
  }

  const unread = unreadFrom(held, me);
  const other = held.participants.find((seat) => seat !== me) ?? me;

  return (
    <div className="min-w-0">
      <Card>
        <CardHeader>
          <CardTitle>
            <Mono className="text-md">{other}</Mono>
          </CardTitle>
          {held.promoted_ticket_id === null ? null : (
            <Chip title={held.promoted_ticket_id}>ticketed</Chip>
          )}
          <span className="flex-1" />
          {thread.answer.kind === "asking" ? <Mark name="working" /> : null}
          {unread.length === 0 ? (
            <span className="text-xs text-muted">All read</span>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              disabled={marked.outcome?.kind === "asking"}
              onClick={(): void => {
                marked.mark(unread);
              }}
            >
              <CheckCheck /> Mark {unread.length} read
            </Button>
          )}
        </CardHeader>
        <CardBody className="py-0">
          <Unanswered
            answer={thread.answer}
            action="What is below is the last thing ctower said. Re-read to ask again."
          />
          {marked.outcome === null ? null : (
            <div className="pt-3">
              <Unanswered
                answer={marked.outcome}
                what="Recording that you read this"
                action="Some of these may already be recorded. Open the thread again to see where it stopped."
              />
            </div>
          )}
          <Conversation thread={held} me={me} />
        </CardBody>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Reply</CardTitle>
        </CardHeader>
        <CardBody>
          <ComposeBox
            offered={offered}
            to={other}
            threadId={held.thread_id}
            onRecorded={onRecorded}
          />
        </CardBody>
      </Card>
    </div>
  );
}

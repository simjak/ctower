import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import { RotateCw } from "lucide-react";
import type { InboxCorrespondentList, InboxThread, InboxThreadList } from "@ctower/client";
import { Mark } from "../ui/marks";
import { Checkbox } from "../ui/form";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Chip,
  Mono,
  PageHead,
} from "../ui/primitives";
import { hasAddress } from "./address";
import { ComposeBox } from "./Composer";
import { useCorrespondents, useThread, useThreads } from "./reads";
import type { Held } from "./reads";
import { ThreadList } from "./ThreadList";
import { ThreadPane } from "./ThreadPane";
import { Unanswered } from "./Unanswered";

/**
 * The Inbox. Threads this company's agents have with this console's address,
 * read here and answered here.
 *
 * It is a company-wide plane by design: there is no project filter on this page
 * because ctower does not scope the inbox by project — a project key travels on
 * a message only to say which registration of a seat key it is for. Implying a
 * filter that does not exist would be the one dishonest thing this screen could
 * do.
 */
export function InboxPage(): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const list = useThreads(unreadOnly, reloadKey);
  const offered = useCorrespondents(reloadKey);
  const thread = useThread(openId, reloadKey);

  const reread = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  return (
    <>
      <PageHead title="Inbox" subtitle={<Standing list={list} />}>
        <Checkbox
          checked={unreadOnly}
          onCheckedChange={setUnreadOnly}
          label="Show only threads with unread messages"
        />
        <span className="text-xs text-muted">Unread only</span>
        <Button variant="quiet" size="sm" onClick={reread}>
          <RotateCw /> Re-read
        </Button>
      </PageHead>

      {list.last === null ? (
        <Unanswered
          answer={list.answer}
          what="Reading this inbox"
          action="Nothing was read. Re-read to ask ctower again."
        />
      ) : (
        <>
          <Unanswered
            answer={list.answer}
            action="What is below is the last thing ctower said. Re-read to ask again."
          />
          <Read
            list={list.last}
            offered={offered}
            thread={thread}
            openId={openId}
            onOpen={setOpenId}
            onCompose={(): void => {
              setOpenId(null);
            }}
            onRecorded={reread}
          />
        </>
      )}
    </>
  );
}

/** The address this console reads as, and how much of it is unread. */
function Standing({ list }: { readonly list: Held<InboxThreadList> }): ReactElement | null {
  const working = list.answer.kind === "asking" ? <Mark name="working" /> : null;
  if (list.last === null) {
    return working;
  }
  const recipient = list.last.recipient;
  const unread = list.last.total_unread;
  if (!hasAddress(recipient)) {
    return (
      <>
        <span>no address on this credential</span>
        {working}
      </>
    );
  }
  return (
    <>
      <Mono>{recipient}</Mono>
      {unread === 0 ? <Chip>all read</Chip> : <Chip tone="amber">{unread} unread</Chip>}
      {working}
    </>
  );
}

function Read({
  list,
  offered,
  thread,
  openId,
  onOpen,
  onCompose,
  onRecorded,
}: {
  readonly list: InboxThreadList;
  readonly offered: Held<InboxCorrespondentList>;
  readonly thread: Held<InboxThread>;
  readonly openId: string | null;
  readonly onOpen: (threadId: string) => void;
  readonly onCompose: () => void;
  readonly onRecorded: () => void;
}): ReactElement {
  if (!hasAddress(list.recipient)) {
    return <Unaddressable />;
  }

  return (
    <div className="grid items-start gap-4 md:grid-cols-[320px_minmax(0,1fr)]">
      <ThreadList threads={list.threads} openId={openId} onOpen={onOpen} onCompose={onCompose} />
      {openId === null ? (
        <Card>
          <CardHeader>
            <CardTitle>New message</CardTitle>
          </CardHeader>
          <CardBody>
            <ComposeBox
              key="new"
              offered={offered}
              to={null}
              threadId={null}
              onRecorded={onRecorded}
            />
          </CardBody>
        </Card>
      ) : (
        <ThreadPane
          key={openId}
          thread={thread}
          me={list.recipient}
          offered={offered}
          onRecorded={onRecorded}
        />
      )}
    </div>
  );
}

/**
 * The credential this console holds has no inbox address.
 *
 * A recorded fact, and not an empty inbox: the API named the reader
 * `unaddressable`, which is what the projection returns for a principal with no
 * seat row. An address is minted with a seat credential, so nothing on this
 * page — and no bundle the operator could apply from the Company page — creates
 * one. There is no mark on this: none of the six says "identity without an
 * address", and borrowing one would state a state ctower never recorded.
 */
function Unaddressable(): ReactElement {
  return (
    <div className="rounded-md border border-line bg-raised p-4">
      <p className="m-0 text-sm font-medium text-fg">
        This console&rsquo;s credential holds no inbox address.
      </p>
      <p className="mt-1.5 mb-0 text-xs text-muted">
        ctower answers <Mono>unaddressable</Mono> for it, so there is nothing to read and nothing to
        send from. An address arrives with a seat credential, which an operator issues.
      </p>
    </div>
  );
}

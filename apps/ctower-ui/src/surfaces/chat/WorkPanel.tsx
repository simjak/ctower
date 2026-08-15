import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { InlineReading } from "@/frame/Declared";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { boardCardContextFor } from "@/read/boardProjection";
import { shortId, stampText } from "@/read/elapsed";
import { NothingGlyph, TicketGlyph } from "./glyphs";
import type { BoardCardContext } from "@/read/boardProjection";
import type { BoardCard, Reading } from "@/read/interface";

/**
 * What the conversation is about, beside the conversation.
 *
 * Conductor puts the pull request a session is producing to the right of the
 * transcript: its state at the top, then the changes, then the checks. ctower's
 * equivalents are recorded facts on the board card behind the thread's promoted
 * ticket — the lane and stage are the state, the recorded change references are
 * the changes, and the applied labels, the blocker and the delivery answer are
 * the checks. Nothing here is a new read: it is the card the Board already
 * reads, folded by the projection every other screen folds it with, so this
 * pane cannot narrow a contract discriminant its own way.
 *
 * A thread with no promoted ticket has no work to show. It says so as a glyph
 * and four words with the promote control right underneath — which is the
 * honest shape, because linking the thread is exactly what fills this pane.
 */

export type WorkTab = "changes" | "checks" | "review";

const TABS: readonly { readonly key: WorkTab; readonly label: string }[] = [
  { key: "changes", label: "Changes" },
  { key: "checks", label: "Checks" },
  { key: "review", label: "Review" },
];

function tabHref(threadId: string, tab: WorkTab): string {
  return `/inbox?thread=${encodeURIComponent(threadId)}&pane=${tab}`;
}

/** The one row shape this pane draws: a dimmed key, the fact, its own detail. */
function Row({
  dir,
  leaf,
  at = null,
  title,
}: {
  readonly dir: string;
  readonly leaf: string;
  readonly at?: string | null;
  readonly title?: string | undefined;
}): ReactElement {
  return (
    <div className="cw-file" title={title}>
      <span className="dir">{dir}</span>
      <span className="leaf">{leaf}</span>
      <span className="at">{at ?? ""}</span>
    </div>
  );
}

function Nothing({ said }: { readonly said: string }): ReactElement {
  return (
    <div className="cw-nil">
      <NothingGlyph />
      <span>{said}</span>
    </div>
  );
}

/**
 * The state banner: the ticket, its lane mark, its priority, and whether the
 * record says a human is waiting. Each is a chip; none is a sentence.
 */
function Banner({
  card,
  context,
}: {
  readonly card: BoardCard;
  readonly context: BoardCardContext;
}): ReactElement {
  return (
    <div className="cw-banner">
      <Link className="cw-art" href={`/ticket/${encodeURIComponent(card.ticketId)}`}>
        <TicketGlyph />
        {shortId(card.ticketId)}
      </Link>
      <span className={`pri ${card.priority.toLowerCase()}`}>{card.priority}</span>
      <span className="chip">
        <StateGlyph name={laneGlyph(card.lane, card.blockerReason !== null)} />
        {card.stageLabel ?? card.lane}
      </span>
      {context.humanWaiting.attention ? (
        <span className="verdict v-changes" title={context.humanWaiting.detail}>
          needs you
        </span>
      ) : null}
    </div>
  );
}

function Changes({
  card,
  context,
}: {
  readonly card: BoardCard;
  readonly context: BoardCardContext;
}): ReactElement {
  if (card.changeReferences.length === 0) {
    return <Nothing said="no change recorded on this ticket" />;
  }
  return (
    <div className="cw-scrollable">
      {card.changeReferences.map((change, index) => (
        <Row
          at={change.change_identity}
          dir={change.repository}
          key={`${change.repository}:${change.change_identity}`}
          leaf={change.reference}
          title={context.changes[index]?.detail}
        />
      ))}
    </div>
  );
}

/**
 * The checks: what the record has already decided about this ticket. The
 * applied labels are the vocabulary's own verdicts, the blocker is the one fact
 * that stops it, and the delivery surface is what the checkpoint answered.
 */
function Checks({
  card,
  context,
}: {
  readonly card: BoardCard;
  readonly context: BoardCardContext;
}): ReactElement {
  const rows: readonly ReactNode[] = [
    ...(card.blockerReason === null
      ? []
      : [
          <Row
            at={card.blockerOpenedAt === null ? null : stampText(card.blockerOpenedAt)}
            dir="blocked"
            key="blocked"
            leaf={card.blockerReason}
          />,
        ]),
    ...card.appliedLabels.map((label, index) => (
      <Row
        at={`r${label.vocabulary_revision.toString()}`}
        dir={label.label_key}
        key={label.label_key}
        leaf={label.label}
        title={context.labels[index]?.detail}
      />
    )),
    ...card.deliveryFacts.map((fact) => <Row dir="delivery" key={fact} leaf={fact} />),
    <Row
      dir="surface"
      key="surface"
      leaf={context.deliverySurface.value}
      title={context.deliverySurface.details?.join(" · ")}
    />,
  ];
  return <div className="cw-scrollable">{rows}</div>;
}

/** Review: who holds it, who it is assigned to, and whose work it is for. */
function Review({
  card,
  context,
}: {
  readonly card: BoardCard;
  readonly context: BoardCardContext;
}): ReactElement {
  return (
    <div className="cw-scrollable">
      <Row
        at={shortId(card.custodianId)}
        dir="custodian"
        leaf={card.custodianName ?? shortId(card.custodianId)}
      />
      {card.assigneeId === null ? null : (
        <Row
          at={shortId(card.assigneeId)}
          dir="assignee"
          leaf={card.assigneeName ?? shortId(card.assigneeId)}
        />
      )}
      <Row dir="waiting on" leaf={context.humanWaiting.value} title={context.humanWaiting.detail} />
      <Row at={card.projectKey} dir="tenant" leaf={context.tenant.value} />
    </div>
  );
}

function Pane({
  card,
  context,
  tab,
}: {
  readonly card: BoardCard;
  readonly context: BoardCardContext;
  readonly tab: WorkTab;
}): ReactElement {
  switch (tab) {
    case "changes":
      return <Changes card={card} context={context} />;
    case "checks":
      return <Checks card={card} context={context} />;
    case "review":
      return <Review card={card} context={context} />;
  }
}

function countOf(card: BoardCard, tab: WorkTab): number | null {
  switch (tab) {
    case "changes":
      return card.changeReferences.length;
    case "checks":
      return (
        card.appliedLabels.length +
        card.deliveryFacts.length +
        (card.blockerReason === null ? 0 : 1) +
        1
      );
    case "review":
      return null;
  }
}

function Linked({
  card,
  tab,
  threadId,
}: {
  readonly card: BoardCard;
  readonly tab: WorkTab;
  readonly threadId: string;
}): ReactElement {
  const context = boardCardContextFor(card);
  return (
    <>
      <Banner card={card} context={context} />
      <div className="cw-tabs">
        {TABS.map((entry) => {
          const count = countOf(card, entry.key);
          return (
            <Link
              className={entry.key === tab ? "on" : ""}
              href={tabHref(threadId, entry.key)}
              key={entry.key}
            >
              {entry.label}
              {count === null ? null : <span className="ct">{count}</span>}
            </Link>
          );
        })}
      </div>
      <Pane card={card} context={context} tab={tab} />
    </>
  );
}

export function WorkPanel({
  threadId,
  card,
  tab,
  promote,
  children,
}: {
  readonly threadId: string;
  /** The board card behind the promoted ticket; `null` when nothing is linked. */
  readonly card: Reading<BoardCard> | null;
  readonly tab: WorkTab;
  /** The promote control, for a thread that links no ticket yet. */
  readonly promote: ReactNode;
  /** The live session pane, mounted under this column. */
  readonly children: ReactNode;
}): ReactElement {
  return (
    <aside className="cw-side">
      {card === null ? (
        <>
          <div className="cw-head">
            <h2>Work</h2>
          </div>
          <Nothing said="no ticket linked to this conversation" />
          {promote}
        </>
      ) : (
        <InlineReading
          missing={(label, detail, tone) => (
            <>
              <div className="cw-banner" style={tone}>
                <span className="chip" title={detail}>
                  board row {label}
                </span>
              </div>
              <Nothing said={detail} />
            </>
          )}
          present={(row) => <Linked card={row} tab={tab} threadId={threadId} />}
          reading={card}
        />
      )}
      {children}
    </aside>
  );
}

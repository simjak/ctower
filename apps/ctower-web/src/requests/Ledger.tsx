import type { ReactElement } from "react";
import type { RequestRow } from "@ctower/client";
import { cn } from "../ui/cn";
import { Mark } from "../ui/marks";
import { Chip, Mono } from "../ui/primitives";
import { age, priorityTone, stateMark, triageTone } from "./facts";

/**
 * The ledger. A table, because a ledger is one: seven columns, row borders and
 * no zebra, at the density `DESIGN.md` fixes.
 *
 * Rows are drawn in the order the record returned them. Nothing here sorts,
 * groups or re-ranks — an order this screen invented would be an order no one
 * recorded, and the operator would have no way to tell the two apart.
 */
export function Ledger({
  rows,
  open,
  onOpen,
}: {
  readonly rows: readonly RequestRow[];
  /** The request whose detail is showing, if one is. */
  readonly open: string | null;
  readonly onOpen: (requestId: string) => void;
}): ReactElement {
  return (
    <table className="w-full table-fixed border-collapse text-left text-sm">
      {/* Fixed layout, and the ask takes what is left. Every other column holds
          a value of known shape, so widths are set once here rather than being
          negotiated per answer — a ledger whose columns move as rows arrive is
          a ledger an operator has to re-read every time. */}
      <colgroup>
        <col className="w-[64px]" />
        <col />
        <col className="w-[104px]" />
        <col className="w-[104px]" />
        <col className="w-[64px]" />
        <col className="w-[112px]" />
        <col className="w-[56px]" />
      </colgroup>
      <thead>
        <tr className="border-b border-line text-2xs font-normal text-muted">
          <Head>Request</Head>
          <Head>Ask</Head>
          <Head>Where</Head>
          <Head>Decision</Head>
          <Head>Priority</Head>
          <Head>Project</Head>
          <Head className="text-right">Age</Head>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <Row key={row.request_id} row={row} open={row.request_id === open} onOpen={onOpen} />
        ))}
      </tbody>
    </table>
  );
}

function Head({
  className,
  children,
}: {
  readonly className?: string;
  readonly children: string;
}): ReactElement {
  return (
    <th scope="col" className={cn("py-1.5 pr-3 font-normal", className)}>
      {children}
    </th>
  );
}

/**
 * One row, with one tab stop.
 *
 * The reference is the control: it is the keyboard's way in, it carries the
 * focus ring, and it names what it opens. The row also takes a pointer click,
 * which is a convenience for the mouse and adds nothing a keyboard could
 * otherwise not reach — so no reader loses anything if it is ignored.
 */
function Row({
  row,
  open,
  onOpen,
}: {
  readonly row: RequestRow;
  readonly open: boolean;
  readonly onOpen: (requestId: string) => void;
}): ReactElement {
  return (
    <tr
      onClick={(): void => {
        onOpen(row.request_id);
      }}
      className={cn("border-b border-line", open ? "bg-amber/12" : "hover:bg-raised")}
    >
      <td className="py-1.5 pr-3">
        <button
          type="button"
          aria-label={`Open ${row.reference}`}
          aria-current={open ? "true" : undefined}
          className="cursor-pointer"
          onClick={(): void => {
            onOpen(row.request_id);
          }}
        >
          <Mono className={open ? "text-amber-ink" : "text-fg"}>{row.reference}</Mono>
        </button>
      </td>
      <td className="py-1.5 pr-3">
        <div className="flex items-center gap-2">
          <span className="truncate" title={row.content}>
            {row.content}
          </span>
          {row.unknown_reason === null ? null : (
            <Chip className="shrink-0" title={row.unknown_reason}>
              unknown
            </Chip>
          )}
        </div>
      </td>
      <td className="py-1.5 pr-3 whitespace-nowrap">
        <Mark name={stateMark(row.state)} />
        <span className="text-muted">{row.state.toLowerCase()}</span>
      </td>
      <td className="py-1.5 pr-3">
        <Chip tone={triageTone(row.triage)}>{row.triage.toLowerCase()}</Chip>
      </td>
      <td className="py-1.5 pr-3">
        {/* A priority nobody chose is still the priority the record will act
            on, so it renders at full contrast — dashed, not dimmed. */}
        <Chip
          tone={priorityTone(row.priority)}
          className={row.priority_default ? "border-dashed" : undefined}
          title={row.priority_default ? "Default; no one chose it" : undefined}
        >
          {row.priority}
        </Chip>
      </td>
      <td className="py-1.5 pr-3">
        <Mono className="text-muted">{row.project_key}</Mono>
      </td>
      <td className="py-1.5 text-right whitespace-nowrap text-muted">{age(row.age_seconds)}</td>
    </tr>
  );
}

import type { ReactElement, ReactNode } from "react";
import type { Answer } from "../../api/client";
import { Asking, Malformed, Refused, Unreachable } from "../../wizard/states";

/**
 * The shapes every section of a ticket's own page is built from.
 *
 * The operator's card is sections of facts separated by space rather than by
 * rules, each under a quiet label, with one line of italics wherever ctower
 * genuinely cannot answer. These are those three things and nothing else — a
 * section, a labelled fact, and an absence said in words.
 */
export function Section({
  title,
  note,
  children,
}: {
  readonly title: string;
  /** The one fact that belongs beside the label rather than under it. */
  readonly note?: ReactNode;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <section className="mb-9">
      <header className="mb-3 flex items-baseline gap-3">
        <h2 className="m-0 text-2xs font-medium tracking-[0.09em] text-muted uppercase">{title}</h2>
        {note === undefined ? null : (
          <span className="ml-auto text-right text-2xs text-muted">{note}</span>
        )}
      </header>
      {children}
    </section>
  );
}

/** One labelled fact on its own line, the label quiet and the value carrying it. */
export function Fact({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-4 border-t border-line py-2 text-sm first:border-t-0">
      <span className="w-28 shrink-0 text-xs text-muted">{label}</span>
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}

/**
 * Something the record does not keep, said once and quietly.
 *
 * Never an empty frame: a heading over nothing reads as a thing that failed to
 * load, and this reads as the thing it is — a fact ctower has never been told.
 */
export function Absent({ children }: { readonly children: ReactNode }): ReactElement {
  return <p className="mt-2.5 mb-0 text-xs text-muted italic">{children}</p>;
}

/** A small panel of facts beside the page, for what is true rather than what happened. */
export function Aside({
  title,
  children,
}: {
  readonly title: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <section className="mb-4 rounded-md border border-line bg-card px-4 pt-3 pb-2">
      <h2 className="m-0 mb-1 text-2xs font-medium tracking-[0.09em] text-muted uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

/**
 * What a read answered, in one place.
 *
 * A read that never landed and a read that answered with nothing are different
 * facts, so they are never drawn as one: absence is a sentence this section
 * wrote, and the four not-an-answer states are the shared components the rest
 * of the console uses.
 */
export function Answered({
  answer,
  asking,
  children,
}: {
  readonly answer: Answer<unknown>;
  readonly asking: string;
  readonly children: ReactNode;
}): ReactElement {
  switch (answer.kind) {
    case "asking":
      return <Asking what={asking} />;
    case "refused":
      return <Refused problem={answer.problem} action="Nothing was read. Reload to ask again." />;
    case "unreachable":
      return <Unreachable detail={answer.detail} action="Reload to ask again." />;
    case "malformed":
      return <Malformed detail={answer.detail} />;
    case "answered":
      return <>{children}</>;
  }
}

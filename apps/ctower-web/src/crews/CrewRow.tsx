import type { ReactElement } from "react";
import { Chip } from "../ui/primitives";
import type { Crew } from "./roster";

/**
 * One crew, the way the operator already reads his fleet: who it is, what it
 * runs on, and what the record last saw it do.
 *
 * Nothing here is a key, a revision or a reference — a crew is a member of
 * staff on this screen and the record's addressing is the wiring's business.
 * A column with nothing recorded draws **nothing**: no dash, no "n/a", no
 * borrowed mark, because a dash is a value and a row of placeholder dashes is
 * exactly the dead screen this replaces.
 *
 * Three of the columns a fleet dashboard wants are that kind of absence, and
 * they are absent for one reason. A recorded session names its crew with a
 * string the caller authored, and `SPEC.md` forbids inferring a seat key from a
 * subject or display text, so no run in the record can be attributed to the
 * crew the bundle calls by this name. That is what the state chip says, in the
 * only words that are true of every row today — the record has not seen this
 * crew work. Its mark is deliberately missing rather than borrowed: unknown is
 * first-class, and a glyph from a neighbouring state is how a read that never
 * happened gets drawn as a state that did.
 *
 * The blank in front of the name is that missing mark's place, kept so the
 * names line up and so the day the record can name a crew's run, the glyph
 * lands where the eye is already looking.
 */
export function CrewRow({ crew }: { readonly crew: Crew }): ReactElement {
  return (
    <div className="flex items-center gap-3 border-b border-line px-3 py-2.5 last:border-b-0">
      <span className="w-[1.4em] shrink-0" />
      <span className="min-w-0 flex-1 truncate text-sm font-semibold">{crew.name}</span>
      <span className="hidden shrink-0 truncate text-xs sm:block sm:w-[196px] sm:text-right">
        {crew.harness}
      </span>
      <Chip>not seen</Chip>
    </div>
  );
}

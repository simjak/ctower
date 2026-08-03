import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { newestTicketId } from "@/read/newest";
import { selectedProjectKey } from "@/read/projects";
import { readParam } from "@/surfaces/screenParams";
import { ArrivalNote, TicketScreen } from "@/surfaces/ticket/TicketScreen";

export const dynamic = "force-dynamic";

/**
 * The rail's `Latest ticket`.
 *
 * Round-3 QA (#243) found this route `redirect()`-ing to whichever ticket had
 * been captured most recently: a nav item labelled *Tickets* landed the operator
 * on one arbitrary P2 probe with nothing on the page saying why, and the
 * sentence that would have explained it rendered only on the path where the
 * redirect did not fire. The same click went somewhere different every time
 * anyone captured a ticket.
 *
 * So the rule is on the label and the destination is on the page: the rail says
 * *Latest ticket*, this route renders that ticket in place at a stable URL, and
 * the note above it states the rule and links the ticket's own permanent
 * address. The board is the list, and it is one click away in the rail.
 */
const RULE =
  "the most recently created ticket the record holds, opened by the rail's Latest ticket";

function IndexFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Ticket" back />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Latest ticket</h1>
            <p>This section opens {RULE}.</p>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Latest ticket</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath="/v1/board" />
        </div>
      </main>
    </>
  );
}

export default async function TicketIndex({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const project = selectedProjectKey(readParam(await searchParams, "project"));
  const newest = await newestTicketId(project);
  return (
    <Resolved
      reading={newest}
      subject={`project ${project}`}
      frame={(declared) => <IndexFrame declared={declared} />}
    >
      {(ranked) => (
        <TicketScreen
          ticketId={ranked.chosen}
          projectKey={project}
          note={<ArrivalNote rule={`You are reading ${RULE}.`} ticketId={ranked.chosen} />}
        />
      )}
    </Resolved>
  );
}

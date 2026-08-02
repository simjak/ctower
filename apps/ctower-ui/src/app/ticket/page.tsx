import { redirect } from "next/navigation";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { newestTicketId } from "@/read/newest";

export const dynamic = "force-dynamic";

function IndexFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Ticket" back />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Ticket</h1>
            <p>
              One ticket in full. This section opens the most recently created ticket on record.
            </p>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Tickets</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath="/v1/board" />
        </div>
      </main>
    </>
  );
}

export default async function TicketIndex(): Promise<ReactNode> {
  const newest = await newestTicketId();
  return (
    <Resolved reading={newest} frame={(declared) => <IndexFrame declared={declared} />}>
      {(ticketId) => redirect(`/ticket/${encodeURIComponent(ticketId)}`)}
    </Resolved>
  );
}

import { redirect } from "next/navigation";
import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter } from "@/read/adapter";
import { newestTicketId } from "@/read/newest";

export const dynamic = "force-dynamic";

export default async function TicketIndex(): Promise<ReactElement> {
  const board = await recordAdapter.board();
  if (board.state === "present") {
    const ticketId = newestTicketId(board.value);
    if (ticketId !== null) {
      redirect(`/ticket/${encodeURIComponent(ticketId)}`);
    }
  }
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
            <DeclaredState reading={board} />
          </section>
          <RecordFoot readPath="/v1/board" />
        </div>
      </main>
    </>
  );
}

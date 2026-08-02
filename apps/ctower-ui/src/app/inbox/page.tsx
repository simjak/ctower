import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter } from "@/read/adapter";

export const dynamic = "force-dynamic";

export default async function InboxPage(): Promise<ReactElement> {
  const inbox = await recordAdapter.seatInbox();
  return (
    <>
      <Chrome section="Inbox" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Inbox</h1>
            <p>
              Each seat has one durable inbox. Messages are addressed to the seat by name, never to
              a session, so a compaction or a closed tab cannot lose one — and the read cursor is
              the seat&rsquo;s, not the reader&rsquo;s.
            </p>
          </div>

          <div className="addr">
            <span className="k">Address as</span>
            <span className="name">—</span>
            <span className="how">
              the seat addressing name and the exact line that reaches it are the loudest thing on
              this screen once the record carries them
            </span>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Messages</h2>
              <span className="sub">no seat inbox recorded</span>
            </header>
            <DeclaredState reading={inbox} />
          </section>

          <RecordFoot />
        </div>
      </main>
    </>
  );
}

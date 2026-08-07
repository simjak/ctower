import {
  inboxProjectionFrom,
  inboxThreadFrom,
} from "../../apps/ctower-ui/src/read/httpRecordAdapter.ts";

function outcome(run: () => unknown): { readonly thrown: boolean; readonly value?: unknown } {
  try {
    return { thrown: false, value: run() };
  } catch {
    return { thrown: true };
  }
}

const projection = {
  recipient: "ctower-commander",
  threads: [
    {
      thread_id: "018f0d5e-7b9a-7c01-8000-000000000600",
      other_agent: "qa-agent",
      last_message_preview: "Native inbox vector",
      last_message_at: "2026-08-06T12:01:00Z",
      unread_count: 1,
      promoted_ticket_id: "018f0d5e-7b9a-7c01-8000-000000000010",
    },
  ],
  total_unread: 1,
  unread_only: false,
};

const thread = {
  thread_id: "018f0d5e-7b9a-7c01-8000-000000000600",
  participants: ["ctower-commander", "qa-agent"],
  messages: [
    {
      message_id: "018f0d5e-7b9a-7c01-8000-000000000602",
      position: 1,
      from: "qa-agent",
      to: "ctower-commander",
      text: "Native inbox vector",
      sent_at: "2026-08-06T12:01:00Z",
    },
  ],
  read_through_position: 1,
  promoted_ticket_id: "018f0d5e-7b9a-7c01-8000-000000000010",
};

process.stdout.write(
  JSON.stringify({
    projection: inboxProjectionFrom(projection),
    thread: inboxThreadFrom(thread),
    rejectsNonBooleanUnreadOnly: outcome(() =>
      inboxProjectionFrom({ ...projection, unread_only: "false" })
    ),
    rejectsNonIntegerUnreadCount: outcome(() =>
      inboxProjectionFrom({
        ...projection,
        threads: [{ ...projection.threads[0], unread_count: "one" }],
      })
    ),
  })
);

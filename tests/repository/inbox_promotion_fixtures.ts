import { promoteInboxThread } from "../../apps/ctower-ui/src/mutate/inboxPromotion.ts";

const threadId = "018f0d5e-7b9a-7c01-8000-000000000600";
const ticketId = "018f0d5e-7b9a-7c01-8000-000000000010";

const promoted = {
  command_id: "018f0d5e-7b9a-7c01-8000-000000000700",
  durability_state: "accepted",
  event_ids: ["018f0d5e-7b9a-7c01-8000-000000000701"],
  outcome: "ticket_linked",
  thread_id: threadId,
  thread_version: 3,
  ticket_id: ticketId,
};

const alreadyPromoted = {
  code: "inbox-already-promoted",
  detail: "The inbox thread is already linked to a ticket.",
  status: 409,
  title: "Inbox promotion refused",
  type: "https://ctower.invalid/problems/inbox-already-promoted",
};

async function main(): Promise<void> {
  process.env.CTOWER_UI_API_TOKEN = "test-credential";
  const requests: Array<{
    readonly url: string;
    readonly method: string;
    readonly body: string;
    readonly idempotencyKey: string | null;
  }> = [];
  globalThis.fetch = async (input, init): Promise<Response> => {
    const request = init ?? {};
    requests.push({
      url: String(input),
      method: String(request.method),
      body: String(request.body),
      idempotencyKey: new Headers(request.headers).get("Idempotency-Key"),
    });
    return new Response(JSON.stringify(promoted), { status: 200 });
  };
  const success = await promoteInboxThread(threadId, ticketId);

  globalThis.fetch = async (): Promise<Response> =>
    new Response(JSON.stringify(alreadyPromoted), {
      status: 409,
      headers: { "content-type": "application/problem+json" },
    });
  const refusal = await promoteInboxThread(threadId, null);

  process.stdout.write(JSON.stringify({ success, refusal, request: requests[0] }));
}

void main();

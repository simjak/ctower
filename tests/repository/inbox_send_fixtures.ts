import { sendInboxMessage } from "../../apps/ctower-ui/src/mutate/inboxSend.ts";

const threadId = "018f0d5e-7b9a-7c01-8000-000000000600";
const otherThreadId = "018f0d5e-7b9a-7c01-8000-000000000601";

const projection = {
  recipient: "designer",
  threads: [
    {
      thread_id: threadId,
      other_agent: "engineer",
      last_message_preview: "the rail this rides",
      last_message_at: "2026-08-09T03:00:00Z",
      unread_count: 1,
      promoted_ticket_id: null,
    },
  ],
  total_unread: 1,
  unread_only: false,
};

const sent = {
  command_id: "018f0d5e-7b9a-7c01-8000-000000000700",
  durability_state: "accepted",
  event_ids: ["018f0d5e-7b9a-7c01-8000-000000000701"],
  from: "designer",
  message_id: "018f0d5e-7b9a-7c01-8000-000000000702",
  position: 2,
  sent_at: "2026-08-09T03:05:00Z",
  thread_id: threadId,
  thread_version: 3,
  to: "engineer",
};

const unaddressable = {
  code: "inbox-sender-unaddressable",
  detail: "The authenticated principal has no addressable project seat.",
  status: 422,
  title: "Inbox command refused",
  type: "https://ctower.invalid/problems/inbox-sender-unaddressable",
};

interface Attempt {
  readonly method: string;
  readonly url: string;
  readonly body: string;
  readonly bodyKeys: readonly string[];
  readonly idempotencyKey: string | null;
  readonly authorized: boolean;
}

function attemptOf(input: RequestInfo | URL, init: RequestInit | undefined): Attempt {
  const request = init ?? {};
  const body = request.body === undefined ? "" : String(request.body);
  const headers = new Headers(request.headers);
  return {
    method: String(request.method ?? "GET"),
    url: String(input),
    body,
    bodyKeys: body === "" ? [] : Object.keys(JSON.parse(body) as Record<string, unknown>).sort(),
    idempotencyKey: headers.get("Idempotency-Key"),
    authorized: headers.get("Authorization") !== null,
  };
}

/** Serve the correspondent read, then hand every command to `answer`. */
function transcript(answer: (attempt: number) => Response): Attempt[] {
  const attempts: Attempt[] = [];
  let commands = 0;
  globalThis.fetch = (input, init): Promise<Response> => {
    const attempt = attemptOf(input, init);
    attempts.push(attempt);
    if (attempt.method === "GET") {
      return Promise.resolve(new Response(JSON.stringify(projection), { status: 200 }));
    }
    commands += 1;
    return Promise.resolve(answer(commands));
  };
  return attempts;
}

async function main(): Promise<void> {
  process.env.CTOWER_UI_API_TOKEN = "test-credential";

  const accepted = transcript(() => new Response(JSON.stringify(sent), { status: 201 }));
  const success = await sendInboxMessage(threadId, "  ready for the taste gate  ");

  const refusedAttempts = transcript(
    () =>
      new Response(JSON.stringify(unaddressable), {
        status: 422,
        headers: { "content-type": "application/problem+json" },
      })
  );
  const refusal = await sendInboxMessage(threadId, "who am I here?");

  // The thread is not in this principal's own projection: nothing is addressed,
  // so no command is attempted at all.
  const strangerAttempts = transcript(() => new Response(null, { status: 500 }));
  const stranger = await sendInboxMessage(otherThreadId, "hello?");

  // An empty message never reaches the boundary.
  const blankAttempts = transcript(() => new Response(null, { status: 500 }));
  const blank = await sendInboxMessage(threadId, "   \n  ");

  // A retryable status re-enters the bounded loop under the one minted key.
  const retryAttempts = transcript((attempt) =>
    attempt === 1
      ? new Response(JSON.stringify({ status: 503 }), { status: 503 })
      : new Response(JSON.stringify(sent), { status: 201 })
  );
  const retried = await sendInboxMessage(threadId, "second attempt, same key");

  // A terminal refusal whose body is not a problem document stays terminal, and
  // the box says so plainly rather than quoting a parser.
  transcript(
    () => new Response("conflict", { status: 409, headers: { "content-type": "text/plain" } })
  );
  const opaque = await sendInboxMessage(threadId, "no problem document here");

  process.stdout.write(
    JSON.stringify({
      success,
      accepted,
      refusal,
      refusedAttempts,
      stranger,
      strangerAttempts,
      blank,
      blankAttempts,
      retried,
      retryKeys: retryAttempts
        .filter((attempt) => attempt.method === "POST")
        .map((attempt) => attempt.idempotencyKey),
      opaque,
    })
  );
}

void main();

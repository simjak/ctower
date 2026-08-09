import { sendInboxMessage } from "../../apps/ctower-ui/src/mutate/inboxSend.ts";
import type { InboxSendState } from "../../apps/ctower-ui/src/mutate/types.ts";

const threadId = "018f0d5e-7b9a-7c01-8000-000000000600";
const otherThreadId = "018f0d5e-7b9a-7c01-8000-000000000601";

/** No answer yet, so nothing to replay: what a first send always carries. */
const FIRST: InboxSendState = { kind: "idle" };

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

/**
 * The same authored answer, explicitly *not* accepted.
 *
 * The command committed, but the off-host durable acknowledgement it needs did
 * not, so the record answers `202` and names the state it is really in. Every
 * other byte is identical to the accepted answer: only the discriminator says
 * whether this message is a recorded fact.
 */
const unconfirmed = { ...sent, durability_state: "durability_pending" };

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

/** The key each command attempt carried, in the order they were attempted. */
function commandKeys(attempts: readonly Attempt[]): Array<string | null> {
  return attempts.filter((attempt) => attempt.method === "POST").map((a) => a.idempotencyKey);
}

async function main(): Promise<void> {
  process.env.CTOWER_UI_API_TOKEN = "test-credential";

  const accepted = transcript(() => new Response(JSON.stringify(sent), { status: 201 }));
  const success = await sendInboxMessage(threadId, "  ready for the taste gate  ", FIRST);

  const refusedAttempts = transcript(
    () =>
      new Response(JSON.stringify(unaddressable), {
        status: 422,
        headers: { "content-type": "application/problem+json" },
      })
  );
  const refusal = await sendInboxMessage(threadId, "who am I here?", FIRST);

  // The thread is not in this principal's own projection: nothing is addressed,
  // so no command is attempted at all.
  const strangerAttempts = transcript(() => new Response(null, { status: 500 }));
  const stranger = await sendInboxMessage(otherThreadId, "hello?", FIRST);

  // An empty message never reaches the boundary.
  const blankAttempts = transcript(() => new Response(null, { status: 500 }));
  const blank = await sendInboxMessage(threadId, "   \n  ", FIRST);

  // A retryable status re-enters the bounded loop under the one minted key.
  const retryAttempts = transcript((attempt) =>
    attempt === 1
      ? new Response(JSON.stringify({ status: 503 }), { status: 503 })
      : new Response(JSON.stringify(sent), { status: 201 })
  );
  const retried = await sendInboxMessage(threadId, "second attempt, same key", FIRST);

  // A terminal refusal whose body is not a problem document stays terminal, and
  // the box says so plainly rather than quoting a parser.
  transcript(
    () => new Response("conflict", { status: 409, headers: { "content-type": "text/plain" } })
  );
  const opaque = await sendInboxMessage(threadId, "no problem document here", FIRST);

  // An explicit non-accepted answer. Nothing here is a recorded message, so the
  // words stay with the sender and the command keeps its identity.
  const heldAttempts = transcript(() => new Response(JSON.stringify(unconfirmed), { status: 202 }));
  const held = await sendInboxMessage(threadId, "  is this recorded?  ", FIRST);

  // The sender presses the box again. The retry carries the identity the first
  // attempt minted, so the record replays one command rather than recording a
  // second message.
  const replayAttempts = transcript((attempt) =>
    attempt === 1
      ? new Response(JSON.stringify(unconfirmed), { status: 202 })
      : new Response(JSON.stringify(sent), { status: 201 })
  );
  const unresolved = await sendInboxMessage(threadId, "  is this recorded?  ", FIRST);
  const resolved = await sendInboxMessage(threadId, "  is this recorded?  ", unresolved);

  // Editing the words first makes it a different message, and a different
  // message is a different command: one key for two different requests is a
  // conflict, not a retry.
  const editedAttempts = transcript(
    () => new Response(JSON.stringify(unconfirmed), { status: 202 })
  );
  const typed = await sendInboxMessage(threadId, "the first words", FIRST);
  const edited = await sendInboxMessage(threadId, "second thoughts", typed);

  // A replay identity that is not one is refused before the boundary rather
  // than sent to the record as a key.
  const forgedAttempts = transcript(() => new Response(JSON.stringify(sent), { status: 201 }));
  const forged = await sendInboxMessage(threadId, "tampered state", {
    kind: "pending",
    message: "held",
    text: "tampered state",
    commandId: "not-a-command-identity",
  });

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
      retryKeys: commandKeys(retryAttempts),
      opaque,
      held,
      heldKeys: commandKeys(heldAttempts),
      unresolved,
      resolved,
      replayKeys: commandKeys(replayAttempts),
      typed,
      edited,
      editedKeys: commandKeys(editedAttempts),
      forged,
      forgedAttempts,
    })
  );
}

void main();
